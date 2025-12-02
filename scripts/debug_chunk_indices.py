import sys
from pathlib import Path

from llama_index.core import SimpleDirectoryReader


def load_full_text(path: Path) -> str:
    reader = SimpleDirectoryReader(input_files=[path])
    docs = reader.load_data()
    if not docs:
        raise RuntimeError("No documents loaded from file")
    # 与 benchmark_chunking.py 保持一致：拼接所有 docs
    text = "\n\n".join(doc.get_content() for doc in docs)
    return text.replace("\x00", "")


def debug_positions(text: str):
    # 这里先硬编码你刚才贴出来的那些 chunk 信息，方便对比
    positions = [
        (0, 809, "硅基数据开放", "3 /27"),
        (809, 1007, "1. 版本信息", " 郭浩"),
        (1007, 1100, "2. 文档概述", "数据同步服务。"),
        (1100, 1280, "2.2.声明\n", "之后再进行开发。"),
        (1280, 1426, "2.3.适用对象", "4 /27"),
    ]

    print(f"TOTAL LEN: {len(text)}")
    for i, (start, end, exp_start, exp_end) in enumerate(positions, 1):
        # 防止越界
        start = max(0, min(start, len(text)))
        end = max(0, min(end, len(text)))
        chunk = text[start:end]
        actual_start = chunk[:10]
        actual_end = chunk[-10:] if chunk else ""

        print(f"\nCHUNK {i}: start={start}, end={end}")
        print("  actual_start_text:", repr(actual_start))
        print("  actual_end_text  :", repr(actual_end))
        print("  expected_start   :", repr(exp_start))
        print("  expected_end     :", repr(exp_end))


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/debug_chunk_indices.py <file_path>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    text = load_full_text(file_path)
    debug_positions(text)


if __name__ == "__main__":
    main()
