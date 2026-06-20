"""공용 유틸 — 시간/히스토리 로깅 + spec 조회/의도적 실패 주입."""
import os
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


def step_by_id(state, step_id) -> dict:
    """현재 spec의 step 정의(dict)를 step_id로 조회. constraints.steps는 spec에서 옴."""
    for s in state["constraints"]["steps"]:
        if s["step_id"] == step_id:
            return s
    raise KeyError(f"미정의 step: {step_id}")


def inject_fault(state, step) -> bool:
    """이 시도를 의도적으로 실패시킬지 결정(차단기/회복 데모용).

    - 환경변수 FORCE_FAIL_STEP == step_id 이면 항상 실패(차단기 데모).
    - step.fault.first_attempt_fails 이면 corrective 플래그가 scratch에 설정되기 전
      (= 첫 시도)에만 실패하고, 보정 후 재시도는 성공(회복 데모).
    엔진이 아니라 핸들러가 호출한다 — '어떻게 실패하는가'는 작업 지식이기 때문.
    """
    if os.environ.get("FORCE_FAIL_STEP") == step["step_id"]:
        return True
    f = step.get("fault")
    if f and f.get("first_attempt_fails"):
        corrective = f.get("corrective")
        retrying = bool(state["scratch"].get(corrective)) if corrective else False
        return not retrying
    return False
