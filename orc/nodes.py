"""L2 노드 5개 — PLAN/OFFER/TOOL/MEMORY/Verify. SPEC §3~§4.

모두 (state) -> dict(부분 갱신). TOOL은 async(MCP 호출).
"""
import os
from .state import STEP_ORDER
from .llm import llm_call
from .mcp_tools import mcp_search
from .util import log


def plan_node(state) -> dict:
    if not state["plan"]:
        crit = state["constraints"]["definition"]["criteria"]
        plan = [
            {"step_id": "s1", "subgoal": "비교기준 정의", "priority": 1, "depends_on": [], "status": "pending"},
            {"step_id": "s2", "subgoal": "대상별 웹검색(fan-out)", "priority": 2, "depends_on": ["s1"], "status": "pending"},
            {"step_id": "s3", "subgoal": "차이분석", "priority": 3, "depends_on": ["s2"], "status": "pending"},
            {"step_id": "s4", "subgoal": "결과요약", "priority": 4, "depends_on": ["s3"], "status": "pending"},
        ]
        log(state, "PLAN", "build_plan", "ok", rout=f"{len(plan)} steps, criteria={crit}")
        return {"plan": plan, "cursor": "s1"}
    cur = state["cursor"]
    nxt = next((s["step_id"] for s in state["plan"] if s["status"] == "pending"), None)
    log(state, "PLAN", "advance", "ok", rin=f"from {cur}", rout=f"to {nxt}")
    return {"cursor": nxt}


def offer_node(state) -> dict:
    cur = state["cursor"]
    targets = state["constraints"]["definition"]["targets"]
    scratch = dict(state["scratch"])
    if cur == "s1":
        scratch["action"] = {"type": "define", "criteria": state["constraints"]["definition"]["criteria"]}
    elif cur == "s2":
        if "web_search_specs" not in state["constraints"]["allowed_tools"]:
            log(state, "OFFER", "reject_tool", "fail", cause="tool_not_allowed")
            return {"scratch": scratch, "verdict": {"passed": False, "cause": "tool_not_allowed"}}
        retrying = scratch.get("s2_retry", False)
        force = os.environ.get("FORCE_S2_FAIL") == "1"   # 차단기 데모: 항상 실패
        broken = force or not retrying                    # 첫 시도 한 대상 검색실패(+force면 영구)
        scratch["action"] = {"type": "extract", "targets": targets,
                             "fail_target": (targets[-1] if broken else None)}
    elif cur == "s3":
        scratch["action"] = {"type": "compare"}
    elif cur == "s4":
        scratch["action"] = {"type": "summarize"}
    log(state, "OFFER", f"decide:{scratch['action']['type']}", "ok", rin=cur)
    return {"scratch": scratch}


async def tool_node(state) -> dict:
    act = state["scratch"].get("action", {})
    artifacts = dict(state["artifacts"])
    t = act.get("type")
    if t == "define":
        artifacts["criteria"] = act["criteria"]
        log(state, "TOOL", "define", "ok", rout=str(act["criteria"]))
    elif t == "extract":
        specs = {}
        for m in act["targets"]:
            if act.get("fail_target") == m:                      # 의도적 실패: 빈 결과
                specs[m] = {"model": m, "snippets": [], "sources": []}
            else:
                specs[m] = await mcp_search(m)                    # 실 MCP 웹검색
        artifacts["specs"] = specs
        got = sum(1 for s in specs.values() if s.get("sources"))
        log(state, "TOOL", "web_search", "ok", rout=f"{got}/{len(specs)} targets via MCP")
    elif t == "compare":
        artifacts["analysis"] = llm_call("compare", {
            "criteria": state["constraints"]["definition"]["criteria"],
            "specs": state["artifacts"].get("specs", {})})
        log(state, "TOOL", "compare", "ok")
    elif t == "summarize":
        artifacts["summary"] = llm_call("summarize", {
            "analysis": state["artifacts"].get("analysis", ""),
            "specs": state["artifacts"].get("specs", {})})
        log(state, "TOOL", "summarize", "ok")
    return {"artifacts": artifacts}


def memory_node(state) -> dict:
    b = dict(state["budget"])
    b["iter"] += 1
    log(state, "MEMORY", "checkpoint", "ok", rout=f"iter={b['iter']}")
    return {"budget": b}


def verify_node(state) -> dict:
    cur = state["cursor"]
    crit = state["constraints"]["definition"]["criteria"]
    targets = state["constraints"]["definition"]["targets"]
    art = state["artifacts"]
    if cur == "s1":
        v = {"passed": bool(art.get("criteria")), "cause": None if art.get("criteria") else "empty_criteria"}
    elif cur == "s2":
        specs = art.get("specs", {})
        ok = all(specs.get(m, {}).get("snippets") and specs.get(m, {}).get("sources") for m in targets)
        v = {"passed": ok, "cause": None if ok else "missing_source"}
    elif cur == "s3":
        v = {"passed": bool(art.get("analysis")), "cause": None if art.get("analysis") else "no_analysis"}
    elif cur == "s4":
        sources = [s for sp in art.get("specs", {}).values() for s in sp.get("sources", [])]
        judge = llm_call("judge", {"summary": art.get("summary", ""), "criteria": crit, "sources": sources})
        ok = judge.strip().upper().startswith("PASS")
        v = {"passed": ok, "cause": None if ok else "judge_reject", "detail": judge[:300]}
    else:
        v = {"passed": False, "cause": "unknown_step"}
    log(state, "Verify", f"verify:{cur}", "ok" if v["passed"] else "fail", cause=v["cause"])
    return {"verdict": v}
