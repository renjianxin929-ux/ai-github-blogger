# V0.1 真实试用检查表 — 连续 3 天

> 开始日期: ______年______月______日
> 结束日期: ______年______月______日
> 操作者: 任健鑫
> 目的: 验证 ai-github-blogger v0.1 在真实日更场景下的可用性

---

## 试用目标

1. 验证每日选题管线能否稳定产出可发布内容
2. 验证内容审核链路（review → revise → approve）的实用性
3. 验证表现数据录入和 insights 复盘建议的可操作性
4. 发现至少 3 个需要改进的地方（为 v0.2 做准备）

---

## 准备事项（试用前）

- [ ] `.env` 文件已配置 `GITHUB_TOKEN` 和 `LLM_API_KEY`
- [ ] `python run.py doctor` 显示 PASS 或仅 WARN（无 FAIL）
- [ ] `python -m pytest tests/ -v` 全部通过
- [ ] `python run.py quality-gate` 显示 VERDICT: PASS
- [ ] 公众号后台可正常登录
- [ ] 小红书/抖音/视频号 至少 1 个平台已准备好
- [ ] Obsidian 或记事本打开，用于记录试用笔记

---

## Day 1 — 管线验证 + 首次内容生成（不发布）

> 目标: 验证整个管线从选题到内容生成都正常，但不实际发布。

### 上午: 环境 + 选题

- [ ] `python run.py doctor` — 确认环境健康
- [ ] `python run.py daily-workflow` — 运行日更选题流程
- [ ] `python run.py workbench` — 查看工作台
- [ ] 记录今日 Top1 候选项目: `_______________`
- [ ] 记录 Top1 的可发布性分数: `______/100`

### 下午: 内容生成

- [ ] `python run.py content <Top1项目>` — 生成内容包
- [ ] 阅读 `data/content_packs/<project>/09_risk_review.md` — 确认无敏感内容
- [ ] 阅读 `data/content_packs/<project>/10_quality_check.md` — 检查 [TODO] 项数量
- [ ] 通读至少 2 个平台 ready 文件（如 `05_wechat_article.md` 和 `02_xiaohongshu.md`）
- [ ] 记录内容质量主观评分 (1-5):
  - 公众号文章: ______/5
  - 小红书笔记: ______/5
  - 视频脚本: ______/5

### 晚间: 反思

- [ ] 试用笔记 Day 1 记录:
  - 什么顺利: _______________
  - 什么卡住: _______________
  - 内容需要改多少才能发布: ( ) 几乎不用改  ( ) 微调  ( ) 大改  ( ) 不能用
  - 发现了什么 bug 或改进点: _______________

---

## Day 2 — 完整发布链路（模拟真实发布）

> 目标: 完成从选题到"发布"的完整链路，实际手动发布到至少 1 个平台。

### 上午: 选题 + 生成

- [ ] `python run.py doctor` — 确认环境
- [ ] `python run.py daily-workflow` — 新一天选题
- [ ] `python run.py workbench` — 查看今日最佳候选
- [ ] 如果有新的 A 级项目，优先选新的；否则用 Day 1 的项目
- [ ] 选定项目: `_______________`
- [ ] `python run.py publish-flow <选定项目>` — 一键发布流程

### 下午: 审核 + 发布

- [ ] 阅读 `06_review_report.md` — 确认审核判决
- [ ] 审核判决是: ( ) ready  ( ) needs_revision  ( ) rejected
- [ ] 如果有阻断问题，用 `python run.py revise-pack` 改稿
- [ ] 确认无误后 `python run.py approve-pack <pack_dir>`
- [ ] 手动复制公众号文章到公众号后台，调整排版
- [ ] **实际发布**到公众号（或其他 1 个平台）
- [ ] `python run.py mark-published <pack_dir> --platform wechat --url "<实际URL>"` — 记录发布
- [ ] `python run.py publish-history` — 确认发布记录正确

### 晚间: 反思

- [ ] 试用笔记 Day 2 记录:
  - publish-flow 流程是否顺畅: _______________
  - review 是否发现了真实问题: _______________
  - 手动发布过程耗时: ______ 分钟
  - 从选题到发布总耗时: ______ 分钟

