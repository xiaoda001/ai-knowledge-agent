# Ragas 离线 RAG 评测

评测脚本通过当前聊天 API 回放固定合成问题集，然后使用 Ragas 计算 Context Precision、Context Recall、Faithfulness、Answer Relevancy。脚本还会检查回答引用编号是否存在。ACL 边界需要继续使用项目自有权限用例验证。

Ragas 只属于离线评测环境，不安装到 API/Worker 的生产依赖中。

## 准备

1. 按 [`sample-documents/README.md`](../../../sample-documents/README.md) 将虚构的人事制度和电商售后样例导入知识库，并等待文档索引完成。
2. 准备有权访问这些知识库且拥有 `chat.use` 权限的用户 bearer token。
3. 为评分器配置获准的 OpenAI-compatible LLM 和 embeddings endpoint。评分器会接收用户问题、检索片段、模型回答和参考答案；仅在合成/批准的数据上运行。
4. 在仓库根目录建立独立环境并安装评测依赖：

   ```powershell
   uv venv --python 3.13 .venv-evaluation
   uv pip install --python .venv-evaluation\Scripts\python.exe -r requirements-evaluation.txt
   ```

## 配置与运行

通过环境变量配置评分器和 API token：

```powershell
$env:RAGAS_API_TOKEN = "<authorized bearer token>"
$env:RAGAS_EVAL_BASE_URL = "http://localhost:8000/v1"
$env:RAGAS_EVAL_API_KEY = "<evaluation provider key>"
$env:RAGAS_EVAL_MODEL = "<judge model>"
$env:RAGAS_EVAL_EMBEDDING_MODEL = "<embedding model>"
```

服务端 API 需已启动。把两个已授权知识库 ID 一起传入，以便样例中的人事和电商问题都能检索：

```powershell
.\.venv-evaluation\Scripts\python.exe apps\server\evaluation\run_ragas.py `
  --knowledge-base-id <hr-kb-id> `
  --knowledge-base-id <commerce-kb-id>
```

评测集位于 [`dataset.jsonl`](dataset.jsonl)。可用 `--dataset <path>` 提供人工维护的新版本，或用 `--output <path>` 指定报告位置。默认报告写入被 Git 忽略的仓库根目录 `evaluation-results/`；报告仅保存各样本分数和总体均值，不保存问题、回答、检索文本或 token。

指标采用 Ragas 0.4 collections API。`langchain-community` 固定在 0.3.31，以保留 Ragas 0.4.1 导入的 Vertex AI 兼容模块路径。首版使用固定人工维护的合成数据；生成式测试样本需要人工审核后才能纳入回归集。
