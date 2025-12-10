from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import logging
from qdrant_client import QdrantClient
from llama_index.core import (
    Document,
    VectorStoreIndex,
    StorageContext,
    Settings,
    SimpleDirectoryReader,
)
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.qdrant import QdrantVectorStore

from slackbot.services.chunker import chunk_document_with_llm


@dataclass
class StoredIndex:
    index: VectorStoreIndex
    metadata: Dict[str, Any]


_GLOBAL_INDEX: Optional[StoredIndex] = None
logger = logging.getLogger(__name__)
SUMMARY_PROMPT = (
    "你是一个文档助手，请用中文简要总结这些 Slack 上传的文档的主要内容，控制在 200 字以内。"
)
DIGEST_FALLBACK_CHARS = int(os.getenv("DOCUMENT_PREVIEW_CHAR_LIMIT", "1600"))


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


def get_index() -> VectorStoreIndex:
    """
    Retrieves the global LlamaIndex VectorStoreIndex, loading or creating it if necessary.
    This function centralizes index access and initialization.
    """
    global _GLOBAL_INDEX

    if _GLOBAL_INDEX is not None:
        return _GLOBAL_INDEX.index

    # If the index is not in memory, load it from the vector store.
    # We pass empty lists for documents and files because we are not inserting new data here.
    return _load_or_create_global_index(documents=[], files=[])

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
            index.insert_nodes([doc for doc in documents])
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
                index.insert_nodes([doc for doc in documents])
        except Exception as exc:
            logger.info("[document_indexer] failed to load index from Qdrant, creating new one: %s", exc)
            print("[document_indexer] creating new Qdrant index, exc=", exc)
            logger.info("[document_indexer] creating new index in Qdrant with %d documents", len(documents))
            print("[document_indexer] before VectorStoreIndex.from_documents (Qdrant)")
            index = VectorStoreIndex.from_documents(documents or [], storage_context=storage_context)
            print("[document_indexer] after VectorStoreIndex.from_documents (Qdrant)")

    _GLOBAL_INDEX = StoredIndex(index=index, metadata={"files": files})
    return index


def _build_summary_from_documents(documents: List[Document]) -> Optional[str]:
    """Build a short summary that only reflects the provided documents."""
    if not documents:
        return None

    try:
        # 使用内存向量存储生成一个临时索引，仅用于当前文档的摘要
        local_storage = StorageContext.from_defaults()
        summary_index = VectorStoreIndex.from_documents(documents, storage_context=local_storage)
        query_engine = summary_index.as_query_engine()
        response = query_engine.query(SUMMARY_PROMPT)
        text = str(response).strip()
        if text:
            logger.info("[document_indexer] generated document-specific summary (len=%d)", len(text))
            return text
    except Exception as exc:
        logger.exception("[document_indexer] failed to summarize document locally: %s", exc)

    merged_text = "\n\n".join(getattr(doc, "text", "").strip() for doc in documents if getattr(doc, "text", "").strip())
    if merged_text:
        logger.info("[document_indexer] falling back to truncated raw text for preview")
        return merged_text[:DIGEST_FALLBACK_CHARS]
    return None


def _build_chunk_payloads(documents: List[Document]) -> List[Dict[str, Any]]:
    """Convert LlamaIndex Document nodes into serializable chunk payloads."""
    payloads: List[Dict[str, Any]] = []
    for idx, doc in enumerate(documents, start=1):
        text = ""
        get_content = getattr(doc, "get_content", None)
        if callable(get_content):
            text = get_content() or ""
        elif hasattr(doc, "text"):
            text = getattr(doc, "text", "") or ""
        else:
            text = str(doc)

        metadata = dict(getattr(doc, "metadata", {}) or {})
        payloads.append(
            {
                "index": int(metadata.get("chunk_number") or idx),
                "text": text,
                "metadata": metadata,
            }
        )
    return payloads


def index_slack_files_and_summarize(
    files: List[Dict[str, Any]],
    *,
    channel: Optional[str],
    thread_ts: Optional[str],
) -> Optional[Dict[str, Any]]:
    documents: List[Document] = []
    _configure_openai_models()

    for file_info in files:
        path = file_info.get("path")
        name = file_info.get("name") or os.path.basename(path or "")
        if not path or not os.path.exists(path):
            continue
        ext = os.path.splitext(name)[1].lower()

        # 针对常见二进制文档（PDF / Office）使用 LlamaIndex 的 SimpleDirectoryReader 进行文本抽取，
        # 行为与 scripts/debug_llamaindex.py 中的调试脚本保持一致。
        if ext in {".pdf", ".docx", ".xlsx"}:
            try:
                reader = SimpleDirectoryReader(input_files=[path])
                loaded_docs = reader.load_data()
            except Exception:
                # 文件解析失败，直接跳过该文件
                continue

            merged_text_parts: List[str] = []
            for doc in loaded_docs:
                doc_text = getattr(doc, "text", None)
                if not doc_text:
                    get_content = getattr(doc, "get_content", None)
                    if callable(get_content):
                        doc_text = get_content()
                if doc_text:
                    merged_text_parts.append(str(doc_text))
            merged_text = "\n\n".join(part.strip() for part in merged_text_parts if part.strip()).replace("\x00", "")

            if not merged_text.strip():
                continue

            base_metadata = dict((loaded_docs[0].metadata or {}) if loaded_docs else {})
            base_metadata.update(
                {
                    "source": "slack_file",
                    "file_name": name,
                    "file_path": path,
                    "channel": channel,
                    "thread_ts": thread_ts,
                }
            )

            try:
                chunk_result = chunk_document_with_llm(merged_text, base_metadata)
                chunk_docs = chunk_result.get("documents") or []
                if chunk_docs:
                    documents.extend(chunk_docs)
                    continue
            except Exception as exc:
                logger.warning(
                    "[document_indexer] LLM chunking failed for file %s, falling back to single document: %s",
                    name,
                    exc,
                )

            documents.append(Document(text=merged_text, metadata=base_metadata))

        # Markdown 文件：按纯文本读取，但同样使用 LLM 语义分块
        elif ext == ".md":
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

            try:
                chunk_result = chunk_document_with_llm(text, metadata)
                chunk_docs = chunk_result.get("documents") or []
                if chunk_docs:
                    documents.extend(chunk_docs)
                else:
                    documents.append(Document(text=text, metadata=metadata))
            except Exception as exc:
                logger.warning(
                    "[document_indexer] LLM chunking failed for markdown file %s, falling back to single document: %s",
                    name,
                    exc,
                )
                documents.append(Document(text=text, metadata=metadata))

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

    summary_text = _build_summary_from_documents(documents)
    chunk_payloads = _build_chunk_payloads(documents)

    _load_or_create_global_index(documents, files)

    if summary_text:
        print("[document_indexer] summary length=", len(summary_text))
    return {"summary": summary_text, "chunks": chunk_payloads}


def query_slack_file_context(
    *,
    channel: Optional[str],
    thread_ts: Optional[str],
    question: str,
    max_indices: int = 3,
) -> str:
    # Use the new get_index function to retrieve the LlamaIndex
    index = get_index()

    snippets: List[str] = []

    try:
        query_engine = index.as_query_engine()
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
