"""비교·분석 작업 핸들러 — 실 LLM + 실 웹검색(MCP). SPEC §6, COMPARE spec.

액션: define/extract/compare/summarize. 검수기: all_targets_sourced/llm_judge.
모두 import 시점에 레지스트리에 등록된다.
"""
from .registry import action, acceptance
from .llm import llm_call
from .mcp_tools import mcp_search
from .util import log, step_by_id, inject_fault


@action("define")
async def _define(state, artifacts):
    crit = state["constraints"]["definition"]["criteria"]
    artifacts["criteria"] = crit
    log(state, "TOOL", "define", "ok", rout=str(crit))


@action("extract")
async def _extract(state, artifacts):
    targets = state["constraints"]["definition"]["targets"]
    step = step_by_id(state, state["cursor"])
    fail_target = targets[-1] if inject_fault(state, step) else None   # 의도적 실패: 한 대상 검색실패
    specs = {}
    for m in targets:
        if m == fail_target:
            specs[m] = {"model": m, "snippets": [], "sources": []}
        else:
            specs[m] = await mcp_search(m)                              # 실 MCP 웹검색
    artifacts["specs"] = specs
    got = sum(1 for s in specs.values() if s.get("sources"))
    log(state, "TOOL", "web_search", "ok", rout=f"{got}/{len(specs)} targets via MCP")


@action("compare")
async def _compare(state, artifacts):
    artifacts["analysis"] = llm_call("compare", {
        "criteria": state["constraints"]["definition"]["criteria"],
        "specs": artifacts.get("specs", {})})
    log(state, "TOOL", "compare", "ok")


@action("summarize")
async def _summarize(state, artifacts):
    artifacts["summary"] = llm_call("summarize", {
        "analysis": artifacts.get("analysis", ""),
        "specs": artifacts.get("specs", {})})
    log(state, "TOOL", "summarize", "ok")


@acceptance("all_targets_sourced")
def _all_sourced(state, acc):
    """전 대상이 스니펫+출처를 가졌는지(구조검증, 결정적)."""
    targets = state["constraints"]["definition"]["targets"]
    specs = state["artifacts"].get("specs", {})
    ok = all(specs.get(m, {}).get("snippets") and specs.get(m, {}).get("sources") for m in targets)
    return {"passed": ok, "cause": None if ok else acc["cause"]}


@acceptance("llm_judge")
def _judge(state, acc):
    """최종 요약을 LLM-judge로 검수(전 기준 언급 + 출처 표기). SPEC §6 s4."""
    art = state["artifacts"]
    crit = state["constraints"]["definition"]["criteria"]
    sources = [s for sp in art.get("specs", {}).values() for s in sp.get("sources", [])]
    judge = llm_call("judge", {"summary": art.get("summary", ""), "criteria": crit, "sources": sources})
    ok = judge.strip().upper().startswith("PASS")
    return {"passed": ok, "cause": None if ok else acc["cause"], "detail": judge[:300]}
