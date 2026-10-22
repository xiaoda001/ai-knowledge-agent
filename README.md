# Enterprise Knowledge Base

首个切片实现：企业自托管 Markdown 知识库，包含登录、知识库成员权限、文档 ACL、异步索引和引用问答界面。

开发目录与模块边界遵循 [DEVELOPMENT.md](DEVELOPMENT.md)。

## 启动

1. 复制 `.env.example` 为 `.env`，设置 MySQL 密码和至少 32 字节的随机 `JWT_SECRET`。JWT 默认有效期为 1440 分钟（24 小时），可通过 `JWT_MINUTES` 配置。本地 Python 进程会自动读取项目根目录 `.env`；Compose 会把 `.env` 注入 API 和 Worker。远程部署时同时将 `VITE_API_URL` 设置为浏览器可访问的 API 地址，并在 `CORS_ORIGINS` 中填写精确的 Web 来源；重新构建 Web 镜像使 API 地址生效。
2. 运行 `docker compose up --build`。
3. 一次性创建管理员：`docker compose exec api python -m app.cli`。
4. API 文档位于 `http://localhost:8022/docs`，Web 位于 `http://localhost:8020`。

管理员登录 Web 后可建库、创建成员并加入当前知识库；登录用户可查看授权范围内的文档，管理员可查看所加入知识库的处理状态。API 文档位于 `/docs`，仍可用于脚本化管理。文档上传当前限管理员，且 ACL 不能超出上传者自己的部门、密级和角色范围。

聊天支持闲聊、授权知识库问答和系统信息查询。系统统计仅返回当前登录用户可访问的知识库数量，或指定知识库中按文档 ACL 可见且已完成索引的文档数量；用户不必先加入知识库即可闲聊或查询自身可访问知识库数。

聊天输入框可附加一个 PDF、DOCX、XLSX、PPTX、TXT、CSV 或 Markdown 文件（最大 20 MiB）作为本轮问答上下文。附加文件时，当前回答基于附件内容生成，不叠加知识库检索。服务端临时提取最多 50,000 个字符后删除临时文件；不支持扫描版 PDF OCR。会话历史只保存附件文件名，不保存附件原文。附件文本经过现有出站脱敏规则；若向远程 LLM 发送且未配置脱敏规则，提取出的原文会发送给该提供方。

管理员账号和用户需具有部门与密级。文档访问规则：知识库成员必需、部门精确匹配、文档密级不高于用户级别；文档指定允许角色时，用户至少匹配一个。缺少部门或密级时拒绝访问。

`LLM_MODE` 是布尔开关，只能设为 `true` 或 `false`，默认为 `false`。设为 `true` 后，本地或云端服务由 `LLM_BASE_URL` 决定。本地地址可使用 HTTP；云端地址必须使用 HTTPS。许可、主机白名单和脱敏规则目前为可选配置；未配置脱敏规则时，问题、对话历史、检索片段和附件提取文本会原样发送给所配置的云端提供方。若配置了 `REDACTION_RULES`，规则解析或执行失败时请求会被拒绝。示例 regex 规则采用 JSON 数组形式配置到 `.env`。

原始 Markdown 保存在 Docker 持久卷 `uploads`，向量数据保存在 `chroma_data`，MySQL 数据保存在 `mysql_data`。

向量化和重排只接入第三方 API，不在本地下载或运行模型。通过 `.env` 设置 `EMBEDDING_MODEL`、`EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`RERANKER_MODEL`、`RERANKER_BASE_URL` 和 `RERANKER_API_KEY`。API 根地址例如 `https://api.siliconflow.cn/v1`；程序分别追加 `/embeddings` 和 `/rerank`。远程调用会将文档片段和查询文本发送到配置的服务商。首次索引会确定 Chroma collection 的向量维度；更换向量模型前，应先迁移或重建向量索引。

`LLM_MODE`、`LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL` 也由 `.env` 配置。向量 API 与重排 API 使用其各自的地址和密钥，不会回退到本地模型。

聊天会在每条助手回复和会话汇总中展示模型 Token 用量。成本按 `.env` 中 `LLM_INPUT_PRICE_PER_1M`、`LLM_OUTPUT_PRICE_PER_1M` 配置的每百万输入/输出 Token 美元费率估算；未填写费率时显示“成本未配置”。模型未返回 usage 时使用 tokenizer 估算并标注“约”。设置 `LLM_STREAM_USAGE=true` 可请求 OpenAI 兼容接口在流式响应中返回用量；部分提供方不支持该选项，默认关闭。该统计只覆盖聊天模型调用，不含 embedding 和 reranker。
# Trace 与观测（本地可选）

默认关闭，避免默认开发环境额外启动观测服务。PowerShell 下启用：

```powershell
$env:OTEL_ENABLED = "true"
docker compose --profile observability up -d --build
```

随后访问 Grafana：<http://localhost:3000>（默认 `admin` / `admin`，首次登录请修改密码）。Prometheus：<http://localhost:9090>。Grafana 已配置 Prometheus、Tempo 和 Loki 数据源。在 Explore 中选择 Tempo 查看 trace 和调用链瀑布图；打开 span 的 `Logs for this span` 可以查看关联日志。在 Explore 选择 Loki 可以检索 API/Worker 日志，日志详情中的 TraceID 链接可跳回 Tempo。

OTel 日志通过 Collector 发往 Loki，保留 72 小时；trace ID/span ID 作为 Loki 结构化元数据用于关联，不作为高基数索引标签。当前聊天异常日志和界面会显示原始异常详情，暂未脱敏，日志只应留在本地开发环境中。

当前应用主要在聊天、检索等失败分支写应用日志；正常请求会有 trace 调用链，但不一定产生应用日志记录。

本地诊断期间，聊天生成失败会在界面显示底层异常文本，API 容器日志也记录异常堆栈；这些错误详情暂未脱敏，不要在共享或生产环境中启用此诊断行为。

只关闭应用遥测而保留观测服务时，设置 `$env:OTEL_ENABLED = "false"` 后重建 API/Worker。完整配置与隐私边界见 [观测模块说明](.ppd/05-modules/observability.md)。服务只在本机监听 UI 端口；不要将默认凭据用于对外部署。
