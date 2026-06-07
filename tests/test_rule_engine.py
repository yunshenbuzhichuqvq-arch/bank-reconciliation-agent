from pathlib import Path

from bank_reconciliation_agent.services.rule_engine import RuleEngine


DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "rules" / "bank_enterprise.yaml"


def test_loads_bank_enterprise_rules_in_priority_order() -> None:
    engine = RuleEngine(DEFAULT_RULES_PATH)

    assert [rule.id for rule in engine.rules] == [
        "BE-R008",
        "BE-R005",
        "BE-R006",
        "BE-R002",
        "BE-R004",
        "BE-R001",
    ]


def test_evaluates_each_bank_enterprise_rule() -> None:
    engine = RuleEngine(DEFAULT_RULES_PATH)

    cases = [
        (
            {
                "duplicate_suspected": True,
                "present_side": None,
                "flow_matched": True,
                "amount_equal": True,
                "narrative_or_name_mismatch": False,
            },
            ("BE-R008", "EXCEPTION", "DUPLICATE_BOOKING", "BE-R008"),
        ),
        (
            {"duplicate_suspected": False, "present_side": "A", "flow_matched": False},
            ("BE-R005", "EXCEPTION", "BANK_UNARRIVED", "BE-R005"),
        ),
        (
            {"duplicate_suspected": False, "present_side": "B", "flow_matched": False},
            ("BE-R006", "EXCEPTION", "BOOK_UNRECORDED", "BE-R006"),
        ),
        (
            {
                "duplicate_suspected": False,
                "present_side": None,
                "flow_matched": True,
                "amount_equal": False,
            },
            ("BE-R002", "EXCEPTION", "AMOUNT_MISMATCH", "BE-R002"),
        ),
        (
            {
                "duplicate_suspected": False,
                "present_side": None,
                "flow_matched": True,
                "amount_equal": True,
                "narrative_or_name_mismatch": True,
            },
            ("BE-R004", "EXCEPTION", "NARRATIVE_NAME_MISMATCH", "BE-R004"),
        ),
        (
            {
                "duplicate_suspected": False,
                "present_side": None,
                "flow_matched": True,
                "amount_equal": True,
                "narrative_or_name_mismatch": False,
            },
            ("BE-R001", "AUTO_FIX", None, None),
        ),
    ]

    for facts, expected in cases:
        match = engine.evaluate(facts)
        assert (
            match.rule_id,
            match.action,
            match.error_type,
            match.exception_branch,
        ) == expected


def test_duplicate_rule_has_highest_priority() -> None:
    engine = RuleEngine(DEFAULT_RULES_PATH)

    match = engine.evaluate(
        {
            "duplicate_suspected": True,
            "present_side": "A",
            "flow_matched": True,
            "amount_equal": False,
            "narrative_or_name_mismatch": True,
        }
    )

    assert match.rule_id == "BE-R008"
    assert match.error_type == "DUPLICATE_BOOKING"


def test_no_match_returns_unclassified_exception() -> None:
    engine = RuleEngine(DEFAULT_RULES_PATH)

    match = engine.evaluate({})

    assert match.rule_id == "NONE"
    assert match.action == "EXCEPTION"
    assert match.error_type == "UNCLASSIFIED"
    assert match.exception_branch is None


def test_eq_and_neq_operators(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        """
rules:
  - id: T-R001
    name: Neq match
    priority: 1
    conditions:
      - field: flag
        operator: neq
        value: false
    action: EXCEPTION
    error_type: NEQ_MATCH
    exception_branch: T-R001
  - id: T-R002
    name: Eq match
    priority: 2
    conditions:
      - field: flag
        operator: eq
        value: false
    action: AUTO_FIX
""",
        encoding="utf-8",
    )
    engine = RuleEngine(rules_path)

    assert engine.evaluate({"flag": True}).rule_id == "T-R001"
    assert engine.evaluate({"flag": False}).rule_id == "T-R002"
