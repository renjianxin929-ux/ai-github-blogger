# Daily Operator SOP — 每日操作标准流程 (v0.1)

> 适用版本: v0.1（2026-06-02）
> 操作者: 任健鑫
> 目的: 每天 30 分钟内完成 AI GitHub 选题 → 内容生成 → 人工审核 → 发布 → 数据复盘

---

## 系统概述

`ai-github-blogger` 是一条 Python CLI 管线，每天帮你：
1. 从 GitHub 抓取 AI 相关新项目并评分
2. 生成多平台内容草稿（公众号/小红书/抖音/视频号/GEO）
3. 审核内容质量并给出发布建议
4. 发布后录入表现数据，持续优化选题方向

**核心原则:**
- 所有发布操作均为手动 — 不自动推送到任何平台
- 所有 LLM 生成内容均需人工通读 — 不盲发
- 所有建议均标注数据依据 — 不编造趋势

---

## 每日操作时间线

```
08:00  环境检查 + 选题发现        (~5 min)
08:05  查看工作台，确定今日选题     (~5 min)
08:10  生成内容包                  (~3 min per project)
08:15  内容审核 + 改稿             (~10 min)
08:30  手动复制到各平台发布         (~5 min per platform)
发布后  录入表现数据               (~2 min)
次日    查看 insights 复盘建议      (~3 min)
```

---

## Step 0: 环境检查（每天必做）

```bash
python run.py doctor
```

**期望结果:** `Overall: PASS` 或 `Overall: WARN`
- PASS → 继续
- WARN → 看具体 warn 项，通常可继续
- FAIL → 先修 FAIL 项再继续（通常是 GitHub Token 或网络问题）

---

## Step 1: 每日选题发现

```bash
# 一键模式（推荐，零 LLM 消耗）
python run.py daily-workflow

# 或分步执行
python run.py daily --no-llm
python run.py quality-gate
```

**输出文件（在 `data/reports/` 下）:**
| 文件 | 用途 |
|------|------|
| `daily_report_YYYY-MM-DD.md` | 完整选题报告 |
| `daily_brief_YYYY-MM-DD.md` | 一屏工作台摘要 |
| `review_queue_YYYY-MM-DD.md` | 人工审核队列 |
| `top5_YYYY-MM-DD.json` | Top5 结构化数据 |

**质量检查:**
```bash
python run.py quality-gate
```
期望 `VERDICT: PASS`，分数 ≥ 90/100。

---

## Step 2: 确定今日选题

```bash
# 工作台视图（最推荐）
python run.py workbench

# 全景仪表盘
python run.py dashboard
```

**workbench 输出解读:**

| 区块 | 看什么 |
|------|--------|
| §1 今日决策摘要 | A/B/C/D 各级候选数量 |
| §2 今日最推荐 | 直接告诉你今天该做什么项目 |
| §3 全部候选 | 所有候选一览表 |
| §4 平台建议 | 每个平台适合做什么 |
| §5 风险提醒 | 有什么需要注意的 |
| §6 下一步命令 | 可以直接复制执行的命令 |
| §7 人工检查清单 | 逐项检查不要漏 |
| §8 复盘建议 | 历史数据驱动的选题方向建议 |

**可发布性分数速查:**

| 分数 | 级别 | 含义 |
|------|------|------|
| ≥ 75 | A 级 ✅ | 推荐发布，素材充分 |
| 60–74 | B 级 ⚠️ | 可观察候选，需确认 |
| 40–59 | C 级 📋 | 需人工审核后决定 |
| < 40 | D 级 ❌ | 不推荐，建议跳过 |

---

## Step 3: 生成内容包

```bash
# 为选定项目生成内容包
python run.py content owner/repo

# 一键发布流程（构建 + 审核 + 改稿建议）
python run.py publish-flow owner/repo
```

**生成文件清单（11 个文件，在 `data/content_packs/<owner>__<repo>/` 下）:**

| 文件 | 平台 | 用途 |
|------|------|------|
| `00_repo_snapshot.md` | 通用 | 仓库快照 |
| `01_ai_fde_deep_analysis.md` | 通用 | FDE 三维深度分析 |
| `02_xiaohongshu.md` | 小红书 | 图文笔记 |
| `03_douyin_video.md` | 抖音 | 口播脚本 |
| `04_videohao_script.md` | 视频号 | 视频脚本 |
| `05_wechat_article.md` | 公众号 | 长文 |
| `06_storyboard.md` | 视频 | 分镜表 |
| `07_geo_angle.md` | GEO | 搜索关键词覆盖 |
| `08_enterprise_pitch.md` | 公众号 | 企业级解读 |
| `09_risk_review.md` | 通用 | 安全审查（发布前必读） |
| `10_quality_check.md` | 通用 | 质检清单 |

**注意:** LLM 可用时自动使用 AI 生成（11 次 LLM 调用）；LLM 不可用时降级为 research brief 模式。

---

## Step 4: 内容审核

```bash
# 审核发布包
python run.py review-pack data/publish_packs/<pack_dir>

# 如果需要改稿
python run.py revise-pack data/publish_packs/<pack_dir>

# 确认无误后批准
python run.py approve-pack data/publish_packs/<pack_dir>
```

**审核判决:**
- `ready` ✅ — 可直接发布
- `needs_revision` ⚠️ — 修改后发布
- `rejected` 🔴 — 不建议发布，换项目

**人工必读:**
1. `09_risk_review.md` — 确认无敏感内容
2. `10_quality_check.md` — 补齐所有 [TODO] 项
3. 各平台文件 — 调整语气和人设

---

## Step 5: 手动发布

