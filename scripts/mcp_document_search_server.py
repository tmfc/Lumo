from __future__ import annotations

import anyio
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

from slackbot.services.document_search import search_documents

mcp = FastMCP("lumo-document-search")


@mcp.tool()
def search(keyword: str) -> List[Dict[str, Any]]:
    """Search uploaded Slack documents stored in Qdrant.

    Args:
        keyword: Query text for semantic search.

    Returns:
        Up to five relevant documents with text content, score, and metadata.
    """

    return search_documents(keyword, limit=5)


if __name__ == "__main__":
    anyio.run(mcp.run)
