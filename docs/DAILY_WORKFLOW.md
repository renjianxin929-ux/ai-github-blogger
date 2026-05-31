# Daily Workflow — 每日工作流指南

## 新手从 0 到每天运行

### 前置条件

```bash
# 1. 克隆项目
git clone <repo-url>
cd ai-github-blogger

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，至少填入 GITHUB_TOKEN
# GITHUB_TOKEN 在 github.com/settings/tokens 生成（不需要特殊权限，仅用于 API 速率提升）
```

### 验证安装

```bash
# 检查环境
python run.py doctor

# 验证系统无损坏
python run.py dry-run
```

如果 doctor 全绿（11/11 PASS），系统就准备好了。

---

## 每天该执行哪些命令

### 一键模式（推荐）

```bash
python run.py daily-workflow
```

执行顺序：doctor → daily --no-llm → quality-gate，零 LLM 消耗。

### 分步模式（需要精细控制时）

```bash
# 1. 环境检查
python run.py doctor

# 2. 抓取 + 评分 + 报告生成
python run.py daily --no-llm

# 3. 质量门检查
python run.py quality-gate
```

### 查看人工审核清单

```bash
python run.py review-queue
```

### 为选定项目生成内容包

```bash
# no-LLM 模式（不消耗 token，规则生成 11 个文件）
python run.py content owner/repo

# LLM 模式（自动检测 LLM_API_KEY，生成高质量 AI 内容）
# 同样命令，有 API Key 时自动使用 LLM
python run.py content owner/repo
```

---

## 结果解读

### 可以发布（绿色信号）

- `python run.py doctor` → 11/11 PASS 或仅 WARN（无 FAIL）
- `python run.py quality-gate` → VERDICT: PASS，Score ≥ 90
- `python run.py review-queue` → 高置信度 Top 5 中有 ≥1 个"可直接采用"项目
- 推荐项目显示"是否可进入 content 生成：是"

### 必须人工审核（黄色信号）

- review_queue 中"需要人工审核"队列非空
- 项目风险等级 = medium
- 项目 content_type = unclear（README 信息不足）
- 项目 stars < 100 且质量未知
- 项目无明确许可证

人工审核清单（8 项检查）会自动包含在 review_queue 报告中。

### 不能发布（红色信号）

- `python run.py doctor` → 有 FAIL 项（GITHUB_TOKEN 未配置、Python 版本过低等）
- `python run.py quality-gate` → VERDICT: FAIL
- Top 5 全部为空或全部 blocked
- review_queue 中所有项目都被标记为 high_risk

---

## GitHub Token vs LLM_API_KEY

| | GITHUB_TOKEN | LLM_API_KEY |
|---|---|---|
| 作用 | GitHub API 搜索和增强 | AI 内容生成（FDE分析 + 11种内容） |
| 是否必需 | 是（无 Token 时仅 60 次/小时 API 配额） | 否（无 Key 时自动降级为规则模式） |
| 如何获取 | github.com/settings/tokens | DeepSeek/OpenAI 等 LLM 平台 |
| 写在哪个文件 | .env → GITHUB_TOKEN=xxx | .env → LLM_API_KEY=xxx |

---

## no-LLM 模式 vs LLM 模式

### no-LLM 模式（LLM_API_KEY 未配置）

- `python run.py daily --no-llm` — 评分 + 分类 + 报告，不调 LLM
- `python run.py content owner/repo` — 所有 11 个文件由规则生成
- quality_check 显示"未评估"（不自证没有的分数）
- 适用场景：快速选题筛选、API 欠费时、日常浏览

### LLM 模式（LLM_API_KEY 已配置）

- `python run.py daily` — 额外对 Top 5 做 AI-FDE 三维分析
- `python run.py content owner/repo` — AI 生成深度分析、小红书、公众号等高质量内容
- quality_check 给出具体分数和评审意见
- 适用场景：发布前生成最终内容
- **注意**：每次 content 生成约消耗 12 次 LLM 调用（11 文件 + 1 FDE）

---

## 快速参考

| 任务 | 命令 |
|---|---|
| 每日选题 | `python run.py daily-workflow` |
| 验证环境 | `python run.py dry-run` |
| 查看审核清单 | `python run.py review-queue` |
| 生成内容 | `python run.py content owner/repo` |
| 只看候选 | `python run.py fetch` |
| 运行测试 | `python -m pytest tests/ -v` |
