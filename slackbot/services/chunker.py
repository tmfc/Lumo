
import json
import logging
import os
from typing import List, Dict, Any
import re

from openai import OpenAI
from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter

logger = logging.getLogger(__name__)

# A simple proxy for token counting
# Average token length is ~4 chars
TOKEN_ESTIMATE_DIVISOR = int(os.getenv("TOKEN_ESTIMATE_DIVISOR", "4"))
LLM_CHUNK_TOKEN_LIMIT = int(os.getenv("LLM_CHUNK_TOKEN_LIMIT", "20000"))

# Use the model configured for the summarizer
LLM_MODEL = os.getenv("LITELLM_MODEL")

SYSTEM_PROMPT = """
You are an expert in semantic document chunking. Your task is to split a given document into meaningful, self-contained chunks.
The goal is to create chunks that are optimized for Retrieval-Augmented Generation (RAG). This means each chunk should ideally cover a single, specific topic or concept.

You must follow these rules:
1.  Read the entire document provided.
2.  Identify the logical and semantic boundaries in the text. These could be sections, subsections, or well-defined topic blocks.
    - Prefer to keep section headings (such as "3. 接口规范", "6.2. 推送服务") **together with** their immediate explanatory content, instead of isolating headings as separate chunks.
    - Avoid creating chunks that contain only page headers/footers or page numbers (for example lines like "硅基数据开放平台（第三方业务对接） 深圳硅基传感科技有限公司 10 /27"). Such boilerplate lines should be grouped with the nearest relevant content, or omitted from boundaries.
    - Aim for moderately large chunks where possible (roughly 500–1500 Chinese characters), as long as they still represent a coherent topic.
3.  Return a JSON object containing a single key "chunks", which is a list of objects.
4.  Each object in the list MUST have at least two keys: "start" and "end", representing the starting and ending character indices of the chunk in the original text.
5.  For debugging, each object SHOULD ALSO include:
    - "start_text": the first 10 characters of the chunk (computed using the same indices you use for "start").
    - "end_text": the last 10 characters of the chunk (also based on the exact same indices).
    These diagnostic fields will be used to verify that your indices are consistent with the actual text boundaries.
6.  The chunks must be contiguous and cover the entire document. The "end" of one chunk should be immediately followed by the "start" of the next chunk.
7.  Do not add any conversational text, explanations, or markdown formatting around the JSON output. The entire response must be only the JSON object.

Example:
If the document is "First sentence. Second sentence. Third sentence."
A possible valid output would be:
{{
    "chunks": [
        {{
            "start": 0,
            "end": 15,
            "start_text": "First sent",
            "end_text": "entence."
        }},
        {{
            "start": 16,
            "end": 33,
            "start_text": "Second sen",
            "end_text": "entence."
        }},
        {{
            "start": 34,
            "end": 50,
            "start_text": "Third sent",
            "end_text": "entence."
        }}
    ]
}}
"""

USER_PROMPT_TEMPLATE = """
Now, please process the following document:
---
{document_text}
---
"""


def _estimate_token_count(text: str) -> int:
    """A very rough estimation of token count."""
    return len(text) // TOKEN_ESTIMATE_DIVISOR


