"""핸들러 등록 집결점 — 이 모듈을 import하면 모든 액션/검수기가 레지스트리에 등록된다.

엔진(orchestrator)이 이걸 import해 그래프 실행 전 등록을 보장한다. 새 작업의
handlers 모듈을 만들면 여기 한 줄 추가하면 된다.
"""
from . import handlers_common   # noqa: F401  (등록 트리거)
from . import handlers_compare  # noqa: F401
from . import handlers_ingest   # noqa: F401
