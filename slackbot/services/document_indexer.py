from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import logging
from qdrant_client import QdrantClient
from llama_index.core import Document, VectorStoreIndex, StorageContext, Settings, SimpleDirectoryReader
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.qdrant import QdrantVectorStore


@dataclass
class StoredIndex:
    index: VectorStoreIndex
    metadata: Dict[str, Any]


_GLOBAL_INDEX: Optional[StoredIndex] = None
logger = logging.getLogger(__name__)


def _configure_openai_models() -> None:
    """Configure OpenAI models for LlamaIndex via Settings.

    对齐 scripts/debug_llamaindex.py 中的用法，通过 Settings 全局配置：
    - OPENAI_API_KEY（必填）
    - OPENAI_BASE_URL（可选，对应 api_base）
    - OPENAI_EMBEDDING_MODEL / OPENAI_MODEL（可选）
    """

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set.")

    api_base = os.getenv("OPENAI_BASE_URL")

    embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"
    llm_model = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

    embed_kwargs = {"model": embedding_model, "api_key": api_key}
    llm_kwargs = {"model": llm_model, "api_key": api_key}
    if api_base:
        # 与 debug_llamaindex.py 保持一致，使用 api_base 而不是 base_url
        embed_kwargs["api_base"] = api_base
        llm_kwargs["api_base"] = api_base

    Settings.embed_model = OpenAIEmbedding(**embed_kwargs)
    Settings.llm = OpenAI(**llm_kwargs)


def _create_qdrant_vector_store() -> QdrantVectorStore:
    """Create a Qdrant vector store for LlamaIndex.

    使用环境变量配置 Qdrant 连接：
    - QDRANT_URL（默认 http://localhost:6333）
    - QDRANT_API_KEY（可选）
    - QDRANT_COLLECTION（可选，默认 "lumo_slack_documents"）
    """

    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY") or None
    collection_name = os.getenv("QDRANT_COLLECTION", "lumo_slack_documents")

    client = QdrantClient(url=url, api_key=api_key)
    return QdrantVectorStore(client=client, collection_name=collection_name)


def _load_or_create_global_index(documents: List[Document], files: List[Dict[str, Any]]) -> VectorStoreIndex:
    global _GLOBAL_INDEX

    # 使用与 debug_llamaindex.py 一致的 Settings 配置 LLM 与 Embedding
    _configure_openai_models()
    vector_store = _create_qdrant_vector_store()
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    print("[document_indexer] _load_or_create_global_index using Qdrant, num_docs=", len(documents))

    index: VectorStoreIndex

    # 如果内存中已有索引，直接复用并插入新文档
    if _GLOBAL_INDEX is not None:
        index = _GLOBAL_INDEX.index
        if documents:
            logger.info("[document_indexer] inserting %d new documents into existing Qdrant index", len(documents))
            print("[document_indexer] inserting", len(documents), "documents into existing index")
            index.insert_documents(documents)
    else:
        # 尝试从已有的 Qdrant 集合恢复索引；如果集合为空或失败，则从当前文档创建新索引
        try:
            logger.info("[document_indexer] trying to load index from existing Qdrant collection")
            print("[document_indexer] before VectorStoreIndex.from_vector_store")
            index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                storage_context=storage_context,
            )
            print("[document_indexer] after VectorStoreIndex.from_vector_store")
            if documents:
                logger.info("[document_indexer] inserting %d new documents into loaded Qdrant index", len(documents))
                print("[document_indexer] inserting", len(documents), "documents into loaded index")
                index.insert_documents(documents)
        except Exception as exc:
            logger.info("[document_indexer] failed to load index from Qdrant, creating new one: %s", exc)
            print("[document_indexer] creating new Qdrant index, exc=", exc)
            logger.info("[document_indexer] creating new index in Qdrant with %d documents", len(documents))
            print("[document_indexer] before VectorStoreIndex.from_documents (Qdrant)")
            index = VectorStoreIndex.from_documents(documents or [], storage_context=storage_context)
            print("[document_indexer] after VectorStoreIndex.from_documents (Qdrant)")

    _GLOBAL_INDEX = StoredIndex(index=index, metadata={"files": files})
    return index


def index_slack_files_and_summarize(
    files: List[Dict[str, Any]],
    *,
    channel: Optional[str],
    thread_ts: Optional[str],
) -> Optional[str]:
    documents: List[Document] = []

    for file_info in files:
        path = file_info.get("path")
        name = file_info.get("name") or os.path.basename(path or "")
        if not path or not os.path.exists(path):
            continue
        ext = os.path.splitext(name)[1].lower()

        # 针对 PDF 使用 LlamaIndex 的 SimpleDirectoryReader 进行文本抽取，
        # 行为与 scripts/debug_llamaindex.py 中的调试脚本保持一致。
        if ext == ".pdf":
            try:
                reader = SimpleDirectoryReader(input_files=[path])
                pdf_docs = reader.load_data()
            except Exception:
                continue

            for doc in pdf_docs:
                meta = dict(doc.metadata or {})
                meta.update(
                    {
                        "source": "slack_file",
                        "file_name": name,
                        "file_path": path,
                        "channel": channel,
                        "thread_ts": thread_ts,
                    }
                )
                documents.append(Document(text=doc.text, metadata=meta))
        else:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception:
                continue

            if not text.strip():
                continue

            metadata = {
                "source": "slack_file",
                "file_name": name,
                "file_path": path,
                "channel": channel,
                "thread_ts": thread_ts,
            }
            documents.append(Document(text=text, metadata=metadata))

    if not documents:
        print("[document_indexer] no documents to index, skip")
        return None

    index = _load_or_create_global_index(documents, files)

    query_engine = index.as_query_engine()
    prompt = "你是一个文档助手，请用中文简要总结这些 Slack 上传的文档的主要内容，控制在 200 字以内。"
    try:
        logger.info("[document_indexer] running summary query over indexed documents")
        print("[document_indexer] running summary query over indexed documents")
        response = query_engine.query(prompt)
    except Exception as exc:
        logger.exception("[document_indexer] summary query failed: %s", exc)
        return None

    text = str(response)
    print("[document_indexer] summary length=", len(text))
    return text


def query_slack_file_context(
    *,
    channel: Optional[str],
    thread_ts: Optional[str],
    question: str,
    max_indices: int = 3,
) -> str:
    global _GLOBAL_INDEX

    # 尝试从内存缓存拿索引；如果没有，则从 Qdrant 创建/恢复索引
    stored = _GLOBAL_INDEX

    if stored is None:
        _configure_openai_models()
        vector_store = _create_qdrant_vector_store()
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        try:
            logger.info("[document_indexer] loading index from Qdrant for query")
            print("[document_indexer] loading index from Qdrant for query")
            index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                storage_context=storage_context,
            )
        except Exception as exc:
            logger.exception("[document_indexer] failed to load index from Qdrant: %s", exc)
            return ""

        stored = _GLOBAL_INDEX = StoredIndex(index=index, metadata={})

    snippets: List[str] = []

    try:
        query_engine = stored.index.as_query_engine()
        logger.info("[document_indexer] running context query for question: %s", question)
        resp = query_engine.query(
            f"根据用户的问题：{question}\n从所有已索引的 Slack 文档中检索最相关的内容，给出一个简要引用段落（可以带少量解释）。"
        )
        text = str(resp).strip()
        if text:
            snippets.append(text)
    except Exception as exc:
        logger.exception("[document_indexer] context query failed: %s", exc)
        return ""

    return "\n\n".join(snippets)
