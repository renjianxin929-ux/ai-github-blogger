# $full_name — Repo Snapshot

## 基本信息

| 字段 | 值 |
|------|----|
| 项目名 | [$full_name]($url) |
| 描述 | $description |
| Stars | $stars |
| Forks | $forks |
| 语言 | $language |
| Topics | $topics |
| 许可证 | $license |
| 最近更新 | $updated_at |
| 贡献者数 | $contributors_count |

## 分类 & 风险

| 字段 | 值 |
|------|----|
| Content Type | 根据 README 和 Topics 判断项目类型（runnable_project / framework_tool / awesome_list / tutorial_guide / high_risk / unclear） |
| Risk Level | 低 / 中 / 高 / blocked |
| High Risk Flags | 列出所有命中的高风险关键词 |
| AI 相关性证据 | 列出所有 AI 相关的 topics 和 README 描述 |

## Layer 1 — 选题评分 (Repo Selection Score)

**$score / 100**

| 维度 | 分数 (max) |
|------|-----------|
| AI 相关性 | / 20 |
| 近期活跃度 | / 15 |
| 项目清晰度 | / 15 |
| 可运行/可展示 | / 15 |
| 内容可讲性 | / 15 |
| 社区信号 | / 10 |
| 风险可控性 | / 10 |

## Layer 2 — 商业价值评分 (Business Value Score)

分析这个项目在以下 6 个维度的商业价值：
1. 普通人理解成本
2. 企业落地场景
3. AI-FDE 训练价值
4. 商业服务延展方式
5. 业务流程结合度
6. 风险可控性

并结合 $name 的具体功能给出各维度 0-10 评分和总分。

## Layer 3 — 平台适配评分 (Platform Fit Score)

为以下 5 个平台给出独立的 0-100 适配度评分：
- 小红书（图文卡片 / 收藏价值 / 小白友好）
- 抖音（钩子 / 视觉演示 / 60秒短视频）
- 视频号（企业老板视角 / 稳重 / 降本增效）
- 公众号（深度长文 / 方法论沉淀 / AI-FDE视角）
- 外贸/GEO（客户分析 / AI搜索可见性 / 服务切入点）

明确标注最佳平台和 GEO 适用判断。

## Layer 4 — 风险画像 (Risk Profile)

评估以下 8 个风险维度：许可证风险、数据隐私、账号自动化、爬虫/平台规则、深伪/冒充、垃圾/钓鱼、夸大宣传、客户端滥用。

给出综合风险等级和具体注意事项。

## README 摘要

从 README 中提取 3-5 个关键点，帮助快速理解项目核心功能和适用场景。
