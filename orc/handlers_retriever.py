"""RAG 검색·응답 작업 핸들러 — 질의→검색→LLM 근거응답. RETRIEVE spec.

compare(실 LLM+웹검색)·ingest(결정적 적재)에 이은 세 번째 실작업 인스턴스.
대상 색인 = Pred-FirefromElec 전체 색인(casehdr/flat, 24만 케이스).

★ 맥 제약(한 프로세스에 torch+faiss = libomp 충돌 세그폴트): 실모드 검색은
scripts/search_preview.py 를 하위 프로세스(embed→search 2단계)로 호출한다. orc
프로세스에는 torch/faiss를 들이지 않는다. RAG_OFFLINE=1(또는 SLICE_OFFLINE=1)이면
고정 fixture로 배선·라우팅·차단기만 검증(인덱스·모델·API키 불필요).

액션: embed_query/search_index/rag_answer. 검수기: hits_nonempty.
"""
import os
import json
import subprocess
from .registry import action, acceptance
from .llm import llm_call
from .util import log, step_by_id, inject_fault


def _offline() -> bool:
    # 검색(embed/search)만 제어. LLM 응답은 llm.py가 SLICE_OFFLINE로 따로 제어 →
    # RAG_OFFLINE 없이 SLICE_OFFLINE=1이면 '실검색 + 스텁응답'으로 실 인덱스만 검증 가능.
    return os.environ.get("RAG_OFFLINE") == "1"


def _ensure_index(d):
    """영구 보관 안전장치 — index_dir이 비었으면(재부팅·삭제로 휘발) gcs_index에서 자동 재다운로드.
    고정 경로(rag_index/idx_full)가 정상이면 아무 일도 안 함(무과금)."""
    idx = d["index_dir"]
    if os.path.exists(os.path.join(idx, "index.faiss")):
        return
    gcs = d.get("gcs_index")
    if not gcs:
        raise FileNotFoundError(f"색인 없음: {idx} (gcs_index 미설정 → 자동복구 불가)")
    os.makedirs(os.path.dirname(idx), exist_ok=True)
    subprocess.run(["gcloud", "storage", "cp", "-r", gcs, os.path.dirname(idx) + "/"], check=True)


# 배선 검증용 고정 결과(실 인덱스/모델/키 없이 라우팅·차단기 확인)
_FIXTURE_HITS = [
    {"id": "case_A.json", "query_subject": "확산경로", "fuel_type": "혼효림"},
    {"id": "case_B.json", "query_subject": "확산속도", "fuel_type": "혼효림"},
    {"id": "case_C.json", "query_subject": "우선순위", "fuel_type": "혼효림"},
]


@action("embed_query")
async def _embed_query(state, artifacts):
    d = state["constraints"]["definition"]
    if _offline():
        artifacts["query_embedded"] = True
        log(state, "TOOL", "embed_query", "ok", rout="offline stub")
        return
    work = d["work"]; os.makedirs(work, exist_ok=True)
    qjson = os.path.join(work, "orc_q.jsonl")
    with open(qjson, "w", encoding="utf-8") as f:
        f.write(json.dumps({"qid": "q0", "query": d["query"]}, ensure_ascii=False) + "\n")
    emb = os.path.join(work, "orc_q.npy")
    subprocess.run([d["py"], d["search_preview"], "embed",
                    "--eval", qjson, "--out-emb", emb, "--device", "cpu"], check=True)
    artifacts["query_embedded"] = True
    artifacts["_emb_path"] = emb
    log(state, "TOOL", "embed_query", "ok", rout=os.path.basename(emb))


@action("search_index")
async def _search_index(state, artifacts):
    d = state["constraints"]["definition"]
    step = step_by_id(state, state["cursor"])
    if inject_fault(state, step):                       # 차단기/회복 데모: 첫 시도 빈 결과
        artifacts["hits"] = []
        log(state, "TOOL", "search_index", "fail", cause="search_empty", rout="0 hits (injected)")
        return
    if _offline():
        artifacts["hits"] = list(_FIXTURE_HITS)[: d.get("topk", 5)]
        log(state, "TOOL", "search_index", "ok", rout=f"{len(artifacts['hits'])} hits (offline)")
        return
    _ensure_index(d)                                    # 영구 보관: 색인 휘발 시 버킷에서 자동 복구
    work = d["work"]
    res = os.path.join(work, "orc_res.jsonl")
    subprocess.run([d["py"], d["search_preview"], "search",
                    "--index-dir", d["index_dir"], "--emb", artifacts["_emb_path"],
                    "--out", res, "--topk-cases", str(d.get("topk", 5))], check=True)
    first = open(res, encoding="utf-8").readline().strip()
    ids = json.loads(first)["retrieved"] if first else []
    meta = _load_meta(os.path.join(d["index_dir"], "case_meta.jsonl"), set(ids))
    artifacts["hits"] = [{"id": i, **meta.get(i, {})} for i in ids]
    log(state, "TOOL", "search_index", "ok", rout=f"{len(artifacts['hits'])} hits")


def _load_meta(path, want):
    """검색된 case id들의 주제·연료만 골라 적재(보고·LLM 근거용)."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            u = json.loads(line)
            if u["id"] in want:
                out[u["id"]] = {"query_subject": u.get("query_subject", ""),
                                "fuel_type": u.get("fuel_type", "")}
                if len(out) == len(want):
                    break
    return out


def _load_bodies(corpus_path, want_ids, cap=900):
    """rag_units.jsonl을 흘려읽어 검색된 case id들의 본문(text)만 모은다(전부 찾으면 조기 종료)."""
    want = set(want_ids); out = {}
    if not corpus_path or not os.path.exists(corpus_path):
        return out
    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            u = json.loads(line)
            if u["id"] in want:
                out[u["id"]] = (u.get("text", "") or "")[:cap]
                if len(out) == len(want):
                    break
    return out


@action("rag_answer")
async def _rag_answer(state, artifacts):
    d = state["constraints"]["definition"]
    hits = artifacts.get("hits", [])
    if not _offline() and d.get("corpus"):                   # 본문 근거 주입(실모드)
        bodies = _load_bodies(d["corpus"], [h["id"] for h in hits])
        hits = [{**h, "text": bodies.get(h["id"], "")} for h in hits]
    artifacts["answer"] = llm_call("rag_answer", {"query": d["query"], "hits": hits})
    log(state, "TOOL", "rag_answer", "ok", rout=f"{len(hits)} 사례 근거")


@acceptance("hits_nonempty")
def _hits_nonempty(state, acc):
    """검색결과가 최소 min건 이상이면 통과(결정적)."""
    hits = state["artifacts"].get("hits", [])
    ok = len(hits) >= acc.get("min", 1)
    return {"passed": ok, "cause": None if ok else acc["cause"]}
