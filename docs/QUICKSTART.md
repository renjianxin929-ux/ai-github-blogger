# Quickstart — 5分钟快速上手

## 前置条件

- Python 3.10+
- GitHub Token (https://github.com/settings/tokens, 勾选 `public_repo`)
- (可选) LLM API Key 用于 AI 分析

## 安装

```bash
cd ai-github-blogger
cp .env.example .env
# 编辑 .env，填入 GITHUB_TOKEN
pip install -r requirements.txt
```

## 第一次运行

```bash
# 1. 环境检查
python run.py doctor

# 2. 无 LLM 模式跑一次完整管道
python run.py daily --no-llm

# 3. 查看生成报告
ls data/reports/
```

## 三个核心命令

| 命令 | 用途 | 耗时 |
|------|------|------|
| `python run.py doctor` | 环境健康检查 | 5秒 |
| `python run.py daily --no-llm` | 每日选题发现 | 2-5分钟 |
| `python run.py content owner/repo` | 为某仓库生成内容包 | 1-3分钟 |
| `python run.py quality-gate` | 系统质量检查 | 30秒 |

## 输出文件

运行 `daily` 后会生成 3 个报告：
- `daily_report_YYYY-MM-DD.md` — 完整选题报告
- `daily_brief_YYYY-MM-DD.md` — 一屏工作台
- `review_queue_YYYY-MM-DD.md` — 人工审核队列
