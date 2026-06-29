"""TaskSpec — 작업 specifics를 코드에서 분리한 설정 객체. SPEC §범용화.

엔진(orchestrator/nodes)은 작업 지식을 코드로 갖지 않는다. 무엇을·어떤 순서로·
어떤 기준으로 할지는 전부 TaskSpec이 데이터로 들고 있고, 엔진은 그걸 읽어 돈다.

한 엔진(build_app)이 서로 다른 TaskSpec을 받아 돌면 그 자체가 '도메인 무관'의
증거다(추상 일반화 주장보다 확실). 현재 두 spec을 둔다:
  - COMPARE      : 실 LLM + 실 웹검색 비교·분석 (기존 v0.4 동작 보존)
  - INGEST_DEMO  : LLM·네트워크 불필요. 로컬 파일 적재 루프(결정적 인스턴스).

새 작업 추가 절차 = 새 handlers 모듈에 액션/검수기 등록 + 여기 TaskSpec 추가.
엔진 코드 수정은 0.
"""
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class StepSpec:
    step_id: str
    subgoal: str
    action: str                                   # registry.ACTION_HANDLERS 키
    acceptance: dict[str, Any]                     # {"kind": ..., 그 외 검수 파라미터}
    depends_on: list[str] = field(default_factory=list)
    requires_tool: Optional[str] = None            # allowed_tools에 있어야 실행(최소권한)
    fault: Optional[dict[str, Any]] = None         # 차단기 데모용 의도적 실패 설정


@dataclass
class TaskSpec:
    name: str
    goal: str
    definition: dict[str, Any]                     # 도메인 데이터(criteria·targets·items ...)
    allowed_tools: list[str]
    forbidden: list[str]
    steps: list[StepSpec]
    # 원인코드 -> [retriable?, corrective_flag]. 어떤 실패가 재시도 가능한지는 작업 지식.
    diagnosis: dict[str, list]

    def to_constraints(self) -> dict:
        """AgentContext.constraints로 직렬화(엔진이 읽는 형태)."""
        return {
            "definition": self.definition,
            "allowed_tools": self.allowed_tools,
            "forbidden": self.forbidden,
            "steps": [asdict(s) for s in self.steps],
            "diagnosis": self.diagnosis,
            # 하위호환: 기존 코드가 참조하던 acceptance.final (보고용)
            "acceptance": {"final": [self.steps[-1].acceptance["kind"]] if self.steps else []},
        }


# ───────────────────────── 작업 1: 모델 비교 (실 LLM + 실 검색) ─────────────────────────
COMPARE = TaskSpec(
    name="compare",
    goal="건설자재 객체탐지 모델 후보 3종(Faster R-CNN/YOLOv8/RT-DETR)을 비교하라",
    definition={
        "criteria": ["mAP", "FPS", "train_cost", "deploy_difficulty"],
        "targets": ["Faster R-CNN", "YOLOv8", "RT-DETR"],
    },
    allowed_tools=["web_search_specs"],
    forbidden=["rm -rf", "DROP TABLE"],
    steps=[
        StepSpec("s1", "비교기준 정의", "define",
                 {"kind": "artifact_non_empty", "key": "criteria", "cause": "empty_criteria"}),
        StepSpec("s2", "대상별 웹검색(fan-out)", "extract",
                 {"kind": "all_targets_sourced", "cause": "missing_source"},
                 depends_on=["s1"], requires_tool="web_search_specs",
                 fault={"first_attempt_fails": True, "corrective": "s2_retry"}),
        StepSpec("s3", "차이분석", "compare",
                 {"kind": "artifact_non_empty", "key": "analysis", "cause": "no_analysis"},
                 depends_on=["s2"]),
        StepSpec("s4", "결과요약", "summarize",
                 {"kind": "llm_judge", "cause": "judge_reject"},
                 depends_on=["s3"]),
    ],
    diagnosis={
        "missing_source": [True, "s2_retry"],
        "no_analysis": [True, None],
        "judge_reject": [True, None],
        "tool_not_allowed": [False, None],
    },
)

# ──────────────── 작업 2: 적재 루프 데모 (결정적 — LLM·네트워크 불필요) ────────────────
# scripts/INGEST-AGENT.md의 Step->verify->DIAGNOSIS->유계재시도->차단기 골격을
# 로컬 파일 작업으로 재현한 인스턴스. 실 GCS·다운로드 대신 로컬 임시폴더라 결정적이고
# 샌드박스에서 키·네트워크 없이 그대로 돈다(silent mock 금지 — 실제 파일 I/O를 함).
INGEST_DEMO = TaskSpec(
    name="ingest_demo",
    goal="데모 데이터 1건을 받아 무결성(체크섬) 검증 후 로컬 저장소에 적재하라",
    definition={"items": ["block-A"]},
    allowed_tools=["local_fs"],
    forbidden=["rm -rf", "DROP TABLE"],
    steps=[
        StepSpec("d1", "데이터 수신(로컬 생성)", "fetch_local",
                 {"kind": "artifact_non_empty", "key": "payload", "cause": "empty_payload"}),
        StepSpec("d2", "무결성 검증(체크섬)", "verify_checksum",
                 {"kind": "flag_true", "key": "checksum_ok", "cause": "checksum_mismatch"},
                 depends_on=["d1"], requires_tool="local_fs",
                 fault={"first_attempt_fails": True, "corrective": "d2_retry"}),
        StepSpec("d3", "저장소 적재(크기 대조)", "store_local",
                 {"kind": "stored_size_match", "cause": "size_mismatch"},
                 depends_on=["d2"], requires_tool="local_fs"),
    ],
    diagnosis={
        "checksum_mismatch": [True, "d2_retry"],
        "size_mismatch": [True, None],
        "empty_payload": [False, None],
        "tool_not_allowed": [False, None],
    },
)


