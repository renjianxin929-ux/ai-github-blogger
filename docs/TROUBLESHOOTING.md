# Troubleshooting — 常见问题排查

## GitHub API 限流

**症状**: `rate_limit` 错误，fetch 返回 0 个 repo

**解决**:
```bash
# 检查剩余额度
python run.py doctor

# 设置 GITHUB_TOKEN（无 token 只有 60次/小时）
# 在 .env 中: GITHUB_TOKEN=ghp_xxxxxxxx
```

## 所有 repo 被拦截

**症状**: `daily` 运行后 "No repos after dedup"

**解决**:
```bash
# 清除 seen_repos 状态重新开始
rm data/state/seen_repos.json
rm data/state/generated_repos.json
python run.py daily --no-llm
```

## 内容包生成失败

**症状**: `python run.py content owner/repo` 返回 exit code 1

**可能原因**:
1. repo 名称拼写错误（区分大小写）
2. 网络超时 — 等待 1 分钟后重试
3. README 缺失 — 系统会自动降级（degraded mode），输出内容标注 `source_status: degraded`

**解决**:
```bash
# 重新生成（自动使用缓存重试）
python run.py content owner/repo

# 检查生成状态
cat data/content_packs/owner_repo/_manifest.json
```

## Windows 控制台乱码

**症状**: 输出中的 emoji 显示为乱码

**解决**: 系统已内置 `sys.stdout.reconfigure(encoding='utf-8')`。如果仍有问题，使用 Windows Terminal 而非 cmd.exe。

## LLM 分析无输出

**症状**: daily_report 中分析章节显示 "未评估"

**原因**: `--no-llm` 模式是默认行为。需要 LLM 分析时：
```bash
python run.py daily  # 不加 --no-llm，需要 LLM_API_KEY
```
