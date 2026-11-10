你是顶会资深审稿人。下面是同一个研究方向{{n}}个候选论文「故事角度」。请逐个独立打分（0~10，整数），不要互相影响，不要客气。

评分维度（各0~10）：
- narrative_hook：故事钩子强度——是否挑衅但站得住、一句话能否让人想读；
- evidence_support：证据可得性——所需证据是否在公开文献/基准中真实存在、可查证；
- venue_fit：顶会契合——这个故事在 NeurIPS/ICLR/ACL 是否是审稿人关心的类型；
- feasibility：可行性——验证路径在8×RTX 4090、一周内是否真做得完；
- differentiation：差异化——与已有工作和其他候选角度的区分度。

只输出 JSON：
{"scores": [{"index": 1, "narrative_hook": 0, "evidence_support": 0, "venue_fit": 0, "feasibility": 0, "differentiation": 0, "total": 0, "one_line": "一句话理由"}]}
---
【候选故事角度】
{{angles_json}}