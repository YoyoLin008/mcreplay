import json

import pytest

from maireplay.cli import main
from maireplay.core import atomic_write_json, build_bundle
from maireplay.demo import demo_bundles
from maireplay.report import render_report


def test_demo_complete_journey_and_breaking_exit(tmp_path, capsys):
    output = tmp_path / "demo"
    assert main(["demo", "--out-dir", str(output)]) == 0
    assert "合成" in capsys.readouterr().out
    report = (output / "report.html").read_text()
    assert "synthetic → synthetic" in report
    assert "timestamp" in report
    assert main(["compare", str(output / "before.json"), str(output / "after.json")]) == 2
    assert main(["demo", "--out-dir", str(output)]) == 1


def test_identical_json_sample_passes(tmp_path):
    before, _ = demo_bundles()
    before["tools"] = [t for t in before["tools"] if t["name"] == "now-time-info"]
    before["observations"] = [o for o in before["observations"] if o["name"] == "now-time-info"]
    path = tmp_path / "sample.json"
    atomic_write_json(path, before)
    assert main(["compare", str(path), str(path), "--json"]) == 0


def test_opaque_text_is_review_not_false_green(tmp_path):
    bundle, _ = demo_bundles()
    path = tmp_path / "sample.json"
    atomic_write_json(path, bundle)
    assert main(["compare", str(path), str(path)]) == 3


def test_import_erases_values_without_leaking_logs(tmp_path, capsys):
    secret = "PERSONAL_SENTINEL_DO_NOT_PUBLISH"
    export = {
        "tools": [{"name": "campaign-calendar", "inputSchema": {"type": "object"}}],
        "observations": [
            {
                "name": "campaign-calendar",
                "arguments": {},
                "response": {
                    "content": [
                        {"type": "text", "text": json.dumps({"name": secret, "points": 92345})}
                    ]
                },
            }
        ],
    }
    source, output = tmp_path / "raw.json", tmp_path / "safe.json"
    source.write_text(json.dumps(export))
    assert main(["import", str(source), "--out", str(output)]) == 0
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err + output.read_text()
    assert "92345" not in output.read_text()
    assert main(["import", str(source), "--out", str(output)]) == 1
    assert source.read_text() == json.dumps(export)


@pytest.mark.parametrize("data", ["bad SECRET_PAYLOAD", "null", "[]", '{"tools":[]}', '"secret"'])
def test_invalid_import_safe_error(tmp_path, capsys, data):
    source = tmp_path / "input.json"
    source.write_text(data)
    assert main(["import", str(source), "--out", str(tmp_path / "safe.json")]) == 1
    assert "SECRET_PAYLOAD" not in capsys.readouterr().err
    assert not (tmp_path / "safe.json").exists()


def test_report_escapes_untrusted_findings():
    bundle = {"source": "synthetic"}
    report = render_report(
        [{"severity": "review", "path": "</td><script>bad()</script>", "message": "<img src=x>"}],
        bundle,
        bundle,
    )
    assert "<script>" not in report
    assert "&lt;script&gt;" in report
    assert "Content-Security-Policy" in report


def test_unknown_transaction_import_rejected(tmp_path):
    export = tmp_path / "input.json"
    export.write_text(json.dumps({"tools": [{"name": "create-order"}], "observations": []}))
    assert main(["import", str(export), "--out", str(tmp_path / "safe.json")]) == 1


def test_source_is_not_proof_of_authenticated_result():
    sample = build_bundle([], [], "user-import")
    assert sample["source"] == "user-import"  # no 'live-verified' provenance category exists
