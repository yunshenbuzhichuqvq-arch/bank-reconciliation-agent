from __future__ import annotations

import argparse
import contextlib
import io
from dataclasses import dataclass
from pathlib import Path

from bank_reconciliation_agent.agents.audit_agent import AuditAgent
from bank_reconciliation_agent.core.llm.provider import FakeLLMProvider
from bank_reconciliation_agent.schemas.rag import RagSearchItem


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT_DIR = PROJECT_ROOT / "prompts"


@dataclass(frozen=True)
class AuditSample:
    flow_id: str
    error_type: str
    exception_branch: str
    bank_amount: str | None
    clear_amount: str | None
    amount_diff: str | None


@dataclass(frozen=True)
class PromptRunSummary:
    version: str
    rows: int
    decisions: dict[str, str]
    mean_confidence: float
    min_confidence: float
    max_confidence: float


@dataclass(frozen=True)
class PromptComparisonReport:
    prompt_name: str
    summaries: list[PromptRunSummary]
    consistency_rate: float | None

    @property
    def single_version(self) -> bool:
        return len(self.summaries) <= 1


DEFAULT_AUDIT_SAMPLES = [
    AuditSample("F2003", "AMOUNT_MISMATCH", "BE-R002", "100.00", "99.00", "1.00"),
    AuditSample("F2004", "NARRATIVE_NAME_MISMATCH", "BE-R004", "88.00", "88.00", "0.00"),
    AuditSample("F2005", "BANK_UNARRIVED", "BE-R005", None, "76.00", "76.00"),
    AuditSample("F2006", "BOOK_UNRECORDED", "BE-R006", "65.00", None, "65.00"),
    AuditSample("F2007", "DUPLICATE_BOOKING", "BE-R008", "42.00", "42.00", "0.00"),
]


def compare_prompt_versions(
    *,
    prompt_dir: Path = DEFAULT_PROMPT_DIR,
    prompt_name: str = "audit",
    samples: list[AuditSample] | None = None,
) -> PromptComparisonReport:
    prompt_paths = _prompt_paths(prompt_dir, prompt_name)
    if not prompt_paths:
        raise FileNotFoundError(f"No {prompt_name}_v*.md prompts found in {prompt_dir}")

    audit_samples = samples or DEFAULT_AUDIT_SAMPLES
    summaries = [
        _run_prompt_version(prompt_path, prompt_name=prompt_name, samples=audit_samples)
        for prompt_path in prompt_paths
    ]
    return PromptComparisonReport(
        prompt_name=prompt_name,
        summaries=summaries,
        consistency_rate=_decision_consistency_rate(summaries),
    )


def render_comparison(report: PromptComparisonReport) -> str:
    lines = [f"prompt_name: {report.prompt_name}"]
    if report.single_version:
        version = report.summaries[0].version
        lines.append(f"Only one {report.prompt_name} prompt version found: {version}")
    elif report.consistency_rate is not None:
        lines.append(f"decision_consistency_rate: {report.consistency_rate:.2%}")

    lines.append("version | rows | mean_confidence | min_confidence | max_confidence")
    lines.append("--- | ---: | ---: | ---: | ---:")
    for summary in report.summaries:
        lines.append(
            " | ".join(
                [
                    summary.version,
                    str(summary.rows),
                    f"{summary.mean_confidence:.2f}",
                    f"{summary.min_confidence:.2f}",
                    f"{summary.max_confidence:.2f}",
                ]
            )
        )
    return "\n".join(lines)


def _run_prompt_version(
    prompt_path: Path,
    *,
    prompt_name: str,
    samples: list[AuditSample],
) -> PromptRunSummary:
    version = prompt_path.stem.rsplit("_", 1)[1]
    agent = AuditAgent(
        provider=FakeLLMProvider(),
        prompt_text=prompt_path.read_text(encoding="utf-8"),
        prompt_version=version,
    )
    evidence = [_sample_evidence()]
    decisions: dict[str, str] = {}
    confidences: list[float] = []
    for sample in samples:
        with contextlib.redirect_stdout(io.StringIO()):
            decision = agent.decide_with_llm(
                flow_id=sample.flow_id,
                error_type=sample.error_type,
                exception_branch=sample.exception_branch,
                bank_amount=sample.bank_amount,
                clear_amount=sample.clear_amount,
                amount_diff=sample.amount_diff,
                evidence=evidence,
            )
        decisions[sample.flow_id] = decision.decision
        confidences.append(decision.confidence)

    return PromptRunSummary(
        version=version,
        rows=len(samples),
        decisions=decisions,
        mean_confidence=round(sum(confidences) / len(confidences), 4),
        min_confidence=min(confidences),
        max_confidence=max(confidences),
    )


def _decision_consistency_rate(summaries: list[PromptRunSummary]) -> float | None:
    if len(summaries) <= 1:
        return None

    base_flow_ids = summaries[0].decisions.keys()
    consistent_rows = 0
    for flow_id in base_flow_ids:
        decisions = {summary.decisions[flow_id] for summary in summaries}
        consistent_rows += int(len(decisions) == 1)
    return consistent_rows / len(summaries[0].decisions)


def _prompt_paths(prompt_dir: Path, prompt_name: str) -> list[Path]:
    return sorted(
        prompt_dir.glob(f"{prompt_name}_v*.md"),
        key=lambda path: _version_number(path, prompt_name),
    )


def _version_number(path: Path, prompt_name: str) -> int:
    version = path.stem.removeprefix(f"{prompt_name}_v")
    if not version.isdigit():
        return -1
    return int(version)


def _sample_evidence() -> RagSearchItem:
    return RagSearchItem(
        chunk_id="rule-001",
        source="rules.md#rule",
        source_name="规则",
        source_url="https://example.com/rule",
        source_file="rules.md",
        section_title="rule",
        element_type="paragraph",
        business_tags=["bank_enterprise"],
        score=0.9,
        content="对账差异处理规则依据。",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare prompt versions with deterministic Fake LLM.")
    parser.add_argument("--prompt-dir", type=Path, default=DEFAULT_PROMPT_DIR)
    parser.add_argument("--prompt-name", default="audit")
    args = parser.parse_args()

    report = compare_prompt_versions(prompt_dir=args.prompt_dir, prompt_name=args.prompt_name)
    print(render_comparison(report))


if __name__ == "__main__":
    main()
