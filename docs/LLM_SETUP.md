# LLM Setup — LLM 接入配置

## 概述

本工具**默认在无 LLM 模式下运行**（纯规则评分），LLM 为可选增强。

## 启用 LLM

1. 在 `.env` 中设置 `LLM_API_KEY`
2. 去掉 `--no-llm` 标志：
```bash
python run.py daily  # 不加 --no-llm
```

## LLM 用于哪些环节

| 环节 | 无 LLM 行为 | 有 LLM 行为 |
|------|------------|------------|
| FDE 分析 | 显示"未评估" | 生成 FDE 三维度分析 |
| 内容包生成 | 模板填充 | AI 生成内容 |
| quality_check | 显示"未评估" | 生成质量评分 |

## 支持的 LLM Provider

配置 `LLM_API_BASE` 和 `LLM_MODEL` 即可接入兼容 OpenAI API 的服务。

```env
# OpenAI
LLM_API_KEY=sk-xxx
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# DeepSeek
LLM_API_KEY=sk-xxx
LLM_API_BASE=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# 其他兼容 API
LLM_API_KEY=your-key
LLM_API_BASE=https://your-api.com/v1
LLM_MODEL=your-model
```

## 降级策略

- LLM 调用超时 120s
- 失败自动重试 3 次（指数退避）
- 3 次失败后降级为无 LLM 模式
- 生成内容标注 `source_status: degraded`

## 安全注意事项

- 不要在代码中硬编码 API Key
- 不要在 git commit 中包含 `.env` 文件
- 定期轮换 API Key
