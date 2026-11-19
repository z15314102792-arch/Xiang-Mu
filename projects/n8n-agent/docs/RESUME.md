# 简历项目描述

## 基于 n8n 的个人 AI Agent 与知识库自动化系统

基于 n8n 搭建个人 AI Agent，使用 DeepSeek 4.1 作为推理模型，接入 SearXNG 网页搜索、Jina Reader 正文读取、Qdrant 向量知识库及 n8n Data Table 记忆系统，构建网页研究、RAG 检索、文档入库、记忆读写和项目进度查询能力。

- 搭建网页搜索与正文读取链路，实现 Agent 动态生成查询词、提取 URL、读取网页正文并整合信息。
- 设计文档入库流程，支持表单上传与本地文件双入口，完成 TXT/PDF 解析、文本切片、512 维 Embedding 和 Qdrant 向量写入。
- 接入 Agent 原生 Qdrant 知识库检索，实现资料语义召回与基于检索内容的问答。
- 设计记忆保存、读取和项目进度查询工具，使用 n8n Data Table 实现结构化信息 Upsert 与条件检索。
- 配置网页研究与多智能体协作 Skills，建立任务拆分、子 Agent 委派、搜索/阅读调用上限和余额异常停止规则。
- 处理 HTTP 500 与空结果判定、Embedding 维度与编码格式、Qdrant 集合别名及子工作流输入 Schema 等集成问题。

**项目职责：** 场景拆解、Agent 工具规划、n8n 工作流设计与配置、模型和外部服务接入、知识库结构设计、异常排查及运行验收。

**技术栈：** n8n 2.46.7、DeepSeek 4.1、SearXNG、Jina Reader、Qdrant、FastEmbed、BAAI/bge-small-zh-v1.5、RAG、Docker、JavaScript。
