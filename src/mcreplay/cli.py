"""Human-facing CLI; all commands operate locally and never read credentials."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import __version__
from .core import atomic_write_json, build_bundle, load_bundle, read_json
from .diff import compare_bundles
from .report import render_report, write_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="McReplay 麦回放 · 本地结构样本与 MCP 回放")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="生成明确标记的合成演示")
    demo.add_argument("--out-dir", type=Path, default=Path("demo-output"))
    imp = sub.add_parser("import", help="从合法导出的 MCP JSON 删除真实值")
    imp.add_argument("export", type=Path)
    imp.add_argument("--out", required=True, type=Path)
    comp = sub.add_parser("compare", help="比较两个结构包；退出码 2=破坏风险，3=审查")
    comp.add_argument("before", type=Path)
    comp.add_argument("after", type=Path)
    comp.add_argument("--html", type=Path)
    comp.add_argument("--json", action="store_true")
    rep = sub.add_parser("replay", help="通过本地 stdio MCP 回放合成结构")
    rep.add_argument("bundle", type=Path)
    cap = sub.add_parser("capture", help="本地 stdio 接收一次响应，删除真实值后保存")
    cap.add_argument("--out", "--output", required=True, type=Path)
    return parser


def _read_export(path: Path) -> dict:
    value = read_json(path)
    if not isinstance(value, dict) or set(value) != {"tools", "observations"}:
        raise ValueError("invalid import envelope")
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "demo":
            from .demo import demo_bundles

            before, after = demo_bundles()
            args.out_dir.mkdir(parents=True, exist_ok=False)
            atomic_write_json(args.out_dir / "before.json", before)
            atomic_write_json(args.out_dir / "after.json", after)
            findings = compare_bundles(before, after)
            write_report(args.out_dir / "report.html", render_report(findings, before, after))
            print("已生成合成演示：before.json、after.json、report.html。不是官方实测数据。")
            for finding in findings:
                print(f"{finding['severity']}: {finding['path']}: {finding['message']}")
            return 0
        if args.command == "import":
            raw = _read_export(args.export)
            bundle = build_bundle(raw["tools"], raw["observations"], source="user-import")
            atomic_write_json(args.out, bundle)
            print("本地结构包已保存；原始值未写入输出。分享前请检查字段名。")
            return 0
        if args.command == "compare":
            before, after = load_bundle(args.before), load_bundle(args.after)
            findings = compare_bundles(before, after)
            if args.html:
                write_report(args.html, render_report(findings, before, after))
            if args.json:
                print(json.dumps(findings, ensure_ascii=False, indent=2))
            else:
                for finding in findings:
                    print(f"{finding['severity']}: {finding['path']}: {finding['message']}")
                if not findings:
                    print("未发现已支持范围内的结构变化；不代表完整业务兼容。")
            if any(f["severity"] == "breaking" for f in findings):
                return 2
            return 3 if any(f["severity"] == "review" for f in findings) else 0
        if args.command == "replay":
            from .server import run_replay

            asyncio.run(run_replay(load_bundle(args.bundle)))
            return 0
        if args.command == "capture":
            from .server import run_capture

            asyncio.run(run_capture(args.out))
            return 0
    except (ValueError, OSError, TypeError, KeyError, RecursionError):
        # Do not echo upstream exception bodies or input values, even on malformed data.
        print(
            "操作失败：检查输入格式、大小、支持的工具及输出路径（不覆盖已有文件）。",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        return 130
    return 1
