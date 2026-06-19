# 실 웹검색 MCP 서버 (키리스, DuckDuckGo). TOOL 경계의 진짜 외부 데이터 출처.
# 평소: 실제 웹검색.  MCP_OFFLINE=1: 고정 스니펫(네트워크 없는 곳 검증용 — 출처는 placeholder).
import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("modeltool")

# 오프라인(샌드박스) 검증 전용 고정 스니펫. 실제론 안 씀.
_CANNED = {
    "Faster R-CNN": {"model": "Faster R-CNN",
        "snippets": ["Faster R-CNN with ResNet-50 FPN reaches ~37-41 box AP on COCO; ~15-20 FPS on a V100."],
        "sources": ["offline-placeholder://faster-rcnn"]},
    "YOLOv8": {"model": "YOLOv8",
        "snippets": ["YOLOv8x ~53.9 mAP COCO; smaller variants 100+ FPS; easy export (ONNX/TensorRT)."],
        "sources": ["offline-placeholder://yolov8"]},
    "RT-DETR": {"model": "RT-DETR",
        "snippets": ["RT-DETR-R50 ~53 AP COCO real-time; ~74-108 FPS on T4; end-to-end no NMS."],
        "sources": ["offline-placeholder://rt-detr"]},
}

@mcp.tool()
def web_search_specs(model: str) -> dict:
    """모델명으로 객체탐지 벤치마크(mAP/FPS/배포 등)를 웹에서 검색해 스니펫과 출처 URL을 반환한다."""
    if os.environ.get("MCP_OFFLINE") == "1":
        return _CANNED.get(model, {"model": model, "snippets": [], "sources": []})
    from ddgs import DDGS
    q = f"{model} object detection mAP FPS COCO benchmark inference speed"
    try:
        hits = DDGS().text(q, max_results=4)
    except Exception as e:
        return {"model": model, "snippets": [], "sources": [], "error": str(e)[:200]}
    return {"model": model,
            "snippets": [h.get("body", "") for h in hits],
            "sources": [h.get("href", "") for h in hits]}

if __name__ == "__main__":
    mcp.run(transport="stdio")
