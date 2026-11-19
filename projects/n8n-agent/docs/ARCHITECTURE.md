# 系统架构

## 1. 总体结构

系统由 Agent 决策层、工具执行层、知识检索层和记忆数据层组成。

- **Agent 决策层：** DeepSeek Flash，负责理解用户目标、规划动作和选择工具。
- **工具执行层：** n8n 工作流封装网页搜索、网页阅读、记忆读写、项目查询和算术计算。
- **知识检索层：** Qdrant 存储文档向量，Agent 使用原生 Vector Store 入口执行语义检索。
- **记忆数据层：** n8n Data Table 保存结构化记忆，供记忆读取和项目进度查询工作流复用。
- **文档处理层：** 表单或本地文件输入，经解析、切片、Embedding 后写入 Qdrant。

## 2. Agent 工具

| 工具 | 输入 | 输出 / 作用 |
|---|---|---|
| web_search | 自然语言查询 | SearXNG 搜索结果、标题、URL、摘要 |
| web_reader | URL | 网页正文内容 |
| 知识库入口 | 自然语言问题 | Qdrant 语义检索结果 |
| save-memory | memory_key、正文、类型、证据等 | Upsert 记忆记录 |
| read-memory | 记忆查询条件 | 返回匹配的记忆记录 |
| 读取项目进度 | project_name、limit | 返回项目进度、证据和更新时间 |
| add-numbers | a、b | 返回结构化加法结果 |

## 3. 知识库入库链路

### 输入入口

「知识库入库」保留两种入口：

1. Form Trigger：通过表单上传文档。
2. When Executed by Another Workflow：接收其他工作流解析后的正文与文件元数据。

### 处理过程

1. Default Data Loader 读取文档正文和元数据。
2. FastEmbed 服务使用 `BAAI/bge-small-zh-v1.5` 生成 512 维向量。
3. Qdrant Vector Store 将向量、正文和 metadata 写入 `agent_knowledge_prod`。
4. Agent 通过「知识库入口」检索正式集合。

### 向量配置

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

「本地文件读取」工作流负责批量读取目录中的资料：

1. 手动或定时触发。
2. 从文件目录读取文件。
3. Switch 按扩展名区分 TXT 与 PDF。
4. 两条分支分别提取正文。
5. 使用统一字段结构整理文件名、来源路径、文件类型、大小和 MIME 类型。
6. Merge 合并解析结果。
7. 调用「知识库入库」子工作流。

父工作流与入库子工作流分离，文档解析逻辑与向量写入逻辑可以独立复用。

## 5. 记忆与项目进度

### 保存记忆

「保存记忆」工作流使用 n8n Data Table 的 Upsert 操作，按 `scope_id`、`agent_id` 和 `memory_key` 匹配记录，存在时更新，不存在时新增。

### 读取记忆

「读取记忆」工作流从「agent记忆」数据表读取结构化记录，为 Agent 提供历史信息。

### 读取项目进度

「读取项目进度」工作流包含两个入口：本地 Webhook 测试入口和 Agent 工作流入口。主流程依次执行：

- 标准化 `project_name` 和 `limit`。
- 读取活动记忆记录。
- 筛选项目类记录。
- 按项目名称匹配并返回正文、证据、重要程度、标签和更新时间。

该工具复用记忆表，不需要为项目进度另建数据存储。

## 6. 搜索与网页阅读

搜索由 SearXNG 提供，Agent 根据任务动态生成查询词。搜索结果中的 URL 可继续传给网页读取工具，获取网页正文后再进行分析。

搜索结果摘要与网页正文分开处理，Agent 可以基于实际读取到的正文提取信息。

## 7. Agent Skills

- **网页资料研究与事实核验：** 规范外部搜索、来源核对和事实整理。
- **复杂任务编排与多智能体协作：** 管理复杂任务拆分、子任务委派和资源使用策略。

Skill 由 Agent 根据任务类型加载，与工作流工具配合使用。
