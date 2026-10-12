# 科研 Idea 迭代实验室（Research Idea Lab）

多智能体流水线：自动调研文献 → 提出创新 idea → 三视角独立评审 + 匿名辩论 → 导师终审 → 迭代修订 → 输出一页看懂简报与实验规格（预注册）。

## 流程

```
文献调研(A：多源检索+期刊分级过滤+40篇保底)
   → 提出N个idea(A)
   → [ B领域查重 / C跨域迁移 / D理论红队  独立评审（互不可见）
       → 匿名辩论(±2分微调) → 导师终审(继续/修订/毙掉) → 修订(A) ] × N轮
   → 排行榜报告 → Top-K实验规格 → 【人工卡点】选定idea开始实验
```

## 运行

```bash
pip install -r requirements.txt

# 1) 配置：复制 config.example.yaml 为 config.yaml，填 base_url / api_key / 各角色模型
#    api_key 也可用环境变量：set IDEA_LAB_API_KEY=你的key

# 2) 跑
python main.py --topic "研究方向"                        # 完整流程（默认3轮评审）
python main.py --topic "方向" --ideas 4 --rounds 2       # 控制idea数与轮数
python main.py --topic "方向" --continue-from runs/某目录 # 续跑：载入存活idea深挖
python forever.py --topics topics.txt                    # 无人值守轮流跑（带预算闸门）

# 3) 看结果
python make_html_report.py runs/某目录                   # 网页报告（含一页看懂简报）
```

## 输出

每次运行在 `runs/<时间戳_主题>/` 下：`final/报告.html`（排行榜+一页看懂简报）、`final/experiment_spec_*.md`（实验规格）、`round_N/`（每轮卡片版本+评审+辩论+终审档案）、`survey/`（检索文献与综述）、`usage.json`（token 用量）。

## 配置要点

- 任何 OpenAI 兼容服务都可用（DeepSeek/智谱/Qwen/Kimi/OpenAI/本地vLLM）；
- 五个角色可各配不同模型，甚至混用不同厂商（见 config.example.yaml 的字典写法）；
- `pipeline.max_rounds` 控制迭代轮数；`retrieval.min_survey_papers` 控制文献池保底数量；`retrieval.quality_filter` 控制一区二区/CCF-A/B 期刊过滤。
