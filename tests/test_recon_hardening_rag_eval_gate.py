from pathlib import Path

from bank_reconciliation_agent.rag.retriever import ChromaRuleStore, RuleRetriever
from bank_reconciliation_agent.services.workflow import run_item
from tests.test_workflow_fallback import (
    EmptyFallbackCaseProvider,
    NoopExtractionAgent,
    SequenceAuditAgent,
    SpyTraceAgent,
    StaticRetriever,
    _evidence,
    _state,
)


def _hash_retriever_no_chunks(tmp_path: Path) -> RuleRetriever:
    empty_chunks = tmp_path / "empty_chunks.jsonl"
    empty_chunks.write_text("", encoding="utf-8")
    store = ChromaRuleStore(
        chunks_path=empty_chunks,
        chroma_path=tmp_path / "chroma",
        embedding_backend="hash",
    )
    return RuleRetriever(store=store)


def test_unrelated_query_reaches_workflow_no_evidence_floor(tmp_path: Path) -> None:
    state = _state()
    state["rag_query"] = "epnbvcyr szkkwltp szoccipw vcbxwjus"
    audit_agent = SequenceAuditAgent([0.4])

    result = run_item(
        state,
        extraction_agent=NoopExtractionAgent(),
        trace_agent=SpyTraceAgent(confidence=0.9),
        audit_agent=audit_agent,
        retriever=_hash_retriever_no_chunks(tmp_path),
        fallback_case_provider=EmptyFallbackCaseProvider(),
    )

    assert result["rag_context"] == []
    assert result["fallback_level"] == 0
    assert result["fallback_path"] == "HUMAN"
    assert result["audit_decision"]["decision"] == "PENDING_HUMAN"


def test_low_confidence_with_evidence_still_reaches_l2() -> None:
    audit_agent = SequenceAuditAgent([0.4, 0.9])

    result = run_item(
        _state(),
        extraction_agent=NoopExtractionAgent(),
        trace_agent=SpyTraceAgent(confidence=0.9),
        audit_agent=audit_agent,
        retriever=StaticRetriever([_evidence(score=0.9)]),
        fallback_case_provider=EmptyFallbackCaseProvider(),
    )

    assert audit_agent.calls == [1, 2]
    assert result["fallback_level"] == 2
    assert result["fallback_path"] == "L1->L2"
