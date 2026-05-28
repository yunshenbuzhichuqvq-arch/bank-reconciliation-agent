import argparse
import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_SOURCES_DIR = PROJECT_ROOT / "data/rag/raw_sources"
DEFAULT_SOURCES_PATH = PROJECT_ROOT / "data/rag/sources.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data/rag/rule_chunks.jsonl"
HEADING_PATTERN = re.compile(r"^##\s+(?P<title>.+)$", re.MULTILINE)
FRONT_MATTER_PATTERN = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)


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


def build_sources_manifest(
    raw_sources_dir: Path = DEFAULT_RAW_SOURCES_DIR,
    sources_path: Path = DEFAULT_SOURCES_PATH,
    project_root: Path = PROJECT_ROOT,
) -> list[dict[str, Any]]:
    """Discover Markdown rule files and write the RAG sources manifest."""
    sources = [_source_from_markdown(path, project_root) for path in sorted(raw_sources_dir.glob("*.md"))]
    sources_path.parent.mkdir(parents=True, exist_ok=True)
    sources_path.write_text(
        json.dumps(sources, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return sources


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


def _source_from_markdown(path: Path, project_root: Path) -> dict[str, Any]:
    front_matter = _read_front_matter(path)
    source_id = front_matter.get("source_id", path.stem)
    return {
        "source_id": source_id,
        "source_name": front_matter.get("source_name", _title_from_markdown(path)),
        "source_url": front_matter.get("source_url", "https://example.com/internal-rule"),
        "source_file": path.relative_to(project_root).as_posix(),
        "source_type": front_matter.get("source_type", "markdown"),
        "business_tags": _parse_business_tags(front_matter.get("business_tags", "")),
    }


def _read_front_matter(path: Path) -> dict[str, str]:
    markdown_text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_PATTERN.match(markdown_text)
    if not match:
        return {}

    metadata: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def _title_from_markdown(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return path.stem.replace("_", " ")


def _parse_business_tags(value: str) -> list[str]:
    if not value:
        return ["audit_trail"]
    return [tag.strip() for tag in value.split(",") if tag.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build RAG rule chunks from public sources.")
    parser.add_argument("--raw-sources", type=Path, default=DEFAULT_RAW_SOURCES_DIR)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    build_sources_manifest(raw_sources_dir=args.raw_sources, sources_path=args.sources)
    chunks = build_rule_chunks(sources_path=args.sources, output_path=args.output)
    print(f"Built {len(chunks)} rule chunks: {args.output}")


if __name__ == "__main__":
    main()
