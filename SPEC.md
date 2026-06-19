# SPEC — 멀티에이전트 오케스트레이터 PoC (LangGraph)

> 상태: **v0.4 (.py 모듈 졸업 완료)**. 구현 = `orc/` 패키지(state·llm·mcp_tools·nodes·orchestrator·run) + `mcp_model_tool.py` + 프로토타입 `orchestrator_slice.ipynb`. 실 LLM+실검색 e2e 확정(A=DONE), 모듈판 `python -m orc.run` 동등성 검증.
> v0.3에서 TOOL이 in-process mock → **별도 프로세스 웹검색 MCP 서버(키리스 DuckDuckGo)**로 교체됨. 데이터 출처가 내부 하드코딩이 아니라 외부 real URL.
> 정본 설계: `cowork/knowledge/multiagent-orchestrator-template.md` (v0.1) + `2026-06-17-checkpoint-오케스트레이터PoC.md`.
> 이력/원격: GitHub `IKWHI-OSS/Building-Infra` (branch main) — 인프라·프로젝트설정·데이터선정 문서만.
> 이 문서는 **그 설계를 LangGraph 코드 골격으로 매핑하는 경량 명세**다. 금도금 금지 — PoC 입증에 필요한 것만 적는다.
> 용어는 고정: `ORC / PLAN / OFFER / TOOL / MEMORY / Verify`, `State(AgentContext) / checkpointer / Store / MCP`. 유사어 임의 정의 금지.

---

## 0. 목적 & 범위

**목적.** 비교·분석 워크플로(비교기준정의 → 항목추출 → 차이분석 → 결과요약) 1회를 ORC+5노드 상태기계로 **end-to-end 통과**시킨다. happy path + 의도적 실패 1건으로 DIAGNOSIS·차단기까지 입증.

**확정 슬라이스 주제(reference instance).** 건설자재 객체탐지 모델 후보 3종 비교 — 대상 = `Faster R-CNN / YOLOv8 / RT-DETR`, 비교기준 = `mAP · FPS · train_cost · deploy_difficulty`. (71388 건설자재 데이터 적재 후 마주한 실제 모델선택 결정)

**빌드 결정(이번 세션 확정).** ①통과 후 경로 = PLAN 경유(§5 유지) ②OFFER/s4 Verify는 **처음부터 실 LLM**(`ChatAnthropic`, `ANTHROPIC_API_KEY` 필요) — 단 그래프 배선 검증용 `SLICE_OFFLINE=1` 결정적 스텁 경로 병행. ③TOOL은 mock(`lookup_model_spec`) → 실 MCP(웹검색) 교체 슬롯.

**범위 안 (this PoC).**
- LangGraph `StateGraph`로 6노드(ORC+5) + 조건부 라우팅.
- 단기 메모리 = `SqliteSaver` checkpointer, 장기 = `InMemoryStore`.
- TOOL은 **모의 도구**로 시작 → 수직 슬라이스 1개를 실 MCP 도구로 교체.
- 검증 비용 계층화(중간 구조검증 / 최종 LLM-judge).

**범위 밖 (out of scope, 명시적으로 안 함).**
- OFFER/PLAN의 MCP 서버 승격(결정 2: in-process 유지).
- 역할별 MCP 서버 분리, Postgres 백엔드, 병렬·경쟁·이벤트 유형.
- 모델 계층화·캐싱·회귀평가 하네스(설계엔 있으나 PoC 비범위).

---

## 1. 확정 결정 (체크포인트 1절 — 이 SPEC의 전제)

1. **스택**: LangGraph(오케스트레이션) + LangChain(LLM/도구 글루) + langchain-mcp-adapters(TOOL 경계 전용). 자작 오케스트레이터 폐기.
2. **결정1 — OFFER/PLAN**: v1 in-process 노드. MCP는 TOOL 경계에만.
3. **결정2 — MCP 배포**: 역할별 서버로 안 쪼갬. 역할 경계 = **State schema + 노드 계약**(in-process). MCP = 부작용 있는 TOOL 경계만(경계 ≠ 별도 서버).
4. **결정3 — MEMORY**: 단기=checkpointer(state·rollback), 장기=Store(User·History). PoC 백엔드 = `SqliteSaver` + `InMemoryStore`.
5. **결정4 — Verify**: 독립 노드. ORC는 **순수 라우터**(LLM 추론 안 함 → 토큰·예측불가 방지).

