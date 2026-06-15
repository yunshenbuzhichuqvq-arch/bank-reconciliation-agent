import json
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_SET_PATH = PROJECT_ROOT / "data/rag_eval_set.json"
CHUNK_PATHS = {
    "BANK_ENTERPRISE": PROJECT_ROOT / "data/rag/rule_chunks_bank_enterprise.jsonl",
    "BANK_CLEARING": PROJECT_ROOT / "data/rag/rule_chunks_bank_clearing.jsonl",
}
REQUIRED_FIELDS = {"id", "scenario_type", "error_type", "query", "expected_chunk_ids"}


def _load_json(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_chunk_ids(path: Path) -> set[str]:
    return {
        json.loads(line)["chunk_id"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def test_rag_eval_set_covers_enterprise_and_clearing_with_valid_chunk_ids() -> None:
    cases = _load_json(EVAL_SET_PATH)
    scenario_counts = Counter(case["scenario_type"] for case in cases)
    valid_chunk_ids = {scenario: _load_chunk_ids(path) for scenario, path in CHUNK_PATHS.items()}

    assert len(cases) >= 120
    assert scenario_counts["BANK_ENTERPRISE"] >= 60
    assert scenario_counts["BANK_CLEARING"] >= 60
    assert len({case["id"] for case in cases}) == len(cases)

    missing_references: list[tuple[str, str]] = []
    for case in cases:
        assert REQUIRED_FIELDS <= set(case)
        assert isinstance(case["query"], str)
        assert case["query"]
        assert isinstance(case["expected_chunk_ids"], list)
        assert case["expected_chunk_ids"]

        scenario_type = str(case["scenario_type"])
        assert scenario_type in valid_chunk_ids
        for chunk_id in case["expected_chunk_ids"]:
            if chunk_id not in valid_chunk_ids[scenario_type]:
                missing_references.append((str(case["id"]), str(chunk_id)))

    assert missing_references == []
