# 科研 Idea 迭代实验室（Research Idea Lab）

模拟人类科研组会的多智能体系统：**Agent A** 调研文献、提出创新 idea；**B / C / D** 三位评审（领域查重、跨域迁移、理论红队）先独立评审、再匿名辩论；**导师（Meta-Reviewer）** 终审决定「继续 / 修订 / 毙掉」；如此迭代若干轮后输出排名报告和实验规格（预注册文档）。

```
调研(A) → 提出N个idea(A)
  └→ [ 独立评审(B/C/D) → 匿名辩论 → 导师终审 → 修订(A) ] × max_rounds
       └→ 排名报告 → Top-K 实验规格 → 【人工卡点】你选定 idea 后开始做实验
```

## 设计原则（为什么这样搭）

1. **一切围绕 Idea Card 迭代**，不围绕聊天记录。每轮输出是「修订后的结构化卡片」，可 diff、可终止、可度量进步。
2. **评审先独立、后辩论**。B/C/D 互相看不到对方意见时先打分，避免锚定效应；辩论只允许 ±2 分微调。
3. **新颖性必须有检索证据**。B 评审前强制检索先行工作；存在高度重叠论文时 novelty 不得高于 4 分。所有引用来自 arXiv / Semantic Scholar API，不靠模型记忆。
4. **角色不对称**。B 只管查重、C 只能检索相邻领域（强制跨域视角）、D 是红队（任务就是证伪可行性）。三人的评分权重也不同（可给不同角色配不同底座模型，进一步去趋同）。
5. **导师有一票否决权 + 明确 kill 标准**。加权分（novelty 0.35 / feasibility 0.40 / significance 0.25，刻意偏重可行性）低于淘汰线直接毙掉；轮数上限 + 收敛阈值防止无限空转。
6. **实验做预注册**。流程结束后为 Top idea 生成冻结的实验规格（数据集/基线/指标/消融/预算 + sanity→玩具→小规模→全量的执行阶梯），防止「跑出什么结果就找什么理由」。
7. **人工卡点**。机器负责把 idea 迭代到「可进实验」，最终选哪个 idea、要不要烧卡，由你决定。
8. **全量落盘**。每张卡的每个版本、每份评审、每场辩论、每次终审都在 `runs/` 下，方便复盘。

## 快速开始

### 方式一：双击运行（最简单，推荐）

- **`run_demo.bat`** —— 离线演示：双击 → 输入研究方向（或直接回车用默认主题）→ 自动跑完整流程。不需要 API key、不联网调模型，用来先看懂流程和输出。
- **`run_real.bat`** —— 正式运行：双击 → 按提示输入研究方向、轮数、idea 数量。运行前需要先完成下面的 API 配置。

两个脚本结束时窗口会停住（按任意键关闭），结果都在 `runs/` 最新的文件夹里。

### 方式二：CMD / PowerShell（效果完全一样，这就是个纯 Python 项目，不依赖 bash）

```bat
cd /d C:\Users\BuAi\.zcode\workspace\default\research-idea-lab
python main.py --topic "低资源场景下的高效大模型微调" --mock
```

```powershell
cd "C:\Users\BuAi\.zcode\workspace\default\research-idea-lab"
python main.py --topic "你的研究方向" --rounds 2 --ideas 4
```

### 方式三：IDE（VSCode / PyCharm）

打开项目文件夹，直接运行 `main.py`，参数写在运行配置的 args 里；或用 IDE 内置终端执行上面的命令。

### 真实运行前的 API 配置（只需一次）

```bat
copy config.example.yaml config.yaml     :: 编辑 base_url / api_key / 各角色模型
set IDEA_LAB_API_KEY=你的key             :: PowerShell: $env:IDEA_LAB_API_KEY="你的key"
python smoke_test.py                     :: 自检：流水线 + 检索是否正常
```

## 输出结构

每次运行在 `runs/<时间戳>_<主题>/` 下生成：

```
├── run_config.json            # 本次配置快照（key 已隐藏）
├── events.log                 # 全部过程日志（DEBUG 级）
├── survey/
│   ├── queries.json           # A 生成的英文检索查询
│   ├── papers.json            # 检索到的论文（去重后）
│   └── survey.md              # A 写的调研综述
├── round_0/idea_cards.json    # 第一轮提出的原始卡片
├── round_N/                   # 第 N 轮「评审-辩论-终审-修订」
│   └── idea-X/
│       ├── card_vN.json       # 本轮输入的卡片版本
│       ├── reviews/B,C,D.json # 三位评审的独立意见（B/C 附检索到的先行工作）
│       ├── debate/rebuttals.json  # 匿名辩论纪要与分数微调
│       ├── meta.json          # 导师终审：verdict + rationale + action_items
│       └── card_vN+1.json     # 修订后的新版本
├── final/
│   ├── ranked_ideas.json      # 排行榜
│   ├── report.md              # 完整报告（人工卡点从这里开始看）
│   └── experiment_spec_idea-X.md  # Top-K 的实验规格（预注册）
└── usage.json                 # token 用量统计
```

