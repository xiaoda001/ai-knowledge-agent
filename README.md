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

聊天会在每条助手回复和会话汇总中展示聊天 LLM 的 Token 用量与估算成本。成本按 `.env` 中 `LLM_INPUT_PRICE_PER_1M`、`LLM_OUTPUT_PRICE_PER_1M` 配置的每百万输入/输出 Token 美元费率估算；未填写费率时显示“成本未配置”。模型未返回 usage 时使用 tokenizer 估算并标注“约”。设置 `LLM_STREAM_USAGE=true` 可请求 OpenAI 兼容接口在流式响应中返回用量；部分提供方不支持该选项，默认关闭。Embedding 和 reranker 用量/成本在启用观测时看 Langfuse 对应 spans，不计入聊天 UI 的 LLM 用量汇总。
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

## Langfuse（可选）

Langfuse 可作为 Agent trace 的额外接收端；现有 Tempo、Prometheus 和 Loki 保持可用。Langfuse 使用 OTLP/HTTP，应用同时保留发往本地 Collector/Tempo 的 OTLP/gRPC 导出。

在 `.env` 中配置 Langfuse 项目密钥：

```dotenv
OTEL_ENABLED=true
LANGFUSE_ENABLED=true
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_CAPTURE_CONTENT=false
```

Langfuse Cloud 用户按项目所在区域填写 `LANGFUSE_HOST`；自托管时填写自己的 Langfuse 地址。然后启动观测 profile：

```powershell
docker compose --profile observability up -d --build
```

每次聊天请求生成一条 trace；同一已保存会话的多条 trace 使用 `conversation_id` 作为 Langfuse `session_id`，可以在 Langfuse Sessions 中回放完整对话。未保存的单轮聊天分配独立 session。API 响应头提供 `X-Trace-ID` 和 `X-Session-ID`，聊天消息的 `usage` 数据也保存这两个 ID，因此可以从消息用量记录定位到对应 trace/session。Token、估算成本、检索/重排与模型操作在 trace spans 中；OTel 日志通过同一 trace context 关联到 Loki/Grafana。`LANGFUSE_CAPTURE_CONTENT=true` 后，还会把问题、模型输入输出和检索片段发送给 Langfuse，也会随现有 OTel trace 一并进入本地 Tempo。若配置了 `REDACTION_RULES`，追踪内容会应用这些规则；未配置时会记录原文。启用前请确认两处的访问范围和数据保留策略符合你的数据要求。未配置有效 Langfuse 凭据时，应用仍可启动并继续把 trace 发往本地观测栈。

Embedding 与 reranker 的远程请求会在 Langfuse 记录模型名、请求数和服务商返回的 token/billed units；请求会把 W3C `traceparent` 传给支持该协议的服务商，方便到服务商侧按同一 Trace ID 查调用。按服务商的可计费输入 Token 单价设置 `EMBEDDING_PRICE_PER_1M_TOKENS`、`RERANKER_PRICE_PER_1M_TOKENS`（美元/百万 Token）后，Langfuse 对应 observation 还会显示成本；未填费率时只显示用量，不伪造成本。提供商账单/用量页仍是最终结算依据。`bge` 等免费模型可留空费率。
