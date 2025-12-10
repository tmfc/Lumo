
import argparse
import os
import time
from pathlib import Path
from dotenv import load_dotenv
import sys
# Load environment variables from .env file
load_dotenv()

# Add project root to the Python path
sys.path.append(str(Path(__file__).parent.parent))

# Configure LlamaIndex settings before importing other modules
# This is crucial to avoid initialization errors
from llama_index.core import Settings, Document, SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter

# Helper to configure OpenAI models for both LlamaIndex and LiteLLM
from slackbot.services.document_indexer import _configure_openai_models
from slackbot.services.chunker import chunk_document_with_llm


def benchmark_sentence_splitter(text: str, metadata: dict):
    """
    Benchmarks the default SentenceSplitter from LlamaIndex.
    """
    print("\n--- Running Baseline: SentenceSplitter ---")
    start_time = time.monotonic()

    splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=200)
    # The splitter expects a list of Documents
    nodes = splitter.get_nodes_from_documents([Document(text=text, metadata=metadata)])
    
    end_time = time.monotonic()
    elapsed_time = end_time - start_time
    
    num_chunks = len(nodes)
    print(f"Generated {num_chunks} chunks in {elapsed_time:.2f} seconds.")
    
    return {
        "chunks": [node.get_content() for node in nodes],
        "num_chunks": num_chunks,
        "time": elapsed_time
    }


def benchmark_llm_chunker(text: str, metadata: dict):
    """
    Benchmarks the new LLM-based chunking method.
    """
    print("\n--- Running New Method: LLM Semantic Chunker ---")
    start_time = time.monotonic()

    result = chunk_document_with_llm(text, metadata)
    
    end_time = time.monotonic()
    elapsed_time = end_time - start_time
    
    documents = result["documents"]
    tokens_used = result["tokens_used"]
    num_chunks = len(documents)

    print(f"Generated {num_chunks} chunks in {elapsed_time:.2f} seconds.")
    print(f"API Usage: {tokens_used['total_tokens']} total tokens "
          f"({tokens_used['prompt_tokens']} prompt + {tokens_used['completion_tokens']} completion).")

    return {
        "chunks": [doc.get_content() for doc in documents],
        "num_chunks": num_chunks,
        "time": elapsed_time,
        "tokens": tokens_used
    }


def write_chunks_to_file(filename: str, chunks: list[str]):
    """
    Writes the list of chunk strings to a file for qualitative analysis.
    """
    output_path = Path("scripts") / filename
    with open(output_path, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks):
            f.write(f"--- CHUNK {i+1} ---\n")
            f.write(chunk)
            f.write("\n\n")
    print(f"Wrote {len(chunks)} chunks to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark and compare document chunking strategies.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "file_path",
        type=str,
        help="Path to the document file to be benchmarked (e.g., 'my_doc.pdf')."
    )
    args = parser.parse_args()

    file_to_test = Path(args.file_path)
    if not file_to_test.exists():
        print(f"Error: File not found at '{file_to_test}'")
        return




    # Configure API keys and models for all services
    try:
        _configure_openai_models()
    except RuntimeError as e:
        print(f"Error: Configuration failed. {e}")
        print("Please ensure your OPENAI_API_KEY (and other necessary env vars) are set in your .env file.")
        return

    print(f"Loading document: {file_to_test.name}...")
    # SimpleDirectoryReader is robust and can handle various file types
    reader = SimpleDirectoryReader(input_files=[file_to_test])
    docs = reader.load_data()
    if not docs:
        print("Error: Could not load any content from the specified file.")
        return
    
    # We assume the file contains a single logical document, but SimpleDirectoryReader
    # may return multiple Document objects (e.g., one per page for PDFs).
    # Concatenate all contents to get the full text.
    full_text = "\n\n".join(doc.get_content() for doc in docs)
    # Clean up any null bytes or other artifacts that may come from parsing
    full_text = full_text.replace("\x00", "")

    # Merge basic metadata from the first document as a representative
    metadata = docs[0].metadata or {}
    print(f"Document loaded successfully ({len(full_text)} characters).")

    if len(full_text) < 50:
        print("\nError: Document content is too short. PDF parsing likely failed.")
        print("Please ensure 'pypdf' is installed ('pip install -r requirements.txt') and the PDF file is not corrupted.")
        return

    # Print document text before calling the LLM so we can inspect parsing output
    preview_limit = 5000
    print("\n===== DOCUMENT TEXT PREVIEW (first {0} characters) =====".format(preview_limit))
    print(full_text[:preview_limit])
    if len(full_text) > preview_limit:
        print("\n[... truncated, total length: {0} characters ...]".format(len(full_text)))

    # Run benchmarks
    baseline_results = benchmark_sentence_splitter(full_text, metadata)
    llm_results = benchmark_llm_chunker(full_text, metadata)

    # Write outputs for manual review
    write_chunks_to_file("baseline_chunks.txt", baseline_results["chunks"])
    write_chunks_to_file("llm_chunks.txt", llm_results["chunks"])

    # Print summary report
    print("\n\n--- Benchmark Summary ---")
    print(f"Document: {file_to_test.name} ({len(full_text)} chars)")
    print("-" * 80)
    print(f"| {'Metric':<20} | {'Baseline (SentenceSplitter)':<30} | {'New (LLM Chunker)':<25} |")
    print(f"|{'-'*22}|{'-'*32}|{'-'*27}|")
    print(f"| {'Processing Time (s)':<20} | {baseline_results['time']:<30.2f} | {llm_results['time']:<25.2f} |")
    print(f"| {'Number of Chunks':<20} | {baseline_results['num_chunks']:<30} | {llm_results['num_chunks']:<25} |")
    print(f"| {'Total API Tokens':<20} | {'N/A':<30} | {llm_results['tokens']['total_tokens']:<25} |")
    print("-" * 80)
    print("\nReview the output files for a qualitative comparison:")
    print("- scripts/baseline_chunks.txt")
    print("- scripts/llm_chunks.txt")


if __name__ == "__main__":
    main()
