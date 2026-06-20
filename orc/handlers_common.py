"""작업 무관 공용 검수기 — 여러 spec이 공유한다. SPEC §6(구조검증).

결정적(LLM 안 씀)이라 어느 작업에든 붙는다.
"""
from .registry import acceptance


@acceptance("artifact_non_empty")
def _non_empty(state, acc):
    """artifacts[key]가 truthy면 통과."""
    ok = bool(state["artifacts"].get(acc["key"]))
    return {"passed": ok, "cause": None if ok else acc["cause"]}


@acceptance("flag_true")
def _flag_true(state, acc):
    """artifacts[key](불리언 플래그)가 True면 통과. False=명시적 실패."""
    ok = state["artifacts"].get(acc["key"]) is True
    return {"passed": ok, "cause": None if ok else acc["cause"]}
