"""ORC(순수 라우터) + DIAGNOSIS + 그래프 조립. SPEC §5·§7.

ORC는 LLM을 안 쓴다. 모든 예산·verdict 기록을 ORC가 소유하고 결정을
scratch["_route"]에 적재 → route()는 읽기만.
"""
import aiosqlite
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.memory import InMemoryStore

from .state import AgentContext, STEP_ORDER
from .util import log
from .nodes import plan_node, offer_node, tool_node, memory_node, verify_node

# 원인코드 -> (retriable?, corrective)
DIAGNOSIS = {
    "missing_source":   (True, "s2_retry"),
    "no_analysis":      (True, None),
    "judge_reject":     (True, None),
    "tool_not_allowed": (False, None),
}


def _retriable(v) -> bool:
    return DIAGNOSIS.get(v.get("cause"), (False, None))[0]


def _is_last_step(state) -> bool:
    return state["cursor"] == STEP_ORDER[-1]


def orc_node(state) -> dict:
    v = state["verdict"]
    b = dict(state["budget"])
    scratch = dict(state["scratch"])

    if v is None:                                   # 최초 진입 → 계획
        scratch["_route"] = "PLAN"
        return {"scratch": scratch}

    if v["passed"]:                                 # 통과 → 현 step done + 연속실패 리셋
        b["consec_fail"] = 0
        plan = [dict(s) for s in state["plan"]]
        for s in plan:
            if s["step_id"] == state["cursor"]:
                s["status"] = "done"
        scratch["_route"] = "END" if _is_last_step(state) else "PLAN"
        log(state, "ORC", "route:pass", "ok", rin=str(state["cursor"]), rout=scratch["_route"])
        return {"budget": b, "verdict": None, "scratch": scratch, "plan": plan}

    if b["consec_fail"] >= b["fail_threshold"] or b["retry"] <= 0:   # 차단기/예산소진
        scratch["_route"] = "FAIL"
        scratch["_status"] = "FAILED"
        log(state, "ORC", "route:halt", "fail", cause=v["cause"], rout="FAIL")
        return {"budget": b, "scratch": scratch}

    b["retry"] -= 1                                 # 유계 재시도
    b["consec_fail"] += 1
    retriable, corrective = DIAGNOSIS.get(v["cause"], (False, None))
    if retriable:
        if corrective:
            scratch[corrective] = True
        scratch["_route"] = "OFFER"
    else:
        scratch["_route"] = "PLAN"
    log(state, "ORC", "route:retry", "ok", rin=f"cause={v['cause']}",
        rout=f"{scratch['_route']} retry={b['retry']} consec={b['consec_fail']}")
    return {"budget": b, "verdict": None, "scratch": scratch}


def route(state) -> str:
    return state["scratch"]["_route"]


async def build_app():
    """그래프 조립 + checkpointer(AsyncSqliteSaver)/Store. async(aiosqlite 연결)."""
    g = StateGraph(AgentContext)
    for name, fn in [("ORC", orc_node), ("PLAN", plan_node), ("OFFER", offer_node),
                     ("TOOL", tool_node), ("MEMORY", memory_node), ("VERIFY", verify_node)]:
        g.add_node(name, fn)
    g.add_edge(START, "ORC")
    g.add_conditional_edges("ORC", route, {"PLAN": "PLAN", "OFFER": "OFFER", "END": END, "FAIL": END})
    g.add_edge("PLAN", "OFFER")
    g.add_edge("OFFER", "TOOL")
    g.add_edge("TOOL", "MEMORY")
    g.add_edge("MEMORY", "VERIFY")
    g.add_edge("VERIFY", "ORC")
    conn = await aiosqlite.connect(":memory:")
    return g.compile(checkpointer=AsyncSqliteSaver(conn), store=InMemoryStore())
