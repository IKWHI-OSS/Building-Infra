"""CLI 진입점 — 노트북 밖이라 asyncio.run 래퍼로 실행.

사용:  (agents/ 폴더에서)  python -m orc.run
환경:  실 LLM/검색 = .env의 CLAUDE_KEY + 네트워크.  배선만 = SLICE_OFFLINE=1 MCP_OFFLINE=1
"""
import os
import asyncio
from pathlib import Path

# .env 자동 로드 (노트북과 동일). agents/orc/run.py -> constgx/scripts/.env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / "scripts" / ".env")
except Exception:
    pass

from .orchestrator import build_app
from .state import initial_state


async def run(tag: str, thread_id: str):
    app = await build_app()
    cfg = {"recursion_limit": 100, "configurable": {"thread_id": thread_id}}
    final = await app.ainvoke(initial_state(), config=cfg)

    print(f"\n===== {tag} =====")
    for h in final["history"]:
        cause = f" cause={h['cause']}" if h["cause"] else ""
        extra = f" :: {h['result_digest']}" if h["result_digest"] else ""
        print(f"  [{h['actor']:<6}] {h['action']:<16} {h['status']}{cause}{extra}")
    status = final["scratch"].get("_status", "DONE")
    print(f"  --- status={status} iter={final['budget']['iter']} "
          f"retry_left={final['budget']['retry']} consec_fail={final['budget']['consec_fail']}")
    specs = final["artifacts"].get("specs", {})
    if specs:
        print("  --- 출처(real URL):")
        for m, sp in specs.items():
            print(f"        {m}: {sp.get('sources', [])[:2]}")
    if final["artifacts"].get("summary"):
        print(f"  --- summary: {final['artifacts']['summary']}")
    v = final.get("verdict")
    if status == "FAILED" and v and v.get("detail"):
        print(f"  --- 실패사유(judge): {v['detail']}")
    print("  --- plan:", {s["step_id"]: s["status"] for s in final["plan"]})
    return final


async def _main():
    await run("A. happy path", "slice-A")
    os.environ["FORCE_S2_FAIL"] = "1"          # 차단기 데모
    await run("B. circuit breaker", "slice-B")
    os.environ.pop("FORCE_S2_FAIL", None)


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()
