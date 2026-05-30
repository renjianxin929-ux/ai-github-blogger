# Safety Boundary — 安全边界声明

## 系统安全边界

本工具是**纯规则评分系统**，不自主生成内容，不自动发布。安全边界如下：

### 不做的事 (Hard Boundary)

1. **不自动发布** — 所有输出为本地 markdown 文件，需人工审核后发布
2. **不生成 NSFW 内容** — Deep-Live-Cam 等 deepfake 工具自动拦截
3. **不推荐高风险项目** — 含 NSFW/adult/uncensored 关键词的项目自动进入 blocked pool
4. **不调用未授权的 API** — 仅使用 GITHUB_TOKEN (public_repo scope) 和 LLM_API_KEY
5. **不存储用户数据** — 所有数据在本地 data/ 目录

### API Key 保护

- `GITHUB_TOKEN` 和 `LLM_API_KEY` 仅通过 `.env` 文件读取
- `.env` 已在 `.gitignore` 中
- 代码中无硬编码密钥
- `cmd_doctor()` 会检查 `.env` 文件权限

### 内容审查

- `content_pack` 生成的内容包含 `risk_review.md` 审查文件
- `quality_check.md` 标注 `source_status: degraded` 表示降级生成
- 人工审核清单 (8项) 必须在发布前完成

### 数据隐私

- 数据全部存储在本地 `data/` 目录
- 无遥测/analytics
- 无用户行为跟踪
- 不上传任何数据到第三方服务器

### 合规说明

- GitHub API 使用遵循 [GitHub Terms of Service](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service)
- 生成的公开内容应遵循各平台的内容政策
- 引用开源项目时保留原作者和许可证信息
