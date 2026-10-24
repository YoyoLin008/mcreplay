"""Directional, conservative comparison of observed MCP contracts.

This is a regression detector for a finite set of samples, not a proof of JSON
Schema compatibility. Output messages intentionally never interpolate sample
values. Callers must validate bundles before calling this module.
"""

from __future__ import annotations

import json
from typing import Any, Literal, TypedDict


class Change(TypedDict):
    severity: Literal["breaking", "review", "info"]
    path: str
    message: str


_JSON_TYPES = {"null", "boolean", "object", "array", "number", "integer", "string"}
_KNOWN_SCHEMA_KEYS = {
    "type",
    "properties",
    "required",
    "items",
    "additionalProperties",
}
_ORDER = {"breaking": 0, "review": 1, "info": 2}


def _path(base: str, part: str) -> str:
    """Use JSON Pointer escaping so paths have an unambiguous meaning."""
    return base + "/" + part.replace("~", "~0").replace("/", "~1")


def _add(changes: list[Change], severity: str, path: str, message: str) -> None:
    changes.append(Change(severity=severity, path=path, message=message))  # type: ignore[typeddict-item]


def _types(schema: dict[str, Any]) -> set[str]:
    value = schema.get("type")
    if value is None:
        return set(_JSON_TYPES)
    values = {value} if isinstance(value, str) else set(value)
    # JSON Schema's number accepts integers too.
    if "number" in values:
        values.add("integer")
    return values


def _schema(
    before: dict[str, Any], after: dict[str, Any], path: str, changes: list[Change]
) -> None:
    if before.get("x-mcreplay-limited") or after.get("x-mcreplay-limited"):
        _add(
            changes,
            "review",
            path,
            "Input schema contains omitted constraints; compatibility outside the "
            "supported structural subset is unverified.",
        )
    old_types, new_types = _types(before), _types(after)
    if old_types - new_types:
        _add(
            changes,
            "breaking",
            _path(path, "type"),
            "Input type constraint narrowed; previously valid callers may fail.",
        )
    elif new_types - old_types:
        _add(changes, "info", _path(path, "type"), "Input type constraint widened.")

    old_required = set(before.get("required", []))
    new_required = set(after.get("required", []))
    for key in sorted(new_required - old_required):
        _add(
            changes,
            "breaking",
            _path(_path(path, "required"), key),
            "New required input field; existing requests may be rejected.",
        )
    for key in sorted(old_required - new_required):
        _add(
            changes,
            "info",
            _path(_path(path, "required"), key),
            "Input field is no longer required.",
        )

    old_props = before.get("properties", {})
    new_props = after.get("properties", {})
    for key in sorted(old_props.keys() - new_props.keys()):
        closed = after.get("additionalProperties") is False
        _add(
            changes,
            "breaking" if closed else "review",
            _path(_path(path, "properties"), key),
            "Input property removed and additional properties are forbidden."
            if closed
            else "Input property removed; acceptance of existing requests needs review.",
        )
    for key in sorted(new_props.keys() - old_props.keys()):
        # A newly declared optional property can constrain a value that was
        # previously accepted through additionalProperties.
        was_closed = before.get("additionalProperties") is False
        _add(
            changes,
            "info" if was_closed else "review",
            _path(_path(path, "properties"), key),
            "New input property accepted."
            if was_closed
            else "New input property constraint; check callers already using this field.",
        )
    for key in sorted(old_props.keys() & new_props.keys()):
        _schema(old_props[key], new_props[key], _path(_path(path, "properties"), key), changes)

    old_extra = before.get("additionalProperties", True)
    new_extra = after.get("additionalProperties", True)
    if old_extra != new_extra:
        extra_path = _path(path, "additionalProperties")
        if new_extra is False:
            _add(changes, "breaking", extra_path, "Additional input properties are now forbidden.")
        elif old_extra is False or new_extra is True:
            _add(
                changes,
                "info",
                extra_path,
                "Additional input properties are accepted more broadly.",
            )
        elif old_extra is True:
            _add(
                changes,
                "breaking",
                extra_path,
                "Additional input properties now have a schema constraint.",
            )
        else:
            _schema(old_extra, new_extra, extra_path, changes)

    old_items, new_items = before.get("items"), after.get("items")
    if old_items != new_items:
        items_path = _path(path, "items")
        if old_items is None and isinstance(new_items, dict):
            _add(changes, "breaking", items_path, "Input array items now have a schema constraint.")
        elif new_items is None:
            _add(changes, "info", items_path, "Input array item constraint removed.")
        elif isinstance(old_items, dict) and isinstance(new_items, dict):
            _schema(old_items, new_items, items_path, changes)
        else:
            _add(
                changes,
                "review",
                items_path,
                "Input array schema changed outside the supported subset.",
            )

    # Do not silently certify unsupported constraints, even if their names
    # happen to be JSON Schema keywords. Their values are never printed.
    old_other = {k: v for k, v in before.items() if k not in _KNOWN_SCHEMA_KEYS}
    new_other = {k: v for k, v in after.items() if k not in _KNOWN_SCHEMA_KEYS}
    if old_other != new_other:
        _add(
            changes,
            "review",
            path,
            "Unsupported or omitted schema constraints changed; inspect the source schema.",
        )


