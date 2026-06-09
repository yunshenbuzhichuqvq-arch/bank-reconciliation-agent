from pathlib import Path

from bank_reconciliation_agent.services.rule_engine import (
    RuleEngine,
    rule_engine,
    rule_engine_for,
)


RULES_DIR = Path(__file__).resolve().parents[1] / "rules"


def test_rule_engine_for_routes_scenarios_to_expected_yaml() -> None:
    bank_enterprise_engine = rule_engine_for("BANK_ENTERPRISE")
    bank_clearing_engine = rule_engine_for("BANK_CLEARING")

    assert bank_enterprise_engine is rule_engine
    assert bank_enterprise_engine.rules_path == RULES_DIR / "bank_enterprise.yaml"
    assert bank_clearing_engine.rules_path == RULES_DIR / "bank_clearing.yaml"


def test_bank_clearing_rules_load_in_priority_order() -> None:
    engine = RuleEngine(RULES_DIR / "bank_clearing.yaml")

    assert [rule.id for rule in engine.rules] == [
        "BC-R003",
        "BC-R001",
        "BC-R000",
    ]


def test_bank_clearing_rule_engine_matches_expected_branches() -> None:
    engine = RuleEngine(RULES_DIR / "bank_clearing.yaml")

    assert (
        engine.evaluate({"present_side": "A", "in_cutoff_window": True}).rule_id,
        engine.evaluate({"present_side": "A", "in_cutoff_window": True}).error_type,
        engine.evaluate({"present_side": "A", "in_cutoff_window": True}).exception_branch,
    ) == ("BC-R003", "CUTOFF_CROSS_DAY", "BC-R003")

    assert (
        engine.evaluate({"present_side": "A", "in_cutoff_window": False}).rule_id,
        engine.evaluate({"present_side": "A", "in_cutoff_window": False}).error_type,
        engine.evaluate({"present_side": "A", "in_cutoff_window": False}).exception_branch,
    ) == ("BC-R001", "CLEARING_SINGLE_SIDE", "BC-R001")

    auto_fix_match = engine.evaluate({"flow_matched": True, "amount_equal": True})
    assert (
        auto_fix_match.rule_id,
        auto_fix_match.action,
        auto_fix_match.error_type,
        auto_fix_match.exception_branch,
    ) == ("BC-R000", "AUTO_FIX", None, None)


def test_bank_clearing_cutoff_rule_has_higher_priority_than_single_side() -> None:
    match = rule_engine_for("BANK_CLEARING").evaluate(
        {"present_side": "A", "in_cutoff_window": True, "flow_matched": False}
    )

    assert match.rule_id == "BC-R003"
    assert match.error_type == "CUTOFF_CROSS_DAY"


def test_bank_enterprise_rule_engine_behavior_is_unchanged() -> None:
    match = rule_engine_for("BANK_ENTERPRISE").evaluate(
        {
            "duplicate_suspected": False,
            "present_side": None,
            "flow_matched": True,
            "amount_equal": True,
            "narrative_or_name_mismatch": False,
        }
    )

    assert (
        match.rule_id,
        match.action,
        match.error_type,
        match.exception_branch,
    ) == ("BE-R001", "AUTO_FIX", None, None)
