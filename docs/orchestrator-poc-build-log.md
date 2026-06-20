# 멀티에이전트 오케스트레이터 PoC — 빌드·테스트 로그 (재학습·포트폴리오용)

> 작성 2026-06-18 · 갱신 2026-06-19. 대상 = `constgx/agents/`(LangGraph 오케스트레이터).
> 목적: 빌드·검증이 *어떻게* 단계적으로 됐는지를 재현 가능하게 남겨, 재학습과 포트폴리오 서술의 1차 자료로 쓴다.
> 한 줄: **위험을 격리해 작은 단위로 먼저 입증(probe) → 통합 → 환경까지 잠금 → 모듈 졸업.** "큰 걸 한 번에 돌려보고 안 되면 디버깅"의 반대.
> 범위: 스레드 A/B/C(슬라이스 검증) → D(모듈 졸업) → 프로젝트 적용 판단(데이터 선정). 코드 정본=`SPEC.md`, 원격=GitHub `IKWHI-OSS/Building-Infra`.

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
- **수정 후 결과:** 사용자 맥에서 실 LLM + 실 웹검색 재실행 → **A=DONE 통과**(s2 재시도 회복 2/3→3/3, s4 judge 통과). 출처가 실제 외부 URL 3종(medium/github/roboflow/ultralytics/springer)으로 찍힘. `train_cost`는 '자료없음'으로 정직 표기하면서도 통과 — 차단기가 '정직한 실패'에서 '정직한 처리'로 전환됨을 확인.

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

## 4. 테스트 스레드 D — 노트북 → .py 모듈 졸업 (v0.4)

**왜.** 노트북은 프로토타입 검증엔 좋지만, 재사용·버전관리엔 모듈이 맞다. 안정화된 로직을 `orc/` 패키지로 분리.

**구성.** `state.py`(AgentContext) · `llm.py`(SYS+호출) · `mcp_tools.py`(MCP 호출) · `nodes.py`(5노드) · `orchestrator.py`(DIAGNOSIS+ORC route+build_app) · `run.py`(asyncio.run 래퍼+.env 자동로드) · `util.py`.

**얻은 사실.** async 노드가 있으면 `build_app`도 async(`await aiosqlite.connect` → AsyncSqliteSaver). 노트북 top-level await가 .py엔 없으니 `asyncio.run`. MCP 서버 경로는 `Path(__file__)...`로 절대화 + `command=sys.executable`.

**검증.** `python -m orc.run`을 OFFLINE으로 돌려 노트북과 **동등**(A=DONE / B=차단기 FAILED) 확인. 격리 환경은 `setup_env.sh`+`requirements-lock.txt`로 1회 셋업.

---

## 5. 프로젝트 적용 판단 (포트폴리오 가치)

슬라이스(건설자재 모델 비교)는 엔진 입증용. 실제 프로젝트는 **ESS 배터리 화재위험 예측**(열폭주 단계 예측 + 기상 + 자료검색 + 보고서, orc/가 지휘)로 정함. 데이터 선정에서 드러난 판단 사례:

- **확인이 추정을 바로잡는다.** 비전 데이터로 처음엔 '산업시설 열화상 CCTV'를 추천했으나, 브라우저로 직접 확인하니 **1.88TB**(과대)였고, 배터리 열폭주 멀티모달(71918, 13GB, 열화상+센서+1~6단계 라벨+베이스라인 모델 제공)이 주제·비용 모두 우월 → 추천이 뒤집힘. **이름·추정 금지, 보고 정한다.**
- **없는 건 솔직히 없다고.** 배터리 '물성' RAG 텍스트는 AI Hub에 없음(검색으로 확인) → AI Hub 밖에서 찾거나 보류로 명시.
- **적재 워크플로 = 또 하나의 인스턴스.** 데이터 적재 러너(`scripts/INGEST-AGENT.md`)가 이미 같은 자기검증 루프(Step→verify→DIAGNOSIS→유계재시도→차단기) → orc/의 두 번째 인스턴스 후보(LLM 없는 결정적 형태).

### 5-1. 외부 RAG 출처 검증 (2026-06-20, 물성·발화 + 가연환경·확산)
AI Hub에 없는 두 RAG 축(**물성·발화 근거**, **가연환경·확산 근거**)을 AI Hub 밖에서 후보 7종으로 좁히고, 출처가 실재·접근가능·텍스트(RAG적합)인지 웹검증함. **7종 전부 실재·접근가능 확정.** 다만 "바로 적재"와 "라이선스 확인"으로 갈림 — 추정으로 등급 매기지 말고 실제 배포형태로 정한 사례.

**물성·발화 근거**
- **KC 62619**(ESS 리튬이차전지 안전성·오용) — KATS 무료 PDF 실재 확인. 발화·오용 조건 정의의 핵심. → 1순위.
- **ESS 셀 열폭주 유도 시험방법** — standard.go.kr 직접 다운로드 링크(fileSn) 확인. 71918 열폭주 1~6단계 라벨과 직결. → 1순위.
- **KS C IEC 62660-2 / KS R ISO 12405-3** — kssn.net 실재하나 **유료·구매 표준** → 본문 재배포(RAG 색인)는 라이선스 확인 후. → 2순위.
- **논문(ACS Omega 등)** — 벤트가스 가연한계 논문 실재. **ACS Omega는 골드 오픈액세스** → 표의 '중간'보다 적합 상향 가능. ScienceDirect/Nature는 저작권 제약 → 인용·요약 위주.

