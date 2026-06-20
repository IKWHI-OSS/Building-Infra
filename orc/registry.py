"""액션/검수 디스패치 레지스트리 — 엔진과 작업 지식의 경계.

엔진(nodes.tool_node / verify_node)은 작업이 무엇인지 모른다. 그저 현재 step의
spec이 지정한 *이름*으로 핸들러를 찾아 실행할 뿐이다.

- ACTION_HANDLERS[name]   : async (state, artifacts) -> None  (artifacts를 제자리 갱신)
- ACCEPTANCE_CHECKERS[k]  : (state, acc) -> Verdict dict       (수락 여부 판정)

작업별 핸들러/검수기는 handlers_*.py가 import 시점에 등록한다. 새 작업을 추가하려면
새 handlers 모듈을 만들어 등록하고 spec에서 그 이름을 참조하면 된다(엔진 수정 0).
"""

ACTION_HANDLERS = {}        # name -> async fn(state, artifacts)
ACCEPTANCE_CHECKERS = {}    # kind -> fn(state, acc) -> verdict dict


def action(name):
    """액션 핸들러 등록 데코레이터."""
    def deco(fn):
        if name in ACTION_HANDLERS:
            raise ValueError(f"중복 액션 등록: {name}")
        ACTION_HANDLERS[name] = fn
        return fn
    return deco


def acceptance(kind):
    """수락기준 검수기 등록 데코레이터."""
    def deco(fn):
        if kind in ACCEPTANCE_CHECKERS:
            raise ValueError(f"중복 검수기 등록: {kind}")
        ACCEPTANCE_CHECKERS[kind] = fn
        return fn
    return deco


def get_action(name):
    if name not in ACTION_HANDLERS:
        raise KeyError(f"미등록 액션: {name} (handlers 모듈 import 여부 확인)")
    return ACTION_HANDLERS[name]


def get_checker(kind):
    if kind not in ACCEPTANCE_CHECKERS:
        raise KeyError(f"미등록 검수기: {kind} (handlers 모듈 import 여부 확인)")
    return ACCEPTANCE_CHECKERS[kind]
