"""CLI 진입점 — 노트북 밖이라 asyncio.run 래퍼로 실행.

사용:  (agents/ 폴더에서)
  python -m orc.run                  # 기본 spec=compare (실 LLM+실 검색)
  python -m orc.run ingest_demo      # 결정적 spec (키·네트워크 불필요)
  SLICE_OFFLINE=1 MCP_OFFLINE=1 python -m orc.run            # 비교 배선만(키 없이)

같은 build_app(엔진)이 어떤 spec이든 받아 돈다 — 그게 도메인 무관의 증거.
"""
import os
import sys
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
from .specs import get_spec


async def run(spec, tag: str, thread_id: str):
    app = await build_app()
    cfg = {"recursion_limit": 100, "configurable": {"thread_id": thread_id}}
    final = await app.ainvoke(initial_state(spec), config=cfg)

    print(f"\n===== {tag} =====")
    for h in final["history"]:
        cause = f" cause={h['cause']}" if h["cause"] else ""
        extra = f" :: {h['result_digest']}" if h["result_digest"] else ""
        print(f"  [{h['actor']:<6}] {h['action']:<16} {h['status']}{cause}{extra}")
    status = final["scratch"].get("_status", "DONE")
    print(f"  --- status={status} iter={final['budget']['iter']} "
          f"retry_left={final['budget']['retry']} consec_fail={final['budget']['consec_fail']}")
    art = final["artifacts"]
    specs = art.get("specs", {})
    if specs:
        print("  --- 출처(real URL):")
        for m, sp in specs.items():
            print(f"        {m}: {sp.get('sources', [])[:2]}")
    if art.get("summary"):
        print(f"  --- summary: {art['summary']}")
    if art.get("answer"):
        print(f"  --- answer: {art['answer']}")
    if art.get("stored"):
        for it, s in art["stored"].items():
            print(f"  --- stored {it}: size={s['size']} (expected {s['expected_size']})")
    v = final.get("verdict")
    if status == "FAILED" and v and v.get("detail"):
        print(f"  --- 실패사유: {v['detail']}")
    print("  --- plan:", {s["step_id"]: s["status"] for s in final["plan"]})
    return final


def _fault_step(spec) -> str:
    """차단기 데모용 — 의도적 실패를 선언한 step_id(없으면 None)."""
    for s in spec.steps:
        if s.fault:
            return s.step_id
    return None


async def _main():
    name = sys.argv[1] if len(sys.argv) > 1 else "compare"
    spec = get_spec(name)
    await run(spec, f"A. {name} happy path", f"{name}-A")

    fstep = _fault_step(spec)
    if fstep:
        os.environ["FORCE_FAIL_STEP"] = fstep          # 해당 step 영구 실패 → 차단기
        await run(spec, f"B. {name} circuit breaker", f"{name}-B")
        os.environ.pop("FORCE_FAIL_STEP", None)


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()
