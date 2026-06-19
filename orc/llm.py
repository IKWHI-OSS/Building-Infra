"""LLM 호출 — 실 LLM 경로 기본 / SLICE_OFFLINE 스텁. SPEC §6.

OFFER 차이분석/요약, s4 LLM-judge가 여기를 쓴다. 스니펫 텍스트를 LLM 언어이해로
criteria에 대응시킨다(임베딩/벡터 유사도 아님).
"""
import os
import json

SYS = {
    "compare": ("너는 ML 엔지니어다. 주어진 검색 스니펫(specs)을 비교기준(criteria)별로 분석하라. "
                "각 기준마다 어느 모델이 우세한지와 근거(스니펫의 수치)를 한 줄씩. "
                "스니펫에 없는 값은 '자료없음'이라 명시. 추측 금지."),
    "summarize": ("너는 PM이다. 차이분석(analysis)을 바탕으로 용도별 추천(실시간성/정확도/균형)을 작성하라. "
                  "주어진 모든 비교기준을 빠짐없이 언급하되, 스니펫에 값이 없는 기준은 '자료없음'이라 명시하라. "
                  "각 추천 근거에 출처 URL(specs의 sources)을 괄호로 반드시 표기."),
    "judge": ("너는 품질 검수자다. summary가 (1) 각 criteria를 다뤘는지 — 수치든 '자료없음'이든 *언급*했으면 다룬 것으로 인정 — "
              "(2) 출처(sources) URL이 표기됐는지 점검. 둘 다 충족이면 첫 줄에 정확히 'PASS'만, 아니면 'FAIL: <부족한 점>'만 출력."),
}


def llm_call(purpose: str, payload: dict) -> str:
    if os.environ.get("SLICE_OFFLINE") == "1":
        return {
            "compare": "차이분석(stub): 스니펫 기준 YOLOv8=고FPS, Faster R-CNN=고정확도, RT-DETR=균형.",
            "summarize": "요약(stub): 실시간성=YOLOv8, 정확도=Faster R-CNN, 균형=RT-DETR. (근거: 검색 출처 URL)",
            "judge": "PASS",
        }.get(purpose, "stub")
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import SystemMessage, HumanMessage
    model = os.environ.get("SLICE_MODEL", "claude-sonnet-4-6")
    api_key = os.environ.get("CLAUDE_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    llm = ChatAnthropic(model=model, temperature=0, max_tokens=1024, api_key=api_key)
    msgs = [SystemMessage(SYS[purpose]), HumanMessage(json.dumps(payload, ensure_ascii=False))]
    return llm.invoke(msgs).content
