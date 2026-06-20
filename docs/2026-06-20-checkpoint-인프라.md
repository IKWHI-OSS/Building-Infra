# 체크포인트 — 인프라(오케스트레이터) 세션 · 2026-06-20

> 다음 세션 시작 시 이 블록을 붙여 깨끗한 컨텍스트에서 이어간다.

---

[인프라 — 이어서]
부팅: CLAUDE.md → SOUL/LOOP/MEMORY/USER. 이어서 `constgx/agents/SPEC.md`, `constgx/agents/orc/README.md` 읽기.

## 한 줄
작업 1(범용화) 완료·검증 끝. 작업 specifics를 `TaskSpec`(specs.py)으로 분리 → 엔진은 spec을 읽어 도는 제네릭 디스패처. 같은 `build_app`이 두 spec(`compare`/`ingest_demo`)을 그대로 돌려 도메인 무관 실증. 다음 = 미리 펼치지 말고 하나씩.

## 현 상태 (산출물, v0.5)
- 엔진(작업 지식 0): `orc/state.py`(initial_state(spec))·`orc/nodes.py`(step의 action/acceptance를 이름으로 디스패치)·`orc/orchestrator.py`(DIAGNOSIS를 spec에서 읽음).
- 경계: `orc/registry.py`(액션/검수기 등록), `orc/handlers.py`(등록 집결점).
- 작업 정의: `orc/specs.py` — `COMPARE`(실 LLM+검색) + `INGEST_DEMO`(결정적·키리스 로컬 적재 루프).
- 핸들러: `handlers_compare.py`·`handlers_ingest.py`·`handlers_common.py`.
- 검증(샌드박스, 키·네트워크 없이): `python -m orc.run compare`(OFFLINE) / `python -m orc.run ingest_demo` 둘 다 A=DONE / B=FAILED(차단기). 잔존 참조 0, 등록 무결성 확인.
- 부수효과: tool_not_allowed 차단경로를 `_offer_block`으로 정정(v0.4까진 verify가 덮어쓰던 미검증 버그).

## 방향 (합의 유지)
- **빠른 진입로 안 감. 기초를 탄탄히. 미리 펼치지 않음(하나씩).**
- 합류 목표(수렴 데모): ESS 배터리 열폭주 단계 예측(비전/멀티모달, 데이터=71918) + 기상(KMA) + 자료검색(RAG) + 보고서(LLM)를 orc/가 묶음.
- 서비스화·배포는 보류(상시 과금 — COST-MODEL.md).

## 정직한 한계 (과장 금지)
- 지금 실증한 것 = '설정 교체 = 다른 작업'(compare ↔ ingest_demo, 같은 엔진). 작업 지식이 코드에서 빠졌다는 증거.
- 아직 *아닌* 것 = 임의의 *워크플로 모양* 일반화. ESS는 더 다른 모양(비전 추론·기상·RAG·보고)이라 합류 단계에서 검증.
- `ingest_demo`는 실 GCS/다운로드가 아니라 로컬 파일 I/O(결정적). 실 적재 루프 흡수는 다음.

## 다음 작업 (하나씩, 기초부터 — 1번 끝났으니 다음 결정)
- 후보 A: 실 적재 루프 흡수 — `scripts/INGEST-AGENT.md`(이미 같은 Step→verify→DIAGNOSIS→유계재시도→차단기 골격)를 ingest_demo 핸들러를 실 다운로드/GCS로 교체해 LLM 없는 결정적 인스턴스로 흡수.
- 후보 B: 도구 감싸기 — 데이터/비전 세션 산출물을 MCP 도구로 감싸 새 spec으로 연결.
- 후보 C: 파일 지속성·관측성(LangSmith — 과금 복기 필요, COST-MODEL.md).
- (A/B/C 중 하나만 골라 진행. 미리 다 펼치지 않는다.)

## 작업 규칙
- 완료는 산출물로 판정. 근거 없는 동일 시도 반복 금지. 셸/코드 출력 이모지·특문 금지. 메모리 박제 승인제. 외래어·버즈워드 금지(평이한 한국어, 새 용어 즉시 정의).