def get_chunks_from_llm(text: str) -> Dict[str, Any]:
    """
    Calls the LLM via a LiteLLM proxy to get semantic chunk boundaries.
    """
    base_url = os.getenv("LITELLM_BASE_URL")
    api_key = os.getenv("LITELLM_API_KEY")
    if not base_url or not api_key:
        raise RuntimeError("LITELLM_BASE_URL and LITELLM_API_KEY must be set to use the proxy.")

    try:
        logger.info(f"[chunker] Calling LLM proxy at {base_url} for model '{LLM_MODEL}' with a document of {len(text)} characters.")
        
        client = OpenAI(base_url=base_url.rstrip("/"), api_key=api_key)
        
        user_prompt = USER_PROMPT_TEMPLATE.format(document_text=text)

        # Using client.chat.completions.create as per user's snippet
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            timeout=300, # Using a 5-minute timeout
        )
        
        response_text = response.choices[0].message.content
        # Log the raw response text so we can inspect the original JSON/document
        logger.info(f"[chunker] Raw LLM response text: {response_text}")

        # Clean the response to ensure it's valid JSON
        json_str = response_text.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        json_str = json_str.strip()

        try:
            data = json.loads(json_str)
        except Exception as parse_err:
            logger.error(f"[chunker] Failed to parse LLM JSON. Raw string: {json_str}")
            fallback_chunks = _recover_chunks_from_invalid_json(json_str)
            if fallback_chunks:
                logger.warning("[chunker] Falling back to regex-based chunk extraction due to JSON decode error.")
                return {"positions": fallback_chunks, "raw_response": response}
            raise parse_err
        
        if "chunks" not in data or not isinstance(data["chunks"], list):
            raise ValueError("LLM response is missing 'chunks' list.")
        
        return {"positions": data["chunks"], "raw_response": response}

    except Exception as e:
        logger.error(f"[chunker] Failed to get or parse chunks from LLM proxy: {e}")
        # Fallback to a simple chunking strategy if LLM fails
        return {"positions": [{"start": 0, "end": len(text)}], "raw_response": None}


def _debug_log_chunk_boundaries(text: str, positions: List[Dict[str, int]], max_chunks: int = 10, context_chars: int = 10) -> None:
    """Optional debug helper to inspect chunk boundary characters.

    When CHUNKER_DEBUG is set in the environment, log the first few chunks'
    start/end positions along with a short preview of the surrounding text.
    """
    if not os.getenv("CHUNKER_DEBUG"):
        return

    try:
        logger.info(
            f"[chunker-debug] Inspecting up to {min(len(positions), max_chunks)} chunks "
            f"(context_chars={context_chars}). Total text length={len(text)}."
        )
        for i, pos in enumerate(positions[:max_chunks]):
            start = pos.get("start")
            end = pos.get("end")
            if start is None or end is None:
                logger.info(f"[chunker-debug] Chunk {i+1}: missing start/end -> {pos}")
                continue

            # Clamp to valid range to avoid IndexError
            start_clamped = max(0, min(start, len(text)))
            end_clamped = max(0, min(end, len(text)))

            before = text[max(0, start_clamped - context_chars):start_clamped]
            start_snippet = text[start_clamped:start_clamped + context_chars]
            end_snippet = text[max(0, end_clamped - context_chars):end_clamped]
            after = text[end_clamped:end_clamped + context_chars]

            logger.info(
                "[chunker-debug] Chunk %d: start=%s end=%s | "
                "before='%s' | start_snippet='%s' | end_snippet='%s' | after='%s'",
                i + 1,
                start,
                end,
                before.replace("\n", "\\n"),
                start_snippet.replace("\n", "\\n"),
                end_snippet.replace("\n", "\\n"),
                after.replace("\n", "\\n"),
            )
    except Exception as e:
        logger.warning(f"[chunker-debug] Failed to log chunk boundaries: {e}")


def _recover_chunks_from_invalid_json(raw_text: str) -> List[Dict[str, Any]]:
    """Attempt to salvage chunk start/end pairs from malformed JSON strings."""
    if not raw_text:
        return []

    # Match each {...} block that contains start/end integers
    chunk_pattern = re.compile(
        r"\{[^{}]*?\"start\"\s*:\s*(-?\d+)[^{}]*?\"end\"\s*:\s*(-?\d+)[^{}]*?\}",
        re.DOTALL,
    )
    recovered: List[Dict[str, Any]] = []

    for match in chunk_pattern.finditer(raw_text):
        try:
            start_value = int(match.group(1))
            end_value = int(match.group(2))
        except (TypeError, ValueError):
            continue

        chunk: Dict[str, Any] = {"start": start_value, "end": end_value}

        # Try best-effort extraction for start_text/end_text to help recompute positions.
        start_text_match = re.search(r'"start_text"\s*:\s*"([^"]*)"', match.group(0))
        if start_text_match:
            chunk["start_text"] = start_text_match.group(1)

        end_text_match = re.search(r'"end_text"\s*:\s*"([^"]*)"', match.group(0))
        if end_text_match:
            chunk["end_text"] = end_text_match.group(1)

        recovered.append(chunk)

    return recovered


