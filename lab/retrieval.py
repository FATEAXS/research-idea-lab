# -*- coding: utf-8 -*-
"""文献检索：arXiv API + Semantic Scholar Graph API（均免费，S2 无 key 有限流）。
带线程安全限速器；单次检索失败降级为空列表并记日志，不中断流程。"""
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass

import requests

log = logging.getLogger("lab")

_ARXIV_URL = "http://export.arxiv.org/api/query"
_S2_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_OPENALEX_URL = "https://api.openalex.org/works"
_CROSSREF_URL = "https://api.crossref.org/works"

_cfg = {}
_arxiv_limiter = None
_s2_limiter = None
_openalex_limiter = None
_crossref_limiter = None


@dataclass
class Paper:
    title: str
    abstract: str
    year: str
    source: str
    url: str
    authors: list
    venue: str = ""

    def brief(self, max_abs: int = 500) -> str:
        abstract = re.sub(r"\s+", " ", self.abstract or "").strip()
        if len(abstract) > max_abs:
            abstract = abstract[:max_abs] + "..."
        venue = f"〈{self.venue}〉" if self.venue else ""
        return f"{self.title}{venue}（{self.year or '年份未知'}, {self.source}）\n  摘要：{abstract or '（无摘要）'}\n  链接：{self.url}"


def configure(rcfg: dict):
    global _cfg, _arxiv_limiter, _s2_limiter, _openalex_limiter, _crossref_limiter
    _cfg = rcfg or {}
    _arxiv_limiter = _RateLimiter(float(_cfg.get("arxiv_min_interval", 3.0)))
    _s2_limiter = _RateLimiter(float(_cfg.get("s2_min_interval", 1.2)))
    _openalex_limiter = _RateLimiter(float(_cfg.get("openalex_min_interval", 0.5)))
    _crossref_limiter = _RateLimiter(float(_cfg.get("crossref_min_interval", 1.0)))


class _RateLimiter:
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self.lock = threading.Lock()
        self.last = 0.0

    def wait(self):
        with self.lock:
            now = time.time()
            delta = self.min_interval - (now - self.last)
            if delta > 0:
                time.sleep(delta)
                now = time.time()
            self.last = now


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", (t or "").lower())[:80]


def search_arxiv(query: str, limit: int, timeout: int = 20):
    try:
        papers = _arxiv_request(f'all:"{query.strip()}"', limit, timeout)
    except requests.RequestException:
        papers = []
    if not papers:
        # 精确短语太严格或网络抖动时，退化为关键词 AND 搜索再试一次
        terms = " AND ".join(
            f"all:{t}" for t in query.replace('"', " ").split() if t)
        if terms:
            try:
                papers = _arxiv_request(terms, limit, timeout)
            except requests.RequestException as e:
                log.warning("arXiv 关键词查询也失败：%s", e)
    return papers


