# AI GitHub Blogger

每天自动发现 GitHub 上与 AI/LLM/Agent 相关的优质开源项目，通过规则打分和 LLM 分析生成选题报告和多平台内容草稿。

## 特性

- **自动抓取**：GitHub Trending RSS + REST API 搜索，覆盖 15 个 AI 相关关键词
- **智能评分**：6 维度规则打分引擎（Stars、活跃度、话题匹配、README 质量、社区健康、许可证）
- **AI-FDE 分析**：LLM 从功能创新(F)、差异化(D)、生态价值(E)三维度深度分析
- **去重系统**：基于 JSON 状态文件的持久化去重，14 天内重复推荐自动降权
- **多平台内容**：一键生成 8 种内容草稿（深度分析、小红书、视频号、抖音、公众号、分镜、风险复核、质检）
- **GitHub Actions**：每天北京时间 08:00 自动运行，也可以手动触发

## 快速开始

### 1. 克隆项目

```bash
git clone <repo-url>
cd ai-github-blogger
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 GitHub Token 和 LLM API Key
```

`.env` 示例：

```bash
# GitHub API（必填，用于搜索和获取仓库信息）
GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# LLM API（必填，用于 AI-FDE 分析和内容生成）
LLM_API_BASE=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxxxxxxxxxxx
LLM_MODEL=deepseek-chat

# 可选配置
# MAX_REPOS_TO_ENRICH=30
# MAX_REPOS_TO_ANALYZE=10
# DAYS_TO_DEDUP=14
```

### 4. 运行

```bash
# 完整日更流程（抓取 → 去重 → 评分 → LLM 分析 → 报告）
python -m src.main daily

# 跳过 LLM 分析（仅打分 + 候选报告）
python -m src.main daily --no-llm

# 仅抓取
python -m src.main fetch

# 仅打分排名
python -m src.main score

# 生成候选报告
python -m src.main report

# 对指定仓库生成内容包
python -m src.main content owner/repo
```

## 项目结构

```
ai-github-blogger/
├── .github/workflows/daily.yml       # GitHub Actions 自动运行
├── templates/                         # LLM prompt 模板（10个）
├── src/
│   ├── main.py                        # CLI 入口
│   ├── config.py                      # 配置管理
│   ├── fetcher.py                     # 数据抓取（RSS + API）
│   ├── enricher.py                    # 数据增强（GitHub API）
│   ├── dedup.py                       # 去重与状态管理
│   ├── scorer.py                      # 规则打分引擎
│   ├── analyzer.py                    # LLM 分析（OpenAI-compatible）
│   ├── report.py                      # 报告生成
│   └── content_pack.py               # 多平台内容包
├── tests/                             # 60 个单元测试
├── data/
│   ├── reports/                       # 每日报告输出
│   ├── state/                         # 去重状态（git 跟踪）
│   └── content_packs/                 # 生成的内容包
├── requirements.txt
├── .env.example
└── README.md
```

## 打分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| Stars | 20% | log 归一化，避免头部项目分数碾压 |
| 活跃度 | 25% | 7天内满分，30天后衰减至 5 |
| 话题匹配 | 25% | 关键词命中数 × 4，检查 topics/name/description |
| README 质量 | 15% | 长度 + 中文内容 + 结构化加分 |
| 社区健康 | 10% | forks + contributors 数量 |
| 许可证 | 5% | 有/无开源许可证 |

## LLM 支持

支持所有 OpenAI-compatible API：

- **DeepSeek**（推荐，性价比高）：`deepseek-chat`
- **OpenAI**：`gpt-4o`
- **OpenRouter**：多模型网关
- **SiliconFlow**：国内低延迟

## 测试

```bash
pytest tests/ -v
```

## GitHub Actions

每天北京时间 08:00 自动运行。首次使用需要配置 GitHub Secrets：

- `GH_TOKEN`：GitHub Personal Access Token
- `LLM_API_KEY`：LLM API Key
- `LLM_API_BASE`：LLM API Base URL
- `LLM_MODEL`：LLM 模型名称

也可以从 Actions 页面手动触发（`workflow_dispatch`）。

## License

MIT
