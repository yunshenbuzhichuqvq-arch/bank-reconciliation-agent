import re
from pathlib import Path

import pytest

from bank_reconciliation_agent.rag import query_enrichment
from bank_reconciliation_agent.rag.query_enrichment import (
    DEFAULT_PROFILE_PATH,
    QueryEnricher,
    QueryEnrichmentConfigError,
    enrich,
    load_config,
)

TARGET_PROFILE_ID = "bank-clearing-single-side-missing"


def _write_yaml(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "profiles.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _valid_config_text() -> str:
    return (
        "version: 1\n"
        "profiles:\n"
        f"  - id: {TARGET_PROFILE_ID}\n"
        "    scenario_type: BANK_CLEARING\n"
        "    error_types:\n"
        "      - SINGLE_SIDE_MISSING\n"
        "      - CLEARING_SINGLE_SIDE\n"
        "    exception_branches:\n"
        "      - BC-R001\n"
        "    terms:\n"
        "      - 清算单边\n"
        "      - 查询查复\n"
    )


def _enricher(tmp_path: Path) -> QueryEnricher:
    return QueryEnricher.from_path(_write_yaml(tmp_path, _valid_config_text()))


# ---------------------------------------------------------------------------
# Default tracked profile
# ---------------------------------------------------------------------------


def test_default_profile_identity_and_scope() -> None:
    config = load_config(DEFAULT_PROFILE_PATH)
    assert len(config.profiles) == 1
    profile = config.profiles[0]
    assert profile.id == TARGET_PROFILE_ID
    assert profile.scenario_type == "BANK_CLEARING"
    assert set(profile.error_types) == {"SINGLE_SIDE_MISSING", "CLEARING_SINGLE_SIDE"}
    assert profile.exception_branches == ["BC-R001"]
    assert profile.terms


def test_default_profile_terms_are_category_level_not_case_answers() -> None:
    config = load_config(DEFAULT_PROFILE_PATH)
    for term in config.profiles[0].terms:
        assert term.strip() == term
        assert term
        assert "chunk" not in term.lower()
        assert "_" not in term
        assert not re.search(r"(?i)\b[a-z]{2}-r\d", term)


def test_module_level_enrich_uses_default_profile() -> None:
    original = "清算流水在核心端缺失如何处理"
    enriched = enrich(original, "BANK_CLEARING", "SINGLE_SIDE_MISSING")
    assert enriched.startswith(original + " ")
    for term in load_config(DEFAULT_PROFILE_PATH).profiles[0].terms:
        assert term in enriched


# ---------------------------------------------------------------------------
# Match semantics
# ---------------------------------------------------------------------------


def test_eval_alias_single_side_missing_hits(tmp_path: Path) -> None:
    enricher = _enricher(tmp_path)
    out = enricher.enrich("q", "BANK_CLEARING", "SINGLE_SIDE_MISSING")
    assert out == "q 清算单边 查询查复"


def test_runtime_alias_matches_same_terms_as_eval_alias(tmp_path: Path) -> None:
    enricher = _enricher(tmp_path)
    eval_out = enricher.enrich("q", "BANK_CLEARING", "SINGLE_SIDE_MISSING")
    runtime_out = enricher.enrich("q", "BANK_CLEARING", "CLEARING_SINGLE_SIDE")
    assert eval_out == runtime_out


def test_branch_only_hit_without_matching_error_type(tmp_path: Path) -> None:
    enricher = _enricher(tmp_path)
    out = enricher.enrich("q", "BANK_CLEARING", "SOME_OTHER_ERROR", exception_branch="BC-R001")
    assert out == "q 清算单边 查询查复"


def test_error_type_and_branch_both_match_appends_terms_once(tmp_path: Path) -> None:
    enricher = _enricher(tmp_path)
    out = enricher.enrich("q", "BANK_CLEARING", "CLEARING_SINGLE_SIDE", exception_branch="BC-R001")
    assert out == "q 清算单边 查询查复"


# ---------------------------------------------------------------------------
# Identity paths
# ---------------------------------------------------------------------------


def test_non_target_scenario_returns_query_unchanged(tmp_path: Path) -> None:
    enricher = _enricher(tmp_path)
    out = enricher.enrich("q", "BANK_ENTERPRISE", "SINGLE_SIDE_MISSING")
    assert out == "q"


def test_non_target_error_and_branch_returns_query_unchanged(tmp_path: Path) -> None:
    enricher = _enricher(tmp_path)
    out = enricher.enrich("q", "BANK_CLEARING", "AMOUNT_MISMATCH", exception_branch="BC-R003")
    assert out == "q"


def test_empty_alias_returns_query_unchanged(tmp_path: Path) -> None:
    enricher = _enricher(tmp_path)
    assert enricher.enrich("q", "BANK_CLEARING", "") == "q"
    assert enricher.enrich("q", "BANK_CLEARING", None) == "q"
    assert enricher.enrich("q", "BANK_CLEARING", "", exception_branch="") == "q"


def test_identity_is_byte_for_byte(tmp_path: Path) -> None:
    enricher = _enricher(tmp_path)
    original = "清算流水  多空格\t制表符 与换行\n结尾"
    assert enricher.enrich(original, "BANK_ENTERPRISE", "SINGLE_SIDE_MISSING") == original


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_enrich_is_deterministic(tmp_path: Path) -> None:
    enricher = _enricher(tmp_path)
    first = enricher.enrich("q", "BANK_CLEARING", "SINGLE_SIDE_MISSING")
    second = enricher.enrich("q", "BANK_CLEARING", "SINGLE_SIDE_MISSING")
    assert first == second


def test_append_preserves_original_query_prefix(tmp_path: Path) -> None:
    enricher = _enricher(tmp_path)
    original = "原始查询内容"
    out = enricher.enrich(original, "BANK_CLEARING", "SINGLE_SIDE_MISSING")
    assert out.startswith(original + " ")
    assert len(out) > len(original)


# ---------------------------------------------------------------------------
# Config validation fails closed
# ---------------------------------------------------------------------------


def test_duplicate_profile_id_fails_closed(tmp_path: Path) -> None:
    text = _valid_config_text() + (
        f"  - id: {TARGET_PROFILE_ID}\n"
        "    scenario_type: BANK_CLEARING\n"
        "    error_types:\n"
        "      - SINGLE_SIDE_MISSING\n"
        "    exception_branches: []\n"
        "    terms:\n"
        "      - 其他\n"
    )
    with pytest.raises(QueryEnrichmentConfigError):
        load_config(_write_yaml(tmp_path, text))


def test_empty_terms_fails_closed(tmp_path: Path) -> None:
    text = (
        "version: 1\n"
        "profiles:\n"
        f"  - id: {TARGET_PROFILE_ID}\n"
        "    scenario_type: BANK_CLEARING\n"
        "    error_types:\n"
        "      - SINGLE_SIDE_MISSING\n"
        "    exception_branches: []\n"
        "    terms: []\n"
    )
    with pytest.raises(QueryEnrichmentConfigError):
        load_config(_write_yaml(tmp_path, text))


def test_blank_term_fails_closed(tmp_path: Path) -> None:
    text = (
        "version: 1\n"
        "profiles:\n"
        f"  - id: {TARGET_PROFILE_ID}\n"
        "    scenario_type: BANK_CLEARING\n"
        "    error_types:\n"
        "      - SINGLE_SIDE_MISSING\n"
        "    exception_branches: []\n"
        "    terms:\n"
        "      - '   '\n"
    )
    with pytest.raises(QueryEnrichmentConfigError):
        load_config(_write_yaml(tmp_path, text))


def test_illegal_type_fails_closed(tmp_path: Path) -> None:
    text = (
        "version: 1\n"
        "profiles:\n"
        f"  - id: {TARGET_PROFILE_ID}\n"
        "    scenario_type: BANK_CLEARING\n"
        "    error_types: SINGLE_SIDE_MISSING\n"
        "    exception_branches: []\n"
        "    terms:\n"
        "      - 清算单边\n"
    )
    with pytest.raises(QueryEnrichmentConfigError):
        load_config(_write_yaml(tmp_path, text))


def test_unknown_field_fails_closed(tmp_path: Path) -> None:
    text = _valid_config_text() + "    unexpected_field: nope\n"
    with pytest.raises(QueryEnrichmentConfigError):
        load_config(_write_yaml(tmp_path, text))


def test_empty_profiles_fails_closed(tmp_path: Path) -> None:
    text = "version: 1\nprofiles: []\n"
    with pytest.raises(QueryEnrichmentConfigError):
        load_config(_write_yaml(tmp_path, text))


def test_helper_has_no_io_dependencies() -> None:
    import inspect

    source = inspect.getsource(query_enrichment)
    for forbidden in ("requests", "httpx", "chromadb", "sentence_transformers", "socket"):
        assert forbidden not in source
