# Content Pack Guide — 内容包使用指南

## 什么是 Content Pack

`content_pack` 命令为给定 GitHub 仓库生成 10 个内容文件，覆盖 5 个平台 + 辅助文件。

## 生成文件清单

| 文件 | 用途 | 平台 |
|------|------|------|
| `ai_fde_analysis.md` | FDE 三维度深度拆解 | 公众号/通用 |
| `deep_analysis.md` | 深度技术分析 | 公众号/博客 |
| `xiaohongshu.md` | 小红书图文 | 小红书 |
| `douyin.md` | 抖音口播脚本 | 抖音 |
| `video_script.md` | 视频脚本 | 抖音/视频号 |
| `storyboard.md` | 分镜表 | 视频制作 |
| `wechat_article.md` | 公众号长文 | 公众号 |
| `risk_review.md` | 内容风险审查 | 发布前必读 |
| `quality_check.md` | 质量检查清单 | 自检 |
| `scorer_rules.md` | 评分规则生成 | 参考 |

## 生成模式

### 正常模式 (source_status: ok)
- README 完整可读
- GitHub API 正常响应
- 10个文件全部生成

### 降级模式 (source_status: degraded)
- README 不完整或 API 超时
- 使用缓存数据 + 规则模板填充
- `_manifest.json` 中标记 `files_degraded`

## manifest.json 字段说明

```json
{
  "repo": "owner/name",
  "generated_at": "2024-01-15T10:30:00Z",
  "status": "ok | degraded | failed",
  "mode": "llm | no_llm",
  "files_generated": 10,
  "files_degraded": 0,
  "files_failed": 0,
  "llm_mode": "disabled | enabled | fallback",
  "missing_fields": [],
  "requires_manual_review": false,
  "quality_status": "ready | needs_review | degraded",
  "risk_level": "none | low | medium | high",
  "recommended_platforms": ["xiaohongshu", "douyin"],
  "max_retries": 3,
  "timeout_seconds": 120
}
```

## 最佳实践

1. 生成后先读 `risk_review.md` 确认安全
2. 检查 `quality_check.md` 中的 [TODO] 项
3. 分镜表需配合视频剪辑使用
4. 各平台文案可能需要微调语气
