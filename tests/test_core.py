"""Synthetic protocol fixtures only: no official business calls or account data."""

import copy
import json
import os

import pytest

from mcreplay.core import (
    MAX_BYTES,
    BundleError,
    atomic_write_json,
    build_bundle,
    infer_shape,
    load_bundle,
    read_json,
    validate_bundle,
)


def tool(schema=None):
    return {"name": "now-time-info", "inputSchema": schema or {"type": "object"}}


def observation(response):
    return {"name": "now-time-info", "arguments": {}, "response": response}


def bundle(response):
    return build_bundle([tool()], [observation(response)], "synthetic")


def test_erases_all_scalar_values_and_private_metadata():
    sentinel = "SECRET_PERSON_13911112222"
    payload = {
        "phone": sentinel,
        "points": 7993,
        "fraction": 3.14,
        "eligible": True,
        "nothing": None,
        "children": [sentinel, False, 44],
    }
    response = {
        "content": [
            {"type": "text", "text": json.dumps(payload), "annotations": {"secret": sentinel}}
        ],
        "structuredContent": payload,
        "_meta": {"token": sentinel},
    }
    actual = bundle(response)
    text = json.dumps(actual)
    assert sentinel not in text
    assert "7993" not in text
    assert "3.14" not in text
    assert actual["observations"][0]["response"]["structuredContent"] == {
        "phone": "[synthetic]",
        "points": 0,
        "fraction": 0.0,
        "eligible": False,
        "nothing": None,
        "children": ["[synthetic]", False, 0],
    }
    validate_bundle(actual)


@pytest.mark.parametrize(
    ("text", "representation"),
    [
        ('{"data":[{"value":42}]}', "json"),
        ('```json\n{"data":[{"value":42}]}\n```', "fenced-json"),
        ('# MCP result\n\n## Original Response\n{"data":[{"value":42}]}', "markdown-json"),
        (
            '# MCP result\n\n## Original Response\n```json\n{"data":[{"value":42}]}\n```',
            "markdown-json",
        ),
        ('prefix contains {"secret":"not a payload"} suffix', "text"),
        ('{"data": true} trailing non JSON', "text"),
        ("", "empty"),
        ("  \n ", "empty"),
    ],
)
def test_representation_parser_never_guesses_embedded_json(text, representation):
    actual = bundle({"content": [{"type": "text", "text": text}]})
    assert actual["observations"][0]["contract"]["blocks"][0]["representation"] == representation
    validate_bundle(actual)


def test_dynamic_field_keys_redacted_without_hash_or_collision():
    payload = {
        "_field_a": "literal",
        "13800138000": "phone",
        "张三": "private",
        "email@example.test": {"123456": True},
    }
    actual = bundle({"content": [], "structuredContent": payload})
    rendered = json.dumps(actual, ensure_ascii=False)
    for private in ("13800138000", "张三", "email@example.test", "123456"):
        assert private not in rendered
    clean = actual["observations"][0]
    assert len(clean["response"]["structuredContent"]) == 4
    assert clean["contract"]["redactedKeys"] == 4
    validate_bundle(actual)


def test_heterogeneous_array_retains_all_sampled_shapes():
    shape = infer_shape([1, "a", {"b": False}, [], 2])
    assert len(shape["items"]) == 4
    assert {item["type"] for item in shape["items"]} == {"integer", "string", "object", "array"}
    assert shape == infer_shape([2, [], {"b": True}, "z", 1])
    assert infer_shape([]) == {"type": "array", "items": []}


def test_schema_metadata_erasure_and_unknown_constraint_marker():
    schema = {
        "type": "object",
        "description": "SENSITIVE_DESCRIPTION",
        "properties": {
            "date": {
                "type": "string",
                "enum": ["SECRET_ENUM"],
                "default": "SECRET_DEFAULT",
                "pattern": "SECRET_PATTERN",
            }
        },
        "required": ["date"],
        "additionalProperties": False,
    }
    actual = build_bundle([tool(schema)], [], "synthetic")
    assert "SECRET" not in json.dumps(actual)
    clean = actual["tools"][0]["inputSchema"]
    assert clean["properties"]["date"] == {"type": "string", "x-mcreplay-limited": True}
    assert clean["required"] == ["date"]
    validate_bundle(actual)


@pytest.mark.parametrize("name", ["create-order", "draw-lottery", "query-order", "", [], {}])
def test_no_unknown_or_state_changing_tool_can_be_recorded(name):
    with pytest.raises(BundleError):
        build_bundle([{"name": name, "inputSchema": {}}], [])


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        {},
        {"content": "secret"},
        {"content": [{"type": "image", "data": "SECRET"}]},
        {"content": [{"type": "resource", "resource": {"uri": "SECRET"}}]},
        {"content": [{"type": "text", "text": 42}]},
        {"content": [], "structuredContent": "SECRET"},
        {"content": [], "isError": "false"},
    ],
)
def test_invalid_or_media_responses_fail_closed_without_echo(response):
    with pytest.raises(BundleError) as error:
        bundle(response)
    assert "SECRET" not in str(error.value)


