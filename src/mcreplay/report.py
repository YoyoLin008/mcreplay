"""A standalone report. No scripts, remote fonts, telemetry or raw responses."""

from collections import Counter
from html import escape
from pathlib import Path

# Original packaging-inspired shapes; deliberately not an official logo.
MOTIF = """
<g transform="translate(113 22) rotate(9 115 110)">
  <path d="M38 4H211V196L199 188L187 196L175 188L163 196L151 188L139 196L127 188
  L115 196L103 188L91 196L79 188L67 196L55 188L38 196Z" fill="#fff8e7"/>
  <path d="M63 36H182M63 49H146M63 79H169M63 92H182M63 105H161" stroke="#d90016"
  stroke-width="7"/>
  <path d="M63 139H117M63 151H163" stroke="#d90016" stroke-width="4"
  stroke-dasharray="4 5"/>
  <circle cx="176" cy="153" r="21" fill="#ffbc0d"/>
  <path d="m166 153 7 7 13-16" fill="none" stroke="#292218" stroke-width="4"/>
</g>
<g transform="translate(22 47) rotate(-8 98 102)">
  <path d="M38 111 28 24 46 22 57 112M61 110 59 6 78 6 81 113
  M88 109 91 19 110 21 106 116M115 111 126 0 145 2 135 118
  M140 116 157 31 176 35 158 120" fill="#ffbc0d"/>
  <path d="M24 96Q96 130 177 96L159 202Q98 220 43 202Z" fill="#ffbc0d"/>
  <path d="M42 119Q98 141 159 119L147 190Q98 203 55 190Z" fill="#d90016"/>
  <path d="M119 154a24 24 0 1 0 0 25" fill="none" stroke="#fff8e7"
  stroke-width="9" stroke-linecap="square"/>
  <path d="m110 139 23 8-20 15Z" fill="#fff8e7"/>
</g>
<path d="m32 29 8-12m-17 8 13 3M306 210l11 11m-1-17-9 10" stroke="#ffbc0d"
stroke-width="5"/>
"""

CSS = """
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
"Microsoft YaHei",sans-serif;color:#292218;background:#fff8e7}
*{box-sizing:border-box}body{margin:0;padding:40px 24px}main{max-width:1100px;margin:auto}
.top{position:relative;background:#d90016;color:#fff8e7;padding:36px 42px 32px;
overflow:hidden}.top-copy{position:relative;z-index:1;max-width:72%}
h1{font-size:58px;font-weight:850;line-height:1.1;letter-spacing:-.045em;margin:0 0 20px}
h1 span{color:#ffbc0d}.top p{max-width:590px;font-size:15px;line-height:1.8;margin:16px 0 0}
.badge{display:inline-block;background:#fff8e7;color:#292218;padding:7px 11px;
font-size:12px;font-weight:650}.motif{position:absolute;width:290px;right:22px;top:24px}
.checker{height:16px;background:repeating-conic-gradient(#d90016 0% 25%,#ffbc0d 0% 50%)
0 0/32px 32px}.metrics{display:flex;align-items:center;gap:0;border-bottom:2px solid
#292218;margin:28px 0 0;padding-bottom:20px}.metric{display:flex;align-items:baseline;
gap:10px;flex:1;padding:0 22px;border-left:1px solid #d8cdb9}.metric:first-child{
border-left:0;padding-left:0}.metric b{font-size:40px;line-height:1;font-weight:850}
.metric span{font-size:14px;font-weight:650}.breaking{color:#bd0013}.review{color:#785400}
.info{color:#4b5746}.receipt{background:#fffdf7;padding:0 24px;border:1px solid #e4d7bf;
border-top:0;box-shadow:0 5px 0 #eadfc9}table{width:100%;border-collapse:collapse;
table-layout:fixed}th,td{text-align:left;vertical-align:top;padding:20px 12px;
border-bottom:1px dashed #cdbfa6;line-height:1.6}th{font-size:12px;font-weight:700;
color:#665b4b}td{font-size:14px}th:first-child{width:17%}th:nth-child(2){width:43%}
th:last-child{width:40%}td:first-child{font-weight:750;white-space:nowrap}
tr:last-child td{border-bottom:0}code{font-family:ui-monospace,SFMono-Regular,monospace;
font-size:12px;overflow-wrap:anywhere}.notice{font-size:13px;line-height:1.8;
padding:18px 0 0;margin:18px 0 0;color:#665b4b}footer{font-size:12px;color:#665b4b;
margin-top:14px;padding-top:14px;border-top:1px solid #d8cdb9}
@media(max-width:720px){body{padding:16px 12px}.top{padding:28px 24px}.top-copy{
max-width:100%}h1{font-size:36px;max-width:72%}.motif{width:145px;right:8px;top:10px}
.top p{font-size:13px}.badge{font-size:11px}.metrics{margin-top:20px;gap:8px}
.metric{padding:0 8px;display:block}.metric b{font-size:32px}.metric span{display:block;
font-size:12px;margin-top:6px}.receipt{padding:0 16px}table,tbody,tr,td{display:block;
width:100%}thead{display:none}tr{padding:16px 0;border-bottom:1px dashed #cdbfa6}
tr:last-child{border-bottom:0}td{padding:4px 0;border-bottom:0;font-size:13px}
td:first-child{font-size:14px}code{font-size:11px}}
@media(max-width:380px){h1{font-size:30px}.motif{width:130px;top:10px;right:6px}}
"""


def render_report(findings: list[dict], before: dict, after: dict) -> str:
    counts = Counter(f["severity"] for f in findings)
    labels = {"breaking": "破坏风险", "review": "需要审查", "info": "兼容性提示"}
    cards = "".join(
        f'<div class="metric"><b class="{key}">{counts[key]}</b><span>{label}</span></div>'
        for key, label in labels.items()
    )
    rows = (
        "".join(
            f'<tr><td class="{escape(f["severity"])}">{labels.get(f["severity"], "审查")}</td>'
            f"<td><code>{escape(f['path'])}</code></td><td>{escape(f['message'])}</td></tr>"
            for f in findings
        )
        or '<tr><td colspan="3">未发现已支持范围内的结构变化。</td></tr>'
    )
    source = f"{before['source']} → {after['source']}"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>McReplay · 本地结构比较</title><style>{CSS}</style></head><body><main>
<header class="top"><div class="top-copy">
<h1>哪里变了？<br><span>回放一下。</span></h1>
<span class="badge">{escape(source)} · 真实值已删除的结构样本</span>
<p>比较字段、类型与响应格式。保留结构，把变化看清楚。</p></div>
<svg class="motif" viewBox="0 0 340 280" aria-hidden="true">{MOTIF}</svg></header>
<div class="checker" aria-hidden="true"></div><div class="metrics">{cards}</div>
<div class="receipt"><table><thead><tr><th>检查结果</th><th>变化位置</th><th>变化说明</th>
</tr></thead><tbody>{rows}</tbody></table></div>
<div class="notice">此报告比较有限观察样本，并非官方完整契约。合成回放不能验证金额、日期、
库存或优惠资格。text 表示未解析文本，必须人工检查适配器行为。</div>
<footer>离线生成 · 无远程资源、无埋点 · synthetic 表示合成演示 · 非麦当劳官方产品</footer>
</main></body></html>"""


def write_report(path: Path, content: str) -> None:
    # Exclusive creation prevents accidental replacement or following an output symlink.
    import os

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)
