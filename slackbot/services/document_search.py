from __future__ import annotations

import logging
from typing import Any, Dict, List

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.schema import MetadataMode

from slackbot.services.document_indexer import _configure_openai_models, _create_qdrant_vector_store

logger = logging.getLogger(__name__)


def _load_qdrant_index() -> VectorStoreIndex:
    """Load the existing Qdrant-backed index using LlamaIndex settings."""

    _configure_openai_models()
    vector_store = _create_qdrant_vector_store()
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    return VectorStoreIndex.from_vector_store(
        vector_store=vector_store, storage_context=storage_context
    )


def search_documents(keyword: str, *, limit: int = 5) -> List[Dict[str, Any]]:
    """Search indexed Slack documents by keyword.

    Args:
        keyword: Query text used for semantic search.
        limit: Maximum number of documents to return.

    Returns:
        A list of search results, each containing text, score, and metadata.
    """

    try:
        index = _load_qdrant_index()
    except Exception as exc:  # pragma: no cover - network/remote dependency
        logger.exception("[document_search] failed to load index: %s", exc)
        return []

    retriever = index.as_retriever(similarity_top_k=limit)

    try:
        nodes = retriever.retrieve(keyword)
    except Exception as exc:  # pragma: no cover - network/remote dependency
        logger.exception("[document_search] retrieval failed: %s", exc)
        return []

    results: List[Dict[str, Any]] = []
    for node in nodes:
        try:
            content = node.get_content(metadata_mode=MetadataMode.NONE).strip()
        except Exception:
            content = ""

        results.append(
            {
                "text": content,
                "score": getattr(node, "score", None),
                "metadata": dict(getattr(node, "metadata", {}) or {}),
            }
        )

    return results
