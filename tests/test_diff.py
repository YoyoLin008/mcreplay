"""Directional regression examples; all samples are synthetic."""

from copy import deepcopy

import pytest

from mcreplay.diff import compare_bundles


def shape(kind, **kwargs):
    return {"type": kind, **kwargs}


def bundle(schema=None, output=None, representation="json", error=False):
    return {
        "format": "mcreplay/v1",
        "source": "synthetic",
        "tools": [{"name": "now-time-info", "inputSchema": schema or {"type": "object"}}],
        "observations": [
            {
                "name": "now-time-info",
                "arguments": {},
                "response": {},
                "contract": {
                    "isError": error,
                    "envelope": shape("object", properties={"content": shape("array", items=[])}),
                    "blocks": [{"representation": representation, "shape": output}],
                    "structured": None,
                },
            }
        ],
    }


def severities(changes):
    return {c["severity"] for c in changes}


def test_identical_sample_does_not_claim_changes():
    a = bundle(output=shape("integer"))
    assert compare_bundles(a, deepcopy(a)) == []


def test_tool_removed_is_breaking_and_missing_sample_review():
    a = bundle()
    b = deepcopy(a)
    b["tools"], b["observations"] = [], []
    changes = compare_bundles(a, b)
    assert severities(changes) == {"breaking", "review"}
    assert any(c["path"] == "/tools/now-time-info" for c in changes)


def test_new_tool_and_sample_are_information():
    a, b = bundle(), bundle()
    a["tools"], a["observations"] = [], []
    assert severities(compare_bundles(a, b)) == {"info", "review"}


def test_empty_bundles_never_silently_pass():
    a = bundle()
    a["tools"], a["observations"] = [], []
    assert severities(compare_bundles(a, deepcopy(a))) == {"review"}


def test_contentless_responses_never_silently_pass():
    a = bundle()
    a["observations"][0]["contract"]["blocks"] = []
    assert severities(compare_bundles(a, deepcopy(a))) == {"review"}


def test_empty_text_responses_never_silently_pass():
    a = bundle(representation="empty")
    assert severities(compare_bundles(a, deepcopy(a))) == {"review"}


def test_new_required_field_is_breaking():
    a = bundle({"type": "object", "properties": {"date": {"type": "string"}}})
    b = deepcopy(a)
    b["tools"][0]["inputSchema"]["required"] = ["date"]
    assert severities(compare_bundles(a, b)) == {"breaking"}


def test_removed_required_field_is_information():
    a = bundle({"type": "object", "required": ["date"]})
    b = bundle({"type": "object"})
    assert severities(compare_bundles(a, b)) == {"info"}


@pytest.mark.parametrize(
    "old,new,expected",
    [
        ("number", "integer", "breaking"),
        ("integer", "number", "info"),
        (["string", "null"], "string", "breaking"),
        ("string", ["string", "null"], "info"),
    ],
)
def test_directional_input_type_compatibility(old, new, expected):
    assert severities(compare_bundles(bundle({"type": old}), bundle({"type": new}))) == {expected}


def test_new_constraint_on_unconstrained_schema_is_breaking():
    a, b = bundle(), bundle()
    a["tools"][0]["inputSchema"] = {}
    b["tools"][0]["inputSchema"] = {"type": "object"}
    assert severities(compare_bundles(a, b)) == {"breaking"}


def test_nested_schema_change():
    a = bundle(
        {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "quantity": {"type": "integer"},
                        },
                    },
                }
            },
        }
    )
    b = deepcopy(a)
    b["tools"][0]["inputSchema"]["properties"]["items"]["items"]["required"] = ["quantity"]
    changes = compare_bundles(a, b)
    assert len(changes) == 1
    assert changes[0]["severity"] == "breaking"
    assert changes[0]["path"].endswith("/items/items/required/quantity")


