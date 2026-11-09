#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Markdown 文档渲染成带样式的网页并打开。
用法：python md_preview.py 文档.md [更多.md ...] [--no-open]"""
import sys
import os
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import markdown
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "markdown"],
                   check=False)
    import markdown

CSS = """
body{font-family:"Microsoft YaHei",system-ui,sans-serif;max-width:920px;margin:28px auto;
     padding:0 18px;color:#222;line-height:1.75;background:#fafafa}
h1{font-size:1.5em;border-bottom:3px solid #2c6fbb;padding-bottom:8px}
h2{font-size:1.25em;border-bottom:1px solid #d5d5d5;padding-bottom:4px;margin-top:1.8em}
h3{color:#2c6fbb}
code{background:#f0f2f5;border-radius:4px;padding:1px 5px;font-family:Consolas,monospace}
pre{background:#f0f2f5;border-radius:8px;padding:12px 14px;overflow-x:auto}
pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:.92em}
th,td{border:1px solid #e0e0e0;padding:7px 10px;text-align:left}
th{background:#eef3f9}
blockquote{border-left:4px solid #2c6fbb;background:#eef4fb;margin:12px 0;padding:8px 14px;color:#345}
strong{color:#111}
"""


def convert(md_text: str) -> str:
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    return (f'<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>方法设计</title><style>{CSS}</style></head>'
            f'<body>{body}</body></html>')


def main():
    args = [a for a in sys.argv[1:] if a != "--no-open"]
    open_browser = "--no-open" not in sys.argv
    for a in args:
        src = Path(a)
        out = src.with_suffix(".html")
        out.write_text(convert(src.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"已生成 {out}")
        if open_browser:
            os.startfile(os.path.abspath(str(out)))
            print("已在浏览器打开")


if __name__ == "__main__":
    main()
