"""Deterministic, branch-aware query enrichment for a single target bucket (ADR-30.1).

The helper appends category-level business retrieval terms to a base query when the
request matches the tracked target profile. It performs no I/O beyond loading the
tracked YAML profile and never calls an LLM, network, database, embedding model or
retriever.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROFILE_PATH = PROJECT_ROOT / "rules/rag_query_terms.yaml"


class QueryEnrichmentConfigError(ValueError):
    """Raised when the tracked query enrichment configuration is invalid."""


class QueryEnrichmentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    scenario_type: str
    error_types: list[str] = []
    exception_branches: list[str] = []
    terms: list[str]

    @field_validator("id", "scenario_type")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("terms")
    @classmethod
    def _terms_non_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("terms must contain at least one item")
        for term in value:
            if not term or not term.strip():
                raise ValueError("terms must not contain blank items")
        return value


class QueryEnrichmentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    profiles: list[QueryEnrichmentProfile]

    @field_validator("profiles")
    @classmethod
    def _profiles_non_empty(
        cls, value: list[QueryEnrichmentProfile]
    ) -> list[QueryEnrichmentProfile]:
        if not value:
            raise ValueError("profiles must contain at least one profile")
        return value

    @model_validator(mode="after")
    def _unique_profile_ids(self) -> QueryEnrichmentConfig:
        seen: set[str] = set()
        for profile in self.profiles:
            if profile.id in seen:
                raise ValueError(f"duplicate profile id: {profile.id}")
            seen.add(profile.id)
        return self


def load_config(path: Path = DEFAULT_PROFILE_PATH) -> QueryEnrichmentConfig:
    """Load and validate the tracked profile config, failing closed on any error."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise QueryEnrichmentConfigError(f"cannot read query enrichment config: {exc}") from exc
    if not isinstance(raw, dict):
        raise QueryEnrichmentConfigError("query enrichment config must be a mapping")
    try:
        return QueryEnrichmentConfig.model_validate(raw)
    except ValidationError as exc:
        raise QueryEnrichmentConfigError(str(exc)) from exc


class QueryEnricher:
    """Applies the matching target profile to a base query, else returns it unchanged."""

    def __init__(self, config: QueryEnrichmentConfig) -> None:
        self._config = config

    @classmethod
    def from_path(cls, path: Path = DEFAULT_PROFILE_PATH) -> QueryEnricher:
        return cls(load_config(path))

    def _match(
        self,
        scenario_type: str,
        error_type: str | None,
        exception_branch: str | None,
    ) -> QueryEnrichmentProfile | None:
        for profile in self._config.profiles:
            if profile.scenario_type != scenario_type:
                continue
            error_hit = bool(error_type) and error_type in profile.error_types
            branch_hit = bool(exception_branch) and exception_branch in profile.exception_branches
            if error_hit or branch_hit:
                return profile
        return None

    def enrich(
        self,
        query: str,
        scenario_type: str,
        error_type: str | None,
        exception_branch: str | None = None,
    ) -> str:
        profile = self._match(scenario_type, error_type, exception_branch)
        if profile is None:
            return query
        return f"{query} {' '.join(profile.terms)}"


_default_enricher: QueryEnricher | None = None


def default_enricher() -> QueryEnricher:
    global _default_enricher
    if _default_enricher is None:
        _default_enricher = QueryEnricher.from_path(DEFAULT_PROFILE_PATH)
    return _default_enricher


def enrich(
    query: str,
    scenario_type: str,
    error_type: str | None,
    exception_branch: str | None = None,
) -> str:
    return default_enricher().enrich(query, scenario_type, error_type, exception_branch)
