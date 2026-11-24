"""Private, audit-only MCP entry point for GEOSITION."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from geo_optimizer.mcp.server import geo_audit, geo_commerce_audit

mcp = FastMCP("geosition-internal-audits")
mcp.tool()(geo_audit)
mcp.tool()(geo_commerce_audit)

if __name__ == "__main__":
    mcp.run(transport="stdio")
