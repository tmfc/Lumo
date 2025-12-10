# Lumo Slack Bot - 项目上下文文档

## 项目概述

Lumo 是一个基于 Django REST Framework 的智能 Slack 机器人，集成了 Slack SDK、LiteLLM 和 LlamaIndex 技术。主要功能包括：

- **对话总结**：对 Slack thread 和 channel 的历史消息进行智能总结
- **文档索引与问答**：支持用户上传文件，自动建立向量索引并基于文档内容进行问答
- **智能交互**：通过 @ 机器人触发总结或问答功能

## 核心技术栈

- **后端框架**：Django 4.2 + Django REST Framework
- **AI/LLM 集成**：LiteLLM（支持多种 LLM 提供商）
- **文档处理**：LlamaIndex + Qdrant 向量存储
- **Slack 集成**：Slack SDK（Python）
- **依赖管理**：uv（现代 Python 包管理器）
- **容器化**：Docker + Docker Compose

## 项目结构

```
Lumo/
├── application/          # Django 项目配置
│   ├── settings.py       # 项目设置（包含 Slack、Qdrant 等配置）
│   └── urls.py           # URL 路由配置
├── slackbot/            # 核心业务逻辑
│   ├── views.py         # DRF API 视图（Slack 事件处理）
│   ├── models.py        # 数据模型（对话摘要、事件记录）
│   ├── services/        # 业务服务层
│   │   ├── slack_client.py      # Slack API 客户端
│   │   ├── summarizer.py        # LLM 总结服务
│   │   ├── document_indexer.py  # 文档索引服务
│   │   ├── chunker.py           # 文档分块处理
│   │   └── memory.py            # 内存管理（已弃用）
│   └── tests/           # 测试文件
├── scripts/             # 调试和基准测试脚本
├── downloads/           # 统一的文件存储目录（Slack 附件与后台上传）
├── llamaindex_store/    # LlamaIndex 存储目录
├── docker-compose.yml   # Docker 编排配置
├── Dockerfile          # Docker 镜像构建配置
├── requirements.txt    # Python 依赖
└── .env.example       # 环境变量模板
```

## 环境配置

### 必需的环境变量

```bash
# Slack 配置（必填）
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-level-token
SLACK_SIGNING_SECRET=your-slack-signing-secret

# LLM 配置（必填）
LITELLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=your-openai-api-key

# 向量存储配置
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=lumo_slack_documents  # 可选
```

### 可选的环境变量

```bash
# 性能调优
SLACK_SUMMARY_MAX_MESSAGES=100

# OpenAI 高级配置
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com  # 可选，用于代理

# Qdrant 认证（可选）
QDRANT_API_KEY=your-qdrant-api-key

# 文件存储
FILE_STORAGE_DIR=/abs/path/to/downloads  # 统一的上传/下载目录（默认 <BASE_DIR>/downloads）
```

## 构建与运行

### 本地开发环境

1. **设置虚拟环境并安装依赖**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   pip install -r requirements.txt
   ```

2. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填入真实的配置
   ```

3. **初始化数据库**
   ```bash
   python manage.py migrate
   ```

4. **运行开发服务器**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

### Docker 环境

1. **准备环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件
   ```

2. **启动服务**
   ```bash
   docker compose up --build
   ```

3. **停止服务**
   ```bash
   docker compose down
   ```

## API 接口

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/api/slack/events/` | Slack Events API 入口 |
| POST | `/api/summaries/channel/` | 请求 channel 总结 |
| POST | `/api/summaries/thread/` | 请求 thread 总结 |
| GET | `/api/health/` | 健康检查 |

## 核心功能流程

### 1. Slack 事件处理流程

1. Slack 发送事件到 `/api/slack/events/`
2. `SlackEventView` 验证并处理事件
3. 如果包含文件附件：
   - 下载文件到统一的 `downloads/` 目录
   - 后台线程调用 LlamaIndex 进行索引
   - 生成文档摘要并发回 Slack
4. 如果是 @ 机器人事件：
   - 根据关键词判断是总结还是问答
   - 调用相应的服务处理

### 2. 文档索引流程

1. 用户在 Slack 中上传文件并 @ 机器人
2. 机器人下载文件到本地
3. 使用 LlamaIndex 读取文件内容
4. 通过 OpenAI Embedding 生成向量
5. 存储到 Qdrant 向量数据库
6. 生成简短摘要并发回 Slack

### 3. 问答流程

1. 用户在 Slack 中提问
2. 机器人获取最近 24 小时的频道消息作为上下文
3. 从 Qdrant 检索相关文档片段
4. 合并上下文和文档内容
5. 通过 LiteLLM 调用 LLM 生成回答
6. 将回答发送回 Slack

## 开发约定

### 代码风格

- 使用 Python 3.11+ 类型注解
- 遵循 Django 和 DRF 最佳实践
- 使用 `from __future__ import annotations` 支持前向引用
- 日志使用标准 logging 模块

### 测试

- 使用 Django 内置测试框架
- 测试文件位于 `slackbot/tests/` 目录
- 运行测试：`python manage.py test`

### 数据库

- 默认使用 SQLite3（开发环境）
- 模型定义在 `slackbot/models.py`
- 迁移文件在 `slackbot/migrations/`

## 调试与故障排除

### 调试脚本

项目包含多个调试脚本，位于 `scripts/` 目录：

- `debug_llamaindex.py` - 测试 LlamaIndex 配置
- `debug_chunk_indices.py` - 调试文档分块
- `test_api_call.py` - 测试 API 调用
- `test_litellm_proxy.py` - 测试 LiteLLM 代理

### 常见问题

1. **Qdrant 连接失败**
   - 检查 `QDRANT_URL` 配置
   - 确认 Qdrant 服务已启动

2. **OpenAI API 调用失败**
   - 验证 `OPENAI_API_KEY` 是否正确
   - 检查网络连接和代理设置

3. **Slack 事件处理失败**
   - 确认 Slack 令牌配置正确
   - 检查事件订阅设置

## 扩展指南

### 添加新的文档类型支持

1. 在 `slackbot/services/document_indexer.py` 中添加新的文件扩展名处理
2. 实现相应的文本提取逻辑
3. 更新文档元数据

### 自定义 LLM 提示

1. 修改 `slackbot/services/summarizer.py` 中的提示模板
2. 调整 `build_summary_prompt` 和 `build_question_prompt` 函数

### 添加新的 API 端点

1. 在 `slackbot/views.py` 中创建新的视图类
2. 在 `application/urls.py` 中添加路由
3. 根据需要创建新的序列化器

## 部署注意事项

1. **安全性**：确保所有 API 密钥和令牌通过环境变量配置
2. **性能**：调整 `SLACK_SUMMARY_MAX_MESSAGES` 平衡响应速度和完整性
3. **可扩展性**：考虑使用 Redis 缓存常见查询结果
4. **监控**：设置日志监控和健康检查告警
