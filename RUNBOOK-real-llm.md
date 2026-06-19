# 런북 — 실 LLM 켜고 품질 확인 (맥 + 주피터)

> 목표: `orchestrator_slice.ipynb`를 스텁이 아닌 **실제 Claude 추론**으로 돌려 s3 차이분석·s4 요약·judge 품질을 본다.
> 비용은 작다: 시나리오 A만 LLM을 부르고(compare 1 + summarize 1 + judge 1 ≈ 3회 호출), B(차단기)는 s2 구조검증에서 멈춰 LLM을 아예 안 부른다.

## 0. 파일 위치
`orchestrator_slice.ipynb`와 `mcp_model_tool.py`가 **같은 폴더**(이 `agents/`)에 있어야 한다. 노트북이 MCP 서버를 상대경로로 띄운다.

## 1. 환경 셋업 — 격리 venv 1회 (pydantic 충돌 방지)
시스템 파이썬에 바로 설치하면 기존 pydantic 등과 충돌한다(`ImportError: InvalidSchemaError` 류). **격리된 venv를 한 번 만들고 끝낸다.** 터미널에서 이 폴더로 가서:
```
cd /Users/karla/Documents/constgx/agents
bash setup_env.sh
```
이게 `.venv`를 만들고 **검증된 버전(`requirements-lock.txt`)**을 설치한 뒤 주피터 커널 `Python (orc-poc)`을 등록한다(샌드박스에서 동시 import 검증된 조합).

그다음 주피터에서:
1. `orchestrator_slice.ipynb` 열기
2. 우상단 **커널을 `Python (orc-poc)`로 변경**
3. 첫 셀의 `%pip` 줄은 **실행하지 말 것**(이미 설치됨) → 바로 Run All

> MCP 서버는 노트북이 자동으로 서브프로세스로 띄운다(당신이 `mcp_model_tool.py`를 따로 실행하지 않는다). 서버는 커널과 같은 파이썬(`sys.executable`)으로 뜨므로 `mcp`·`ddgs`도 그 venv 것을 쓴다.
>
> **셀 번호가 In[25]처럼 큰 건 정상** — "몇 번째 칸"이 아니라 그 커널의 누적 실행 횟수다. Kernel→Restart 하면 In[1]부터 리셋.

## 2. API 키 — export 안 함. `.env`에서 자동 로드
키는 이미 `/Users/karla/Documents/constgx/scripts/.env`에 `CLAUDE_KEY=...`로 있고, `.gitignore`가 `.env`를 막아 git에 안 올라간다. **터미널 export도, 노트북에 키 적기도 안 한다.**

노트북 첫 코드 셀이 `python-dotenv`로 그 `.env`를 직접 읽어 `os.environ`에 올린다 → 키가 셸 히스토리·화면·노트북 파일 어디에도 안 남는다. 코드는 `CLAUDE_KEY`(없으면 `ANTHROPIC_API_KEY`)를 읽어 `ChatAnthropic(api_key=...)`에 명시 전달한다.

확인: 첫 셀 실행 후 출력이 `CLAUDE_KEY 로드됨: True`면 정상. `False`면 `.env` 경로(`ENV_PATH`)나 변수명을 확인.
> 참고: 일단 로드되면 `ps eww`로 본인 프로세스 env에서 키가 보이는 건 env 변수의 본질이라 어떤 방식이든 동일하다(SDK가 메모리에 키를 가져야 호출 가능). `.env` 로드는 그 외의 *추가* 노출(히스토리·화면·파일)을 없애는 것.

## 3. 오프라인 스위치 OFF 확인
첫 코드 셀의 두 줄이 **주석 처리(꺼짐)** 상태여야 실 LLM + 실 웹검색이 돈다:
```
# os.environ["SLICE_OFFLINE"] = "1"   # LLM 스텁 — 주석 그대로 두기
# os.environ["MCP_OFFLINE"]   = "1"   # 검색 고정 — 주석 그대로 두기
```
(네트워크 없는 곳에서 배선만 보려면 둘 다 주석 해제.)

## 4. 전체 실행
위에서부터 모든 셀 실행 (메뉴 Run > Run All Cells). 시나리오 A 출력의 다음 줄을 본다:
- `[TOOL] compare` → `artifacts["analysis"]` = 실제 모델 비교 분석
- `[TOOL] summarize` → `summary` = 용도별 추천 + 출처 표기
- `[Verify] verify:s4` → judge가 PASS/FAIL 판정

## 5. 품질 확인 포인트
- TOOL 로그에 `web_search ... via MCP`가 찍히고, A 끝의 `출처(real URL)`가 **실제 접속 가능한 외부 URL**인가? (mock 아님을 확인)
- 차이분석이 4개 기준(mAP·FPS·train_cost·deploy_difficulty)을 **다 다뤘는가**? (스니펫에 없으면 '자료없음'이라 나옴)
- 요약에 **출처 URL이 괄호로** 붙었는가?
- judge가 PASS면 → acceptance(전 기준 커버·출처 존재) 충족.

> 웹검색 품질은 스니펫에 좌우된다 — 숫자가 스니펫에 안 잡히면 '자료없음'이 정상이다(조작이 아니라 실제 검색의 한계). 정확도가 필요하면 런북 끝의 Tavily 승급 참고.

## 6. 결과 공유
A 시나리오의 `summary`와 `analysis` 출력을 그대로 복사해 채팅에 붙여주면, 프롬프트(`SYS` 딕셔너리)를 보고 품질을 같이 다듬는다.

## 막히면
- `model not found`/`404` → 노트북 첫 셀에 `os.environ["SLICE_MODEL"]="<접근가능한 모델ID>"` 추가 후 재실행. (기본값 `claude-sonnet-4-6`)
- 첫 셀이 `CLAUDE_KEY 로드됨: False` → `.env` 경로(`ENV_PATH`)가 맞는지, `.env` 안 변수명이 `CLAUDE_KEY`인지 확인.
- 인증 401 → `.env`의 `CLAUDE_KEY` 값이 유효한지 확인(따옴표 포함 저장돼 있어도 dotenv가 벗겨줌).
- `ModuleNotFoundError: langchain_anthropic` → 1단계를 주피터 커널과 같은 환경에서 다시.
