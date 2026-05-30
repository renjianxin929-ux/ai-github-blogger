# Scoring System — 四层评分体系

## 概述

v4 四层评分，每层独立计算，最终综合排序。

## Layer 1: 选题分 (repo_selection_score) — 0-100

判断项目是否适合做内容选题。

| 因子 | 权重 | 说明 |
|------|------|------|
| Stars | 30% | star 越多分越高，但 >50000 反而降分 |
| Description 质量 | 25% | 有清晰中文描述加分 |
| Language | 15% | Python/JS/TS 加分，C++/Rust 不加分 |
| Topics | 15% | 含 AI/ML/LLM 等 tag 加分 |
| Activity | 15% | 7天内更新加分 |

## Layer 2: 商业价值分 (business_value_score) — 0-100

判断项目的"可拆解度"——做内容是否能吸引眼球。

| 因子 | 权重 |
|------|------|
| 话题热度 | 35% |
| 案例丰富度 | 25% |
| 教程友好度 | 20% |
| 商业化潜力 | 20% |

## Layer 3: 平台适配分 (platform_fit_score)

判断项目最适合哪个平台发布。

- 小红书 (图文/教程)
- 抖音 (短视频/演示)
- 视频号 (企业/深度)
- 公众号 (长文/技术)
- 外贸/GEO (跨境/seo)

## Layer 4: 风险评分 (risk_score)

安全/内容风险评估。

- 关键词匹配 (NSFW/隐私/侵权)
- 许可证检查
- 内容类型判断

## Pool 分类逻辑

```
runnable + 高分 → pool=top5
evergreen (Dify/n8n/LangChain等) → pool=evergreen (降权到 6-20)
awesome_list/tutorial_guide → pool=resource (降权)
高风险 → pool=blocked (拦截)
WEAK_AI/信息不足 → pool=review (人工审核)
```

## 人工校准

- `golden_cases.json` — 80个黄金样本，确保核心路由 100% 正确
- `adversarial_cases.json` — 30个对抗样本，确保边缘情况不误判
- `benchmark.py` — 每次代码改动后跑 benchmark 验证
