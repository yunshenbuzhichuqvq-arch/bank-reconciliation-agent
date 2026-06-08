from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


class PromptNotFound(RuntimeError):
    pass


def load_prompt(name: str) -> tuple[str, str]:
    candidates = sorted(
        PROMPTS_DIR.glob(f"{name}_v*.md"),
        key=lambda path: _version_number(path, name),
    )
    if not candidates:
        raise PromptNotFound(f"Prompt not found: {name}")

    prompt_path = candidates[-1]
    version = prompt_path.stem.rsplit("_", 1)[1]
    return prompt_path.read_text(encoding="utf-8"), version


def _version_number(path: Path, name: str) -> int:
    version = path.stem.removeprefix(f"{name}_v")
    if not version.isdigit():
        return -1
    return int(version)
