# Lumo Slack Bot

Lumo 是一个基于 **Django REST Framework**、**Slack SDK** 以及 **LiteLLM** 的 Slack 机器人。
它可以在 Slack 中和用户对话，并且能够对 thread 及 channel 的历史消息进行总结：

- Thread：总结整个 thread 的所有消息。
- Channel：默认总结当天的内容，也可以自定义日期或时间范围。

## 快速开始

1. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```
2. **配置环境变量**：复制 `.env.example` 为 `.env` 并填入真实的 Slack / LiteLLM 配置。
3. **初始化数据库**
   ```bash
   python manage.py migrate
   ```
4. **运行开发服务器**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

## 使用 Docker Compose（uv + Qdrant 向量存储）

项目内置了 `docker-compose.yml` 与 `Dockerfile`，默认使用 [uv](https://docs.astral.sh/uv/) 来安装依赖并运行 Django。
组合服务包含：

- `bot`：Lumo Slack Bot，本地端口 `8000`。
- `qdrant`：向量存储服务，使用官方 `qdrant/qdrant` 镜像并持久化到 `qdrant_data` 卷。

使用方式：

1. 准备 `.env`，包含原本运行机器人所需的 Slack、LiteLLM 变量。`docker compose` 会自动加载该文件。
2. （可选）如需为 Qdrant 设置 API Key，可在 `.env` 中加入 `QDRANT_API_KEY=<your-key>`，Compose 会自动透传给 Qdrant 容器。
3. 启动全部服务：
   ```bash
   docker compose up --build
   ```
   首次启动会在 `bot` 容器内执行 `uv run python manage.py migrate` 并拉起开发服务器。
4. 访问接口：
   - Slack bot API: http://localhost:8000/

若需要停止服务，执行 `docker compose down`；若希望清理向量存储数据，可同时加上 `-v` 删除 `qdrant_data` 卷。

## MCP 文档搜索服务器

项目包含一个基于 Model Context Protocol（MCP）的文档搜索服务，方便在本地用 LLM 工具调用已索引的 Slack 上传文档：

1. 确保已经通过 `docker compose up` 启动了 Qdrant，并配置好 OpenAI 相关环境变量（`OPENAI_API_KEY`、`OPENAI_MODEL`、`OPENAI_EMBEDDING_MODEL` 等）。
2. 运行 MCP 服务器：
   ```bash
   python scripts/mcp_document_search_server.py
   ```
3. 在支持 MCP 的客户端中调用 `search` 工具，输入关键词即可返回最多 5 条匹配的文档片段（包含文本、元数据与相似度）。

## 必填环境变量
| 变量 | 描述 |
| --- | --- |
| `SLACK_BOT_TOKEN` | Slack Bot Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Slack App Token (`xapp-...`) |
| `SLACK_SIGNING_SECRET` | 验证 Slack 请求使用 |
| `LITELLM_MODEL` | LiteLLM 使用的模型名称，例如 `gpt-4o-mini` |
| `SLACK_SUMMARY_MAX_MESSAGES` | 每次拉取的最大消息条数 |
> LiteLLM 需要配置对应模型供应商的 API Key，例如 `OPENAI_API_KEY`，配置方式详见 [LiteLLM 文档](https://docs.litellm.ai/).

## 可选环境变量
| 变量 | 描述 |
| --- | --- |
| `FILE_STORAGE_DIR` | 自定义统一的文件存储目录，默认为 `<BASE_DIR>/downloads` |

## Slack 文档索引与 LlamaIndex 集成

项目内置了基于 [LlamaIndex](https://github.com/run-llama/llama_index) 的文档索引能力，用于处理用户在 Slack 中上传的文件，并在后续对话问答中利用这些文档作为上下文。

- **依赖与环境变量**
  - 依赖已在 `requirements.txt` 中包含：`llama-index>=0.10.0`。
  - 需要的 OpenAI 相关配置：
    - `OPENAI_API_KEY`
    - `OPENAI_MODEL`（例如 `gpt-4o-mini`）
    - `OPENAI_EMBEDDING_MODEL`（例如 `text-embedding-3-small`）
    - `OPENAI_BASE_URL`（可选，用于通过代理 / 自建网关访问 OpenAI 接口）

- **文件下载与索引流程**
  - 当用户在 Slack 中上传文件并通过 `app_mention` @ 机器人时：
    1. `SlackEventView` 会调用 `_log_and_download_slack_files`，将附件下载到统一的 `downloads/` 目录，并记录本地路径。
    2. 下载成功后，先向用户回复一条固定消息：
       > 已成功下载你发的文件，我正在阅读中，稍后再帮你分析。
    3. 随后调用 `slackbot/services/document_indexer.py` 中的 `index_slack_files_and_summarize`：
       - 使用 LlamaIndex 读取本地文件，按「一个文件一个 Document」方式构建索引，并将索引存储在 Qdrant 中。
       - 为所有已上传的文件维护一个**全局向量索引**；
       - 生成简短的中文摘要，并以第二条消息的形式发回同一个 Slack 线程。

- **索引的持久化存储**
  - 所有文档向量索引会写入 Qdrant 中（默认集合名 `lumo_slack_documents`，可通过 `QDRANT_COLLECTION` 环境变量覆盖）。

- **在问答中使用文档上下文**
  - 当用户在 Slack 中继续向机器人提问时，`SlackEventView._answer_question` 会：
    1. 先拉取最近 24 小时的频道消息，构造原有的 Slack 对话上下文；
    2. 调用 `query_slack_file_context`，从全局 LlamaIndex 索引中检索与当前问题最相关的文档片段；
    3. 将检索到的文档片段与 Slack 消息上下文合并，一并发送给底层 LLM（通过 LiteLLM 调用），从而实现「结合上传文档内容进行回答」。

后续如果需要按 channel / thread 进一步拆分索引或优化查询策略，可以基于 `Document` 中的 `channel`、`thread_ts` 等元数据做更细粒度的扩展。

## API 设计

| Method | Endpoint | 说明 |
| --- | --- | --- |
| `POST` | `/api/slack/events/` | Slack Events API 入口，支持 `url_verification` 与 `app_mention` 事件 |
| `POST` | `/api/summaries/channel/` | 主动请求 channel 总结，支持指定日期或 `start_date`/`end_date` |
| `POST` | `/api/summaries/thread/` | 主动请求 thread 总结，需要传 `channel_id` + `thread_ts` |
| `GET` | `/api/health/` | 健康检查 |

### 示例：Channel Summaries
```http
POST /api/summaries/channel/
Content-Type: application/json

{
  "channel_id": "C123",
  "date": "2024-05-01",
  "max_messages": 100
}
```

### 示例：Thread Summaries
```http
POST /api/summaries/thread/
Content-Type: application/json

{
  "channel_id": "C123",
  "thread_ts": "1714567890.123456"
}
```

## Slack 配置建议
1. 在 [api.slack.com](https://api.slack.com/apps) 创建一个 App。
2. 打开 Event Subscriptions，回调 URL 指向 `/api/slack/events/`。
3. 订阅 `app_mention`、`message.channels` 等事件。
4. 将 Slash 命令或快捷方式指向 channel/thread summarization 接口以便手动触发。

## 测试
```bash
python manage.py test
```

## 架构概览
```
Lumo
├── manage.py
├── application/        # Django 项目配置
├── slackbot/       # 业务逻辑 (API、服务、模型)
└── requirements.txt
```

- `slackbot/services/slack_client.py`：封装 Slack API 访问。
- `slackbot/services/summarizer.py`：调用 LiteLLM 生成总结。
- `slackbot/views.py`：DRF API 视图，处理事件及总结请求。

欢迎根据业务需求扩展消息持久化、身份认证以及定时调度任务。
