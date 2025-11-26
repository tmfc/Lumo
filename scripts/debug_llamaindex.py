import argparse
import os

from dotenv import load_dotenv
from llama_index.core import Settings, SimpleDirectoryReader, VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI


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


def build_index(downloads_dir: str) -> VectorStoreIndex:
    _configure_openai_models()

    if not os.path.isdir(downloads_dir):
        raise FileNotFoundError(f"Downloads directory not found: {downloads_dir}")

    print(f"[INFO] Loading documents from: {downloads_dir}")
    documents = SimpleDirectoryReader(downloads_dir, recursive=True).load_data()

    if not documents:
        raise RuntimeError("No documents found in downloads directory. Put some files there and retry.")

    print(f"[INFO] Loaded {len(documents)} documents, building index...")
    index = VectorStoreIndex.from_documents(documents)
    print("[INFO] Index built.")
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