> 템플릿 v0.1과의 차이: v0.1은 "계층 간 호출=MCP"가 기본이었으나, 결정2에서 **역할 경계는 in-process State+노드계약**으로 좁혀졌다. 본 SPEC은 최신 결정을 따른다.

---

## 2. State Schema = AgentContext (TypedDict)

단일 진실 객체. 모든 노드는 이걸 읽고 *자기 소관 필드만* 쓴다(4절 행동제약). `history`는 원문이 아니라 **digest**만(컨텍스트 희석 방지).

```python
from typing import TypedDict, Literal, Optional, Any
from typing_extensions import NotRequired

class PlanStep(TypedDict):
    step_id: str
    subgoal: str
    priority: int
    depends_on: list[str]
    status: Literal["pending", "running", "done", "failed"]

class Constraints(TypedDict):
    definition: dict[str, Any]        # 작업 초기 정의(예: 비교기준 목록)
    allowed_tools: list[str]          # 최소권한 화이트리스트
    forbidden: list[str]              # 안전필터(rm -rf, DROP TABLE ...)
    acceptance: dict[str, Any]        # 완결성 기준

class HistoryEntry(TypedDict):
    t: str                            # ISO ts
    actor: Literal["ORC","PLAN","OFFER","TOOL","MEMORY","Verify"]
    action: str                       # 예: "call_tool:extract"
    input_digest: str
    result_digest: str
    status: Literal["ok","fail"]
    cause: Optional[str]              # 실패 원인코드(DIAGNOSIS 키)

class Budget(TypedDict):
    iter: int
    max_iter: int                     # 무한루프 방지 상한(예 12)
    retry: int                        # 잔여 재시도 예산
    consec_fail: int                  # 연속 실패 카운터(차단기)
    fail_threshold: int               # 차단기 임계(예 3)

class Verdict(TypedDict):
    passed: bool
    cause: Optional[str]              # 실패 시 원인코드(retriable 매핑용)
    detail: NotRequired[str]

class AgentContext(TypedDict):
    goal: str                         # 불변 — ORC만, 유저 합의 시에만 변경
    constraints: Constraints
    plan: list[PlanStep]
    cursor: Optional[str]             # 현재 step_id
    artifacts: dict[str, Any]         # 단계 산출물(또는 외부저장 포인터)
    scratch: dict[str, Any]           # OFFER 휘발성 작업메모
    history: list[HistoryEntry]       # digest만
    budget: Budget
    verdict: Optional[Verdict]        # 통과 전 None
```

장기 보존 항목은 `artifacts`에 **포인터**(파일/DB/GCS 경로)만, 본문은 Store/외부에.

---

## 3. 노드 목록 (ORC + 5)

| 노드 | 계층 | 역할 | LLM | 부작용 |
|---|---|---|---|---|
| **ORC** | L1 | 순수 라우터. 목표충돌 방지·실행순서 통제. 조건부 엣지로만 동작 | X | 없음 |
| **PLAN** | L2 | 목표 분해·우선순위·동적 replan | (경량) | 없음 |
| **OFFER** | L2 | 상태해석·행동결정·도구호출 판단·출력구성 | **O** | 없음(판단만) |
| **TOOL** | L2 | 실행·보안경계. MCP 경유 | X | **O**(외부 I/O) |
| **MEMORY** | L2 | state·checkpoint 쓰기, 장기 Store | X | O(영속) |
| **Verify** | L2 | 수락기준 평가 → verdict | 최종만 O | 없음 |

각 노드 함수 시그니처는 동일: `def node(state: AgentContext) -> dict` (갱신할 부분 dict 반환, LangGraph가 머지).

---

## 4. 행동제약 (역할 침범 방지 — reads/writes/may_call)

