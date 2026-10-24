"""Check the recorded official shapes through local MCP capture and replay.

Usage: python examples/check_recorded_structure.py
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

FIXTURE = Path(__file__).parent / "fixtures" / "official-20261024.json"


def check_payload(name: str, response: CallToolResult) -> None:
    assert not response.isError, name
    assert response.structuredContent is not None, name
    data = response.structuredContent["data"]
    if name == "now-time-info":
        assert type(data["timestamp"]) is int
        assert isinstance(data["datetime"], str)
    elif name == "campaign-calendar":
        assert isinstance(data["dailyList"], list)
        assert isinstance(data["subscribedEvents"], list)
    elif name == "list-nutrition-foods":
        assert isinstance(data, str)
    else:
        raise AssertionError("Unexpected recorded tool")


async def check() -> None:
    bundle = json.loads(FIXTURE.read_text())
    expected = {entry["name"]: entry["response"] for entry in bundle["observations"]}
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "mcreplay", "replay", str(FIXTURE.resolve())]
    )
    with tempfile.TemporaryDirectory(prefix="mcreplay-check-") as directory:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            assert {tool.name for tool in (await session.list_tools()).tools} == set(expected)
            for name, recorded in expected.items():
                response = await session.call_tool(name, {})
                assert response == CallToolResult.model_validate(recorded), name
                check_payload(name, response)
                output = Path(directory) / f"{name}.json"
                capture = StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "mcreplay", "capture", "--out", str(output)],
                )
                async with (
                    stdio_client(capture) as (capture_read, capture_write),
                    ClientSession(capture_read, capture_write) as sink,
                ):
                    await sink.initialize()
                    saved = await sink.call_tool(
                        "record_mcd_observation", {"name": name, "result": recorded}
                    )
                    assert not saved.isError, name
                captured = json.loads(output.read_text())
                assert captured["observations"][0]["response"] == recorded, name
                print(f"{name}: recorded shape, capture and replay PASS")


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(check(), timeout=30))