## 配置要点（config.yaml）

| 配置 | 说明 |
|---|---|
| `llm.base_url` / `api_key` | 任何 OpenAI 兼容服务；key 建议用环境变量 `IDEA_LAB_API_KEY` |
| `llm.models.*` | **五个角色可以配不同模型**：评审/终审用最强模型，起草用便宜模型压成本 |
| `pipeline.num_ideas` | 第一轮生成几个 idea（3~5 合理，多个 idea 并行迭代防趋同） |
| `pipeline.max_rounds` | 组会轮数上限，2~3 轮通常够（人类组会也不是无限开的） |
| `pipeline.debate` | 是否加匿名辩论环节（更接近真实组会，token 约 +40%） |
| `pipeline.kill_threshold` | 加权分淘汰线；调高更严格、更省钱 |
| `retrieval.providers` | arxiv / s2 任选组合；S2 无 key 限流严，建议免费申请 key |

## 如何定制

- **调角色行为**：直接改 `prompts/` 下的 Markdown（每个文件 = SYSTEM 段 + `---` + USER 段）。想让 D 更凶、C 更偏某个学科，改措辞即可。
- **加第四位评审**：在 `lab/pipeline.py` 的 `REVIEWERS` 里加一行（角色名、模型角色、提示词文件名），再补两份提示词文件即可。
- **换领域**：无需改代码，`--topic` 换成任何方向；检索用的是通用 API。

## 无人值守（让 Agent 一直跑）

```bash
# 方向清单（每行一个，# 为注释）
python forever.py --topics topics.txt                 # 轮流循环跑，永远不停
python forever.py --topic "某方向" --max-cycles 3      # 单方向跑3轮「探索+深挖」
```

`forever.py` 是永动驱动器，四层保障：
1. **故障不停车**：单场崩溃/超时只记入 `runs/forever_state.json`，驱动器继续下一场；
2. **自动深挖**：每场探索完后，自动用 `--continue-from` 载入存活 idea 再迭代一轮（跳过调研）；
3. **预算闸门**：累计 tokens 超过 `--max-total-tokens`（默认500万）自动优雅停车；
4. **断点友好**：随时 Ctrl+C，成果和进度都在 `runs/` 与状态文件里，`--continue-from` 可从任何一场接着跑。

单场续跑也可以手动触发：
```bash
python main.py --topic "方向" --continue-from runs/某次运行目录
```

要真正 7×24 跑，把它挂进 Windows 任务计划程序（开机自启/每天定时）即可；注意三件事：电脑别关机、网络要通、DeepSeek 余额要够——这是"不停"的物理边界。

## 常见问题

- **检索源怎么选**：默认 `arxiv + openalex`（OpenAlex 免 key、免费、限额宽松）。Semantic Scholar 无 key 限流极严，想要它的话去 semanticscholar.org/product/api 点 "Request API Key" 填表（入口是 Google 表单，需要相应网络条件），审核通过后把 key 填入 `retrieval.s2_api_key` 并把 `s2` 加回 `providers`。
- **arXiv 偶尔超时**：官方限速 + 网络抖动属正常；系统会自动退化到关键词检索再试一次，仍失败则由 OpenAlex 兜底，不中断流程。
- **模型输出解析失败**：会自动带着错误信息重试 3 次；仍失败时该环节降级（评审降级为中性分并记日志），不会拖垮整轮。
- **一次运行要花多少钱**：默认配置（4 ideas × 2 轮 + 辩论）约 100~200 次 LLM 调用。先用 `--ideas 2 --rounds 1 --no-debate` 试水，估算单价后再放大。`usage.json` 会记录精确用量。
- **Mock 模式是什么**：`--mock` 用内置假响应替代大模型、假论文替代检索，用于零成本验证流程和改代码后回归测试。

## 路线图（v1 建议方向）

- **实验执行沙箱**：对接 Docker + 你的 GPU 机器，让 A 按实验规格的执行阶梯（L0 sanity → L1 玩具 → L2 小规模 → L3 全量）真正跑代码，每级通过才放大；
- **结果验证 agent**：实验完成后强制消融归因（提升真的来自声称的修改吗）；
- **断点续跑 / 断点改参数**：从 `runs/` 档案恢复任意轮次；
- **Web 界面**：把 report.md 变成可交互的看板，人工卡点直接在界面上批注。
