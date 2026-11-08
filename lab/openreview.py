# -*- coding: utf-8 -*-
"""Oral 论文模式库：为 ideate 提供「顶会 oral 论文如何发现 idea」的学习材料。

数据来源优先级：
1. data/oral_patterns.md —— 静态模式库（默认，随仓库维护，无需联网）；
2. OpenReview 匿名抓取 —— 仅当配置 openreview.fetch: true 时尝试，
   绝不使用任何账号凭据；匿名接口（403/限流）失败则静默回退静态库。"""
import logging
from pathlib import Path

import requests

log = logging.getLogger("lab")

_STATIC = Path(__file__).resolve().parent.parent / "data" / "oral_patterns.md"
_API2 = "https://api2.openreview.net/notes"

# 常见顶会的 venueid（按需在 config 的 openreview.venueids 里增删）
DEFAULT_VENUEIDS = [
    "ICLR.cc/2025/Conference",
    "ICLR.cc/2024/Conference",
    "NeurIPS.cc/2024/Conference",
    "ICML.cc/2024/Conference",
]


def load_static() -> str:
    if _STATIC.exists():
        return _STATIC.read_text(encoding="utf-8")
    return "（模式库文件缺失：data/oral_patterns.md）"


def _fetch_anonymous(venueid: str, limit: int = 1000):
    """匿名拉取某 venue 的 oral/spotlight 论文（标题+摘要）。
    不携带任何账号凭据；失败返回空列表。"""
    headers = {"User-Agent": "research-idea-lab/1.0 (anonymous public data)"}
    papers, offset = [], 0
    while True:
        try:
            r = requests.get(
                _API2,
                params={"content.venueid": venueid, "limit": limit,
                        "offset": offset},
                headers=headers, timeout=30,
            )
            if r.status_code != 200:
                log.info("OpenReview %s 匿名访问不可用（HTTP %s）", venueid,
                         r.status_code)
                return papers
            notes = r.json().get("notes", [])
        except requests.RequestException as e:
            log.info("OpenReview 访问失败（%s），回退静态模式库", e)
            return papers
        for n in notes:
            c = n.get("content", {})
            def _v(k):
                v = (c.get(k) or {}).get("value")
                return v if isinstance(v, str) else ""
            venue = _v("venue")
            if any(w in venue.lower() for w in ("oral", "spotlight")):
                papers.append({"title": _v("title"), "abstract": _v("abstract"),
                               "venue": venue})
        if len(notes) < limit:
            break
        offset += limit
    return papers


def build_oral_patterns(rcfg: dict = None, mock: bool = False,
                        topic: str = "") -> str:
    """返回给 ideate 提示词的 oral 模式材料。静态库为主，可选匿名抓取增强。"""
    rcfg = rcfg or {}
    if mock:
        return load_static()
    text = load_static()
    if not rcfg.get("fetch"):
        return text
    # 仅当显式开启 fetch 才匿名抓取（openreview.fetch: true）
    venueids = rcfg.get("venueids") or DEFAULT_VENUEIDS
    fetched = []
    for vid in venueids:
        fetched.extend(_fetch_anonymous(vid))
    if fetched:
        lines = ["\n## 四、OpenReview 匿名抓取的最新 oral/spotlight 论文（摘要）"]
        for p in fetched[:20]:
            lines.append(f"- {p['title']}（{p['venue']}）："
                         f"{p['abstract'][:180]}...")
        log.info("OpenReview 匿名抓取到 %d 篇 oral/spotlight", len(fetched))
        text += "\n".join(lines)
    else:
        log.info("OpenReview 匿名抓取不可用，仅使用静态模式库")
    return text
