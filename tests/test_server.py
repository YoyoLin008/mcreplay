"""Protocol checks use the official SDK against local processes, never the service."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest

from mcreplay.core import atomic_write_json, build_bundle, load_bundle
from mcreplay.server import (
    CAPTURE_TOOL,
    create_capture_server,
    create_replay_server,
)

SENTINEL = "DO_NOT_PERSIST_PRIVATE_VALUE"


def sample_bundle() -> dict[str, Any]:
    return build_bundle(
        tools=[
            {
                "name": "now-time-info",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ],
        observations=[
            {
                "name": "now-time-info",
                "arguments": {},
                "response": {
                    "content": [{"type": "text", "text": json.dumps({"currentTime": SENTINEL})}],
                    "isError": False,
                },
            }
        ],
        source="synthetic",
    )


async def invoke(server, name: str, arguments: dict[str, Any] | None = None):
    result = await server.request_handlers[CallToolRequest](
        CallToolRequest(params=CallToolRequestParams(name=name, arguments=arguments or {}))
    )
    return result.root


def test_replay_advertises_only_observed_tools():
    async def check():
        server = create_replay_server(sample_bundle())
        result = await server.request_handlers[ListToolsRequest](ListToolsRequest())
        assert [tool.name for tool in result.root.tools] == ["now-time-info"]
        assert result.root.tools[0].annotations.readOnlyHint is True
        assert result.root.tools[0].inputSchema["additionalProperties"] is False

    asyncio.run(asyncio.wait_for(check(), timeout=25))


def test_replay_response_is_minimized_and_defensively_copied():
    async def check():
        bundle = sample_bundle()
        server = create_replay_server(bundle)
        bundle["observations"][0]["response"]["content"][0]["text"] = SENTINEL
        response = await invoke(server, "now-time-info")
        assert not response.isError
        assert SENTINEL not in response.model_dump_json()
        assert "currentTime" in response.content[0].text
        response.content[0].text = SENTINEL
        second = await invoke(server, "now-time-info")
        assert SENTINEL not in second.model_dump_json()

    asyncio.run(asyncio.wait_for(check(), timeout=25))


@pytest.mark.parametrize(
    "name", ["create-order", "auto-bind-coupons", "campaign-calendar", "missing"]
)
def test_unrecorded_and_transactional_calls_are_errors(name):
    async def check():
        response = await invoke(create_replay_server(sample_bundle()), name)
        assert response.isError
        assert "No recorded" in response.content[0].text

    asyncio.run(asyncio.wait_for(check(), timeout=25))


def test_replay_rejects_parameters_without_echoing_them():
    async def check():
        response = await invoke(
            create_replay_server(sample_bundle()),
            "now-time-info",
            {"private": SENTINEL},
        )
        assert response.isError
        assert SENTINEL not in response.model_dump_json()

    asyncio.run(asyncio.wait_for(check(), timeout=25))


def test_capture_writes_only_minimized_data(tmp_path):
    async def check():
        output = tmp_path / "capture.json"
        server = create_capture_server(output)
        response = await invoke(
            server,
            CAPTURE_TOOL,
            {
                "name": "now-time-info",
                "result": {"content": [{"type": "text", "text": SENTINEL}]},
            },
        )
        assert not response.isError
        assert SENTINEL not in output.read_text()
        assert load_bundle(output)["source"] == "user-import"
        second = await invoke(
            server,
            CAPTURE_TOOL,
            {
                "name": "now-time-info",
                "result": {"content": [{"type": "text", "text": SENTINEL}]},
            },
        )
        assert second.isError
        assert SENTINEL not in second.model_dump_json()

    asyncio.run(asyncio.wait_for(check(), timeout=25))


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"name": "draw-lottery", "result": {"content": []}},
        {"name": "now-time-info", "result": "not an object"},
        {"name": "now-time-info", "result": {}, "token": SENTINEL},
        {"name": SENTINEL, "result": {"content": []}},
        {"name": "now-time-info", "result": {"content": [{"type": "image", "data": SENTINEL}]}},
    ],
)
def test_capture_rejects_invalid_input_without_writing_or_echoing(tmp_path, arguments):
    async def check():
        output = tmp_path / "capture.json"
        response = await invoke(create_capture_server(output), CAPTURE_TOOL, arguments)
        assert response.isError
        assert not output.exists()
        assert SENTINEL not in response.model_dump_json()

    asyncio.run(asyncio.wait_for(check(), timeout=25))


def test_capture_rejects_unknown_tool(tmp_path):
    async def check():
        output = tmp_path / "capture.json"
        response = await invoke(
            create_capture_server(output),
            "create-order",
            {"private": SENTINEL},
        )
        assert response.isError
        assert SENTINEL not in response.model_dump_json()
        assert not output.exists()

    asyncio.run(asyncio.wait_for(check(), timeout=25))


def test_capture_does_not_overwrite_existing_file(tmp_path):
    async def check():
        output = tmp_path / "capture.json"
        output.write_text("existing")
        response = await invoke(
            create_capture_server(output),
            CAPTURE_TOOL,
            {"name": "now-time-info", "result": {"content": []}},
        )
        assert response.isError
        assert output.read_text() == "existing"

    asyncio.run(asyncio.wait_for(check(), timeout=25))


def test_replay_rejects_invalid_bundle():
    with pytest.raises(ValueError):
        create_replay_server({"format": "unsupported"})


def test_sdk_stdio_replay_end_to_end(tmp_path):
    """Real SDK initialization/list/call against the installed CLI subprocess."""
    output = tmp_path / "fixture.json"
    atomic_write_json(output, sample_bundle())

    async def check():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcreplay", "replay", str(output)],
            env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                initialization = await session.initialize()
                assert "STRUCTURAL" in initialization.instructions
                tools = await session.list_tools()
                assert [tool.name for tool in tools.tools] == ["now-time-info"]
                response = await session.call_tool("now-time-info", {})
                assert not response.isError
                assert SENTINEL not in response.model_dump_json()
                assert "currentTime" in response.content[0].text
                for name in ("create-order", "campaign-calendar"):
                    response = await session.call_tool(name, {})
                    assert response.isError

    asyncio.run(asyncio.wait_for(check(), timeout=25))


def test_sdk_stdio_capture_end_to_end(tmp_path):
    output = tmp_path / "capture.json"

    async def check():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcreplay", "capture", "--out", str(output)],
            env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert [tool.name for tool in tools.tools] == [CAPTURE_TOOL]
                response = await session.call_tool(
                    CAPTURE_TOOL,
                    {
                        "name": "campaign-calendar",
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps({"events": [{"title": SENTINEL}]}),
                                }
                            ],
                        },
                    },
                )
                assert not response.isError
                assert SENTINEL not in response.model_dump_json()
                assert SENTINEL not in output.read_text()
                assert load_bundle(output)["source"] == "user-import"

    asyncio.run(asyncio.wait_for(check(), timeout=25))
