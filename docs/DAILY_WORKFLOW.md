# Daily Workflow — 每日工作流

## 30-60 分钟标准流程

### Step 1: 查看一屏工作台 (2-3 min)

```bash
cat data/reports/daily_brief_$(date +%Y-%m-%d).md
```

关注：Top 5 高置信选题、需人工审核数量、管道健康度。

### Step 2: 审核候选 (5-10 min)

```bash
cat data/reports/review_queue_$(date +%Y-%m-%d).md
```

按 8 项清单逐项检查需人工审核的候选：
1. 选题是否符合账号定位
2. README 是否清晰
3. 许可证是否允许引用
4. Star 数是否合理
5. 最近是否活跃
6. 竞品是否已做过
7. 是否有敏感内容
8. 是否值得分配时间

### Step 3: 选取最终选题 (2-3 min)

从 Top 5 + 审核通过候选中选 1-3 个今天做的选题。

### Step 4: 生成内容包 (15-30 min)

```bash
python run.py content owner/repo
```

每个 repo 生成 10 个内容文件：
- 深度分析、小红书、抖音、视频号、公众号
- 视频脚本、分镜表、风险审查、质量检查、评分规则

### Step 5: 发布 (5-10 min)

将生成的 markdown 文件发布到对应平台。

### Step 6: 标记完成 (1 min)

系统自动在管道末尾更新 seen_repos 状态，避免重复选题。

## 快捷操作

```bash
# 跑完立刻看结果
python run.py daily --no-llm && cat data/reports/daily_brief_$(date +%Y-%m-%d).md

# 质量检查
python run.py quality-gate

# 为 Top 1 选题生成全部内容
python run.py content <top1-owner/repo>
```
