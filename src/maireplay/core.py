"""Value-erased, bounded MCP observations. This module never performs network I/O.

The inferred contract describes one sample, not the official response schema.
Only MCP envelope metadata and public schema structure survive value erasure.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
from pathlib import Path
from typing import Any

FORMAT = "maireplay/v1"
SAFE_TOOLS = frozenset({"now-time-info", "campaign-calendar", "list-nutrition-foods"})
MAX_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 32
MAX_NODES = 20_000
SAFE_KEY = re.compile(r"[A-Za-z_]{1,64}\Z")
SYNTHETIC = "[synthetic]"
SYNTHETIC_TEXT = "[synthetic text]"
JSON_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}


class BundleError(ValueError):
    """A safe, actionable validation error. Never contains upstream data."""


def _bounded(value: Any) -> None:
    """Check JSON compatibility and resource limits without echoing input values."""
    nodes = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise BundleError("Input exceeds the depth or node limit.")
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise BundleError("JSON object keys must be strings.")
            for child in item.values():
                visit(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                visit(child, depth + 1)
        elif item is None or isinstance(item, (str, bool, int)):
            pass
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise BundleError("Non-finite JSON numbers are unsupported.")
        else:
            raise BundleError("Input contains an unsupported JSON value.")

    visit(value, 0)
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BundleError("Input is not valid bounded UTF-8 JSON.") from exc
    if len(encoded) > MAX_BYTES:
        raise BundleError("Input exceeds the 2 MiB limit.")


def read_json(path: str | Path) -> Any:
    """Read at most 2 MiB, refusing symlink and nonregular files."""
    path = Path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise BundleError("Input must be a regular file.")
            data = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        raise BundleError("Cannot read input file; check the path and permissions.") from exc
    if len(data) > MAX_BYTES:
        raise BundleError("Input exceeds the 2 MiB limit.")
    try:
        value = json.loads(
            data.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BundleError("Input is not valid UTF-8 JSON.") from exc
    _bounded(value)
    return value


def _reject_constant(_: str) -> None:
    raise ValueError("Invalid JSON numeric constant")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object keys are unsupported")
        result[key] = value
    return result


def _letter_index(index: int) -> str:
    result = ""
    while True:
        result = chr(ord("a") + index % 26) + result
        index = index // 26 - 1
        if index < 0:
            return result


def _key_map(keys: list[str]) -> tuple[dict[str, str], int]:
    """Discard dynamic keys; do not publish hashes of potentially private IDs."""
    used = {key for key in keys if SAFE_KEY.fullmatch(key)}
    mapping: dict[str, str] = {}
    count = 0
    for key in keys:
        if SAFE_KEY.fullmatch(key):
            mapping[key] = key
            continue
        candidate = "_field_" + _letter_index(count)
        while candidate in used:
            count += 1
            candidate = "_field_" + _letter_index(count)
        used.add(candidate)
        mapping[key] = candidate
        count += 1
    return mapping, sum(key != mapped for key, mapped in mapping.items())


def _erase(value: Any) -> tuple[Any, int]:
    """Erase all response scalar values, retaining container shape and JSON type."""
    if isinstance(value, dict):
        mapping, count = _key_map(list(value))
        result: dict[str, Any] = {}
        for key, child in value.items():
            erased, child_count = _erase(child)
            result[mapping[key]] = erased
            count += child_count
        return result, count
    if isinstance(value, list):
        result = []
        count = 0
        for child in value:
            erased, child_count = _erase(child)
            result.append(erased)
            count += child_count
        return result, count
    if value is None:
        return None, 0
    if isinstance(value, bool):
        return False, 0
    if isinstance(value, str):
        return SYNTHETIC, 0
    if isinstance(value, int):
        return 0, 0
    return 0.0, 0


def infer_shape(value: Any) -> dict[str, Any]:
    """A deterministic observed shape, including every sampled array member type."""
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {key: infer_shape(child) for key, child in sorted(value.items())},
        }
    if isinstance(value, list):
        shapes = {json.dumps(infer_shape(child), sort_keys=True) for child in value}
        return {"type": "array", "items": [json.loads(shape) for shape in sorted(shapes)]}
    if value is None:
        kind = "null"
    elif isinstance(value, bool):
        kind = "boolean"
    elif isinstance(value, str):
        kind = "string"
    elif isinstance(value, int):
        kind = "integer"
    else:
        kind = "number"
    return {"type": kind}


def _parse_text(text: str) -> tuple[str, Any | None]:
    """Parse complete JSON representations only; never scrape arbitrary braces."""
    candidate = text.strip()
    if not candidate:
        return "empty", None
    representation = "json"
    marker = "## Original Response"
    if marker in candidate:
        # Only a final, exact Markdown section can introduce the payload.
        prefix, _, candidate = candidate.rpartition(marker)
        if prefix and not prefix.endswith("\n"):
            return "text", None
        candidate = candidate.strip()
        representation = "markdown-json"
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
        if representation == "json":
            representation = "fenced-json"
    try:
        payload = json.loads(
            candidate, parse_constant=_reject_constant, object_pairs_hook=_unique_object
        )
        _bounded(payload)
        return representation, payload
    except (ValueError, RecursionError):
        return "text", None


def _render_text(representation: str, payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if representation == "fenced-json":
        return "```json\n" + text + "\n```"
    if representation == "markdown-json":
        return "## Original Response\n" + text
    return text


def _minimize_response(response: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(response, dict):
        raise BundleError("A response must be an MCP CallToolResult object.")
    if "isError" in response and not isinstance(response["isError"], bool):
        raise BundleError("MCP isError must be a boolean.")
    content = response.get("content")
    if not isinstance(content, list):
        raise BundleError("MCP content must be an array.")
    clean: dict[str, Any] = {"content": [], "isError": response.get("isError", False)}
    blocks = []
    redacted_keys = 0
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            raise BundleError("Only MCP text content is supported; media/resources are refused.")
        if not isinstance(block.get("text"), str):
            raise BundleError("MCP text content must contain a string.")
        representation, payload = _parse_text(block["text"])
        shape = None
        if representation in {"json", "fenced-json", "markdown-json"}:
            erased, count = _erase(payload)
            redacted_keys += count
            shape = infer_shape(erased)
            text = _render_text(representation, erased)
        elif representation == "empty":
            text = ""
        else:
            text = SYNTHETIC_TEXT
        clean["content"].append({"type": "text", "text": text})
        blocks.append({"representation": representation, "shape": shape})
    structured = None
    if "structuredContent" in response:
        if not isinstance(response["structuredContent"], dict):
            raise BundleError("MCP structuredContent must be an object.")
        erased, count = _erase(response["structuredContent"])
        redacted_keys += count
        clean["structuredContent"] = erased
        structured = infer_shape(erased)
    contract = {
        "envelope": infer_shape(
            {
                "content": [{"type": "text", "text": ""} for _ in content],
                **({"structuredContent": {}} if structured is not None else {}),
                "isError": clean["isError"],
            }
        ),
        "blocks": blocks,
        "structured": structured,
        "isError": clean["isError"],
        "redactedKeys": redacted_keys,
    }
    return clean, contract


def _sanitize_schema(schema: Any) -> dict[str, Any]:
    """Keep schema structure only; remove descriptions, defaults, enums and refs.

    This intentionally is not a full JSON Schema preservation operation. A schema
    baseline is for reviewing structural changes, not proving compatibility.
    """
    if not isinstance(schema, dict):
        raise BundleError("Tool inputSchema must be a JSON object.")
    result: dict[str, Any] = {}
    kind = schema.get("type")
    if isinstance(kind, str) and kind in JSON_TYPES:
        result["type"] = kind
    elif (
        isinstance(kind, list)
        and kind
        and all(isinstance(t, str) and t in JSON_TYPES for t in kind)
    ):
        result["type"] = sorted(set(kind))
    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, dict):
            raise BundleError("Schema properties must be a JSON object.")
        mapping, _ = _key_map(list(properties))
        result["properties"] = {
            mapping[key]: _sanitize_schema(child) for key, child in properties.items()
        }
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(isinstance(key, str) for key in required):
            raise BundleError("Schema required must be an array of property names.")
        if any(key not in properties for key in required):
            raise BundleError("Required schema fields must have property definitions.")
        if required:
            result["required"] = sorted({mapping[key] for key in required})
    elif schema.get("required"):
        raise BundleError("Required schema fields must have property definitions.")
    if "items" in schema:
        result["items"] = _sanitize_schema(schema["items"])
    if isinstance(schema.get("additionalProperties"), bool):
        result["additionalProperties"] = schema["additionalProperties"]
    elif isinstance(schema.get("additionalProperties"), dict):
        result["additionalProperties"] = _sanitize_schema(schema["additionalProperties"])
    # Metadata is generated from known keyword names, never from arbitrary values.
    structural = {"type", "properties", "required", "items", "additionalProperties"}
    descriptive = {"description", "title", "$schema", "$id", "$comment", "examples", "default"}
    if set(schema) - structural - descriptive:
        result["x-maireplay-limited"] = True
    if schema.get("x-maireplay-limited") is True:
        result["x-maireplay-limited"] = True
    return result


def build_bundle(
    tools: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    source: str = "user-import",
) -> dict[str, Any]:
    """Minimize a client export; arguments must be empty and no writes can enter."""
    _bounded({"tools": tools, "observations": observations})
    if not isinstance(source, str) or source not in {"synthetic", "user-import"}:
        raise BundleError("Source must be synthetic or user-import.")
    if not isinstance(tools, list) or not isinstance(observations, list):
        raise BundleError("Tools and observations must be arrays.")
    clean_tools = []
    seen: set[str] = set()
    input_schemas: dict[str, dict[str, Any]] = {}
    for tool in tools:
        if (
            not isinstance(tool, dict)
            or not isinstance(tool.get("name"), str)
            or tool.get("name") not in SAFE_TOOLS
        ):
            raise BundleError("Only the three supported read-only tool names are allowed.")
        name = tool["name"]
        if name in seen:
            raise BundleError("Duplicate tool definitions are not allowed.")
        seen.add(name)
        schema = _sanitize_schema(tool.get("inputSchema", {"type": "object"}))
        input_schemas[name] = schema
        clean_tools.append({"name": name, "inputSchema": schema})
    clean_observations = []
    observed: set[str] = set()
    for observation in observations:
        if (
            not isinstance(observation, dict)
            or not isinstance(observation.get("name"), str)
            or observation.get("name") not in seen
        ):
            raise BundleError("Every observation must match a supported tool definition.")
        name = observation["name"]
        if name in observed:
            raise BundleError("Use one observation per tool per bundle.")
        observed.add(name)
        if observation.get("arguments") != {}:
            raise BundleError("Only explicit empty arguments are supported.")
        if input_schemas[name].get("required"):
            raise BundleError("Empty observed arguments do not satisfy declared required fields.")
        clean, contract = _minimize_response(observation.get("response"))
        clean_observations.append(
            {
                "name": name,
                "arguments": {},
                "response": clean,
                "contract": contract,
            }
        )
    result = {
        "format": FORMAT,
        "source": source,
        "tools": sorted(clean_tools, key=lambda item: item["name"]),
        "observations": sorted(clean_observations, key=lambda item: item["name"]),
    }
    _bounded(result)
    return result


def _assert_erased(value: Any) -> None:
    if isinstance(value, dict):
        if any(not SAFE_KEY.fullmatch(key) for key in value):
            raise BundleError("A minimized bundle contains an unsafe response field name.")
        for child in value.values():
            _assert_erased(child)
    elif isinstance(value, list):
        for child in value:
            _assert_erased(child)
    elif value is None:
        return
    elif isinstance(value, str):
        if value != SYNTHETIC:
            raise BundleError("A bundle contains a response string that was not value-erased.")
    elif isinstance(value, bool):
        if value:
            raise BundleError("A bundle contains a response boolean that was not value-erased.")
    elif value != 0:
        raise BundleError("A bundle contains a response number that was not value-erased.")


def validate_bundle(bundle: Any) -> None:
    """Reject tampered/raw imported bundles before replay or report rendering."""
    _bounded(bundle)
    if not isinstance(bundle, dict) or set(bundle) != {"format", "source", "tools", "observations"}:
        raise BundleError("Unrecognized bundle envelope.")
    if bundle.get("format") != FORMAT:
        raise BundleError("Unsupported bundle format.")
    if not isinstance(bundle.get("tools"), list) or not isinstance(
        bundle.get("observations"), list
    ):
        raise BundleError("Tools and observations must be arrays.")
    for tool in bundle["tools"]:
        if not isinstance(tool, dict) or set(tool) != {"name", "inputSchema"}:
            raise BundleError("Unrecognized tool metadata in bundle.")
        if _sanitize_schema(tool.get("inputSchema")) != tool.get("inputSchema"):
            raise BundleError("Bundle schema contains unminimized metadata.")
    rebuilt = build_bundle(bundle["tools"], bundle["observations"], bundle.get("source"))
    # Erasure must be idempotent; contract recomputation checks forged metadata.
    for original, expected in zip(bundle["observations"], rebuilt["observations"], strict=True):
        if not isinstance(original, dict) or set(original) != {
            "name",
            "arguments",
            "response",
            "contract",
        }:
            raise BundleError("Unrecognized observation metadata in bundle.")
        response = original["response"]
        if not isinstance(response, dict) or set(response) - {
            "content",
            "isError",
            "structuredContent",
        }:
            raise BundleError("Unrecognized MCP response metadata in bundle.")
        for block in response["content"]:
            if set(block) != {"type", "text"}:
                raise BundleError("Unrecognized text block metadata in bundle.")
            representation, payload = _parse_text(block["text"])
            if representation in {"json", "fenced-json", "markdown-json"}:
                _assert_erased(payload)
            elif block["text"] not in {"", SYNTHETIC_TEXT}:
                raise BundleError("A bundle contains text that was not value-erased.")
        if "structuredContent" in response:
            _assert_erased(response["structuredContent"])
        # redactedKeys records source information lost by erasure, validate its
        # bounded count separately; all other contract fields must be recomputable.
        actual_contract = original["contract"]
        if not isinstance(actual_contract, dict):
            raise BundleError("Invalid observed contract.")
        redacted = actual_contract.get("redactedKeys")
        if type(redacted) is not int or not 0 <= redacted <= MAX_NODES:
            raise BundleError("Invalid field-redaction count.")
        expected["contract"]["redactedKeys"] = redacted
        if original != expected:
            raise BundleError("Bundle content does not match its recomputed contract.")
    if bundle["tools"] != rebuilt["tools"]:
        raise BundleError("Bundle tool definitions are not canonical.")


def load_bundle(path: str | Path) -> dict[str, Any]:
    bundle = read_json(path)
    validate_bundle(bundle)
    return bundle


def atomic_write_json(path: str | Path, data: Any) -> None:
    """Create a private new file without following links or replacing old data.

    O_EXCL reserves the destination atomically. On failure, an incomplete file is
    removed. Existing files (including symlinks) are never overwritten.
    """
    _bounded(data)
    path = Path(path)
    encoded = (json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode(
        "utf-8"
    )
    fd: int | None = None
    created = False
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        created = True
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        if fd is not None:
            os.close(fd)
        if created:
            path.unlink(missing_ok=True)
        raise BundleError("Cannot create output; use a new path in an existing directory.") from exc
