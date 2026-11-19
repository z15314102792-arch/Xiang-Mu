# 工作流导入指南

## 1. 导入顺序

先导入被调用的子工作流，再导入父工作流：

1. `knowledge-base-ingest.json` — 知识库入库。
2. `save-memory.json` — 保存记忆。
3. `read-memory.json` — 读取记忆。
4. `read-project-progress.json` — 读取项目进度。
5. `agent-tool-demo.json` — Agent 工具演示。
6. `local-file-ingest.json` — 本地文件读取与入库父工作流。

## 2. n8n 导入

1. 打开 n8n。
2. 进入 **Workflows（工作流）**。
3. 选择 **Import from File（从文件导入）**。
4. 选择对应 JSON 文件。
5. 保存工作流。

导入完成后，先配置服务连接、数据表和文件路径，再按使用场景启用工作流。

## 3. 环境配置

### Qdrant 与 Embedding

- 配置 Qdrant Credentials（凭据）。
- 创建或选择集合 `agent_knowledge_prod`，向量维度为 512，距离算法为 Cosine。
- 配置本地 FastEmbed 服务，模型为 `BAAI/bge-small-zh-v1.5`。
- Embedding 节点使用 `encodingFormat=float`。
- Agent 原生知识库入口连接到 Qdrant 正式集合；「知识库入口」和 `agent_knowledge_native` 指向 `agent_knowledge_prod`。

### 记忆 Data Table

在 n8n Data Tables（数据表）中创建「agent记忆」表，并在以下工作流中选择该表：

- 保存记忆
- 读取记忆
- 读取项目进度

将这三个工作流中的占位值替换为当前环境一致的标识：

- `YOUR_SCOPE_ID`：当前用户或记忆空间标识。
- `YOUR_AGENT_ID`：当前 Agent 标识。

三个工作流必须使用同一组值，才能读写同一批记忆记录。

### 本地文件目录

在「本地文件读取与入库」工作流的 **Read/Write Files from Disk（从磁盘读取/写入文件）** 节点中，将 `/path/to/knowledge/inbox/*` 改为 n8n 容器实际可访问的文件目录。

工作流按 TXT/PDF 分流解析，合并统一字段后调用「知识库入库」子工作流。导入后在 **Call '知识库入库'** 节点重新选择刚导入的子工作流。

### 项目进度测试入口

「读取项目进度」保留本地 Webhook（网络钩子）测试入口，路径为 `agent-project-progress-test`，请求方式为 POST；Agent 则通过独立工作流入口调用。

## 4. Agent 工具连接

在 Agent Builder 中连接：

- SearXNG 搜索工具。
- Jina Reader 网页正文读取工具。
- Qdrant 原生知识库入口。
- 保存记忆工作流。
- 读取记忆工作流。
- 读取项目进度工作流。
- 算术计算工作流。

将工具输入字段与工作流触发器 Schema 对齐。

## 5. 凭据与本机配置

工作流 JSON 不包含真实服务凭据。请在 n8n **Credentials（凭据）** 中创建 Qdrant、Embedding、搜索和其他服务的连接，并按本机环境设置容器网络地址。

本地路径、Data Table、工作流 ID 和 Agent 标识均按导入环境重新选择或填写，不直接沿用其他 n8n 实例的内部 ID。
