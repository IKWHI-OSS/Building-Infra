# 체크포인트 — 인프라(오케스트레이터) 세션 · 2026-06-19

> 다음 세션 시작 시 이 블록을 붙여 깨끗한 컨텍스트에서 이어간다.

---

[인프라 — 이어서]
부팅: CLAUDE.md → SOUL/LOOP/MEMORY/USER. 이어서 `constgx/agents/SPEC.md`, `constgx/agents/orc/README.md` 읽기.

## 한 줄
orc/ 패키지(v0.4) 완성·검증 끝(실 LLM + 실 MCP 웹검색 e2e). 다음 = **조급하게 5단계 달리지 말고 기초부터.** 첫 걸음 = '범용화(설정화)'로 한 엔진이 여러 작업을 돌게 만들기.

## 현 상태 (산출물)
- `constgx/agents/orc/` : state·llm·mcp_tools·nodes·orchestrator·run·util + README. `python -m orc.run` 동등성 검증(A=DONE / B=차단기 FAILED). 실 LLM + 실 웹검색 e2e 통과.
- `mcp_model_tool.py`(웹검색 MCP 서버), `setup_env.sh`+`requirements-lock.txt`(격리 venv), `COST-MODEL.md`, `RUNBOOK-real-llm.md`.

## 방향 (합의)
- **빠른 진입로 안 감. 기초를 탄탄히.** 계획을 늘어놓지 않는다(컨텍스트 오염 방지).
- 합류 목표(수렴 데모): ESS 배터리 열폭주 단계 예측(비전/멀티모달, 데이터=71918) + 기상(KMA API) + 자료검색(RAG) + 보고서(LLM)를 orc/가 묶음.
- 인프라 성숙 중 지금 필요한 최소선 = 범용화 + 실 도구 2~3개 + 파일 지속성 + 관측성. **서비스화·배포는 보류**(상시 과금 — COST-MODEL.md).

## 다음 작업 (하나씩, 기초부터)
1. **범용화:** 작업 specifics(goal·targets·criteria·allowed_tools·acceptance)를 코드에서 분리해 **설정/인자로 받게** 한다. → '모델 비교' 작업과 'ESS' 작업이 **같은 엔진**에서 돌면, 그 자체가 도메인 무관의 증거(추상 일반화보다 확실).
- 이후 단계(도구 감싸기·지속성·관측성)는 1번이 끝난 뒤 결정. 미리 펼치지 않음.

## 합류
- 데이터 세션(71918→GCS)·비전 세션(모델 추론)이 끝나면, 그 산출물을 **MCP 도구로 감싸** orc/에 연결.

## 작업 규칙
- 완료는 산출물로 판정. 근거 없는 동일 시도 반복 금지. 셸/코드 출력 이모지·특문 금지. 메모리 박제 승인제. **외래어·버즈워드 금지(평이한 한국어로, 새 용어는 즉시 정의).**