# ──────────── 작업 3: 실 AI Hub 적재 (71918/71921) — 실 I/O, filekey당 1 트랜잭션 ────────────
# handlers_ingest.py의 aihub_* 액션을 INGEST-AGENT.md 게이트 순서로 엮은 spec. filekey마다
# 1개 spec(= process_fk 1트랜잭션). 큐/멱등/연속실패 차단기는 외부 드라이버(ingest_driver.py).
# 안전: g5(삭제)는 g2(무결성)·g4(크기) 통과 후에만 도달 = 두 게이트 후 삭제.
def ingest_aihub_spec(datasetkey, filekey, bk_prefix, dldir, name="", offline=False) -> "TaskSpec":
    return TaskSpec(
        name=f"ingest_aihub_{filekey}",
        goal=f"AI Hub {datasetkey} filekey {filekey} 1건: 다운로드→무결성→업로드→크기검증→삭제",
        definition={"datasetkey": str(datasetkey), "filekey": str(filekey),
                    "bk_prefix": bk_prefix, "dldir": dldir, "name": name, "offline": offline},
        allowed_tools=["aihub", "gcs"],
        forbidden=["rm -rf /", "DROP TABLE"],
        steps=[
            StepSpec("g1", "다운로드(aihubshell)", "aihub_download",
                     {"kind": "download_ok"}, requires_tool="aihub",
                     fault={"first_attempt_fails": True, "corrective": "g1_retry"}),  # 오프라인 회복/차단기 데모용
            StepSpec("g2", "무결성(unzip -t)", "aihub_integrity",
                     {"kind": "flag_true", "key": "integrity_ok", "cause": "integrity_fail"},
                     depends_on=["g1"]),
            StepSpec("g3", "업로드(gsutil)", "aihub_upload",
                     {"kind": "flag_true", "key": "upload_ok", "cause": "upload_fail"},
                     depends_on=["g2"], requires_tool="gcs"),
            StepSpec("g4", "크기검증(로컬==GCS)", "aihub_sizecheck",
                     {"kind": "size_match_gcs"}, depends_on=["g3"], requires_tool="gcs"),
            StepSpec("g5", "로컬삭제(2게이트 후)", "aihub_delete",
                     {"kind": "flag_true", "key": "deleted_ok", "cause": "delete_fail"},
                     depends_on=["g4"]),
        ],
        diagnosis={
            "download_empty": [True, "g1_retry"],     # 일시 실패 → resume 재시도
            "download_aborted": [False, None],        # 승인/해외/502 → 비재시도(드라이버가 HITL 중단)
            "integrity_fail": [False, None],          # 손상 → 해당 filekey FAILED(다음 실행때 재시도)
            "upload_fail": [True, "g3_retry"],        # gsutil 일시장애 → 재업로드
            "upload_aborted": [False, None],          # 인증 실패 → HITL
            "size_mismatch": [True, "g4_retry"],      # 절단 → 재업로드 후 재검증
            "delete_fail": [False, None],
            "tool_not_allowed": [False, None],
        },
    )


# 외부 RAG 출처(manifest §4): 직접 URL → curl 다운로드. 같은 게이트/엔진, download만 url_*로 분기.
def ingest_url_spec(url, filename, bk_prefix, dldir, ftype="pdf", offline=False) -> "TaskSpec":
    return TaskSpec(
        name=f"ingest_url_{filename}",
        goal=f"외부 RAG 출처 {filename} 1건: URL다운로드→타입검증→업로드→크기검증→삭제",
        definition={"url": url, "filename": filename, "ftype": ftype,
                    "bk_prefix": bk_prefix, "dldir": dldir, "offline": offline,
                    "datasetkey": "rag", "filekey": filename},
        allowed_tools=["web", "gcs"],
        forbidden=["rm -rf /", "DROP TABLE"],
        steps=[
            StepSpec("g1", "URL 다운로드(curl)", "url_download",
                     {"kind": "download_ok"}, requires_tool="web",
                     fault={"first_attempt_fails": True, "corrective": "g1_retry"}),
            StepSpec("g2", "타입검증(PDF/HTML 매직)", "url_integrity",
                     {"kind": "flag_true", "key": "integrity_ok", "cause": "integrity_fail"},
                     depends_on=["g1"]),
            StepSpec("g3", "업로드(gsutil)", "aihub_upload",
                     {"kind": "flag_true", "key": "upload_ok", "cause": "upload_fail"},
                     depends_on=["g2"], requires_tool="gcs"),
            StepSpec("g4", "크기검증(로컬==GCS)", "aihub_sizecheck",
                     {"kind": "size_match_gcs"}, depends_on=["g3"], requires_tool="gcs"),
            StepSpec("g5", "로컬삭제(2게이트 후)", "aihub_delete",
                     {"kind": "flag_true", "key": "deleted_ok", "cause": "delete_fail"},
                     depends_on=["g4"]),
        ],
        diagnosis={
            "download_empty": [True, "g1_retry"], "download_aborted": [False, None],
            "integrity_fail": [False, None],
            "upload_fail": [True, "g3_retry"], "upload_aborted": [False, None],
            "size_mismatch": [True, "g4_retry"],
            "delete_fail": [False, None], "tool_not_allowed": [False, None],
        },
    )


