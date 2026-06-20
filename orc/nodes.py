"""L2 노드 5개 — PLAN/OFFER/TOOL/MEMORY/Verify. SPEC §3~§4.

작업 지식을 코드로 갖지 않는다. 현재 step의 spec(constraints.steps)을 읽어
레지스트리에서 액션·검수기를 *이름으로* 찾아 디스패치할 뿐이다. 작업이 바뀌어도
이 파일은 그대로다 — 바뀌는 건 spec과 handlers뿐.
"""
from .registry import get_action, get_checker
from .util import log, step_by_id


def plan_node(state) -> dict:
    """spec.steps로 plan을 만들거나(최초), 다음 pending step으로 전진."""
    steps = state["constraints"]["steps"]
    if not state["plan"]:
        plan = [{"step_id": s["step_id"], "subgoal": s["subgoal"], "priority": i + 1,
                 "depends_on": s["depends_on"], "status": "pending"}
                for i, s in enumerate(steps)]
        log(state, "PLAN", "build_plan", "ok", rout=f"{len(plan)} steps")
        return {"plan": plan, "cursor": plan[0]["step_id"]}
    cur = state["cursor"]
    nxt = next((s["step_id"] for s in state["plan"] if s["status"] == "pending"), None)
    log(state, "PLAN", "advance", "ok", rin=f"from {cur}", rout=f"to {nxt}")
    return {"cursor": nxt}


def offer_node(state) -> dict:
    """현재 step의 action을 정하고, 최소권한(requires_tool)을 constraints에 대조. SPEC §4.

    도구가 화이트리스트에 없으면 실행경로를 1차 차단(_offer_block) → TOOL은 건너뛰고
    Verify가 그 verdict를 그대로 통과시킨다.
    """
    cur = state["cursor"]
    step = step_by_id(state, cur)
    scratch = dict(state["scratch"])
    req = step.get("requires_tool")
    if req and req not in state["constraints"]["allowed_tools"]:
        scratch["_offer_block"] = {"passed": False, "cause": "tool_not_allowed"}
        log(state, "OFFER", "reject_tool", "fail", cause="tool_not_allowed", rin=cur)
        return {"scratch": scratch}
    scratch["action"] = {"type": step["action"]}
    log(state, "OFFER", f"decide:{step['action']}", "ok", rin=cur)
    return {"scratch": scratch}


async def tool_node(state) -> dict:
    """현재 action 이름으로 핸들러를 디스패치(부작용 경계). SPEC §3 TOOL."""
    if state["scratch"].get("_offer_block"):           # OFFER가 차단 → 도구 실행 안 함
        return {}
    t = state["scratch"].get("action", {}).get("type")
    if not t:
        return {}
    artifacts = dict(state["artifacts"])
    await get_action(t)(state, artifacts)
    return {"artifacts": artifacts}


def memory_node(state) -> dict:
    b = dict(state["budget"])
    b["iter"] += 1
    log(state, "MEMORY", "checkpoint", "ok", rout=f"iter={b['iter']}")
    return {"budget": b}


def verify_node(state) -> dict:
    """현재 step의 acceptance.kind로 검수기를 디스패치 → verdict. SPEC §6."""
    blk = state["scratch"].get("_offer_block")
    if blk:                                            # OFFER 차단 verdict를 그대로 통과
        scratch = dict(state["scratch"])
        scratch.pop("_offer_block", None)
        log(state, "Verify", "verify:blocked", "fail", cause=blk["cause"])
        return {"verdict": blk, "scratch": scratch}
    cur = state["cursor"]
    acc = step_by_id(state, cur)["acceptance"]
    v = get_checker(acc["kind"])(state, acc)
    log(state, "Verify", f"verify:{cur}", "ok" if v["passed"] else "fail", cause=v["cause"])
    return {"verdict": v}