def test_removed_property_is_breaking_when_new_schema_closed():
    a = bundle(
        {"type": "object", "properties": {"old": {"type": "string"}}, "additionalProperties": False}
    )
    b = bundle({"type": "object", "properties": {}, "additionalProperties": False})
    assert severities(compare_bundles(a, b)) == {"breaking"}


def test_removed_property_with_open_schema_requires_review():
    a = bundle({"type": "object", "properties": {"old": {"type": "string"}}})
    assert severities(compare_bundles(a, bundle())) == {"review"}


def test_new_optional_property_in_open_schema_can_constrain_old_requests():
    a = bundle()
    b = bundle({"type": "object", "properties": {"existing": {"type": "integer"}}})
    assert severities(compare_bundles(a, b)) == {"review"}


def test_new_optional_property_in_closed_schema_is_information():
    a = bundle({"type": "object", "additionalProperties": False})
    b = bundle(
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {"new": {"type": "integer"}},
        }
    )
    assert severities(compare_bundles(a, b)) == {"info"}


def test_additional_properties_closing_breaks():
    assert severities(
        compare_bundles(bundle(), bundle({"type": "object", "additionalProperties": False}))
    ) == {"breaking"}


def test_input_item_constraint_added_is_breaking():
    a, b = bundle({"type": "array"}), bundle({"type": "array", "items": {"type": "string"}})
    assert severities(compare_bundles(a, b)) == {"breaking"}


def test_input_item_constraint_removed_is_information():
    a, b = bundle({"type": "array", "items": {"type": "string"}}), bundle({"type": "array"})
    assert severities(compare_bundles(a, b)) == {"info"}


def test_unknown_constraint_changes_are_never_silently_certified():
    a, b = (
        bundle({"type": "string", "pattern": "old"}),
        bundle({"type": "string", "pattern": "new"}),
    )
    assert severities(compare_bundles(a, b)) == {"review"}


def test_omitted_schema_constraints_require_review_even_when_marker_unchanged():
    a = bundle({"type": "object", "x-mcreplay-limited": True})
    assert severities(compare_bundles(a, deepcopy(a))) == {"review"}


def test_opaque_text_requires_review_even_when_representation_unchanged():
    a = bundle(representation="text")
    assert severities(compare_bundles(a, deepcopy(a))) == {"review"}


def test_replaced_dynamic_keys_make_field_identity_uncertain():
    a = bundle(output=shape("object", properties={"_field_a": shape("string")}))
    a["observations"][0]["contract"]["redactedKeys"] = 1
    assert severities(compare_bundles(a, deepcopy(a))) == {"review"}


@pytest.mark.parametrize("use_text", [False, True])
def test_reordered_redacted_keys_cannot_produce_false_breaking(use_text):
    import json

    from mcreplay.core import build_bundle

    def observed(payload):
        response = {"content": []}
        if use_text:
            response["content"] = [{"type": "text", "text": json.dumps(payload)}]
        else:
            response["structuredContent"] = payload
        return build_bundle(
            [{"name": "now-time-info", "inputSchema": {"type": "object"}}],
            [{"name": "now-time-info", "arguments": {}, "response": response}],
            source="synthetic",
        )

    a = observed({"13800138000": 1, "张三": "x"})
    b = observed({"张三": "x", "13800138000": 1})
    assert severities(compare_bundles(a, b)) == {"review"}


def test_identical_error_samples_with_structured_data_need_review():
    a = bundle(output=shape("object", properties={"code": shape("integer")}), error=True)
    a["observations"][0]["contract"]["structured"] = shape(
        "object", properties={"message": shape("string")}
    )
    assert severities(compare_bundles(a, deepcopy(a))) == {"review"}


def test_error_transition_still_breaks_when_payload_keys_redacted():
    a, b = bundle(), bundle(error=True)
    a["observations"][0]["contract"]["redactedKeys"] = 1
    assert severities(compare_bundles(a, b)) == {"breaking", "review"}


