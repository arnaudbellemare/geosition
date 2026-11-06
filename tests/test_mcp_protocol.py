"""Verify that a real MCP client can discover the server's tools over stdio."""
from __future__ import annotations

import asyncio
import sys

import pytest

pytest.importorskip("mcp", reason="Install geosition[mcp] to test the MCP protocol")


def test_mcp_stdio_client_discovers_tools() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def check() -> None:
        server = StdioServerParameters(command=sys.executable, args=["-m", "geo_optimizer.mcp.server"])
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                assert any(tool.name == "geo_audit" for tool in result.tools)

    asyncio.run(asyncio.wait_for(check(), timeout=30))
