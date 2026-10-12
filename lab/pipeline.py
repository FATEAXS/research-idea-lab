# -*- coding: utf-8 -*-
"""流程编排（状态机）：

  调研(A) → 提出N个idea(A)
    → [ 独立评审(B查重 / C跨域 / D红队) → 匿名辩论 → 导师终审 → 修订(A) ] × max_rounds
  → 排名报告 → 为Top-K生成实验规格（预注册）

设计原则（对应真实组会）：
  1. 一切围绕 Idea Card 迭代，不围绕聊天记录；
  2. 评审先独立、后辩论（避免锚定效应）；
  3. novelty 必须有检索证据（B 评审前先查先行工作）；
  4. 导师(Meta)有真正的一票否决权 + 明确的 kill 标准；
  5. 全部中间产物落盘，每张卡的每次修订可 diff。
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from lab.idea_card import IdeaCard
from lab.llm import MockClient, OpenAICompatClient, Usage, call_json
from lab import promptkit, retrieval

log = logging.getLogger("lab")

SCORE_KEYS = ["novelty", "feasibility", "significance"]
# 刻意让 feasibility 权重最高：LLM 生成的 idea 普遍「新颖有余、可行不足」
WEIGHTS = {"novelty": 0.35, "feasibility": 0.40, "significance": 0.25}
REVIEWERS = [
    ("B", "reviewer_domain", "b_review"),
    ("C", "reviewer_cross", "c_review"),
    ("D", "reviewer_theory", "d_review"),
]


def _clamp(x, lo=1, hi=10):
    return max(lo, min(hi, x))


def weighted_score(mean_scores: dict) -> float:
    return sum(WEIGHTS[k] * float(mean_scores.get(k, 5)) for k in SCORE_KEYS)


def _mean_scores(score_dicts) -> dict:
    out = {}
    for k in SCORE_KEYS:
        vals = [float(s.get(k, 5)) for s in score_dicts]
        out[k] = sum(vals) / len(vals) if vals else 5.0
    return out


class Pipeline:
    def __init__(self, cfg: dict, run_dir):
        self.cfg = cfg
        self.run_dir = Path(run_dir)
        self.usage = Usage()
        self.mock = cfg["llm"].get("provider") == "mock"
        if self.mock:
            self.llm = MockClient(cfg, self.usage)
        else:
            self.llm = OpenAICompatClient(cfg, self.usage)
        self.prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
        retrieval.configure(cfg.get("retrieval", {}))
        for sub in ["survey", "final"]:
            (self.run_dir / sub).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def _resolve_model(self, model_role):
        """解析角色的模型配置：字符串=用全局服务；字典=可覆盖 model/base_url/api_key
        （实现不同角色混用不同厂商的专家模型）。"""
        llm_cfg = self.cfg["llm"]
        models = llm_cfg.get("models", {})
        spec = models.get(model_role) or models.get("researcher")
        base_url = llm_cfg.get("base_url")
        api_key = llm_cfg.get("api_key")
        if isinstance(spec, dict):
            fallback = models.get("researcher")
            model = spec.get("model") or \
                (fallback if isinstance(fallback, str) else "deepseek-chat")
            base_url = spec.get("base_url", base_url)
            api_key = spec.get("api_key", api_key)
            return str(model), base_url, api_key
        return str(spec), base_url, api_key

    def _call(self, model_role, task, prompt_name, **variables):
        system, user = promptkit.render(self.prompts_dir, prompt_name, **variables)
        model, base_url, api_key = self._resolve_model(model_role)
        return call_json(self.llm, model, task, system, user,
                         base_url=base_url, api_key=api_key)

    @staticmethod
    def _save(path, data):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            path.write_text(data, encoding="utf-8")
        else:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    # ------------------------------------------------------------------
    def phase_survey(self, topic: str):
        log.info("== 阶段1/4：文献调研 ==")
        q = self._call("researcher", "survey_queries", "a_survey_queries",
                       topic=topic, n_queries=6)
        queries = [str(x) for x in (q.get("queries") or [])][:6]
        self._save(self.run_dir / "survey" / "queries.json", queries)
        log.info("调研查询：%s", queries)

        papers = retrieval.search(queries, mock=self.mock)
        papers = self._filter_papers(papers)

        # 文献池保底：不足 min_survey_papers 时换角度补充检索（最多补两轮）
        min_papers = int(self.cfg.get("retrieval", {})
                         .get("min_survey_papers", 40))
        seen = {retrieval._norm_title(p.title) for p in papers}
        extra_round = 0
        while len(papers) < min_papers and extra_round < 2:
            extra_round += 1
            log.info("调研文献 %d 篇 < 保底 %d 篇，第 %d 次补充检索",
                     len(papers), min_papers, extra_round)
            mq = self._call("researcher", "survey_queries", "a_survey_queries",
                            topic=topic + "（补充检索：换不同切入角度，避免与已有查询重复）",
                            n_queries=6)
            mqs = [str(x) for x in (mq.get("queries") or [])][:6]
            fresh = [p for p in retrieval.search(mqs, mock=self.mock)
                     if retrieval._norm_title(p.title) not in seen]
            fresh = self._filter_papers(fresh)
            for p in fresh:
                seen.add(retrieval._norm_title(p.title))
            papers.extend(fresh)

        self._save(self.run_dir / "survey" / "papers.json",
                   retrieval.papers_to_json(papers))
        log.info("调研文献池最终 %d 篇", len(papers))

        sv = self._call("researcher", "write_survey", "a_write_survey",
                        topic=topic, papers_block=retrieval.papers_block(papers))
        survey_md = str(sv.get("survey") or "")
        insights = "\n".join(f"- {x}" for x in (sv.get("key_insights") or []))
        self._save(self.run_dir / "survey" / "survey.md", survey_md)
        log.info("调研综述完成（%d 字），机会点 %d 条", len(survey_md),
                 len(sv.get("key_insights") or []))
        return survey_md, insights, papers

    def phase_ideate(self, topic, survey_md, insights):
        log.info("== 阶段2/4：提出idea ==")
        n = int(self.cfg["pipeline"].get("num_ideas", 4))
        resp = self._call("researcher", "ideate", "a_ideate", topic=topic,
                          survey=survey_md, insights=insights, num_ideas=n)
        cards = [IdeaCard(d, i)
                 for i, d in enumerate(resp.get("ideas") or [], 1)][:n]
        if not cards:
            raise RuntimeError("idea 提出阶段没有产出任何卡片，请检查模型输出")
        self._save(self.run_dir / "round_0" / "idea_cards.json",
                   [c.to_dict() for c in cards])
        for c in cards:
            log.info("提出 %s：%s", c.id, c.title)
        return cards

    # ------------------------------------------------------------------
    def _filter_papers(self, papers):
        """期刊/会议分级过滤：一区二区/顶会顶刊才放行，拿不准就剔除。
        arXiv 预印本默认保留（顶刊工作多先挂预印本）。失败时保留全部（降级）。"""
        rf = self.cfg.get("retrieval", {})
        if (not papers) or self.mock or not rf.get("quality_filter", True):
            return papers
        arxiv = [p for p in papers if p.source == "arXiv"]
        candidates = [p for p in papers if p.source != "arXiv"]
        if not candidates:
            return papers
        listing = "\n".join(
            f"[{i}] {p.title}｜{p.venue or '来源不明'}｜{p.year}"
            for i, p in enumerate(candidates, 1))
        try:
            resp = self._call("researcher", "filter", "filter_papers",
                              papers_block=listing)
            keep = {int(str(x).strip()) for x in (resp.get("keep") or [])
                    if str(x).strip().isdigit()}
        except Exception as e:
            log.warning("质量过滤失败（保留全部，降级）：%s", e)
            return papers
        kept = [p for i, p in enumerate(candidates, 1) if i in keep]
        log.info("质量过滤：%d 篇候选 → 保留 %d 篇（另保留 %d 篇 arXiv 预印本）%s",
                 len(candidates), len(kept), len(arxiv),
                 resp.get("dropped_note") or "")
        return kept + arxiv

    def _review_one(self, role, model_role, review_prompt, card_json,
                    with_retrieval):
        """单个评审员的完整流程；失败时降级为中性分，不拖垮整轮。"""
        try:
            papers_block = "（该评审未使用检索）"
            papers = []
            if with_retrieval:
                q = self._call(model_role, "prior_queries",
                               f"{role.lower()}_queries", idea_card=card_json)
                queries = [str(x) for x in (q.get("queries") or [])][:4]
                papers = retrieval.search(queries, mock=self.mock)
                papers = self._filter_papers(papers)
                papers_block = retrieval.papers_block(papers)
            rev = self._call(model_role, f"review_{role.lower()}",
                             review_prompt, idea_card=card_json,
                             papers_block=papers_block)
            return rev, papers
        except Exception as e:
            log.error("评审 %s 失败（降级为中性评审）：%s", role, e)
            return {"scores": {k: 5 for k in SCORE_KEYS},
                    "error": str(e),
                    "strengths": [], "weaknesses": ["评审过程出错，本次意见缺失"],
                    "action_items": []}, []

    def _review_panel(self, card: IdeaCard, round_dir: Path):
        """B/C/D 独立评审（互相不可见），B/C 带检索、D 纯红队。"""
        card_json = card.to_json()
        reviews, papers_by_role = {}, {}
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {}
            for role, model_role, prompt in REVIEWERS:
                with_retrieval = role in ("B", "C")
                futures[ex.submit(self._review_one, role, model_role, prompt,
                                  card_json, with_retrieval)] = role
            for fut in as_completed(futures):
                role = futures[fut]
                reviews[role], papers_by_role[role] = fut.result()

        for role in ("B", "C", "D"):
            self._save(round_dir / card.id / "reviews" / f"{role}.json",
                       reviews[role])
            if papers_by_role.get(role):
                self._save(round_dir / card.id / "reviews" /
                           f"{role}_retrieved_papers.json",
                           retrieval.papers_to_json(papers_by_role[role]))
        log.info("%s 独立评审完成：%s", card.id,
                 {r: reviews[r].get("scores") for r in reviews})
        return reviews

    def _debate(self, card: IdeaCard, reviews: dict, round_dir: Path):
        """匿名辩论：每个评审看到其他人的意见后，可回应并微调分数（±2以内）。"""
        debates, final_scores = {}, {}
        for role, model_role, _ in REVIEWERS:
            peers = {k: v for k, v in reviews.items() if k != role}
            try:
                reb = self._call(model_role, "debate", "debate",
                                 role_name=role,
                                 idea_card=card.to_json(),
                                 own_review=json.dumps(reviews[role],
                                                       ensure_ascii=False),
                                 peers_reviews=json.dumps(peers,
                                                          ensure_ascii=False))
            except Exception as e:
                log.error("辩论环节 %s 失败（跳过）：%s", role, e)
                reb = {}
            adj = reb.get("score_adjustment") or {}
            base = reviews[role].get("scores") or {}
            final_scores[role] = {
                k: _clamp(float(base.get(k, 5)) +
                          _clamp(float(adj.get(k, 0)), -2, 2))
                for k in SCORE_KEYS}
            debates[role] = reb
        self._save(round_dir / card.id / "debate" / "rebuttals.json", debates)
        log.info("%s 辩论后评分：%s", card.id, final_scores)
        return debates, final_scores

    def _meta_review(self, card: IdeaCard, reviews, debates, weighted,
                     rnd, round_dir: Path):
        try:
            meta = self._call("meta", "meta", "meta_review",
                              round=rnd, idea_id=card.id, idea_card=card.to_json(),
                              weighted=f"{weighted:.2f}",
                              reviews_json=json.dumps(reviews, ensure_ascii=False),
                              debate_json=json.dumps(debates, ensure_ascii=False))
        except Exception as e:
            # 导师终审失败不能炸掉整场：降级为「继续迭代」
            log.error("%s 终审失败（降级为 revise）：%s", card.id, e)
            meta = {"verdict": "revise",
                    "rationale": f"终审输出解析失败，按默认规则继续迭代（{e}）",
                    "action_items": ["补强与最接近先行工作的机制级对比",
                                     "为成功标准给出定量阈值"],
                    "ready_for_experiment": False}
        self._save(round_dir / card.id / "meta.json", meta)
        return meta

    def _revise(self, card: IdeaCard, reviews, debates, meta, rnd,
                round_dir: Path):
        try:
            data = self._call("researcher", "revise", "a_revise",
                              idea_card=card.to_json(),
                              reviews_json=json.dumps(reviews, ensure_ascii=False),
                              debate_json=json.dumps(debates, ensure_ascii=False),
                              meta_actions="；".join(meta.get("action_items") or []),
                              meta_rationale=meta.get("rationale", ""))
            revised = IdeaCard(data, int(card.id.split("-")[-1] or 1))
            revised.id = card.id  # id 恒定，卡片的版本由目录记录
        except Exception as e:
            log.error("%s 修订失败（沿用当前版本）：%s", card.id, e)
            revised = card
        self._save(round_dir / card.id / f"card_v{rnd + 1}.json",
                   revised.to_dict())
        log.info("%s 修订完成：%s", card.id, revised.title)
        return revised

    # ------------------------------------------------------------------
    def run(self, topic: str, seed_cards=None):
        """seed_cards 非空时为续跑模式：跳过调研与提出，直接迭代已有 idea。"""
        self.seed_mode = seed_cards is not None
        if seed_cards:
            log.info("== 续跑模式：跳过调研与提出，直接迭代 %d 个已有 idea ==", len(seed_cards))
            self._save(self.run_dir / "round_0" / "idea_cards.json",
                       [c.to_dict() for c in seed_cards])
            cards = list(seed_cards)
        else:
            survey_md, insights, _ = self.phase_survey(topic)
            cards = self.phase_ideate(topic, survey_md, insights)

        pl = self.cfg["pipeline"]
        max_rounds = int(pl.get("max_rounds", 2))
        kill_threshold = float(pl.get("kill_threshold", 4.5))
        epsilon = float(pl.get("converge_epsilon", 0.3))

        alive = list(cards)
        history = {c.id: [] for c in cards}
        prev_mean = None
        final_rnd = 0

        for rnd in range(1, max_rounds + 1):
            log.info("== 阶段3/4：第 %d/%d 轮 评审-辩论-终审-修订 ==", rnd, max_rounds)
            round_dir = self.run_dir / f"round_{rnd}"
            round_dir.mkdir(parents=True, exist_ok=True)
            survivors, round_weighted = [], []

            for card in alive:
                idea_dir = round_dir / card.id
                idea_dir.mkdir(parents=True, exist_ok=True)
                self._save(idea_dir / f"card_v{rnd}.json", card.to_dict())

                reviews = self._review_panel(card, round_dir)
                debates = {}
                if pl.get("debate", True):
                    debates, final_scores = self._debate(card, reviews, round_dir)
                else:
                    final_scores = {
                        r: {k: float(reviews[r].get("scores", {}).get(k, 5))
                            for k in SCORE_KEYS} for r in reviews}
                mean_scores = _mean_scores(list(final_scores.values()))
                weighted = weighted_score(mean_scores)

                meta = self._meta_review(card, reviews, debates, weighted,
                                         rnd, round_dir)
                verdict = str(meta.get("verdict") or "revise").lower()
                if verdict not in ("advance", "revise", "kill"):
                    verdict = "revise"
                # 系统规则只拦「带病 advance」，不覆盖导师的 revise/kill 判断：
                # 分数是噪声较大的聚合值，导师正文明说的结论应当被尊重。
                if verdict == "advance" and weighted < kill_threshold:
                    verdict = "revise"
                    meta["rationale"] = (meta.get("rationale") or "") + \
                        f"［系统规则：加权分 {weighted:.2f} 低于 advance 门槛 {kill_threshold}，降级为 revise］"
                ready = bool(meta.get("ready_for_experiment"))

                log.info("%s 第%d轮 → 加权 %.2f｜结论 %s｜%s",
                         card.id, rnd, weighted, verdict.upper(),
                         (meta.get("rationale") or "")[:80])
                history[card.id].append({
                    "round": rnd, "weighted": round(weighted, 2),
                    "verdict": verdict, "ready": ready,
                    "title": card.title,
                    "rationale": meta.get("rationale", ""),
                    "mean_scores": {k: round(v, 2) for k, v in mean_scores.items()},
                })

                if verdict == "kill":
                    continue
                survivors.append(self._revise(card, reviews, debates, meta,
                                              rnd, round_dir))
                round_weighted.append(weighted)

            final_rnd = rnd
            if not survivors:
                log.warning("第 %d 轮后所有 idea 均被毙掉，提前结束", rnd)
                break
            cur_mean = sum(round_weighted) / len(round_weighted)
            if prev_mean is not None and (cur_mean - prev_mean) < epsilon:
                log.info("平均加权分提升 %.2f < 收敛阈值 %.2f，判定收敛，提前结束",
                         cur_mean - prev_mean, epsilon)
                break
            if all(h["ready"] for c in survivors
                   for h in [history[c.id][-1]]):
                log.info("所有存活 idea 均被标记为可进入实验，提前结束")
                break
            prev_mean = cur_mean
            alive = survivors

        ranked = self.phase_final(topic, history, final_rnd)
        return ranked

    # ------------------------------------------------------------------
    def phase_final(self, topic, history, final_rnd):
        log.info("== 阶段4/4：生成报告与实验规格 ==")
        entries = []
        for cid, records in history.items():
            if not records:
                continue
            last = records[-1]
            entries.append({"id": cid, "title": last["title"],
                            "weighted": last["weighted"],
                            "verdict": last["verdict"], "ready": last["ready"],
                            "history": records})
        entries.sort(key=lambda e: (e["verdict"] == "kill", -e["weighted"]))

        self._save(self.run_dir / "final" / "ranked_ideas.json", entries)
        self._save(self.run_dir / "usage.json", self.usage.to_dict())

        # 为每个存活 idea 生成「一页看懂」简报（一句话/创新/凭什么/怎么验/命门）
        for e in entries:
            if e["verdict"] == "kill":
                continue
            try:
                card_data = self._load_latest_card(e["id"], final_rnd)
                t = self._call("researcher", "tldr", "a_tldr",
                               idea_card=json.dumps(card_data,
                                                    ensure_ascii=False))
                self._save(self.run_dir / "final" / f"tldr_{e['id']}.json", t)
                log.info("已生成 %s 的一页简报", e["id"])
            except Exception as ex:
                log.warning("生成 %s 简报失败（不影响报告）：%s", e["id"], ex)

        from lab.report import generate_report
        report_md, summary_lines = generate_report(
            self.run_dir, topic, entries, self.usage,
            seed_mode=getattr(self, "seed_mode", False))
        (self.run_dir / "final" / "report.md").write_text(
            report_md, encoding="utf-8")

        top_k = int(self.cfg["pipeline"].get("spec_top_k", 1))
        specd = 0
        for e in entries:
            if specd >= top_k or e["verdict"] == "kill":
                continue
            try:
                card_data = self._load_latest_card(e["id"], final_rnd)
                spec = self._call("researcher", "spec", "a_experiment_spec",
                                  idea_card=json.dumps(card_data,
                                                       ensure_ascii=False))
                (self.run_dir / "final" /
                 f"experiment_spec_{e['id']}.md").write_text(
                    str(spec.get("markdown") or ""), encoding="utf-8")
                specd += 1
                log.info("已生成 %s 的实验规格", e["id"])
            except Exception as ex:
                log.error("生成 %s 实验规格失败：%s", e["id"], ex)
        return entries, summary_lines

    def _load_latest_card(self, idea_id: str, final_rnd: int) -> dict:
        """沿轮次倒序找某 idea 最新的卡片版本（含续跑输入与修订产物）。"""
        for rnd in range(final_rnd, 0, -1):
            p = self.run_dir / f"round_{rnd}" / idea_id / f"card_v{rnd + 1}.json"
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
            p = self.run_dir / f"round_{rnd}" / idea_id / f"card_v{rnd}.json"
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        p = self.run_dir / "round_0" / "idea_cards.json"
        for d in json.loads(p.read_text(encoding="utf-8")):
            if d.get("id") == idea_id:
                return d
        return {"id": idea_id, "title": "（未找到卡片档案）"}


def load_survivors(run_dir) -> list:
    """从一次运行的档案里加载所有未被毙掉的 idea 的最新卡片，供续跑。"""
    run_dir = Path(run_dir)
    ranked = json.loads(
        (run_dir / "final" / "ranked_ideas.json").read_text(encoding="utf-8"))
    finder = Pipeline.__dict__["_load_latest_card"]
    rounds = sorted(
        (int(p.name.split("_")[1]) for p in run_dir.glob("round_*")
         if p.is_dir() and p.name != "round_0" and p.name.split("_")[1].isdigit()),
        reverse=True)
    cards = []
    for e in ranked:
        if e.get("verdict") == "kill":
            continue
        latest = None
        for rnd in rounds:
            d = run_dir / f"round_{rnd}" / e["id"]
            if not d.exists():
                continue
            for v in range(rnd + 1, 0, -1):
                p = d / f"card_v{v}.json"
                if p.exists():
                    latest = json.loads(p.read_text(encoding="utf-8"))
                    break
            if latest:
                break
        if latest:
            cards.append(IdeaCard(latest, int(e["id"].split("-")[-1] or 1)))
    return cards