def test_output_field_removed_is_breaking():
    a = bundle(output=shape("object", properties={"date": shape("string")}))
    b = bundle(output=shape("object", properties={}))
    assert severities(compare_bundles(a, b)) == {"breaking"}


def test_output_field_added_is_information():
    a, b = (
        bundle(output=shape("object", properties={})),
        bundle(output=shape("object", properties={"date": shape("string")})),
    )
    assert severities(compare_bundles(a, b)) == {"info"}


@pytest.mark.parametrize(
    "old,new,expected",
    [
        ("integer", "string", "breaking"),
        ("integer", "number", "review"),
        ("number", "integer", "breaking"),
        ("null", "string", "breaking"),
    ],
)
def test_output_type_drift(old, new, expected):
    assert severities(compare_bundles(bundle(output=shape(old)), bundle(output=shape(new)))) == {
        expected
    }


@pytest.mark.parametrize(
    "old_items,new_items",
    [
        ([], [shape("string")]),
        ([shape("string")], []),
    ],
)
def test_empty_array_is_unknown_not_empty_contract(old_items, new_items):
    a, b = (
        bundle(output=shape("array", items=old_items)),
        bundle(output=shape("array", items=new_items)),
    )
    assert severities(compare_bundles(a, b)) == {"review"}


def test_homogeneous_array_nested_field_regression():
    a = bundle(output=shape("array", items=[shape("object", properties={"date": shape("string")})]))
    b = bundle(output=shape("array", items=[shape("object", properties={})]))
    assert severities(compare_bundles(a, b)) == {"breaking"}


def test_heterogeneous_array_variant_changes_need_review():
    a = bundle(output=shape("array", items=[shape("string"), shape("integer")]))
    b = bundle(output=shape("array", items=[shape("string")]))
    assert severities(compare_bundles(a, b)) == {"review"}


def test_heterogeneous_array_order_does_not_matter():
    a = bundle(output=shape("array", items=[shape("string"), shape("integer")]))
    b = bundle(output=shape("array", items=[shape("integer"), shape("string")]))
    assert compare_bundles(a, b) == []


def test_representation_change_detected_even_when_same_json_shape():
    assert severities(
        compare_bundles(
            bundle(output=shape("string")),
            bundle(output=shape("string"), representation="fenced-json"),
        )
    ) == {"breaking"}


def test_text_to_empty_never_silently_passes():
    assert severities(
        compare_bundles(bundle(representation="text"), bundle(representation="empty"))
    ) == {"breaking"}


def test_tool_error_transition():
    assert severities(compare_bundles(bundle(), bundle(error=True))) == {"breaking"}
    assert severities(compare_bundles(bundle(error=True), bundle())) == {"review"}


def test_structured_output_disappearance():
    a, b = bundle(), bundle()
    a["observations"][0]["contract"]["structured"] = shape("object", properties={})
    assert severities(compare_bundles(a, b)) == {"breaking"}


def test_mcp_content_block_disappearance():
    a, b = bundle(), bundle()
    b["observations"][0]["contract"]["blocks"] = []
    assert severities(compare_bundles(a, b)) == {"breaking", "review"}


def test_paths_are_unambiguous_json_pointers():
    a = bundle(output=shape("object", properties={"a/b~c": shape("string")}))
    b = bundle(output=shape("object", properties={}))
    assert compare_bundles(a, b)[0]["path"].endswith("a~1b~0c")


def test_deterministic_order_and_no_interpolated_constraint_values():
    a = bundle({"type": "string", "pattern": "PRIVATE-SENTINEL"}, output=shape("integer"))
    b = bundle({"type": "object", "additionalProperties": False}, output=shape("string"))
    first = compare_bundles(a, b)
    assert first == compare_bundles(a, b)
    assert "PRIVATE-SENTINEL" not in repr(first)
    assert [c["severity"] for c in first] == sorted(
        [c["severity"] for c in first], key={"breaking": 0, "review": 1, "info": 2}.get
    )
