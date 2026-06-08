from pathlib import Path

from scripts.compare_prompts import compare_prompt_versions, render_comparison


def test_compare_prompt_versions_reports_single_version_without_crashing(tmp_path: Path) -> None:
    (tmp_path / "audit_v1.md").write_text("audit prompt v1", encoding="utf-8")

    report = compare_prompt_versions(prompt_dir=tmp_path)
    output = render_comparison(report)

    assert report.single_version is True
    assert [summary.version for summary in report.summaries] == ["v1"]
    assert "Only one audit prompt version found: v1" in output


def test_compare_prompt_versions_computes_consistency_and_confidence(tmp_path: Path) -> None:
    (tmp_path / "audit_v1.md").write_text("audit prompt v1", encoding="utf-8")
    (tmp_path / "audit_v2.md").write_text("audit prompt v2", encoding="utf-8")

    report = compare_prompt_versions(prompt_dir=tmp_path)
    output = render_comparison(report)

    assert report.single_version is False
    assert report.consistency_rate == 1.0
    assert [summary.version for summary in report.summaries] == ["v1", "v2"]
    assert all(summary.mean_confidence == 0.88 for summary in report.summaries)
    assert "decision_consistency_rate: 100.00%" in output
    assert "version | rows | mean_confidence" in output
