# orc — 멀티에이전트 오케스트레이터 (모듈판)

노트북 `../orchestrator_slice.ipynb`의 .py 졸업판. 설계 정본 = `../SPEC.md`.
ORC(순수 라우터) + 5노드(PLAN/OFFER/TOOL/MEMORY/Verify) 상태기계.

## 모듈 구성
```
orc/
├── __init__.py
├── state.py          # AgentContext(TypedDict) + initial_state()  (§2)
├── llm.py            # SYS 프롬프트 + llm_call (실 LLM / SLICE_OFFLINE 스텁)  (§6)
├── mcp_tools.py      # 웹검색 MCP 서버 호출(mcp_search, async)  (§1·결정2)
├── nodes.py          # plan/offer/tool(async)/memory/verify  (§3·§4)
├── orchestrator.py   # DIAGNOSIS + orc_node + route + build_app  (§5·§7)
└── run.py            # CLI 진입점(asyncio.run 래퍼) + 시나리오 A/B
../mcp_model_tool.py  # 별도 프로세스로 뜨는 MCP 서버(노트북·모듈 공용)
```

## 실행
agents/ 폴더(이 패키지의 상위)에서:
```
# 실 LLM + 실 웹검색 (run.py가 ../scripts/.env의 CLAUDE_KEY 자동 로드)
python -m orc.run

# 배선/라우팅/차단기만 (네트워크·키 불필요)
SLICE_OFFLINE=1 MCP_OFFLINE=1 python -m orc.run
```
출력: 시나리오 A(happy path, DONE)와 B(차단기, FAILED).

## Cursor에서
1. `constgx/`(또는 `agents/`)를 Cursor로 연다.
2. 인터프리터를 `agents/.venv`(setup_env.sh가 만든 격리 환경)로 선택.
3. `orc/run.py`를 실행하거나 터미널에서 `python -m orc.run`.
4. 노트북은 인터랙티브 프로토타입으로 유지 — 로직 변경은 모듈에 하고 노트북은 모듈을 import하도록 점진 전환 가능.

## 다음 개선 후보
- 검색 쿼리를 criteria로부터 동적 구성(train_cost/deploy_difficulty 반영).
- TOOL 결과 캐싱, 모델 계층화(무거운 추론만 대형 LLM), LangSmith 트레이싱(→ COST-MODEL.md 복기).