---

## Day 3 — 复盘 + 全链路验证

> 目标: 录入 Day 1 和 Day 2 的表现数据（真实或模拟），运行 insights，验证闭环。

### 上午: 数据录入 + 复盘

- [ ] `python run.py record-metrics <项目1> --platform wechat --views ... --likes ...` — 录入 Day 1 数据
- [ ] `python run.py record-metrics <项目2> --platform wechat --views ... --likes ...` — 录入 Day 2 数据
- [ ] 如果只有 1 个平台有数据，至少录入 3 条（满足 insights 最小置信度）
- [ ] `python run.py metrics-history` — 确认数据正确
- [ ] `python run.py insights` — 查看复盘建议
- [ ] 检查 insights 的每个建议是否都有"依据"标注: ( ) 全部有  ( ) 部分缺
- [ ] insights 的建议是否有实际指导意义: ( ) 有  ( ) 一般  ( ) 没有

### 下午: 全面验证

- [ ] `python -m pytest tests/ -v` — 确认全部通过
- [ ] `python run.py doctor` — 确认环境健康
- [ ] `python run.py quality-gate` — 确认 VERDICT: PASS
- [ ] `python run.py workbench` — 确认 §8 复盘建议正常输出
- [ ] `python run.py dashboard` — 确认 §7 发布后表现 + §8 趋势摘要正常
- [ ] `python run.py insights` — 确认所有 5 个区块正常

### 晚间: 总结

- [ ] 试用笔记 Day 3 记录:
  - 3 天总共发布了几篇: ______
  - 3 天总共覆盖了几个平台: ______
  - insights 的复盘建议是否靠谱: _______________
  - 最大的痛点是什么: _______________
  - 最希望 v0.2 加什么功能: _______________

---

## 试用终期评估

完成 3 天试用后，逐项评估:

### 功能完整性

| 功能 | 可用? | 备注 |
|------|-------|------|
| 每日选题 (daily) | [ ] 是  [ ] 否 | |
| 工作台 (workbench) | [ ] 是  [ ] 否 | |
| 仪表盘 (dashboard) | [ ] 是  [ ] 否 | |
| 内容生成 (content) | [ ] 是  [ ] 否 | |
| 发布审核 (review/approve) | [ ] 是  [ ] 否 | |
| 表现录入 (record-metrics) | [ ] 是  [ ] 否 | |
| 复盘建议 (insights) | [ ] 是  [ ] 否 | |

### 可用性评分

| 维度 | 评分 (1-5) | 说明 |
|------|------------|------|
| 安装部署 | /5 | |
| 命令易用性 | /5 | |
| 内容质量 | /5 | |
| 错误提示 | /5 | |
| 文档完整度 | /5 | |

### 是否建议继续投入?

- [ ] 是 — 系统可用，建议进入 v0.2 迭代
- [ ] 条件通过 — 需要修复 ______ 后再继续
- [ ] 否 — 需要重大重构

### 发现的 Bug 和改进点

1. _______________
2. _______________
3. _______________
4. _______________
5. _______________

### v0.2 期望功能

1. _______________
2. _______________
3. _______________

---

## 附: 每日快速命令序列

```bash
# === 每天早上 3 条命令 ===
python run.py doctor          # 1. 环境检查
python run.py daily-workflow  # 2. 选题发现
python run.py workbench       # 3. 查看工作台，确定今天做什么

# === 选定项目后 ===
python run.py publish-flow owner/repo   # 一键: 构建 + 审核 + 发布指引

# === 手动发布后 ===
python run.py mark-published <pack_dir> --platform wechat --url "https://..."

# === 发布 24-48h 后 ===
python run.py record-metrics owner/repo --platform wechat --views ... --likes ... --favorites ... --comments ... --leads ...

# === 每天收尾 ===
python run.py insights        # 查看数据驱动的复盘建议
```

---

## 版本记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-02 | v0.1 | 初始版本，3天试用计划 |