def _recompute_positions_from_markers(text: str, positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recompute reliable start/end indices using start_text/end_text markers.

    Many LLMs are not precise at counting character indices. Instead of trusting
    the raw "start"/"end" values from the model, we use the provided
    "start_text" and "end_text" as semantic anchors and locate them in the
    original text. We then derive consistent indices from those anchors.

    Strategy (processed in order to keep chunks non-overlapping):
    - For each chunk, search for start_text in `text` starting from the current
      cursor position.
    - Search for end_text after the start position (or reuse a reasonable
      default if not found).
    - Clamp and monotically increase indices to avoid overlaps.
    - If markers are missing or not found, fall back to any existing start/end.
    """
    if not positions:
        return []

    new_positions: List[Dict[str, Any]] = []
    cursor = 0
    n = len(text)

    for i, pos in enumerate(positions):
        start_marker = pos.get("start_text")
        end_marker = pos.get("end_text")
        orig_start = pos.get("start")
        orig_end = pos.get("end")

        start_idx = None
        end_idx = None

        # 1. Try to locate start using start_marker
        if isinstance(start_marker, str) and start_marker:
            found = text.find(start_marker, cursor)
            if found != -1:
                start_idx = found
        # Fallbacks for start
        if start_idx is None:
            if isinstance(orig_start, int):
                start_idx = max(cursor, min(orig_start, n))
            else:
                start_idx = cursor

        # 2. Try to locate end using end_marker
        if isinstance(end_marker, str) and end_marker:
            search_start = start_idx
            found = text.find(end_marker, search_start)
            if found != -1:
                end_idx = found + len(end_marker)

        # Fallbacks for end
        if end_idx is None:
            if isinstance(orig_end, int):
                end_idx = max(start_idx, min(orig_end, n))
            else:
                # Default: extend a bit beyond start, but not past text end
                end_idx = min(start_idx + 512, n)

        # 3. Ensure monotonic, non-overlapping ranges
        if start_idx < cursor:
            start_idx = cursor
        if end_idx < start_idx:
            end_idx = start_idx
        if end_idx > n:
            end_idx = n

        new_pos = dict(pos)
        new_pos["start"] = start_idx
        new_pos["end"] = end_idx
        new_positions.append(new_pos)

        cursor = end_idx

    return new_positions


def _merge_small_chunks(positions: List[Dict[str, Any]], min_chars: int = 400) -> List[Dict[str, Any]]:
    """Merge overly small chunks with their subsequent neighbor to avoid fragmentation.

    This is a simple heuristic:
    - If a chunk's character length is below `min_chars`, merge it forward into
      the next chunk by extending its `end` to the next chunk's `end`.
    - This tends to merge page headers/footers or short headings with the main
      content that follows, producing more useful, larger chunks.
    """
    if not positions:
        return []

    merged: List[Dict[str, Any]] = []
    current = dict(positions[0])

    for next_pos in positions[1:]:
        cur_len = current.get("end", 0) - current.get("start", 0)
        if cur_len < min_chars:
            # Merge current with next: extend end and propagate marker hints
            current_end = current.get("end", 0)
            next_end = next_pos.get("end", current_end)
            if isinstance(next_end, int) and next_end > current_end:
                current["end"] = next_end
                # Prefer the end_text from the latter chunk if available
                if "end_text" in next_pos:
                    current["end_text"] = next_pos["end_text"]
        else:
            merged.append(current)
            current = dict(next_pos)

    merged.append(current)
    return merged



def chunk_document_with_llm(text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Splits a document into semantic chunks using an LLM.
    Handles very large documents by pre-splitting them.
    Returns a dictionary containing the list of Document objects and total tokens used.
    """
    token_count = _estimate_token_count(text)

    all_chunks_positions: List[Dict[str, int]] = []
    total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    use_sentence_fallback = False

    if token_count > LLM_CHUNK_TOKEN_LIMIT:
        logger.warning(
            f"[chunker] Document is too large ({token_count} estimated tokens > {LLM_CHUNK_TOKEN_LIMIT}). "
            f"Pre-splitting before sending to LLM."
        )

        char_limit = LLM_CHUNK_TOKEN_LIMIT * TOKEN_ESTIMATE_DIVISOR
        text_parts = [text[i:i+char_limit] for i in range(0, len(text), char_limit)]

        char_offset = 0
        for part in text_parts:
            result = get_chunks_from_llm(part)
            raw_response = result.get("raw_response")
            if not raw_response:
                use_sentence_fallback = True
                break

            # Recompute positions for this part using markers, then adjust
            part_chunks = _recompute_positions_from_markers(part, result["positions"])

            # Adjust chunk positions to be relative to the original document
            for chunk in part_chunks:
                if "start" in chunk and "end" in chunk:
                    chunk["start"] += char_offset
                    chunk["end"] += char_offset
            all_chunks_positions.extend(part_chunks)
            char_offset += len(part)

            if raw_response and hasattr(raw_response, 'usage'):
                usage = raw_response.usage
                total_tokens["prompt_tokens"] += usage.prompt_tokens
                total_tokens["completion_tokens"] += usage.completion_tokens
                total_tokens["total_tokens"] += usage.total_tokens

    else:
        result = get_chunks_from_llm(text)
        raw_response = result.get("raw_response")
        if not raw_response:
            use_sentence_fallback = True
        else:
            # Recompute positions on the full text using semantic markers
            all_chunks_positions = _recompute_positions_from_markers(text, result["positions"])
            if hasattr(raw_response, 'usage'):
                usage = raw_response.usage
                total_tokens["prompt_tokens"] = usage.prompt_tokens
                total_tokens["completion_tokens"] = usage.completion_tokens
                total_tokens["total_tokens"] = usage.total_tokens

    documents: List[Document] = []
    if not use_sentence_fallback:
        # Merge overly small chunks to avoid excessively fine-grained splitting
        all_chunks_positions = _merge_small_chunks(all_chunks_positions)

        # Optional: debug-log boundaries to verify LLM-provided indices
        _debug_log_chunk_boundaries(text, all_chunks_positions)

        # Create LlamaIndex Document objects from the chunks
        for i, chunk_pos in enumerate(all_chunks_positions):
            start, end = chunk_pos.get("start"), chunk_pos.get("end")
            if start is None or end is None or start > end or start > len(text) or end > len(text):
                logger.warning(f"[chunker] Invalid chunk position received: {chunk_pos}, skipping.")
                continue

            chunk_text = text[start:end]
            if not chunk_text.strip():
                logger.warning(f"[chunker] Empty chunk generated from positions: {chunk_pos}, skipping.")
                continue

            chunk_metadata = metadata.copy()
            chunk_metadata["chunk_number"] = i + 1
            chunk_metadata["total_chunks"] = len(all_chunks_positions)

            documents.append(Document(text=chunk_text, metadata=chunk_metadata))

    if use_sentence_fallback or not documents:
        if use_sentence_fallback:
            logger.warning("[chunker] Falling back to SentenceSplitter due to LLM chunking failure.")
        else:
            logger.warning("[chunker] LLM chunking resulted in zero documents. Falling back to SentenceSplitter chunks.")
        documents = _fallback_sentence_splitter_documents(text, metadata)

    return {"documents": documents, "tokens_used": total_tokens}


def _fallback_sentence_splitter_documents(text: str, metadata: Dict[str, Any]) -> List[Document]:
    """Use LlamaIndex SentenceSplitter as a deterministic fallback."""
    splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=200)
    nodes = splitter.get_nodes_from_documents([Document(text=text, metadata=metadata)])
    if not nodes:
        return [Document(text=text, metadata=metadata)]

    documents: List[Document] = []
    for idx, node in enumerate(nodes):
        chunk_metadata = metadata.copy()
        chunk_metadata["chunk_number"] = idx + 1
        chunk_metadata["total_chunks"] = len(nodes)
        documents.append(Document(text=node.get_content(), metadata=chunk_metadata))
    return documents
