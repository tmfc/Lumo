import argparse
import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from llama_index.core import Settings, SimpleDirectoryReader, VectorStoreIndex, StorageContext
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.qdrant import QdrantVectorStore


load_dotenv()


def _configure_openai_models() -> None:
    """Configure OpenAI embedding + LLM via environment variables.

    Env vars:
    - OPENAI_API_KEY (必填)
    - OPENAI_BASE_URL (可选，用于代理，等价于 api_base)
    - OPENAI_EMBEDDING_MODEL (可选，默认 text-embedding-3-small)
    - OPENAI_MODEL (可选，默认 gpt-4o-mini)
    """

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set.")

    api_base = os.getenv("OPENAI_BASE_URL")

    embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"
    llm_model = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

    print(f"[INFO] Using OpenAI embedding model: {embedding_model}")
    print(f"[INFO] Using OpenAI LLM model: {llm_model}")

    embed_kwargs = {"model": embedding_model, "api_key": api_key}
    llm_kwargs = {"model": llm_model, "api_key": api_key}
    if api_base:
        embed_kwargs["api_base"] = api_base
        llm_kwargs["api_base"] = api_base

    Settings.embed_model = OpenAIEmbedding(**embed_kwargs)
    Settings.llm = OpenAI(**llm_kwargs)


def _create_qdrant_vector_store() -> QdrantVectorStore:
    """Create a Qdrant vector store for this debug script.

    环境变量：
    - QDRANT_URL（默认 http://localhost:6333）
    - QDRANT_API_KEY（可选）
    - QDRANT_COLLECTION（可选，默认 "lumo_slack_documents"，与主应用保持一致）
    """

    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY") or None
    collection_name = os.getenv("QDRANT_COLLECTION", "lumo_slack_documents")

    print(f"[INFO] Using Qdrant URL: {url}")
    print(f"[INFO] Using Qdrant collection: {collection_name}")

    client = QdrantClient(url=url, api_key=api_key)
    return QdrantVectorStore(client=client, collection_name=collection_name)


def build_index(downloads_dir: str) -> VectorStoreIndex:
    _configure_openai_models()

    if not os.path.isdir(downloads_dir):
        raise FileNotFoundError(f"Downloads directory not found: {downloads_dir}")

    print(f"[INFO] Loading documents from: {downloads_dir}")
    documents = SimpleDirectoryReader(downloads_dir, recursive=True).load_data()

    if not documents:
        raise RuntimeError("No documents found in downloads directory. Put some files there and retry.")

    print(f"[INFO] Loaded {len(documents)} documents.")

    # 使用与主应用相同的 Qdrant 配置，便于在命令行下快速验证 Qdrant 后端。
    vector_store = _create_qdrant_vector_store()
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # 尝试从已有 Qdrant 集合加载索引；如失败则基于当前文档创建新索引。
    try:
        print("[INFO] Trying to load existing index from Qdrant...")
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            storage_context=storage_context,
        )
        print("[INFO] Existing index loaded from Qdrant.")
        print("[INFO] Inserting documents into existing index...")
        # 逐个插入文档，避免传入嵌套列表导致 'list' object has no attribute 'id_'
        for doc in documents:
            index.insert(doc)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Failed to load existing index from Qdrant, creating new one: {exc}")
        print("[INFO] Building new index in Qdrant from documents...")
        index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)
        print("[INFO] New index built and stored in Qdrant.")

    return index


def interactive_query(index: VectorStoreIndex) -> None:
    query_engine = index.as_query_engine()

    print("\n[READY] 输入你的问题，或输入 'exit' / 'quit' 退出。\n")
    while True:
        try:
            query = input("Q> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[INFO] Bye.")
            break

        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            print("[INFO] Bye.")
            break

        print("[INFO] Running query...")
        try:
            response = query_engine.query(query)
            print("A>", str(response))
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] Query failed: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Debug script: use LlamaIndex to analyze files in downloads/ directory.",
    )
    parser.add_argument(
        "--downloads-dir",
        type=str,
        default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "downloads"),
        help="Directory containing downloaded files (default: <project_root>/downloads)",
    )

    args = parser.parse_args()

    try:
        index = build_index(args.downloads_dir)
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] Failed to build index: {e}")
        return

    interactive_query(index)


if __name__ == "__main__":
    main()