def _shape(before: dict[str, Any], after: dict[str, Any], path: str, changes: list[Change]) -> None:
    old_type, new_type = before.get("type"), after.get("type")
    if old_type != new_type:
        _add(
            changes,
            "review" if (old_type, new_type) == ("integer", "number") else "breaking",
            path,
            "Observed output type widened from integer to number; review numeric assumptions."
            if (old_type, new_type) == ("integer", "number")
            else "Observed output type changed; adapters depending on the old type may fail.",
        )
        return
    if old_type == "object":
        old_props, new_props = before.get("properties", {}), after.get("properties", {})
        for key in sorted(old_props.keys() - new_props.keys()):
            _add(
                changes,
                "breaking",
                _path(path, key),
                "Previously observed output field is absent in the new sample.",
            )
        for key in sorted(new_props.keys() - old_props.keys()):
            _add(
                changes,
                "info",
                _path(path, key),
                "New output field observed; strict parsers may require review.",
            )
        for key in sorted(old_props.keys() & new_props.keys()):
            _shape(old_props[key], new_props[key], _path(path, key), changes)
    elif old_type == "array":
        old_items, new_items = before.get("items", []), after.get("items", [])
        if old_items == new_items:
            return
        if not old_items or not new_items:
            _add(
                changes,
                "review",
                path,
                "Array sample changed between empty and populated; item compatibility is unknown.",
            )
        elif len(old_items) == len(new_items) == 1:
            _shape(old_items[0], new_items[0], _path(path, "items"), changes)
        else:
            # A finite sample cannot establish optionality or type coverage.
            old_set = {json.dumps(x, sort_keys=True) for x in old_items}
            new_set = {json.dumps(x, sort_keys=True) for x in new_items}
            if old_set != new_set:
                _add(
                    changes,
                    "review",
                    _path(path, "items"),
                    "Heterogeneous array variants changed; "
                    "finite samples cannot prove compatibility.",
                )


def _optional_shape(before: Any, after: Any, path: str, changes: list[Change]) -> None:
    if before == after:
        return
    if before is None:
        _add(changes, "info", path, "Structured output is newly present in the sample.")
    elif after is None:
        _add(changes, "breaking", path, "Previously observed structured output is absent.")
    else:
        _shape(before, after, path, changes)


