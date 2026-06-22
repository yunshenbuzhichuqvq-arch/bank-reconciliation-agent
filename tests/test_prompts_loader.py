import pytest

from bank_reconciliation_agent.core.prompts import PromptNotFound, load_prompt


def test_load_prompt_returns_latest_text_and_version() -> None:
    text, version = load_prompt("audit")

    assert version == "v2"
    assert text.strip()
    assert "金额不重新计算" in text


def test_all_mvp2a1_prompts_include_json_and_amount_constraints() -> None:
    for name in ("extraction", "audit", "trace"):
        text, version = load_prompt(name)

        assert version == "v2" if name == "audit" else "v1"
        assert "JSON" in text
        assert "金额不重新计算" in text


def test_load_prompt_raises_for_unknown_prompt() -> None:
    with pytest.raises(PromptNotFound):
        load_prompt("rewrite")