# 기본 인스턴스(데모/회귀용) — `INGEST_OFFLINE=1 python -m orc.run ingest_aihub` 로 배선·차단기 확인.
INGEST_AIHUB = ingest_aihub_spec(71918, 565888, "aihub-71918",
                                 os.path.expanduser("~/aihub_dl"), "Other.zip", offline=True)
INGEST_AIHUB.name = "ingest_aihub"

# ──────────── 작업 4: RAG 검색·응답 (질의→검색→LLM 근거응답) — 세 번째 실작업 인스턴스 ────────────
# Pred-FirefromElec 전체 색인(casehdr/flat, 24만 케이스)을 검색해 질문에 답한다. 맥 segfault
# 회피로 검색은 search_preview.py 하위프로세스(embed/search 분리, handlers_retriever.py).
# 회복/차단기: r2(검색)에 first_attempt_fails — 첫 시도 빈결과→r2_retry→재검색 성공(시나리오 A),
# FORCE_FAIL_STEP=r2면 영구 빈결과→연속실패 차단기(시나리오 B). RAG_OFFLINE=1이면 fixture로 배선만.
def retrieve_spec(query, index_dir, search_preview, py="python3.12", topk=5, work=None,
                  gcs_index=None, corpus=None) -> "TaskSpec":
    return TaskSpec(
        name="retrieve",
        goal=f"색인에서 질문에 맞는 사례를 검색해 근거와 함께 답하라: {query}",
        definition={"query": query, "index_dir": index_dir, "search_preview": search_preview,
                    "py": py, "topk": topk, "work": work or os.path.expanduser("~/.orc_rag"),
                    "gcs_index": gcs_index, "corpus": corpus},  # corpus=rag_units.jsonl(본문 근거)
        allowed_tools=["embedder", "faiss_index", "llm"],
        forbidden=["rm -rf /", "DROP TABLE"],
        steps=[
            StepSpec("r1", "질의 임베딩", "embed_query",
                     {"kind": "flag_true", "key": "query_embedded", "cause": "embed_fail"},
                     requires_tool="embedder"),
            StepSpec("r2", "색인 검색(top-k)", "search_index",
                     {"kind": "hits_nonempty", "min": 1, "cause": "search_empty"},
                     depends_on=["r1"], requires_tool="faiss_index",
                     fault={"first_attempt_fails": True, "corrective": "r2_retry"}),
            StepSpec("r3", "LLM 근거응답", "rag_answer",
                     {"kind": "artifact_non_empty", "key": "answer", "cause": "no_answer"},
                     depends_on=["r2"], requires_tool="llm"),
        ],
        diagnosis={
            "embed_fail": [True, "r1_retry"],
            "search_empty": [True, "r2_retry"],
            "no_answer": [True, None],
            "tool_not_allowed": [False, None],
        },
    )


# 기본 인스턴스 — `RAG_OFFLINE=1 SLICE_OFFLINE=1 python -m orc.run retrieve`로 배선·차단기 확인.
# 실모드는 index_dir에 전체 색인(gs.../rag_index/full/idx_full)을 내려받아 두고 키 설정 후 실행.
RETRIEVE = retrieve_spec(
    query="혼효림에서 풍속이 높을 때 주거지와 관광지 중 어디에 자원을 집중해야 합니까?",
    index_dir=os.path.expanduser("~/Documents/Pred-FirefromElec/rag_index/idx_full_v2"),  # v2=수치헤더+오타통일(영구 보관)
    search_preview=os.path.expanduser("~/Documents/Pred-FirefromElec/scripts/search_preview.py"),
    gcs_index="gs://constgx_electrofire/rag_index/full_v2/idx_full",  # 폴더 없으면 여기서 자동 재다운로드
    corpus=os.path.expanduser("~/Documents/Pred-FirefromElec/scripts/rag_units_v2.jsonl"),  # 사례 본문+수치(근거 주입)
)

SPECS = {s.name: s for s in [COMPARE, INGEST_DEMO, INGEST_AIHUB, RETRIEVE]}


def get_spec(name: str) -> TaskSpec:
    if name not in SPECS:
        raise KeyError(f"미등록 spec: {name}. 사용 가능: {list(SPECS)}")
    return SPECS[name]