**가연환경·확산 근거**
- **소방청 리튬이온 화재예방대책 PDF** — isafe.go.kr 무료 실재(2025-08 최신본 포함). → 1순위.
- **KFPA 화재안전 웹진** — 무료 HTML, 전기차/ESS 화재 확산·열폭주 다수 기사 실재. → 1순위.
- **화재확산/벤트가스 논문(H2·CO·HF 분산)** — ACS Omega 가연한계·분산 논문으로 충당, 오픈액세스 분 우선.

**검증으로 바로잡은 표 보정 2건:** ①ACS Omega 벤트가스 논문은 골드 OA라 'RAG 적합 중간 → 높음' 상향 가능. ②kssn.net 표준 2건은 표상 '높음'이나 실제 유료·라이선스라 무료 공식배포(KC 62619·열폭주 시험방법)보다 한 단계 아래로 두는 게 안전.
- **적재 형태 차이(중요):** 외부 RAG 출처는 AI Hub filekey가 아니라 **직접 URL 다운로드**(kats/standard/isafe/kfpa/pubs.acs) → 71918/71921의 aihubshell 루프와 별개로 `aihub-rag-sources-manifest.md`(직접 URL·라이선스·BK prefix)로 관리. 적재 루프(무결성→업로드→크기검증)는 동일 재사용.

---

## 6. 관통하는 방법론 (재학습 핵심)
1. **위험을 격리해 작은 probe부터.** MCP 배관 → 실 LLM → 환경, 각각 독립 입증 후 통합.
2. **검증은 산출물·결정적 부분 우선.** 네트워크/LLM 불가한 곳에선 듀얼모드(OFFLINE)로 배선·라우팅·차단기를 먼저 확정.
3. **정직한 실패를 1급 시민으로.** 데이터가 안 맞으면 통과를 꾸미지 말고 실패+차단기. 그게 신뢰의 근거.
4. **환경까지 잠근다.** 코드만이 아니라 버전·커널을 고정해야 "내 맥에선 안 돼"를 없앤다.
5. **확인이 추정을 이긴다.** 데이터·사실은 이름·기억으로 정하지 말고 직접 보고 정한다(추천이 뒤집힌 71918 사례).

_연관 파일: `constgx/agents/`(SPEC.md, orc/, orchestrator_slice.ipynb, mcp_model_tool.py, setup_env.sh, requirements-lock.txt, COST-MODEL.md, RUNBOOK-real-llm.md), `docs/`(체크포인트)._

---

## 7. cowork MEMORY에서 이관한 설계지식 (2026-06-20 정본화)
> 아래는 원래 cowork `MEMORY.md`에 있던 인프라 오케스트레이션 설계지식이다. 프로젝트 무관 범용 인프라라 **Building-Infra 레포가 정본**이 맞아 이리로 이관했다(cowork엔 포인터만 남김). 스파게티 방지를 위한 정본 단일화.

**(1) LangGraph "ORC=순수 라우터" 2단 분리 구현** — `orc_node`가 결정을 계산해 `scratch["_route"]`에 적재 → `add_conditional_edges(ORC, route, {...})`의 `route()`는 그걸 읽기만(LLM·분기로직 없음). ORC가 예산(retry/consec_fail)·verdict·현 step done까지 다 기록(완결판정 소유), Verify는 verdict만 반환. 무한루프 방지 = 유계재시도(retry 차감)+연속실패 차단기(consec_fail>=threshold→FAIL). 통과 시 END 분기는 PLAN 전진노드를 안 거치므로 **현 step done 마킹을 ORC 통과분기에서** 처리(안 하면 마지막 step이 pending). recursion_limit는 재시도 고려해 100(기본 25는 부족).

**(2) PoC 테스트 방법론(3스레드)** — 에이전트/통합 PoC는 **위험을 격리해 작은 probe부터 → 통합 → 환경까지 잠금** 순. ①MCP 배관(최소 stdio 서버+get_tools/ainvoke 단독 입증, content블록→json.loads) ②실 LLM 연동(스니펫 텍스트를 LLM 언어이해로 criteria에 대응 — 임베딩/벡터 아님; 샌드박스선 SLICE_OFFLINE 스텁으로 배선만) ③커널/env 격리(호환버전 동시import→requirements-lock→venv+ipykernel 등록, pydantic 충돌 회피). 원칙: 결정적 부분 우선 + 듀얼모드(OFFLINE) + 정직한 실패를 1급 시민으로 + 버전·커널까지 잠금.

**(3) orc 엔진에 인스턴스 장착 패턴 (2026-06-20 실증)** — 엔진은 작업 지식을 코드로 안 갖고, `TaskSpec`(specs.py)이 무엇을·순서·기준을 데이터로 들고, 액션·검수기는 `registry.py` 디스패치, 작업별 구현은 `handlers_*.py`. 이 구조로 **compare(실 LLM, 비결정적)**·**ingest(결정적, 키 없는 I/O)** 두 작업을 한 엔진이 그대로 실행 = 도메인 무관 = 범용화 실증. 적재 인스턴스(`INGEST_AIHUB` spec + `handlers_ingest.py` + `ingest_driver.py`)에서 삭제(g5)는 무결성·크기 두 게이트 통과 후에만 구조적으로 도달. INGEST-AGENT의 게이트/DIAGNOSIS/차단기/HITL과 1:1 매핑. (639건 무인 적재 0 실패로 입증, 2026-06-20.)
