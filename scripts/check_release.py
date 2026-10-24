"""Offline release hygiene. This is a narrow check, not a complete secret detector."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECLARATION_SHA256 = "cd28101bcb29cc8fb24b372fe91ce6b42c4a1487a54e01f7ade0c8c6a84241b7"
REQUIRED = (
    "README.md",
    "CONTEST_DECLARATION.md",
    "MCP_INTEGRATION.md",
    "mcp-config.example.json",
    "pyproject.toml",
    "LICENSE",
    "skills/mcreplay/SKILL.md",
)


def main():
    for name in REQUIRED:
        assert (ROOT / name).is_file(), f"Missing release file: {name}"
    actual = hashlib.sha256((ROOT / "CONTEST_DECLARATION.md").read_bytes()).hexdigest()
    assert actual == DECLARATION_SHA256, "Official declaration changed"
    config = json.loads((ROOT / "mcp-config.example.json").read_text())
    assert config["mcpServers"]["mcd-mcp"]["headers"]["Authorization"] == "Bearer ${MCD_MCP_TOKEN}"
    assert not (ROOT / "workbuddy.md").exists(), "Do not claim an unused WorkBuddy reward"
    tracked = (
        subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True)
        .stdout.decode()
        .split("\0")
    )
    patterns = (
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"gh[pousr]_[A-Za-z0-9]{25,}"),
        re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
        re.compile(r"Bearer [A-Za-z0-9_.-]{25,}"),
    )
    for name in filter(None, tracked):
        path = ROOT / name
        assert not path.is_symlink(), "Release must not contain symlinks"
        if path.suffix.lower() in {".svg", ".png", ".jpg", ".gif"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert not any(pattern.search(text) for pattern in patterns), (
            f"Credential pattern in {name}"
        )
    print("Release files, declaration SHA-256, placeholders and credential-pattern checks passed.")


if __name__ == "__main__":
    main()
