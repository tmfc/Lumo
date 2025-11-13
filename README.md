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

## 使用 Docker Compose（uv、mem0 自建 + 向量存储）

项目内置了 `docker-compose.yml` 与 `Dockerfile`，默认使用 [uv](https://docs.astral.sh/uv/) 来安装依赖并运行 Django。
组合服务包含：

- `bot`：Lumo Slack Bot，本地端口 `8000`。
- `mem0`：自建 mem0 服务器，本地端口 `8100`。
- `qdrant`：mem0 需要的向量存储，使用官方 `qdrant/qdrant` 镜像并持久化到 `qdrant_data` 卷。

使用方式：

1. 准备 `.env`，包含原本运行机器人所需的 Slack、LiteLLM、mem0 变量（`MEM0_API_KEY`、`MEM0_DEFAULT_USER_ID` 等）。`docker compose` 会自动加载该文件，并将 `MEM0_BASE_URL` 指向容器内的 mem0 服务。
2. （可选）如需为 Qdrant 设置 API Key，可在 `.env` 中加入 `QDRANT_API_KEY=<your-key>`，Compose 会自动透传给 mem0。
3. 启动全部服务：
   ```bash
   docker compose up --build
   ```
   首次启动会在 `bot` 容器内执行 `uv run python manage.py migrate` 并拉起开发服务器。
4. 访问接口：
   - Slack bot API: http://localhost:8000/
   - mem0 API: http://localhost:8100/

若需要停止服务，执行 `docker compose down`；若希望清理向量存储数据，可同时加上 `-v` 删除 `qdrant_data` 卷。

## 必填环境变量
| 变量 | 描述 |
| --- | --- |
| `SLACK_BOT_TOKEN` | Slack Bot Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Slack App Token (`xapp-...`) |
| `SLACK_SIGNING_SECRET` | 验证 Slack 请求使用 |
| `LITELLM_MODEL` | LiteLLM 使用的模型名称，例如 `gpt-4o-mini` |
| `SLACK_SUMMARY_MAX_MESSAGES` | 每次拉取的最大消息条数 |
| `MEM0_API_KEY` | （可选）mem0.ai 的 API Key，用于开启总结记忆功能 |
| `MEM0_DEFAULT_USER_ID` | （可选）mem0.ai 用户 ID，默认 `lumo-slackbot`。也可以在 API 调用或 Slack 事件中覆盖，用于为不同 Slack 账号隔离记忆 |
| `MEM0_BASE_URL` | （可选）自建 mem0 服务地址，例如 `https://mem0.yourdomain.com` |

> LiteLLM 需要配置对应模型供应商的 API Key，例如 `OPENAI_API_KEY`，配置方式详见 [LiteLLM 文档](https://docs.litellm.ai/).

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
  "max_messages": 100,
  "mem0_user_id": "T123"  // 覆盖默认记忆空间
}
```

### 示例：Thread Summaries
```http
POST /api/summaries/thread/
Content-Type: application/json

{
  "channel_id": "C123",
  "thread_ts": "1714567890.123456",
  "mem0_user_id": "T123"
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

## 开启记忆功能（mem0.ai）

项目集成了 [mem0.ai](https://mem0.ai/) 作为总结记忆存储。配置步骤：

1. 安装依赖（可选）：
   ```bash
   pip install mem0ai
   ```
2. 配置环境变量：
   ```bash
   export MEM0_API_KEY="your_mem0_api_key"
   export MEM0_DEFAULT_USER_ID="lumo-slackbot"
   # 如果你使用 self-host 的 mem0 服务，设置 base url
   export MEM0_BASE_URL="https://mem0.yourdomain.com"
   ```

配置完成后，所有通过机器人生成的总结会自动写入 mem0（无论是官方云还是自建服务），方便检索与长期记忆。如果你将机器人接入多个 Slack Workspace，可以：

1. 通过 Slack Events Payload 中的 `team`/`team_id` 自动区分（系统已默认支持，mem0 `user_id` 会使用触发事件的 workspace）。
2. 在手动调用 channel / thread 总结接口时传入 `mem0_user_id` 字段，覆盖默认用户 ID。

这样就可以为不同的 Slack 账号维护各自独立的记忆空间。
