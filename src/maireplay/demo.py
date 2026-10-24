"""Invented examples illustrating parser drift; these are NOT official API schemas."""

import json

from .core import build_bundle

NAMES = ("now-time-info", "campaign-calendar", "list-nutrition-foods")


def demo_bundles():
    tools = [{"name": name, "inputSchema": {"type": "object", "properties": {}}} for name in NAMES]
    before = [
        {
            "name": NAMES[0],
            "arguments": {},
            "response": {
                "content": [],
                "structuredContent": {"timestamp": 1792857600, "timezone": "Asia/Shanghai"},
                "isError": False,
            },
        },
        {
            "name": NAMES[1],
            "arguments": {},
            "response": {
                "content": [
                    {
                        "type": "text",
                        "text": "## Original Response\n"
                        + json.dumps(
                            {"events": [{"name": "Invented demo event", "endDate": "2026-10-25"}]}
                        ),
                    }
                ],
                "isError": False,
            },
        },
        {
            "name": NAMES[2],
            "arguments": {},
            "response": {
                "content": [{"type": "text", "text": "Demonstration only; not nutrition data"}],
                "isError": False,
            },
        },
    ]
    after = json.loads(json.dumps(before))
    after[0]["response"]["structuredContent"]["timestamp"] = "changed-to-string"
    after[1]["response"]["content"][0]["text"] = (
        '## Original Response\n{"events":[{"name":"Invented demo event"}]}'
    )
    after[2]["response"]["content"][0]["text"] = ""
    return (
        build_bundle(tools, before, source="synthetic"),
        build_bundle(tools, after, source="synthetic"),
    )