| 노드 | reads | writes | may_call | must_not |
|---|---|---|---|---|
| ORC | 전체 | `goal`,`constraints`,`verdict`,`budget` | (라우팅만) | LLM 추론, TOOL 직접 실행 |
| PLAN | `goal`,`constraints`,`cursor`,`artifacts` | `plan` | — | TOOL 호출, artifacts 생성 |
| OFFER | `goal`,`constraints`,`plan`,`artifacts`,`scratch`,`history` | `scratch`, 제안 action | TOOL, MEMORY | 최종 완결판정, constraints 위배 도구선택 |
| TOOL | action spec | `artifacts`, 구조화 result | 외부(화이트리스트) | `forbidden` 매칭 실행, 인터페이스 외 접근 |
| MEMORY | `state`,`history` | `history`, checkpoint, Store | — | 판단·도구실행 |
| Verify | `constraints.acceptance`, `artifacts` | `verdict` | (최종만 LLM) | 라우팅(엣지 결정은 ORC) |

핵심 불변식: **OFFER가 도구선택을 `constraints`에 대조·거부**(실행경로통제 1차) → **TOOL이 `allowed_tools`/`forbidden`로 2차 차단** → 파괴적 작업은 **HITL 게이트** 후에만.

---

## 5. 엣지 / 라우팅 (Verify 뒤 조건부 분기 — 핵심)

순서: `stage 실행(OFFER→TOOL→MEMORY) → Verify가 done 판정 → ORC가 verdict 보고 라우팅`. Verify=평가자(verdict만), ORC=라우터(엣지 결정). either/or 아닌 순차.

```python
def route(state: AgentContext) -> str:
    v = state["verdict"]
    b = state["budget"]
    if v and v["passed"]:
        return "END" if _is_last_step(state) else "PLAN"   # 다음 step
    # 실패 분기
    if b["consec_fail"] >= b["fail_threshold"]:
        return "FAIL"                                       # 차단기
    if b["retry"] > 0:
        return "OFFER" if _retriable(v) else "PLAN"         # 실행문제→OFFER, 계획문제→PLAN
    return "FAIL"                                           # 예산 소진
```

그래프 골격:

```
entry → ORC
ORC → PLAN            (정상 진입/다음 step)
PLAN → OFFER → TOOL → MEMORY → Verify
Verify → ORC          (verdict 보고)
ORC --conditional(route)--> {PLAN, OFFER, END, FAIL}
```

`_retriable(verdict)`는 **DIAGNOSIS 표**로 원인코드 → (retriable?, corrective) 매핑. 미진단 원인은 retriable=False → PLAN(또는 FAIL). corrective 적용(새 증거 생성) 후에만 재시도(유계).

---

## 6. 단계별 acceptance (비교·분석 4단계)

4단계는 노드가 아니라 **PLAN이 만든 4개 plan-step**. 각 step이 역할 노드를 돈다.

| step | 역할 흐름 | Verify 수락기준 | 검증 종류 |
|---|---|---|---|
| s1 비교기준정의 | ORC goal 고정 → PLAN 분해 → OFFER 기준 구성 → MEMORY가 `constraints.definition` 저장 | 기준 형식 충족(non-empty·스키마) | **구조(결정적)** |
| s2 항목추출(fan-out) | PLAN 대상별 step 확산 → OFFER 추출판단 → TOOL 실행 → MEMORY 저장 | 전 대상 공통 스키마 수렴 | **구조(결정적)** |
| s3 차이분석 | OFFER 수렴항목 비교(필요시 TOOL) → MEMORY 저장 | 전 기준 비교됨 | **구조(결정적)** |
| s4 결과요약 | OFFER 출력 구성 → ORC 종료/replan 라우팅 | 전 기준 커버 + 출처 존재 | **LLM-as-judge** |

**검증 비용 계층화**: s1~s3은 결정적 구조검증(스키마 충족·전 대상 수렴·non-empty, LLM 안 씀) → fail-fast + 토큰 최소. s4만 LLM-judge.

---

## 7. 의도적 실패 1건 (DIAGNOSIS·차단기 입증)

PoC 검증용으로 s2에서 **의도적 실패** 주입(예: 한 대상 추출 결과 스키마 누락).

