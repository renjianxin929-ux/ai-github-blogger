# AI GitHub Blogger — 每日 AI 选题发现 Skill

## 一、概述与能力边界

`ai-github-blogger` 是一个**双用途 AI 博主工具**：

- **数据引擎**：从 GitHub 自动发现 AI 开源项目 → 四层评分筛选 → 多池分类 → 人工审核队列
- **内容工厂**：基于评分结果生成多平台内容包（小红书/抖音/视频号/公众号/外贸GEO）

### 核心原则

**规则引擎负责筛选和评分，LLM 负责内容润色。No-LLM 模式仅输出结构模板。**

### 能力边界

**系统负责**：
- 每日从 GitHub 抓取 AI 项目并评分
- 按 5 个池 (top5/evergreen/resource/blocked/review) 分类
- 生成多平台内容模板
- 输出去重、风险拦截、质量检查

**人工负责**：
- 最终选题决策
- 行业观点和见解补充
- 事实和数据准确性验证
- 内容发布和平台适配
- 风险管理最终把关

### 不做的事

- 不自动发布到任何平台
- 不登录任何社交平台账号
- 不绕过验证码/反爬机制
- 不生成违规/高风险项目推广内容
- 不自动推送内容

---

## 二、快速开始

### 前置条件

- Python 3.10+
- GitHub Token (https://github.com/settings/tokens, 勾选 `public_repo`)

### 安装

```bash
cd ai-github-blogger
cp .env.example .env
# 编辑 .env，填入 GITHUB_TOKEN=ghp_xxxxxxxx
pip install -r requirements.txt
```

### 第一次运行

```bash
python run.py doctor              # 环境健康检查
python run.py daily --no-llm      # 无 LLM 模式跑一次
ls data/reports/                  # 查看生成的 3 个报告
```

### 配置 LLM（可选）

```bash
# .env 中添加
LLM_API_KEY=sk-xxxxxxxx
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o
```

---

## 三、每日工作流 (30-60 分钟)

```
1. 查看一屏工作台 (2-3 min)
   python run.py daily --no-llm
   cat data/reports/daily_brief_YYYY-MM-DD.md

2. 审核候选 (5-10 min)
   cat data/reports/review_queue_YYYY-MM-DD.md
   按 8 项清单逐项检查

3. 选取最终选题 (2-3 min)
   从 Top 5 + 审核通过的候选中选择 1-3 个

4. 生成内容包 (15-30 min)
   python run.py content owner/repo

5. 发布前检查 (5 min)
   检查 risk_review.md 和 quality_check.md

6. 发布到对应平台 (5-10 min)
   各平台独立发布，适配不同格式
```

### 什么时候不要接 LLM

1. 首次调参/调试阶段 — 先用 `--no-llm` 验证规则评分
2. GitHub API 不稳定时 — LLM 会增加调用链复杂度
3. Token 预算有限时 — 每日全管线约 5000-10000 tokens
4. 测试/CI 环境 — 应始终使用 `--no-llm`

---

## 四、命令参考

```bash
python run.py doctor              # 环境健康检查（10项）
python run.py daily --no-llm      # 每日管线（无 LLM）
python run.py daily               # 每日管线（含 LLM 分析）
python run.py fetch               # 仅抓取仓库
python run.py score               # 仅评分
python run.py report              # 仅生成报告
python run.py content <repo>      # 生成内容包
python run.py benchmark           # 评分基准测试
python run.py quality-gate        # 质量门评估
```

### 输出文件

| 命令 | 输出文件 |
|------|----------|
| `daily` | `daily_report_*.md`, `daily_brief_*.md`, `review_queue_*.md` |
| `content` | `data/content_packs/<owner>-<repo>/` (10个文件 + manifest) |
| `quality-gate` | `data/reports/system_quality_report_v8.md` |
| `benchmark` | 终端输出 golden/adversarial 准确率 |

---

## 五、安全边界

### API Key 保护

- `GITHUB_TOKEN` 和 `LLM_API_KEY` 仅通过 `.env` 文件读取
- `.env` 已在 `.gitignore` 中
- 代码中无硬编码密钥
- `python run.py doctor` 会检查密钥状态

### 内容安全

- Deep-Live-Cam 等 deepfake 工具自动拦截 (G7)
- NSFW/adult/uncensored 关键词自动进 blocked pool
- 数据隐私监控关键词检测（fingerprint/surveillance/keylogger）
- 所有内容生成后带 `risk_review.md` 审查文件

### 数据隐私

- 全部数据存储本地 `data/` 目录
- 无遥测/analytics/用户行为跟踪
- 不上传任何数据到第三方服务器

---

## 六、评分系统说明

### 四层评分架构

| 层级 | 名称 | 范围 | 说明 |
|------|------|------|------|
| L1 | repo_selection_score | 0-100 | 7维度：AI相关性/活跃度/清晰度/可运行/可讲性/社区/风险 |
| L2 | business_value_score | 0-100 | 6维度：理解成本/企业场景/FDE训练/服务延展/流程结合/风险 |
| L3 | platform_fit_score | 每平台0-100 | 5平台：小红书/抖音/视频号/公众号/外贸GEO |
| L4 | risk_score | low/medium/high/blocked | 8维度风险评估 |

### 池分类逻辑

| 池 | 说明 | 路由规则 |
|----|------|----------|
| top5 | 每日最佳选题 | runnable + 高评分 + 非evergreen |
| evergreen | 常青基础设施 | KNOWN_EVERGREEN 或 name 匹配 |
| resource | 资料库/合集 | awesome_list / tutorial_guide |
| blocked | 高风险拦截 | NSFW/deepfake/隐私侵犯 |
| review | 待人工审查 | WEAK_AI 或信息不足 或 hype |

### 质量保证

- 80 个 golden cases — 确保核心路由 100% 正确
- 30 个 adversarial cases — 确保边缘情况不误判 (≥85%)
- 15 个 gate conditions — pass/conditional_pass/fail 三级 verdict

---

## 七、常见问题

### GitHub API 限流

```bash
python run.py doctor  # 检查剩余额度
# 无 token: 60次/小时, 有 token: 5000次/小时
# daily 命令约需 60-80 次 API 调用
```

### 所有 repo 被拦截

```bash
rm data/state/seen_repos.json
rm data/state/generated_repos.json
python run.py daily --no-llm
```

### 内容包生成失败

系统自动重试 3 次（指数退避），失败后降级为模板填充，标注 `source_status: degraded`。

```bash
python run.py content owner/repo  # 重试
cat data/content_packs/owner_repo/_manifest.json  # 查看状态
```

### Windows 控制台乱码

使用 Windows Terminal 而非 cmd.exe。系统已内置 UTF-8 重配置。

### 需要 LLM 但没有 API Key

使用 `--no-llm` 模式（默认行为），输出结构化模板，人工填充内容。

---

## 项目结构

```
ai-github-blogger/
├── src/                        # 源代码
│   ├── main.py                 # CLI 入口
│   ├── scorer.py               # 四层评分 + 池分类
│   ├── risk_score.py           # 风险评估
│   ├── business_score.py       # 商业价值评分
│   ├── platform_score.py       # 平台适配评分
│   ├── quality_gate.py         # 15条件质量门 (v8)
│   ├── error_handler.py        # 统一错误处理 + 重试
│   ├── content_pack.py         # 内容包生成
│   ├── report.py               # 报告生成 (含 daily_brief + review_queue)
│   ├── benchmark.py            # 基准测试
│   ├── enricher.py             # GitHub API 数据富化
│   ├── fetcher.py              # GitHub 搜索抓取
│   ├── dedup.py                # 去重管理
│   └── config.py               # 配置中心
├── docs/                       # 使用文档
│   ├── QUICKSTART.md
│   ├── DAILY_WORKFLOW.md
│   ├── TROUBLESHOOTING.md
│   ├── SCORING_SYSTEM.md
│   ├── SAFETY_BOUNDARY.md
│   ├── CONTENT_PACK_GUIDE.md
│   ├── LLM_SETUP.md
│   └── REVIEW_CHECKLIST.md
├── tests/fixtures/             # 测试样本
│   ├── golden_cases.json       # 80 个黄金样本
│   ├── adversarial_cases.json  # 30 个对抗样本
│   └── live_sample_cases.json  # 20 个真实样本
├── templates/                  # 内容模板
├── data/                       # 运行时数据
│   ├── state/                  # 去重状态
│   ├── reports/                # 日报输出
│   └── content_packs/          # 内容包
├── SKILL.md                    # 本文件
└── run.py                      # 入口脚本
```