def _arxiv_request(search_query: str, limit: int, timeout: int = 20):
    _arxiv_limiter.wait()
    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": limit,
        "sortBy": "relevance",
    }
    resp = requests.get(_ARXIV_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    papers = []
    for e in root.findall("a:entry", ns):
        title = " ".join((e.findtext("a:title", "", ns) or "").split())
        abstract = (e.findtext("a:summary", "", ns) or "").strip()
        url = e.findtext("a:id", "", ns) or ""
        year = (e.findtext("a:published", "", ns) or "")[:4]
        authors = [
            (a.findtext("a:name", "", ns) or "").strip()
            for a in e.findall("a:author", ns)
        ]
        if title:
            papers.append(Paper(title=title, abstract=abstract, year=year,
                                source="arXiv", url=url, authors=authors))
    return papers


def search_s2(query: str, limit: int, timeout: int = 30):
    api_key = _cfg.get("s2_api_key") or ""
    headers = {"x-api-key": api_key} if api_key else {}
    for attempt in range(2):
        _s2_limiter.wait()
        resp = requests.get(
            _S2_URL,
            params={"query": query, "limit": limit,
                    "fields": "title,abstract,year,url"},
            headers=headers, timeout=timeout,
        )
        if resp.status_code == 429:
            log.warning("Semantic Scholar 限流（429），%d 秒后重试", 5)
            time.sleep(5)
            continue
        resp.raise_for_status()
        papers = []
        for p in resp.json().get("data") or []:
            if p.get("title"):
                papers.append(Paper(
                    title=p["title"], abstract=p.get("abstract") or "",
                    year=str(p.get("year") or ""), source="Semantic Scholar",
                    url=p.get("url") or "", authors=[]))
        return papers
    log.warning("Semantic Scholar 持续限流，跳过查询：%s", query)
    return []


def _clean_html(text: str) -> str:
    """Crossref 的标题/摘要/期刊名常带 JATS 标签和 HTML 实体（<sub>、&amp;），统一清洗。"""
    import html as _html
    text = _html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _rebuild_abstract(inv) -> str:
    """OpenAlex 的摘要以 倒排索引 形式返回，这里还原成正常文本。"""
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


def search_openalex(query: str, limit: int, timeout: int = 30):
    """OpenAlex：免 key、免费、限额宽松（约10万次/天），摘要覆盖率高。
   偶发 429（共享出口 IP 被节流）时自动退避重试。"""
    params = {
        "search": query,
        "per-page": limit,
        "mailto": "research-idea-lab@example.com",  # 进入 polite pool，限流更宽
        "select": "display_name,publication_year,doi,id,"
                  "abstract_inverted_index,authorships,primary_location",
    }
    resp = None
    for attempt in range(3):
        _openalex_limiter.wait()
        try:
            resp = requests.get(_OPENALEX_URL, params=params, timeout=timeout)
        except requests.RequestException:
            if attempt == 2:
                return []
            time.sleep(3 * (attempt + 1))
            continue
        if resp.status_code in (429, 500, 502, 503):
            if attempt == 2:
                log.warning("OpenAlex 持续限流，跳过查询：%s", query)
                return []
            time.sleep(3 * (attempt + 1))
            continue
        break
    resp.raise_for_status()
    papers = []
    for w in resp.json().get("results") or []:
        title = (w.get("display_name") or "").strip()
        if not title:
            continue
        authors = [
            (a.get("author") or {}).get("display_name", "")
            for a in (w.get("authorships") or [])
        ][:6]
        papers.append(Paper(
            title=title,
            abstract=_rebuild_abstract(w.get("abstract_inverted_index")),
            year=str(w.get("publication_year") or ""),
            source="OpenAlex",
            venue=((w.get("primary_location") or {}).get("source") or {})
                .get("display_name", "") or "",
            url=w.get("doi") or w.get("id") or "",
            authors=authors))
    return papers


def search_crossref(query: str, limit: int, timeout: int = 30):
    """Crossref：免 key、免费、覆盖全部期刊（控制/制造领域文献主要在期刊不在 arXiv）。
   摘要仅部分出版商提供，缺失时只剩标题元数据。"""
    params = {
        "query": query, "rows": limit,
        "mailto": "research-idea-lab@example.com",
        "filter": "type:journal-article",  # 服务端过滤：只要期刊论文
        "select": "title,abstract,issued,DOI,author,container-title",
    }
    resp = None
    for attempt in range(3):
        _crossref_limiter.wait()
        try:
            resp = requests.get(_CROSSREF_URL, params=params, timeout=timeout)
        except requests.RequestException:
            if attempt == 2:
                return []
            time.sleep(3 * (attempt + 1))
            continue
        if resp.status_code in (429, 500, 502, 503):
            if attempt == 2:
                log.warning("Crossref 持续限流，跳过查询：%s", query)
                return []
            time.sleep(3 * (attempt + 1))
            continue
        break
    papers = []
    for it in resp.json().get("message", {}).get("items") or []:
        title = _clean_html((it.get("title") or [""])[0])
        if not title:
            continue
        venue = _clean_html(it.get("container-title")[0]) \
            if isinstance(it.get("container-title"), list) and it["container-title"] else ""
        abstract = _clean_html(it.get("abstract") or "")
        year = ""
        issued = (it.get("issued") or {}).get("date-parts") or []
        if issued and issued[0]:
            year = str(issued[0][0] or "")
        authors = [
            f"{(a.get('given') or '')} {(a.get('family') or '')}".strip()
            for a in (it.get("author") or [])
        ][:6]
        papers.append(Paper(title=title, abstract=abstract, year=year,
                            source="Crossref", venue=venue,
                            url=f"https://doi.org/{it.get('DOI')}" if it.get("DOI") else "",
                            authors=authors))
    return papers


def search(queries, mock: bool = False, max_queries: int = 6):
    """跑一批查询并合并去重。mock=True 时返回内置假论文（离线联调）。"""
    if mock:
        return [
            Paper(title="MockPaper: Data-Efficient LLM Fine-tuning via Subset Selection",
                  abstract="这是Mock论文，仅用于离线联调流程，不代表真实文献。",
                  year="2024", source="Mock", url="https://example.com/mock-1", authors=[]),
            Paper(title="MockPaper: LoRA and Beyond: Parameter-Efficient Adaptation",
                  abstract="这是Mock论文，仅用于离线联调流程。",
                  year="2023", source="Mock", url="https://example.com/mock-2", authors=[]),
            Paper(title="MockPaper: Curriculum Learning Revisited",
                  abstract="这是Mock论文，仅用于离线联调流程。",
                  year="2022", source="Mock", url="https://example.com/mock-3", authors=[]),
        ]
    providers = _cfg.get("providers") or ["arxiv"]
    limit = int(_cfg.get("max_per_query", 8))
    papers, seen = [], set()
    for q in [q for q in queries if q and q.strip()][:max_queries]:
        log.info("检索：%s", q)
        for prov in providers:
            try:
                if prov == "arxiv":
                    got = search_arxiv(q, limit)
                elif prov == "openalex":
                    got = search_openalex(q, limit)
                elif prov == "crossref":
                    got = search_crossref(q, limit)
                elif prov == "s2":
                    got = search_s2(q, limit)
                else:
                    log.warning("未知检索来源：%s", prov)
                    continue
                for p in got:
                    key = _norm_title(p.title)
                    if key and key not in seen:
                        seen.add(key)
                        papers.append(p)
            except Exception as e:
                log.warning("检索失败（来源 %s，查询 %s）：%s", prov, q, e)
    log.info("检索完成，共 %d 篇（去重后）", len(papers))
    return papers


def papers_block(papers, max_abs: int = 500) -> str:
    """把检索结果渲染成带编号的文本块，供提示词引用（[编号]）。"""
    if not papers:
        return "（本次检索没有返回结果）"
    return "\n".join(f"[{i}] {p.brief(max_abs)}" for i, p in enumerate(papers, 1))


def papers_to_json(papers):
    return [asdict(p) for p in papers]
