from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class RuleCondition(BaseModel):
    field: str
    operator: Literal["eq", "neq"]
    value: object


class Rule(BaseModel):
    id: str
    name: str
    priority: int
    conditions: list[RuleCondition]
    action: Literal["AUTO_FIX", "EXCEPTION"]
    error_type: str | None = None
    exception_branch: str | None = None


class RuleMatch(BaseModel):
    rule_id: str
    action: Literal["AUTO_FIX", "EXCEPTION"]
    error_type: str | None = None
    exception_branch: str | None = None


class RuleEngine:
    def __init__(self, rules_path: str | Path) -> None:
        self.rules_path = Path(rules_path)
        self.rules = self._load_rules()

    def evaluate(self, facts: dict[str, object]) -> RuleMatch:
        for rule in self.rules:
            if all(self._matches_condition(condition, facts) for condition in rule.conditions):
                return RuleMatch(
                    rule_id=rule.id,
                    action=rule.action,
                    error_type=rule.error_type,
                    exception_branch=rule.exception_branch,
                )

        return RuleMatch(
            rule_id="NONE",
            action="EXCEPTION",
            error_type="UNCLASSIFIED",
            exception_branch=None,
        )

    def _load_rules(self) -> list[Rule]:
        raw = yaml.safe_load(self.rules_path.read_text(encoding="utf-8")) or {}
        rules = [Rule.model_validate(item) for item in raw.get("rules", [])]
        return sorted(rules, key=lambda rule: rule.priority)

    def _matches_condition(self, condition: RuleCondition, facts: dict[str, object]) -> bool:
        fact_value = facts.get(condition.field)
        if condition.operator == "eq":
            return fact_value == condition.value
        return fact_value != condition.value


rule_engine = RuleEngine(Path(__file__).resolve().parents[3] / "rules" / "bank_enterprise.yaml")
