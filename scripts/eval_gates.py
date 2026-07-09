from __future__ import annotations

from typing import Any

STAGE = "stage-24-eval-gate-layering"


def build_eval_gate_summary(
    *,
    harness_comparison: dict[str, Any],
    schema_conformance: dict[str, Any] | None = None,
    agent_real_report: dict[str, Any] | None = None,
    rag_matrix: dict[str, Any] | None = None,
    performance_cost_report: dict[str, Any] | None = None,
    triage_summary: dict[str, Any] | None = None,
    source_reports: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    ci_checks = [
        _ci_harness_gates_check(harness_comparison),
        _ci_schema_conformance_check(schema_conformance),
    ]
    manual_checks = [
        _manual_deepseek_agent_eval_check(agent_real_report),
        _manual_real_embedding_rag_matrix_check(rag_matrix),
        _manual_real_provider_performance_cost_check(performance_cost_report),
    ]
    release_checks = [
        _release_unsafe_auto_fix_check(agent_real_report),
        _release_hard_constraint_violation_check(agent_real_report),
        _release_real_provider_trust_check(agent_real_report),
        _release_real_embedding_trust_check(rag_matrix),
        _release_performance_cost_trust_check(performance_cost_report),
    ]

    ci_layer = _build_ci_layer(ci_checks)
    manual_layer = _build_manual_layer(manual_checks)
    release_layer = _build_release_layer(release_checks)

    layers = {
        "ci": ci_layer,
        "manual_diagnostic": manual_layer,
        "release": release_layer,
    }

    return {
        "stage": STAGE,
        "overall_status": _overall_status(ci_layer, manual_layer, release_layer),
        "source_reports": _normalize_source_reports(source_reports),
        "layers": layers,
        "claim_boundary": _claim_boundary(),
    }


def _check(
    *,
    check_id: str,
    layer: str,
    status: str,
    blocks_ci: bool,
    blocks_release: bool,
    summary: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": check_id,
        "layer": layer,
        "status": status,
        "blocks_ci": blocks_ci,
        "blocks_release": blocks_release,
        "summary": summary,
        "evidence": evidence,
    }


def _ci_harness_gates_check(harness_comparison: dict[str, Any]) -> dict[str, Any]:
    after_gates = (harness_comparison or {}).get("gates", {}).get("after")
    has_gates = isinstance(after_gates, dict) and len(after_gates) > 0
    all_pass = has_gates and all(bool(v) for v in after_gates.values())

    if all_pass:
        return _check(
            check_id="ci_default_fake_hash_harness_gates",
            layer="ci",
            status="pass",
            blocks_ci=False,
            blocks_release=False,
            summary="Deterministic fake/hash harness after-gates all pass.",
            evidence={"after_gates": after_gates},
        )
    return _check(
        check_id="ci_default_fake_hash_harness_gates",
        layer="ci",
        status="fail",
        blocks_ci=True,
        blocks_release=True,
        summary=(
            "Deterministic fake/hash harness after-gates are missing or failing."
            if has_gates
            else "Deterministic fake/hash harness after-gates object is missing."
        ),
        evidence={"after_gates": after_gates},
    )


def _ci_schema_conformance_check(
    schema_conformance: dict[str, Any] | None,
) -> dict[str, Any]:
    rate: Any = None
    if isinstance(schema_conformance, dict):
        rate = schema_conformance.get("schema_conformance_rate")

    if rate == 1.0:
        return _check(
            check_id="ci_agent_schema_conformance",
            layer="ci",
            status="pass",
            blocks_ci=False,
            blocks_release=False,
            summary="Agent schema conformance rate is 1.0.",
            evidence={"schema_conformance_rate": rate},
        )
    return _check(
        check_id="ci_agent_schema_conformance",
        layer="ci",
        status="fail",
        blocks_ci=True,
        blocks_release=True,
        summary=(
            "Agent schema conformance report missing or malformed."
            if rate is None
            else f"Agent schema conformance rate {rate} is below 1.0."
        ),
        evidence={"schema_conformance_rate": rate},
    )


def _is_trusted_deepseek_agent(report: dict[str, Any] | None) -> bool:
    if not isinstance(report, dict):
        return False
    return (
        report.get("provider_effective") == "deepseek"
        and report.get("real_provider_call") is True
    )


def _manual_deepseek_agent_eval_check(
    agent_real_report: dict[str, Any] | None,
) -> dict[str, Any]:
    trusted = _is_trusted_deepseek_agent(agent_real_report)
    evidence = {
        "report_present": agent_real_report is not None,
        "provider_effective": (agent_real_report or {}).get("provider_effective"),
        "real_provider_call": (agent_real_report or {}).get("real_provider_call"),
    }
    if trusted:
        return _check(
            check_id="manual_deepseek_agent_eval",
            layer="manual_diagnostic",
            status="pass",
            blocks_ci=False,
            blocks_release=False,
            summary="DeepSeek Agent Eval evidence is trusted (real provider call).",
            evidence=evidence,
        )
    return _check(
        check_id="manual_deepseek_agent_eval",
        layer="manual_diagnostic",
        status="environment_gap",
        blocks_ci=False,
        blocks_release=False,
        summary=(
            "DeepSeek Agent Eval report is missing." if agent_real_report is None
            else "DeepSeek Agent Eval report is not trusted real-provider evidence."
        ),
        evidence=evidence,
    )


def _has_trusted_real_embedding(rag_matrix: dict[str, Any] | None) -> bool:
    if not isinstance(rag_matrix, dict):
        return False
    requirement = rag_matrix.get("real_backend_requirement") or {}
    if requirement.get("satisfied") is not True:
        return False
    rows = rag_matrix.get("rows") or {}
    for backend, row in rows.items():
        if backend == "hash":
            continue
        if not isinstance(row, dict):
            continue
        effective = row.get("effective_backend")
        if (
            row.get("status") == "measured"
            and row.get("requested_backend") == effective
            and effective not in (None, "hash")
        ):
            return True
    return False


def _manual_real_embedding_rag_matrix_check(
    rag_matrix: dict[str, Any] | None,
) -> dict[str, Any]:
    trusted = _has_trusted_real_embedding(rag_matrix)
    requirement = (rag_matrix or {}).get("real_backend_requirement") or {}
    evidence = {
        "report_present": rag_matrix is not None,
        "real_backend_requirement": requirement,
    }
    if trusted:
        return _check(
            check_id="manual_real_embedding_rag_matrix",
            layer="manual_diagnostic",
            status="pass",
            blocks_ci=False,
            blocks_release=False,
            summary="Real embedding RAG matrix has a trusted measured non-hash backend.",
            evidence=evidence,
        )
    return _check(
        check_id="manual_real_embedding_rag_matrix",
        layer="manual_diagnostic",
        status="environment_gap",
        blocks_ci=False,
        blocks_release=False,
        summary=(
            "Real embedding RAG matrix report is missing." if rag_matrix is None
            else "Real embedding RAG matrix has no trusted measured non-hash backend "
            "(missing, unavailable, or fallback to hash)."
        ),
        evidence=evidence,
    )


def _is_trusted_performance_cost(report: dict[str, Any] | None) -> bool:
    if not isinstance(report, dict):
        return False
    trust = report.get("trust") or {}
    tokens = report.get("tokens") or {}
    cost = report.get("cost") or {}
    return (
        report.get("status") == "measured"
        and report.get("provider_effective") == "deepseek"
        and tokens.get("token_usage_available") is True
        and cost.get("cost_available") is True
        and trust.get("trusted") is True
        and trust.get("real_provider_evidence") is True
        and trust.get("cost_evidence_available") is True
    )


def _manual_real_provider_performance_cost_check(
    performance_cost_report: dict[str, Any] | None,
) -> dict[str, Any]:
    trusted = _is_trusted_performance_cost(performance_cost_report)
    report = performance_cost_report or {}
    evidence = {
        "report_present": performance_cost_report is not None,
        "provider_effective": report.get("provider_effective"),
        "status": report.get("status"),
        "trust": report.get("trust"),
    }
    if trusted:
        return _check(
            check_id="manual_real_provider_performance_cost",
            layer="manual_diagnostic",
            status="pass",
            blocks_ci=False,
            blocks_release=False,
            summary="Real provider performance/cost evidence is trusted.",
            evidence=evidence,
        )
    return _check(
        check_id="manual_real_provider_performance_cost",
        layer="manual_diagnostic",
        status="environment_gap",
        blocks_ci=False,
        blocks_release=False,
        summary=(
            "Performance/cost report is missing." if performance_cost_report is None
            else "Performance/cost report is not trusted real-provider evidence "
            "(fake provider, missing token/cost, or partial trust metadata)."
        ),
        evidence=evidence,
    )


def _release_safety_rate_check(
    *,
    check_id: str,
    agent_real_report: dict[str, Any] | None,
    rate_key: str,
    metric_label: str,
) -> dict[str, Any]:
    trusted = _is_trusted_deepseek_agent(agent_real_report)
    if not trusted:
        return _check(
            check_id=check_id,
            layer="release",
            status="environment_gap",
            blocks_ci=False,
            blocks_release=True,
            summary=(
                f"No trusted DeepSeek evidence for effective {metric_label}; "
                "release fails closed."
            ),
            evidence={
                "report_present": agent_real_report is not None,
                "trusted": False,
            },
        )
    rate = agent_real_report.get(rate_key)
    if rate == 0 or rate == 0.0:
        return _check(
            check_id=check_id,
            layer="release",
            status="pass",
            blocks_ci=False,
            blocks_release=False,
            summary=f"Trusted DeepSeek effective {metric_label} is 0.",
            evidence={rate_key: rate, "trusted": True},
        )
    return _check(
        check_id=check_id,
        layer="release",
        status="fail",
        blocks_ci=False,
        blocks_release=True,
        summary=f"Trusted DeepSeek effective {metric_label} is non-zero ({rate}).",
        evidence={rate_key: rate, "trusted": True},
    )


def _release_unsafe_auto_fix_check(
    agent_real_report: dict[str, Any] | None,
) -> dict[str, Any]:
    return _release_safety_rate_check(
        check_id="release_effective_unsafe_auto_fix_zero",
        agent_real_report=agent_real_report,
        rate_key="agent_unsafe_auto_fix_rate",
        metric_label="unsafe auto-fix rate",
    )


def _release_hard_constraint_violation_check(
    agent_real_report: dict[str, Any] | None,
) -> dict[str, Any]:
    return _release_safety_rate_check(
        check_id="release_effective_hard_constraint_violation_zero",
        agent_real_report=agent_real_report,
        rate_key="agent_hard_constraint_violation_rate",
        metric_label="hard constraint violation rate",
    )


def _release_real_provider_trust_check(
    agent_real_report: dict[str, Any] | None,
) -> dict[str, Any]:
    trusted = _is_trusted_deepseek_agent(agent_real_report)
    evidence = {
        "report_present": agent_real_report is not None,
        "provider_effective": (agent_real_report or {}).get("provider_effective"),
        "real_provider_call": (agent_real_report or {}).get("real_provider_call"),
    }
    if trusted:
        return _check(
            check_id="release_real_provider_trust_visible",
            layer="release",
            status="pass",
            blocks_ci=False,
            blocks_release=False,
            summary="Real provider trust metadata is trusted DeepSeek evidence.",
            evidence=evidence,
        )
    return _check(
        check_id="release_real_provider_trust_visible",
        layer="release",
        status="environment_gap",
        blocks_ci=False,
        blocks_release=True,
        summary=(
            "Real provider trust metadata is missing or untrusted; release fails closed."
        ),
        evidence=evidence,
    )


def _release_real_embedding_trust_check(
    rag_matrix: dict[str, Any] | None,
) -> dict[str, Any]:
    trusted = _has_trusted_real_embedding(rag_matrix)
    requirement = (rag_matrix or {}).get("real_backend_requirement") or {}
    evidence = {
        "report_present": rag_matrix is not None,
        "real_backend_requirement": requirement,
    }
    if trusted:
        return _check(
            check_id="release_real_embedding_trust_visible",
            layer="release",
            status="pass",
            blocks_ci=False,
            blocks_release=False,
            summary="Real embedding trust metadata satisfies the manual real embedding rule.",
            evidence=evidence,
        )
    return _check(
        check_id="release_real_embedding_trust_visible",
        layer="release",
        status="environment_gap",
        blocks_ci=False,
        blocks_release=True,
        summary=(
            "Real embedding trust metadata is missing, unavailable, or fallback; "
            "release fails closed."
        ),
        evidence=evidence,
    )


def _release_performance_cost_trust_check(
    performance_cost_report: dict[str, Any] | None,
) -> dict[str, Any]:
    trusted = _is_trusted_performance_cost(performance_cost_report)
    report = performance_cost_report or {}
    evidence = {
        "report_present": performance_cost_report is not None,
        "provider_effective": report.get("provider_effective"),
        "status": report.get("status"),
        "trust": report.get("trust"),
    }
    if trusted:
        return _check(
            check_id="release_performance_cost_trust_visible",
            layer="release",
            status="pass",
            blocks_ci=False,
            blocks_release=False,
            summary="Performance/cost trust metadata is trusted real-provider evidence.",
            evidence=evidence,
        )
    return _check(
        check_id="release_performance_cost_trust_visible",
        layer="release",
        status="environment_gap",
        blocks_ci=False,
        blocks_release=True,
        summary=(
            "Performance/cost report is missing." if performance_cost_report is None
            else "Performance/cost trust metadata is untrusted (fake provider or partial "
            "trust); release fails closed."
        ),
        evidence=evidence,
    )


def _build_ci_layer(checks: list[dict[str, Any]]) -> dict[str, Any]:
    status = "pass" if all(c["status"] == "pass" for c in checks) else "fail"
    return {
        "name": "ci",
        "status": status,
        "blocks_ci": any(c["blocks_ci"] for c in checks),
        "blocks_release": any(c["blocks_release"] for c in checks),
        "required_for_default_ci": True,
        "checks": checks,
    }


def _build_manual_layer(checks: list[dict[str, Any]]) -> dict[str, Any]:
    status = "pass" if all(c["status"] == "pass" for c in checks) else "environment_gap"
    return {
        "name": "manual_diagnostic",
        "status": status,
        "blocks_ci": False,
        "blocks_release": False,
        "required_for_default_ci": False,
        "checks": checks,
    }


def _build_release_layer(checks: list[dict[str, Any]]) -> dict[str, Any]:
    status = "pass" if all(c["status"] == "pass" for c in checks) else "blocked"
    return {
        "name": "release",
        "status": status,
        "blocks_ci": False,
        "blocks_release": any(c["blocks_release"] for c in checks),
        "required_for_default_ci": False,
        "checks": checks,
    }


def _overall_status(
    ci_layer: dict[str, Any],
    manual_layer: dict[str, Any],
    release_layer: dict[str, Any],
) -> str:
    if ci_layer["status"] == "fail":
        return "blocked"
    if release_layer["status"] == "blocked":
        return "blocked"
    if manual_layer["status"] == "environment_gap":
        return "environment_gap"
    return "pass"


def _normalize_source_reports(
    source_reports: dict[str, str | None] | None,
) -> dict[str, str | None]:
    keys = [
        "harness_comparison",
        "schema_conformance",
        "agent_real_json",
        "rag_matrix",
        "performance_cost_json",
        "triage_json",
    ]
    provided = source_reports or {}
    return {key: provided.get(key) for key in keys}


def _claim_boundary() -> list[str]:
    return [
        "CI layer is deterministic: fake-provider harness gates and agent schema "
        "conformance run without credentials, network, token spend, or model loads.",
        "Manual diagnostic layer is opt-in: real DeepSeek Agent Eval, real embedding "
        "RAG matrix, and real provider performance/cost require external resources and "
        "never block default CI.",
        "Release layer fails closed: missing or untrusted safety/trust metadata is "
        "reported as an environment gap that blocks release, not as a pass.",
        "Fake-provider, hash-embedding, fallback, missing, or stale evidence must not "
        "be presented as trusted real-provider or real-embedding evidence.",
        "Release safety is based on effective policy-gated system output; raw provider "
        "safety metrics are diagnostic caveats only.",
    ]