- Verify가 `passed=False, cause="schema_incomplete"` → ORC `route`.
- DIAGNOSIS: `schema_incomplete` → (retriable=True, corrective="재추출 파라미터 보정") → OFFER 재시도(retry 차감, 새 증거 생성).
- 보정 후에도 연속 실패가 `fail_threshold` 도달 → `route`가 `FAIL` 반환(차단기). 무한루프 안 돎.
- 미진단 원인(예: `unknown_x`)은 retriable=False → FAILED + halt, DIAGNOSIS 표에 항목 추가(자기학습).

---

## 8. 운영 3축 매핑 (GAP-ANALYSIS 🔴 갭 흡수 확인)

| GAP 🔴 | 본 SPEC 흡수 위치 |
|---|---|
| AgentContext 부재 | §2 State schema(단일 진실 객체) |
| HITL 부재 | §4 TOOL 불변식("파괴적 작업은 HITL 게이트 후") |
| 안전필터 부재 | §2 `constraints.forbidden` + §4 TOOL 2차 차단 |
| 최소권한 부재 | §2 `constraints.allowed_tools` 화이트리스트 |
| MCP 검증 부재 | §1 결정2(TOOL 경계 MCP) + langchain-mcp-adapters 서버측 검증 |

품질=§6 acceptance + s4 LLM-judge. 비용=§2 history digest. (모델 계층화·캐싱은 비범위.)

---

## 9. 빌드 순서 (체크포인트 7절)

```
1. pip install langgraph langchain langchain-mcp-adapters langgraph-checkpoint-sqlite
2. State(TypedDict)=AgentContext (§2)
3. 노드 함수: PLAN/OFFER/TOOL/MEMORY/Verify (state→dict)
4. g=StateGraph(State) → add_node → add_edge/add_conditional_edges(route) → entry/finish
5. checkpointer(SqliteSaver)+Store(InMemoryStore) 부착
6. client=MultiServerMCPClient({...}) → tools=await client.get_tools() → TOOL 노드 바인드
7. app=g.compile(checkpointer=...) → app.invoke(input, config={"thread_id":...})
8. 트레이싱=LangSmith(LANGSMITH_*)
```

빌드 플랫폼: Jupyter 셀 단위 반복·검증(state·verdict 즉시 관찰) → 안정화 후 `constgx/agents/*.py` 모듈로 졸업.

---

_v0.1 2026-06-17 — 에이전트 초안._
_v0.2 2026-06-18 — 유저 검토 후 수직 슬라이스 빌드. `orchestrator_slice.ipynb`로 e2e 검증(A/B 시나리오 nbconvert 통과)._
_v0.3 2026-06-18 — TOOL = 실 MCP 웹검색 교체. `mcp_model_tool.py`(stdio, 키리스 DDG, MCP_OFFLINE 듀얼모드) + langchain-mcp-adapters. tool_node async화 → app.ainvoke + AsyncSqliteSaver. s2 acceptance: 스키마충족 → 대상별 스니펫·출처 존재. 의도적 실패: 한 대상 검색실패(missing_source). 다음 = 실LLM+실검색 품질검토 → .py 모듈 졸업._
_v0.4 2026-06-19 — .py 모듈 졸업. 노트북 로직을 `orc/` 패키지로 분리(state/llm/mcp_tools/nodes/orchestrator/run + util). build_app async화(AsyncSqliteSaver), run.py가 asyncio.run 래퍼 + .env 자동로드, MCP 서버 경로는 sys.executable+패키지 상위 resolve. `python -m orc.run` 동등성 검증(A=DONE/B=FAILED). 노트북은 인터랙티브 프로토타입으로 유지. 커서 전환 대상. orc/README.md 참조._
_v0.3.1 2026-06-18 — 실 LLM 첫 실행 피드백 반영. 발견: 웹 스니펫에 train_cost/deploy_difficulty 부재 → s4 judge가 "전 기준 커버" 미충족으로 정직하게 reject(차단기 정상 작동, mock 아님의 방증). 수정: ①리포팅을 성공·실패 무관 출처 출력 + judge 사유(verdict.detail) 노출 ②judge·summarize 프롬프트 정렬 — 스니펫에 없는 기준은 '자료없음' 명시하면 '다룸'으로 인정(정직한 데이터 갭이 통과 가능). 환경: `setup_env.sh`+`requirements-lock.txt`(격리 venv, pydantic 충돌 회피)._