> ⚠️ 系统不会自动发布到任何平台。所有发布操作需人工执行。

1. 打开对应平台（公众号后台 / 小红书 / 抖音 / 视频号）
2. 复制对应 ready 文件内容
3. 调整排版、配图、话题标签
4. 发布后记录 URL

```bash
# 记录发布到系统
python run.py mark-published data/publish_packs/<pack_dir> --platform wechat --url "https://..." --note "第一条测试"
```

**平台标识对照:**

| CLI 参数 | 平台 | 内容格式 |
|----------|------|----------|
| `wechat` | 公众号 | 长文 |
| `xiaohongshu` | 小红书 | 图文笔记 |
| `douyin` | 抖音 | 短视频口播 |
| `videohao` | 视频号 | 短视频 |
| `geo` | GEO | 搜索优化内容 |

---

## Step 6: 录入表现数据

发布后 24-48 小时，收集各平台的表现数据：

```bash
python run.py record-metrics owner/repo \
  --platform wechat \
  --views 1000 \
  --likes 50 \
  --favorites 20 \
  --comments 10 \
  --leads 3 \
  --note "发布后48h数据"
```

**指标说明:**
| 参数 | 含义 |
|------|------|
| `--views` | 阅读/播放量 |
| `--likes` | 点赞数 |
| `--favorites` | 收藏/书签数 |
| `--comments` | 评论数 |
| `--leads` | 线索数（加微信/私信/转化） |

**派生指标（自动计算）:**
- **互动率** = (点赞 + 收藏 + 评论) / 浏览
- **线索率** = 线索 / 浏览

```bash
# 查看历史表现
python run.py metrics-history
```

---

## Step 7: 每日复盘

```bash
# 全量复盘报告
python run.py insights

# 按项目查看
python run.py insights owner/repo
```

**insights 输出 5 个区块:**

| 区块 | 内容 |
|------|------|
| 1. 总体表现摘要 | 总览数据，最佳平台/项目 |
| 2. 平台表现建议 | 每个平台是继续做还是暂停 |
| 3. Repo 复盘建议 | 哪些值得二创、换平台再发 |
| 4. 明日选题建议 | 基于历史数据的方向推荐 |
| 5. 风险提示 | 样本不足、数据异常等警告 |

**关键原则:** 所有建议都标注了「依据: xxx」，方便你判断是否采信。

---

## 命令速查表

### 日常管线
| 命令 | 用途 | 耗时 |
|------|------|------|
| `python run.py doctor` | 环境健康检查 | ~5s |
| `python run.py daily-workflow` | 一键选题流程 | ~3min |
| `python run.py workbench` | 每日工作台（决策入口） | ~1s |
| `python run.py dashboard` | 全景仪表盘 | ~1s |
| `python run.py content <repo>` | 生成内容包 | ~2min |
| `python run.py publish-flow <repo>` | 一键发布流程 | ~3min |
| `python run.py quality-gate` | 质量门检查 | ~30s |

### 审核与发布
| 命令 | 用途 |
|------|------|
| `python run.py review-pack <dir>` | 审核发布包 |
| `python run.py approve-pack <dir>` | 批准发布 |
| `python run.py reject-pack <dir> --reason "..."` | 拒绝发布 |
| `python run.py revise-pack <dir>` | 生成改稿建议 |
| `python run.py mark-published <dir> --platform <p>` | 记录已发布 |
| `python run.py publish-history` | 查看发布历史 |

### 数据与复盘
| 命令 | 用途 |
|------|------|
| `python run.py record-metrics <repo> --platform <p> --views ...` | 录入表现数据 |
| `python run.py metrics-history` | 查看表现历史 |
| `python run.py insights` | 复盘建议报告 |
| `python run.py insights <repo>` | 单项目复盘 |

### 诊断与验证
| 命令 | 用途 |
|------|------|
| `python run.py dry-run` | 端到端验证（不消耗 LLM） |
| `python run.py llm-doctor` | LLM 连接诊断 |
| `python run.py benchmark` | 评分系统基准测试 |
| `python -m pytest tests/ -v` | 运行全部测试 |

---

## 快速决策流程图

```
doctor PASS?
  ├─ NO  → 修环境
  └─ YES → daily-workflow
              │
              └─ workbench 查看
                  │
                  ├─ A 级项目存在?
                  │   ├─ YES → publish-flow <repo>
                  │   │         │
                  │   │         ├─ review PASS? → approve → 手动发布 → mark-published
                  │   │         └─ review FAIL? → revise 或换项目
                  │   └─ NO  → 等下一轮 daily
                  │
                  └─ 发布 24-48h 后:
                      record-metrics → insights 复盘 → 指导下一天选题
```

---

## 常见问题

### Q: doctor 显示 GitHub API WARN
A: 可能是网络/SSL 问题。尝试 `python run.py dry-run` 确认管线是否可用。WARN 不阻断使用。

### Q: 没有 A 级候选怎么办？
A: 正常现象。可以等下一轮 daily，或手动指定项目 `python run.py content owner/repo`。

### Q: LLM 不可用时内容质量如何？
A: 降级为 structured_fallback 模式，生成 research brief 而非成品文章。需要人工补写后发布。

### Q: 数据太少，insights 一直提示"样本不足"？
A: 正常。至少积累 3 条表现数据后系统才能给出有信心的建议。先手动判断，持续录入即可。

### Q: 某个项目想发多个平台怎么办？
A: content pack 已经为 5 个平台都生成了内容。逐个复制发布，每次用 `mark-published --platform <name>` 记录。

---

## 版本记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-02 | v0.1 | 初始版本，覆盖完整日更管线 |
