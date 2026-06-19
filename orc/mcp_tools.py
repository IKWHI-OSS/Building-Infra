"""MCP TOOL 경계 — 웹검색 MCP 서버(mcp_model_tool.py)를 stdio로 띄워 호출. SPEC §1·결정2.

서버는 패키지 상위 폴더의 mcp_model_tool.py. command=sys.executable로 띄워
서버 서브프로세스가 호출자와 같은 파이썬을 쓰게 한다(패키지 불일치 방지).
"""
import os
import sys
import json
from pathlib import Path
from langchain_mcp_adapters.client import MultiServerMCPClient

# agents/orc/mcp_tools.py -> agents/mcp_model_tool.py
SERVER_PATH = str(Path(__file__).resolve().parent.parent / "mcp_model_tool.py")

_tools_by = None


async def _ensure_tools():
    global _tools_by
    if _tools_by is None:
        client = MultiServerMCPClient({
            "modeltool": {"command": sys.executable, "args": [SERVER_PATH],
                          "transport": "stdio", "env": dict(os.environ)}
        })
        tools = await client.get_tools()
        _tools_by = {t.name: t for t in tools}
    return _tools_by


async def mcp_search(model: str) -> dict:
    """모델명 → 웹검색 스니펫+출처(dict). MCP content 블록 리스트를 파싱."""
    tb = await _ensure_tools()
    raw = await tb["web_search_specs"].ainvoke({"model": model})
    return json.loads(raw[0]["text"]) if isinstance(raw, list) else raw
