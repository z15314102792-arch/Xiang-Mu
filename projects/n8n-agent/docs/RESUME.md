# 简历项目描述

## 基于 n8n 的个人 AI Agent 与知识库自动化系统

基于 n8n 搭建个人 AI Agent，接入 DeepSeek、SearXNG 网页搜索、网页正文读取及 Qdrant 向量知识库，设计文档入库、记忆管理和项目进度查询等可调用工作流。

- 搭建网页搜索与正文读取链路，实现搜索结果 URL 自动传递、正文获取和信息整合。
- 设计文档入库流程，支持表单与工作流双入口，完成 TXT/PDF 解析、文本切片、512 维 Embedding 和 Qdrant 向量写入。
- 接入 Agent 原生知识库检索，实现资料语义召回与基于检索内容的问答。
- 设计记忆保存、读取和项目进度查询工具，使用 n8n Data Table 实现结构化信息 Upsert 与条件检索。
- 完成模型、搜索服务、向量数据库和工作流工具的集成，处理 HTTP 状态、Embedding 编码、向量维度及集合别名等问题。

**项目职责：** 需求拆解、Agent 工具规划、工作流设计与配置、服务集成、数据结构设计、异常排查和运行验收。

**技术栈：** n8n、DeepSeek Flash、SearXNG、Qdrant、FastEmbed、RAG、Embedding、Docker、JavaScript。
