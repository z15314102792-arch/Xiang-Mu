# 项目运行结果

## 网页搜索与正文读取

- Agent 根据任务动态生成搜索查询并调用 SearXNG。
- 历史多轮搜索返回约 42–45 条结果。
- Agent 提取搜索结果 URL，继续调用 Jina Reader 读取网页正文。
- 网页读取请求返回 HTTP 200，正文约 3,899 字节，Agent 随后基于正文整理信息。

## 文档解析与知识库入库

使用一份 99 行 TXT 文档进行入库验证：

| 环节 | 运行结果 |
|---|---|
| 文档解析 | 成功提取正文 |
| 文本切片 | 生成 2 个文本块 |
| Embedding | 生成 512 维向量 |
| 向量写入 | 写入 Qdrant 的 `agent_knowledge_prod` 集合 |
| 数据读回 | 两个 Point 的正文和 metadata 均可读回 |
| 语义检索 | 查询命中相关文本块 |

入库 metadata 包含文件名、来源路径、分类、数据集标记、状态、导入时间和文件属性。

## Agent 知识库检索

Agent 通过原生 Qdrant 知识库工具执行语义检索：

- 使用本地 Embedding 服务生成查询向量。
- 从 `agent_knowledge_prod` 集合检索相关文本块。
- Agent Preview 的执行记录中包含原生 Qdrant 检索工具调用。
- 独立语义查询返回的相关结果得分约为 0.6816 和 0.5661。

## 项目进度查询

「读取项目进度」工作流使用 `project_name=n8n` 进行查询：

- 扫描活动记忆记录：3 条。
- 匹配项目记录：1 条。
- 返回字段：`memory_key`、`memory_type`、`content`、`evidence`、`importance`、`tags`、`updatedAt`。
- 不存在的项目名称返回 0 条匹配记录。

## 重新 Embedding 迁移对照（2026-11-19）

- 正式源集合：`agent_knowledge_prod`，共 2 个 Point。
- 测试目标集合：`knowledge-test-v2`，512 维、Cosine，迁移前为空。
- 迁移方式：Scroll 读取原始文本块，调用本地 FastEmbed `BAAI/bge-small-zh-v1.5` 重新生成向量，再按原 Point ID Upsert。
- 迁移校验：2 个 Point 的 ID、正文和 metadata 完全一致；向量均为 512 维，重新生成前后向量相似度约 1.0。
- 同一问题在新旧集合的语义检索结果、排序和分数一致：0.68157613、0.56608593。
- 原集合未修改；「知识库入口」与 `agent_knowledge_native` 仍指向 `agent_knowledge_prod`。
- **尚未完成：** Agent 1 尚未切换到 `knowledge-test-v2`，因此新集合的 Agent 运行时检索仍待验收。迁移测试工作流不属于本仓库六条核心导出。

## 记忆保存与读取

- 「保存记忆」工作流使用 Upsert，根据记忆键新增或更新记录。
- 「读取记忆」工作流按查询条件读回结构化记录。
- Agent Preview 执行记录中包含记忆读取和项目进度查询工具调用。

## Agent 多工具协作

Agent 可在同一任务中组合搜索、网页读取、知识库检索和工作流工具。复杂任务由 Skills 指导拆分、委派与结果整合，并受到搜索、网页读取和子 Agent 调用上限约束。
