"""State schema = AgentContext (단일 진실 객체) + 초기 상태 빌더. SPEC §2."""
from typing import TypedDict, Literal, Optional, Any
from typing_extensions import NotRequired

STEP_ORDER = ["s1", "s2", "s3", "s4"]


class PlanStep(TypedDict):
    step_id: str
    subgoal: str
    priority: int
    depends_on: list[str]
    status: Literal["pending", "running", "done", "failed"]


class Constraints(TypedDict):
    definition: dict[str, Any]      # 비교기준/대상 등 초기 정의
    allowed_tools: list[str]        # 최소권한 화이트리스트
    forbidden: list[str]            # 안전필터(rm -rf, DROP TABLE ...)
    acceptance: dict[str, Any]      # 완결성 기준


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


def initial_state() -> AgentContext:
    """비교·분석 워크플로의 초기 AgentContext."""
    return {
        "goal": "건설자재 객체탐지 모델 후보 3종(Faster R-CNN/YOLOv8/RT-DETR)을 비교하라",
        "constraints": {
            "definition": {
                "criteria": ["mAP", "FPS", "train_cost", "deploy_difficulty"],
                "targets": ["Faster R-CNN", "YOLOv8", "RT-DETR"],
            },
            "allowed_tools": ["web_search_specs"],
            "forbidden": ["rm -rf", "DROP TABLE"],
            "acceptance": {"final": ["all_criteria_covered", "sources_present"]},
        },
        "plan": [], "cursor": None, "artifacts": {}, "scratch": {},
        "history": [], "verdict": None,
        "budget": {"iter": 0, "max_iter": 12, "retry": 3,
                   "consec_fail": 0, "fail_threshold": 3},
    }