def _contract(
    before: dict[str, Any], after: dict[str, Any], path: str, changes: list[Change]
) -> None:
    redacted_keys = bool(before.get("redactedKeys", 0) or after.get("redactedKeys", 0))
    if redacted_keys:
        _add(
            changes,
            "review",
            path,
            "Dynamic field names were replaced; field identity cannot be established "
            "across these samples. Payload shape comparison is skipped.",
        )
    if before.get("isError", False) and after.get("isError", False):
        _add(
            changes,
            "review",
            _path(path, "isError"),
            "Both samples report tool errors; a successful output baseline is unavailable.",
        )
    if before.get("isError", False) != after.get("isError", False):
        _add(
            changes,
            "breaking" if after.get("isError", False) else "review",
            _path(path, "isError"),
            "The new sample reports a tool error; it is not a successful response."
            if after.get("isError", False)
            else "Sample changed from tool error to success; establish a successful baseline.",
        )
    _optional_shape(before.get("envelope"), after.get("envelope"), _path(path, "envelope"), changes)
    if not redacted_keys:
        _optional_shape(
            before.get("structured"), after.get("structured"), _path(path, "structured"), changes
        )
    old_blocks, new_blocks = before.get("blocks", []), after.get("blocks", [])
    if (not old_blocks and before.get("structured") is None) or (
        not new_blocks and after.get("structured") is None
    ):
        _add(
            changes,
            "review",
            path,
            "At least one response has no content or structured payload; "
            "output compatibility is untested.",
        )
    if len(old_blocks) != len(new_blocks):
        _add(
            changes,
            "breaking" if len(new_blocks) < len(old_blocks) else "review",
            _path(path, "blocks"),
            "Observed MCP content block count changed.",
        )
    for index, (old, new) in enumerate(zip(old_blocks, new_blocks, strict=False)):
        block_path = _path(_path(path, "blocks"), str(index))
        if old.get("representation") == new.get("representation") == "text":
            _add(
                changes,
                "review",
                block_path,
                "Unparsed text is opaque; this sample cannot establish payload compatibility.",
            )
        if old.get("representation") == new.get("representation") == "empty":
            _add(
                changes,
                "review",
                block_path,
                "Both text samples are empty; payload compatibility is untested.",
            )
        if old.get("representation") != new.get("representation"):
            _add(
                changes,
                "breaking",
                _path(block_path, "representation"),
                "Response representation changed; parser selection may need updating.",
            )
        if not redacted_keys:
            _optional_shape(old.get("shape"), new.get("shape"), _path(block_path, "shape"), changes)


def compare_bundles(before: dict[str, Any], after: dict[str, Any]) -> list[Change]:
    """Return stable directional change records for two validated bundles.

    ``breaking`` means a previously observed dependency may fail, not that every
    consumer necessarily fails. ``review`` represents incomplete evidence or an
    unsupported rule. No changes means only *no observed structural change*.
    """
    changes: list[Change] = []
    old_tools = {tool["name"]: tool for tool in before["tools"]}
    new_tools = {tool["name"]: tool for tool in after["tools"]}
    for name in sorted(old_tools.keys() - new_tools.keys()):
        _add(changes, "breaking", _path("/tools", name), "Tool is absent from the new catalog.")
    for name in sorted(new_tools.keys() - old_tools.keys()):
        _add(changes, "info", _path("/tools", name), "New tool in the catalog.")
    for name in sorted(old_tools.keys() & new_tools.keys()):
        _schema(
            old_tools[name].get("inputSchema", {}),
            new_tools[name].get("inputSchema", {}),
            _path(_path("/tools", name), "inputSchema"),
            changes,
        )

    old_obs = {obs["name"]: obs for obs in before["observations"]}
    new_obs = {obs["name"]: obs for obs in after["observations"]}
    if not old_obs or not new_obs:
        _add(
            changes,
            "review",
            "/observations",
            "At least one bundle has no observations; output compatibility is untested.",
        )
    for name in sorted(old_obs.keys() - new_obs.keys()):
        _add(
            changes,
            "review",
            _path("/observations", name),
            "No new response sample for this tool; output compatibility is untested.",
        )
    for name in sorted(new_obs.keys() - old_obs.keys()):
        _add(
            changes,
            "info",
            _path("/observations", name),
            "First response sample; no previous output baseline exists.",
        )
    for name in sorted(old_obs.keys() & new_obs.keys()):
        _contract(
            old_obs[name]["contract"],
            new_obs[name]["contract"],
            _path(_path("/observations", name), "contract"),
            changes,
        )

    unique = {(c["severity"], c["path"], c["message"]): c for c in changes}
    return sorted(unique.values(), key=lambda c: (_ORDER[c["severity"]], c["path"], c["message"]))