def test_arguments_required_explicitly_and_empty():
    for arguments in (None, [], {"token": "SECRET"}, {"storeCode": "x"}):
        item = observation({"content": []})
        item["arguments"] = arguments
        with pytest.raises(BundleError):
            build_bundle([tool()], [item])


def test_duplicate_tool_or_observation_rejected():
    with pytest.raises(BundleError):
        build_bundle([tool(), tool()], [])
    item = observation({"content": []})
    with pytest.raises(BundleError):
        build_bundle([tool()], [item, item])


def test_limits_nonfinite_and_bad_json():
    deep = {}
    cursor = deep
    for _ in range(34):
        cursor["data"] = {}
        cursor = cursor["data"]
    for payload in (deep, {"x": "s" * MAX_BYTES}, {"x": [0] * 20_001}, {"x": float("nan")}):
        with pytest.raises(BundleError):
            bundle({"content": [], "structuredContent": payload})


def test_error_response_preserves_error_state_without_text():
    actual = bundle({"isError": True, "content": [{"type": "text", "text": "PRIVATE ERROR"}]})
    assert actual["observations"][0]["response"]["isError"] is True
    assert actual["observations"][0]["contract"]["isError"] is True
    assert "PRIVATE ERROR" not in json.dumps(actual)
    validate_bundle(actual)


@pytest.mark.parametrize(
    "tamper",
    [
        lambda b: b.update({"secret": "private"}),
        lambda b: b["observations"][0]["response"]["content"][0].update(text="PRIVATE"),
        lambda b: b["observations"][0]["contract"].update(isError=True),
        lambda b: b["observations"][0]["response"].update(_meta={"token": "PRIVATE"}),
        lambda b: b["tools"][0]["inputSchema"].update(description="PRIVATE"),
    ],
)
def test_bundle_validation_rejects_raw_or_forged_payloads(tamper):
    actual = bundle({"content": [{"type": "text", "text": "some text"}]})
    tamper(actual)
    with pytest.raises(BundleError):
        validate_bundle(actual)


def test_bundle_validation_rejects_unerased_json_scalars():
    actual = bundle({"content": [{"type": "text", "text": '{"phone":"SECRET"}'}]})
    actual["observations"][0]["response"]["content"][0]["text"] = '{"phone":"PRIVATE"}'
    with pytest.raises(BundleError):
        validate_bundle(actual)


def test_private_new_file_roundtrip_refuses_overwrite_and_symlink(tmp_path):
    path = tmp_path / "sample.json"
    actual = bundle({"content": []})
    atomic_write_json(path, actual)
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert load_bundle(path) == actual
    with pytest.raises(BundleError):
        atomic_write_json(path, {"overwrite": True})
    assert load_bundle(path) == actual
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(BundleError):
        atomic_write_json(link, actual)
    with pytest.raises(BundleError):
        read_json(link)


def test_file_size_and_invalid_encoding(tmp_path):
    path = tmp_path / "raw.json"
    for content in (b"{" + b"x" * MAX_BYTES, b'"\xff"', b'{"x":NaN}'):
        path.write_bytes(content)
        with pytest.raises(BundleError):
            read_json(path)


def test_validation_does_not_mutate_bundle():
    actual = bundle({"content": [{"type": "text", "text": '{"x": [1, 2]}'}]})
    previous = copy.deepcopy(actual)
    validate_bundle(actual)
    assert actual == previous


def test_duplicate_json_keys_rejected_in_file_and_unparsed_in_response(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"secret": "a", "secret": "b"}')
    with pytest.raises(BundleError):
        read_json(path)
    actual = bundle({"content": [{"type": "text", "text": path.read_text()}]})
    assert actual["observations"][0]["contract"]["blocks"][0]["representation"] == "text"
    assert actual["observations"][0]["response"]["content"][0]["text"] == "[synthetic text]"


def test_required_tool_arguments_cannot_have_empty_observation():
    schema = {
        "type": "object",
        "properties": {"date": {"type": "string"}},
        "required": ["date"],
    }
    # Catalog-only structural snapshots remain valid, but a call with empty
    # arguments cannot be presented as satisfying this observed tool contract.
    catalog = build_bundle([tool(schema)], [], "synthetic")
    validate_bundle(catalog)
    with pytest.raises(BundleError, match="required fields"):
        build_bundle([tool(schema)], [observation({"content": []})], "synthetic")
