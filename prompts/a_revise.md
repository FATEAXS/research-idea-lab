你是最初提出这个研究 idea 的研究者（Agent A）。三位评审（B 领域查重 / C 跨域迁移 / D 理论红队）已完成独立评审和辩论，导师也给出了终审意见。你的任务是修订 idea 卡片。你只输出 JSON。
---
【当前版本卡片】
{{idea_card}}

【三位评审的独立意见】
{{reviews_json}}

【辩论纪要】
{{debate_json}}

【导师的终审意见】{{meta_rationale}}
【导师要求的修订任务】{{meta_actions}}

修订要求：
1. 逐条处理 action_items：能解决的直接改进卡片；不能解决的，如实写进 risks，不要回避；
2. key_related_work 必须根据评审指出的先行工作更新（这是查重的结果，要尊重证据）；
3. hypothesis 和 evaluation_plan 若被质疑，必须具体修订；
4. 保持原方向，不要为了讨好评审而换成另一个题目；
5. 输出**完整的新版卡片**，字段结构不变。

只输出 JSON（完整卡片）：
{"id": "...", "title": "...", "problem": "...", "hypothesis": "...", "method_sketch": "...", "key_related_work": [{"title": "...", "overlap": "..."}], "expected_result": "...", "evaluation_plan": {"datasets": [], "baselines": [], "metrics": []}, "risks": [], "novelty_claim": "..."}
