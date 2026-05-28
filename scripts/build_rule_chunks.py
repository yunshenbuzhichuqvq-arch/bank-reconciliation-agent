import argparse
import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES_PATH = PROJECT_ROOT / "data/rag/sources.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data/rag/rule_chunks.jsonl"
HEADING_PATTERN = re.compile(r"^##\s+(?P<title>.+)$", re.MULTILINE)


def build_rule_chunks(
    sources_path: Path = DEFAULT_SOURCES_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> list[dict[str, Any]]:
    """Build traceable rule chunks from curated public-source excerpts."""
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    chunks: list[dict[str, Any]] = []

    for source in sources:
        source_file = PROJECT_ROOT / source["source_file"]
        sections = _split_markdown_sections(source_file.read_text(encoding="utf-8"))
        for index, section in enumerate(sections, start=1):
            chunks.append(
                {
                    "chunk_id": f"{source['source_id']}_{index:03d}",
                    "source_name": source["source_name"],
                    "source_url": source["source_url"],
                    "source_file": source["source_file"],
                    "source_type": source["source_type"],
                    "section_title": section["section_title"],
                    "page_no": None,
                    "element_type": "paragraph",
                    "business_tags": source["business_tags"],
                    "content": section["content"],
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    return chunks


def _split_markdown_sections(markdown_text: str) -> list[dict[str, str]]:
    matches = list(HEADING_PATTERN.finditer(markdown_text))
    sections: list[dict[str, str]] = []

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_text)
        content = markdown_text[start:end].strip()
        if content:
            sections.append(
                {
                    "section_title": match.group("title").strip(),
                    "content": content,
                }
            )

    return sections


def main() -> None:
    parser = argparse.ArgumentParser(description="Build RAG rule chunks from public sources.")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    chunks = build_rule_chunks(sources_path=args.sources, output_path=args.output)
    print(f"Built {len(chunks)} rule chunks: {args.output}")


if __name__ == "__main__":
    main()
