"""State schema = AgentContext (단일 진실 객체) + 초기 상태 빌더. SPEC §2.

작업 specifics는 코드에 없다 — initial_state(spec)가 TaskSpec을 받아 채운다(범용화).
"""
from typing import TypedDict, Literal, Optional, Any
from typing_extensions import NotRequired


class PlanStep(TypedDict):
    step_id: str
    subgoal: str
    priority: int
    depends_on: list[str]
    status: Literal["pending", "running", "done", "failed"]


class Constraints(TypedDict):
    definition: dict[str, Any]      # 도메인 데이터(criteria·targets·items ...) — spec에서
    allowed_tools: list[str]        # 최소권한 화이트리스트
    forbidden: list[str]            # 안전필터(rm -rf, DROP TABLE ...)
    steps: list[dict[str, Any]]     # 워크플로 정의(step별 action·acceptance) — spec에서
    diagnosis: dict[str, list]      # 원인코드 -> [retriable?, corrective] — spec에서
    acceptance: dict[str, Any]      # 보고용 요약(하위호환)


class HistoryEntry(TypedDict):
    t: str
    actor: Literal["ORC", "PLAN", "OFFER", "TOOL", "MEMORY", "Verify"]
    action: str
    input_digest: str
    result_digest: str
    status: Literal["ok", "fail"]
    cause: Optional[str]


class Budget(TypedDict):
    iter: int
    max_iter: int
    retry: int
    consec_fail: int
    fail_threshold: int


class Verdict(TypedDict):
    passed: bool
    cause: Optional[str]
    detail: NotRequired[str]


class AgentContext(TypedDict):
    goal: str
    constraints: Constraints
    plan: list[PlanStep]
    cursor: Optional[str]
    artifacts: dict[str, Any]
    scratch: dict[str, Any]
    history: list[HistoryEntry]
    budget: Budget
    verdict: Optional[Verdict]


def initial_state(spec) -> AgentContext:
    """TaskSpec을 받아 초기 AgentContext를 만든다. 작업 지식은 전부 spec에서 온다."""
    return {
        "goal": spec.goal,
        "constraints": spec.to_constraints(),
        "plan": [], "cursor": None, "artifacts": {}, "scratch": {},
        "history": [], "verdict": None,
        "budget": {"iter": 0, "max_iter": 12, "retry": 3,
                   "consec_fail": 0, "fail_threshold": 3},
    }
