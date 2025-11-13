# Lumo Slack Bot Gemini Context

This document provides instructional context for Gemini to effectively assist with development tasks on the Lumo Slack Bot project.

## Project Overview

Lumo is a Slack bot built with Python and the Django REST Framework. Its primary function is to summarize conversations within Slack channels and threads. It uses LiteLLM to interface with various language models (like GPT-4) for summarization and can be triggered via app mentions or direct API calls. The bot also integrates with mem0.ai to provide a persistent memory of past summaries, allowing it to answer questions based on historical context.

### Key Technologies

*   **Backend:** Django, Django REST Framework
*   **Slack Integration:** `slack_sdk`
*   **Language Models:** `litellm`
*   **Memory:** `mem0.ai`
*   **Dependencies:** Managed with `pip` and `requirements.txt`
*   **Configuration:** `python-dotenv` (loads from a `.env` file)
*   **Containerization:** Docker, Docker Compose

### Architecture

*   **`application/`**: The main Django project directory containing `settings.py` and `urls.py`.
*   **`slackbot/`**: The core application logic.
    *   **`views.py`**: Handles all incoming API requests, including Slack events (`app_mention`) and manual summary requests.
    *   **`services/`**: Contains the business logic, decoupled from the views.
        *   `slack_client.py`: A client to interact with the Slack Web API (fetch messages, post replies).
        *   `summarizer.py`: A client to interact with `litellm` for generating summaries and answering questions.
        *   `memory.py`: A client to store and retrieve summaries from `mem0.ai`.
    *   **`serializers.py`**: Defines serializers for validating incoming request data for the API views.
    *   **`models.py`**: Defines the `ConversationSummary` model for logging generated summaries in the database.
    *   **`urls.py`**: Maps API endpoints to the corresponding views.

## Building and Running

### 1. Initial Setup

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
2.  **Configure Environment:**
    Create a `.env` file in the project root. You can copy `.env.example` if it exists. Key variables to set include:
    *   `SLACK_BOT_TOKEN`
    *   `SLACK_APP_TOKEN`
    *   `LITELLM_MODEL`
    *   `MEM0_API_KEY` (optional)

3.  **Database Migration:**
    ```bash
    python manage.py migrate
    ```

### 2. Running the Development Server

```bash
python manage.py runserver
```
The application will be available at `http://127.0.0.1:8000/`.

### 3. Running with Docker

The project includes a `docker-compose.yml` for a containerized setup.

```bash
docker compose up --build
```

This will build the `bot` service and run the application, along with a `mem0` service and a `qdrant` vector database if configured.

## Development Conventions

### Testing

The project uses Django's built-in testing framework. Tests are located in the `slackbot/tests/` directory.

To run the test suite:

```bash
python manage.py test
```

### Code Style

*   The code follows standard Python (PEP 8) and Django conventions.
*   Service modules (`slack_client`, `summarizer`, `memory`) are used to encapsulate third-party API interactions and business logic, keeping views clean.
*   Type hints are used throughout the codebase.
*   Environment variables are the primary method of configuration, following the 12-factor app methodology.

### API Endpoints

*   `/api/slack/events/`: Handles incoming events from Slack (e.g., `app_mention`).
*   `/api/summaries/channel/`: Manually trigger a summary for a channel.
*   `/api/summaries/thread/`: Manually trigger a summary for a thread.
*   `/api/health/`: A simple health check endpoint.
