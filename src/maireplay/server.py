"""Local-only MCP endpoints for minimized capture and structural replay.

No remote transport, credential handling, proxying or account operation exists here.
The official MCP SDK supplies framing and initialization on standard I/O.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from .core import SAFE_TOOLS, BundleError, atomic_write_json, build_bundle, validate_bundle

CAPTURE_TOOL = "record_mcd_observation"
ZERO_ARGUMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def _error(message: str) -> CallToolResult:
    # Every caller passes a constant. Never interpolate upstream results or inputs.
    return CallToolResult(
        content=[TextContent(type="text", text=message)],
        isError=True,
    )


def create_replay_server(bundle: dict[str, Any]) -> Server:
    """Serve the already-minimized responses in one validated bundle.

    This is a structural fixture, not a business-response recording. Original
    strings, prices, dates and identifiers have been erased by the core module.
    Only the exact observed zero-argument calls can be replayed.
    """
    validate_bundle(bundle)
    frozen = copy.deepcopy(bundle)
    observations = {item["name"]: item for item in frozen["observations"]}
    server = Server(
        "maireplay-structural-replay",
        version="0.1.0",
        instructions=(
            "OFFLINE STRUCTURAL FIXTURES ONLY. Values are synthetic and do not "
            "represent real McDonald's prices, availability, eligibility or time. "
            "This server never contacts the official service."
        ),
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=name,
                description=(
                    "Offline value-erased structural fixture for the observed "
                    "zero-argument call. Not a real business result."
                ),
                inputSchema=copy.deepcopy(ZERO_ARGUMENT_SCHEMA),
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
            for name in sorted(observations)
        ]

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        if name not in SAFE_TOOLS or name not in observations:
            return _error("No recorded structural fixture exists for this tool.")
        if arguments != {}:
            return _error("Only the recorded zero-argument call can be replayed.")
        try:
            return CallToolResult.model_validate(copy.deepcopy(observations[name]["response"]))
        except Exception:
            # validate_bundle should already make this unreachable. Remain safe if
            # future SDK versions impose a stricter response model.
            return _error("The structural fixture is incompatible with this MCP SDK.")

    return server


def create_capture_server(output: Path) -> Server:
    """Receive one user-triggered official result and persist only its minimization.

    The agent's normal MCP client performs the authorized official query. This
    server merely receives the result locally; it cannot call the official MCP.
    Existing files, symlinks and repeated captures are never overwritten.
    """
    output = Path(output)
    server = Server(
        "maireplay-local-capture",
        version="0.1.0",
        instructions=(
            "Local minimization sink. After one explicitly requested official "
            "read-only call, pass its original CallToolResult to "
            "record_mcd_observation. Never include credentials. Only a synthetic "
            "value-erased bundle is written. One capture per output path."
        ),
    )
    captured = False

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=CAPTURE_TOOL,
                description=(
                    "Minimize one normal-client McDonald's MCP result in local "
                    "memory and write a private structural fixture. Does not "
                    "contact McDonald's or store original scalar values."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "enum": sorted(SAFE_TOOLS)},
                        "result": {"type": "object"},
                    },
                    "required": ["name", "result"],
                    "additionalProperties": False,
                },
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
            )
        ]

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        nonlocal captured
        if name != CAPTURE_TOOL:
            return _error("Unknown local capture tool.")
        if captured:
            return _error("This output has already been captured; start with a new path.")
        if (
            not isinstance(arguments, dict)
            or set(arguments) != {"name", "result"}
            or not isinstance(arguments.get("name"), str)
            or arguments["name"] not in SAFE_TOOLS
            or not isinstance(arguments.get("result"), dict)
        ):
            return _error("Expected one supported tool name and a CallToolResult object.")
        try:
            # This schema describes the observed call, not an official schema export.
            bundle = build_bundle(
                tools=[
                    {
                        "name": arguments["name"],
                        "inputSchema": copy.deepcopy(ZERO_ARGUMENT_SCHEMA),
                    }
                ],
                observations=[
                    {
                        "name": arguments["name"],
                        "arguments": {},
                        "response": arguments["result"],
                    }
                ],
                source="user-import",
            )
        except Exception:
            return _error(
                "Result rejected: invalid or unsupported MCP response. Nothing was captured."
            )
        try:
            atomic_write_json(output, bundle)
        except (BundleError, OSError):
            return _error(
                "Cannot create output. Choose an unused path in an existing writable directory. "
                "Nothing was overwritten."
            )
        captured = True
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=(
                        "Saved one value-erased structural fixture locally. "
                        "Original response values were not persisted. "
                        "This is not a live verification or official schema. "
                        "Inspect field names before sharing the bundle."
                    ),
                )
            ],
            isError=False,
        )

    return server


async def _run(server: Server) -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def run_replay(bundle: dict[str, Any]) -> None:
    """Run the fixture replay endpoint on stdio until the client closes it."""
    await _run(create_replay_server(bundle))


async def run_capture(output: Path) -> None:
    """Run the local minimization endpoint on stdio until the client closes it."""
    await _run(create_capture_server(output))
