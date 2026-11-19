# 系统架构

## 1. 总体结构

系统由 Agent 决策层、工具执行层、知识检索层、记忆数据层和文档处理层组成。

- **Agent 决策层：** n8n Agent 1，使用 DeepSeek 4.1，负责理解任务、规划动作和选择工具。
- **工具执行层：** SearXNG 搜索、Jina Reader 正文读取，以及独立 n8n 工作流工具。
- **知识检索层：** Qdrant 保存文档向量；Agent 通过原生 Qdrant Vector Store 入口执行语义检索。
- **记忆数据层：** n8n Data Table 保存结构化记忆，供记忆读取和项目进度查询工作流复用。
- **文档处理层：** 表单或本地文件输入，经 TXT/PDF 解析、文本切片和 Embedding 后写入 Qdrant。

## 2. Agent 工具

| 工具 | 输入 | 输出 / 作用 |
|---|---|---|
| web_search | 自然语言查询 | SearXNG 搜索结果、标题、URL 和摘要 |
| web_reader | URL | Jina Reader 网页正文 |
| 知识库入口 | 自然语言问题 | Qdrant 语义检索结果 |
| save-memory | memory_key、正文、类型、证据等 | Upsert 记忆记录 |
| read-memory | 记忆查询条件 | 返回匹配的记忆记录 |
| 读取项目进度 | project_name、limit | 返回项目进度、证据和更新时间 |
| add-numbers | a、b | 返回结构化加法结果 |

## 3. 知识库入库链路

「知识库入库」保留两种入口：

1. Form Trigger（表单触发）：通过表单上传文档。
2. When Executed by Another Workflow（由其他工作流执行时）：接收本地文件父工作流解析后的正文与文件元数据。

处理过程：

1. Default Data Loader（默认文档加载器）读取正文和元数据。
2. FastEmbed 使用 `BAAI/bge-small-zh-v1.5` 生成 512 维向量。
3. Qdrant Vector Store 将向量、正文和 metadata 写入 `agent_knowledge_prod`。
4. Agent 1 当前通过「知识库入口」检索正式集合；别名 `agent_knowledge_native` 同样指向 `agent_knowledge_prod`。2026-11-19 已完成 2 个 Point 到 `knowledge-test-v2` 的重新 Embedding 对照迁移，但 Agent 1 尚未切换到测试集合。

| 参数 | 值 |
|---|---|
| Qdrant | 1.20.0 |
| Collection | `agent_knowledge_prod` |
| Vector size | 512 |
| Distance | Cosine |
| Embedding | `BAAI/bge-small-zh-v1.5` |
| Embedding 服务 | FastEmbed 0.9.1 |
| Encoding format | float |

## 4. 本地文件解析链路

「本地文件读取与入库」工作流负责读取资料目录：

1. 手动触发。
2. 从配置的文件目录读取文件。
3. Switch 按扩展名区分 TXT 与 PDF。
4. 两条分支分别提取正文。
5. 统一文件名、来源路径、文件类型、大小和 MIME 类型等元数据。
6. Merge 合并解析结果。
7. 调用「知识库入库」子工作流。

父工作流与入库子工作流分离，文档解析逻辑与向量写入逻辑可以独立复用。

## 5. 记忆与项目进度

「保存记忆」使用 n8n Data Table Upsert，按 `scope_id`、`agent_id` 和 `memory_key` 匹配记录；存在时更新，不存在时新增，并保存 memory_type、content、evidence、importance 和 tags。

「读取记忆」按 scope、Agent 和 active 状态读取结构化记录。

「读取项目进度」标准化 `project_name` 和 `limit`，读取活动记忆、筛选项目类记录，并返回正文、证据、重要程度、标签和更新时间。该工具复用记忆表，不需要为项目进度另建数据存储。

## 6. 搜索与网页阅读

搜索由 SearXNG 提供，Agent 根据任务动态生成查询词。搜索结果 URL 继续传给 Jina Reader，获取网页正文后再进行分析。搜索摘要与网页正文分开处理。

## 7. Skills 与任务协作

Agent 1 配置两类 Skills：

- **网页资料研究与事实核验：** 规范外部搜索、原文读取、来源核对和事实整理。
- **复杂任务编排与多智能体协作：** 管理复杂任务拆分、子任务委派和协作结果整合。

复杂任务设置资源上限：每个任务最多委派 2 个子 Agent、最多同时运行 1 个；搜索和网页读取设置全局调用上限；出现余额不足或 HTTP 402 时停止后续调用。
