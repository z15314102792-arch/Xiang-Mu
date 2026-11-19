# 工作流导入指南

## 导入顺序

建议先导入被调用的子工作流，再导入父工作流：

1. `knowledge-base-ingest.json` — 知识库入库。
2. `save-memory.json` — 保存记忆。
3. `read-memory.json` — 读取记忆。
4. `read-project-progress.json` — 读取项目进度。
5. `agent-tool-demo.json` — Agent 工具演示。
6. `local-file-ingest.json` — 本地文件读取父工作流。

## n8n 导入

1. 打开 n8n。
2. 进入 Workflows（工作流）。
3. 选择 Import from File（从文件导入）。
4. 选择对应 JSON 文件。
5. 保存工作流。

## 环境配置

导入后按实际环境完成以下配置：

- Qdrant API 凭据与集合 `agent_knowledge_prod`。
- 本地 Embedding 服务地址及模型 `BAAI/bge-small-zh-v1.5`。
- n8n Data Table「agent记忆」的数据表选择。
- 本地文件读取目录。
- 父工作流调用子工作流时重新选择「知识库入库」。
- 本地测试 Webhook 路径。
- Agent Builder 中对应工具的输入字段和工作流关联。

## Agent 工具连接

将以下能力接入 Agent：

- SearXNG 搜索工具。
- 网页正文读取工具。
- Qdrant 原生知识库入口。
- 保存记忆工作流。
- 读取记忆工作流。
- 读取项目进度工作流。
- 算术计算工作流。

凭据应在 n8n Credentials（凭据）中单独创建，不写入工作流 JSON。
