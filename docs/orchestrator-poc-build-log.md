# 멀티에이전트 오케스트레이터 PoC — 빌드·테스트 로그 (재학습·포트폴리오용)

> 작성 2026-06-18. 대상 = `constgx/agents/`(LangGraph 오케스트레이터 수직 슬라이스).
> 목적: 초기 테스트가 *어떻게* 단계적으로 검증됐는지를 재현 가능하게 남겨, 재학습과 포트폴리오 서술의 1차 자료로 쓴다.
> 한 줄: **위험을 격리해 작은 단위로 먼저 입증(probe) → 통합 → 환경까지 잠금.** "큰 걸 한 번에 돌려보고 안 되면 디버깅"의 반대.

---

## 0. 무엇을 만들었나 (맥락)
ORC(순수 라우터) + 5노드(PLAN/OFFER/TOOL/MEMORY/Verify) 상태기계로 "건설자재 객체탐지 모델 3종(Faster R-CNN/YOLOv8/RT-DETR) 비교·분석" 워크플로를 e2e로 돌리는 PoC. 단일 진실 객체 = `AgentContext`(TypedDict). TOOL 경계만 MCP, 나머지 역할 경계는 in-process State+노드계약.

---

## 1. 테스트 스레드 A — MCP 서버 연결·도구 호출 (배관 먼저 격리 입증)

**왜 먼저?** 그래프 전체에 MCP를 꽂기 전에, "별도 프로세스로 뜬 MCP 서버에 붙어 도구를 부르는 것"만 따로 입증해야 실패 지점이 좁아진다.

**어떻게.**
1. `langchain-mcp-adapters`(0.3.0) + `mcp`(1.28.0) 설치.
2. 최소 stdio 서버(`FastMCP` + `@mcp.tool()` + `mcp.run(transport="stdio")`) 1개 작성.
3. 클라이언트로 검증: `MultiServerMCPClient({...,"command":sys.executable,"args":["server.py"],"transport":"stdio","env":dict(os.environ)})` → `await client.get_tools()` → `await tool.ainvoke({...})`.

**얻은 사실(재사용).**
- 반환은 **content 블록 리스트** → `json.loads(r[0]["text"])`로 파싱해야 dict가 나온다.
- 서버는 노트북이 자동 spawn — 사용자가 따로 실행하지 않는다.
- `command=sys.executable`로 띄워야 서버 서브프로세스가 커널과 *같은 파이썬*을 써 패키지 불일치(ModuleNotFoundError)를 막는다.
- 서버 env는 `dict(os.environ)`로 상속(PATH·플래그). 안 넘기면 minimal env.
- 샌드박스는 외부 검색 네트워크 차단 → 서버에 `MCP_OFFLINE` 듀얼모드(고정 스니펫)를 넣어 **전송·흐름만** 검증, 라이브 검색은 사용자 맥에서.

---

## 2. 테스트 스레드 B — 실 LLM 연동 + 스니펫 언어 이해 대응

**구조.** TOOL(MCP 웹검색)이 모델별 **스니펫+출처 URL**을 가져오면, OFFER/Verify의 LLM(`ChatAnthropic`)이 그 스니펫 텍스트를 읽어 비교기준(criteria)에 **언어 이해로 대응**시킨다. ※임베딩·벡터 유사도 검색이 아님 — 키워드 웹검색 + LLM 추론. (벡터DB 장기기억은 미구현, GAP-ANALYSIS 참조.)

**검증 분리.** 실 LLM API는 샌드박스에서 호출 불가 → `SLICE_OFFLINE` 스텁으로 그래프 배선·라우팅·차단기(결정적)만 검증, 실 추론은 사용자 맥에서.

**실 실행에서 나온 핵심 발견(포트폴리오 가치 큼).**
- 첫 실 실행은 s2 웹검색 3/3 성공(실 URL) 후 **s4에서 judge가 3회 reject → 차단기 정지(FAILED)**.
- 원인: criteria 4개 중 `train_cost`·`deploy_difficulty`가 웹 벤치마크 스니펫에 거의 없어 "전 기준 커버" 미충족. 검색 쿼리에도 그 두 기준이 안 들어가 있었음.
- 의미: 데이터가 안 맞으니 시스템이 **통과를 꾸며내지 않고 정직하게 실패**했고 무한루프를 막음 → mock이 아니라 진짜 외부 데이터라는 방증.
- 보정: ①리포팅을 성공·실패 무관 출처 출력 + judge 사유(verdict.detail) 노출 ②judge·summarize 정렬 — 스니펫에 없는 기준은 '자료없음' 명시하면 '다룸'으로 인정(정직한 갭이 통과 가능). 후속 개선 후보 = **검색 쿼리를 criteria로부터 동적 구성**.

---

## 3. 테스트 스레드 C — 커널/패키지 환경 격리

**문제.** 시스템 파이썬(3.12)에 바로 설치 → 기존 pydantic과 충돌(`ImportError: InvalidSchemaError`). 터미널 pip와 주피터 커널의 파이썬이 달라 설치가 커널에 안 잡히는 문제도.

**해법(재현 가능).**
1. 샌드박스에서 전체 스택을 동시 import해 **호환 버전 조합 확정** → `requirements-lock.txt`로 잠금.
2. `setup_env.sh`: 격리 `.venv` 생성 → 잠긴 버전 설치 → `ipykernel`로 주피터 커널 `Python (orc-poc)` 등록.
3. 노트북 안 설치는 `%pip`(커널 자기 환경에 설치)로, 또는 아예 격리 커널로.

**검증된 잠금(2026-06-18):** langgraph 1.2.5 / langchain-core 1.4.7 / langchain-anthropic 1.4.6 / anthropic 0.109.2 / langchain-mcp-adapters 0.3.0 / mcp 1.28.0 / aiosqlite 0.22.1 / ddgs 9.14.4 / pydantic 2.13.4.

**부수 사실.** async 노드(TOOL이 `await mcp_search`) → `app.ainvoke` → sync `SqliteSaver` 불가, **`AsyncSqliteSaver`(aiosqlite)** 필요. 노트북 top-level await는 ipykernel·nbconvert 모두 지원. 셀 번호 In[25] 등은 "칸 순서"가 아니라 커널 누적 실행수(Restart 시 리셋).

---

## 4. 관통하는 방법론 (재학습 핵심)
1. **위험을 격리해 작은 probe부터.** MCP 배관 → 실 LLM → 환경, 각각 독립 입증 후 통합.
2. **검증은 산출물·결정적 부분 우선.** 네트워크/LLM 불가한 곳에선 듀얼모드(OFFLINE)로 배선·라우팅·차단기를 먼저 확정.
3. **정직한 실패를 1급 시민으로.** 데이터가 안 맞으면 통과를 꾸미지 말고 실패+차단기. 그게 신뢰의 근거.
4. **환경까지 잠근다.** 코드만이 아니라 버전·커널을 고정해야 "내 맥에선 안 돼"를 없앤다.

_연관 파일: `constgx/agents/`(SPEC.md, orchestrator_slice.ipynb, mcp_model_tool.py, setup_env.sh, requirements-lock.txt, COST-MODEL.md, RUNBOOK-real-llm.md)._
