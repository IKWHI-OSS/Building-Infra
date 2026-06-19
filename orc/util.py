"""공용 유틸 — 시간/히스토리 로깅."""
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(state, actor, action, status, cause=None, rin="", rout=""):
    """AgentContext.history에 digest 한 줄 추가(원문 아님 — 컨텍스트 희석 방지)."""
    state["history"].append({
        "t": now(), "actor": actor, "action": action,
        "input_digest": rin, "result_digest": rout,
        "status": status, "cause": cause,
    })
