"""An independent SDK consumer for the INVENTED demo schema, never the live service.

Usage: python examples/check_adapter.py demo-output/before.json
       python examples/check_adapter.py demo-output/after.json  # exits 2
This adapter checks the demo field at the root. The recorded official response
uses data.timestamp; see check_recorded_structure.py for that workflow.
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check(bundle: str) -> bool:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "mcreplay", "replay", str(Path(bundle).resolve())]
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("now-time-info", {})
        data = result.structuredContent
        ok = not result.isError and isinstance(data, dict) and type(data.get("timestamp")) is int
        print("DEMO adapter: timestamp integer contract", "PASS" if ok else "FAIL")
        return ok


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python examples/check_adapter.py BUNDLE.json")
    raise SystemExit(0 if asyncio.run(check(sys.argv[1])) else 2)
