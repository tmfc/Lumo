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

## 必填环境变量
| 变量 | 描述 |
| --- | --- |
| `SLACK_BOT_TOKEN` | Slack Bot Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Slack App Token (`xapp-...`) |
| `SLACK_SIGNING_SECRET` | 验证 Slack 请求使用 |
| `LITELLM_MODEL` | LiteLLM 使用的模型名称，例如 `gpt-4o-mini` |
| `SLACK_SUMMARY_MAX_MESSAGES` | 每次拉取的最大消息条数 |

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
├── lumobot/        # Django 项目配置
├── slackbot/       # 业务逻辑 (API、服务、模型)
└── requirements.txt
```

- `slackbot/services/slack_client.py`：封装 Slack API 访问。
- `slackbot/services/summarizer.py`：调用 LiteLLM 生成总结。
- `slackbot/views.py`：DRF API 视图，处理事件及总结请求。

欢迎根据业务需求扩展消息持久化、身份认证以及定时调度任务。
