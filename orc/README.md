# orc — 멀티에이전트 오케스트레이터 (모듈판)

노트북 `../orchestrator_slice.ipynb`의 .py 졸업판. 설계 정본 = `../SPEC.md`.
ORC(순수 라우터) + 5노드(PLAN/OFFER/TOOL/MEMORY/Verify) 상태기계.

## 엔진 ↔ 작업 경계 (v0.5 범용화)

엔진(state·nodes·orchestrator)은 **작업 지식을 코드로 갖지 않는다.** 무엇을·어떤
순서로·어떤 기준으로 할지는 전부 `TaskSpec`(specs.py)이 데이터로 들고 있고, 엔진은
그걸 읽어 돈다. 한 엔진(`build_app`)이 서로 다른 spec을 받아 돌면 그 자체가 도메인
무관의 증거다(추상 일반화 주장보다 확실).

새 작업 추가 = `handlers_<x>.py`에 액션/검수기 등록 + `specs.py`에 `TaskSpec` 추가 +
`handlers.py`에 한 줄. **엔진 코드 수정은 0.**

## 모듈 구성
```
orc/
├── __init__.py
├── state.py            # AgentContext(TypedDict) + initial_state(spec)  (§2)
├── specs.py            # TaskSpec/StepSpec + COMPARE·INGEST_DEMO + get_spec  (범용화)
├── registry.py         # ACTION_HANDLERS/ACCEPTANCE_CHECKERS + 등록 데코레이터
├── handlers.py         # 등록 집결점(import 트리거)
├── handlers_common.py  # 공용 검수기(artifact_non_empty/flag_true)
├── handlers_compare.py # 비교 작업: define/extract/compare/summarize + 검수기 (실 LLM+검색)
├── handlers_ingest.py  # 적재 데모: fetch/verify_checksum/store + 검수기 (결정적·로컬)
├── handlers_retriever.py # RAG 검색·응답: embed_query/search_index/rag_answer (실검색은 search_preview.py 하위프로세스=맥 segfault 회피)
├── llm.py              # SYS 프롬프트 + llm_call (실 LLM / SLICE_OFFLINE 스텁)  (§6)
├── mcp_tools.py        # 웹검색 MCP 서버 호출(mcp_search, async)  (§1·결정2)
├── nodes.py            # plan/offer/tool(async)/memory/verify — spec 기반 제네릭 디스패치
├── orchestrator.py     # orc_node + route + build_app, DIAGNOSIS는 spec에서  (§5·§7)
└── util.py             # 로깅 + step_by_id + inject_fault(의도적 실패)
../mcp_model_tool.py    # 별도 프로세스로 뜨는 MCP 서버(노트북·모듈 공용)
```

## 실행
agents/ 폴더(이 패키지의 상위)에서. **같은 엔진, spec만 인자로 교체:**
```
# 작업1: 모델 비교 — 실 LLM + 실 웹검색 (run.py가 ../scripts/.env의 CLAUDE_KEY 자동 로드)
python -m orc.run                # 기본 spec=compare
python -m orc.run compare

# 작업2: 적재 루프 데모 — 결정적(키·네트워크 불필요, 로컬 파일 I/O)
python -m orc.run ingest_demo

# 비교 배선/라우팅/차단기만 (키 없이)
SLICE_OFFLINE=1 MCP_OFFLINE=1 python -m orc.run compare
```
각 spec마다 시나리오 A(happy path, DONE)와 B(차단기, FAILED)를 출력한다.

## Cursor에서
1. `constgx/`(또는 `agents/`)를 Cursor로 연다.
2. 인터프리터를 `agents/.venv`(setup_env.sh가 만든 격리 환경)로 선택.
3. `orc/run.py`를 실행하거나 터미널에서 `python -m orc.run`.
4. 노트북은 인터랙티브 프로토타입으로 유지 — 로직 변경은 모듈에 하고 노트북은 모듈을 import하도록 점진 전환 가능.

## 다음 후보 (범용화 이후 — 미리 펼치지 않음, 하나씩)
- 실 도구 감싸기: 데이터/비전 세션 산출물을 MCP 도구로 감싸 새 spec으로 연결.
- 실 적재 루프 흡수: scripts/INGEST-AGENT.md(이미 같은 자기검증 골격)를 ingest_demo의
  결정적 핸들러를 실 다운로드/GCS로 교체해 흡수(키·네트워크는 사용자 맥).
- 파일 지속성·관측성(LangSmith). 검색 쿼리 동적 구성, 캐싱, 모델 계층화.
