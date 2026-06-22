import json
from collections.abc import Iterable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.schemas.stream import AgentStreamEvent, StreamEventType
from scripts.generate_mock_excel import generate_mvp1_mock_excel, generate_mvp2a3_mock_excel
from tests.auth_helpers import demo_bearer_headers


client = TestClient(app)
DEMO_HEADERS = demo_bearer_headers()


@pytest.mark.parametrize(
    ("scenario_type", "generator", "bank_filename", "clear_filename"),
    [
        (
            "BANK_ENTERPRISE",
            generate_mvp1_mock_excel,
            "bank_transactions.xlsx",
            "clear_transactions.xlsx",
        ),
        (
            "BANK_CLEARING",
            generate_mvp2a3_mock_excel,
            "mvp2a3_core.xlsx",
            "mvp2a3_clearing.xlsx",
        ),
    ],
)
def test_stream_endpoint_emits_e2e_sequence_and_matches_upload_terminal_counts(
    tmp_path: Path,
    scenario_type: str,
    generator,
    bank_filename: str,
    clear_filename: str,
) -> None:
    bank_path, clear_path = generator(tmp_path / scenario_type.lower())

    stream_response = _post_reconcile(
        "/api/v1/reconcile/stream",
        bank_path=bank_path,
        clear_path=clear_path,
        bank_filename=bank_filename,
        clear_filename=clear_filename,
        scenario_type=scenario_type,
    )

    assert stream_response.status_code == 200
    assert stream_response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse_events(stream_response.text)
    event_types = [event.event_type for event in events]
    decision_events = [
        event
        for event in events
        if event.event_type == StreamEventType.AGENT_DECISION
        and event.payload.get("agent_name") == "AuditAgent"
    ]

    assert event_types[0] == StreamEventType.TASK_STARTED
    assert StreamEventType.RAG_RETRIEVED in event_types
    assert decision_events
    assert events[-1].event_type == StreamEventType.TASK_DONE
    assert events[-1].payload["status"] == "COMPLETED"
    assert [event.seq for event in events] == sorted(event.seq for event in events)
    assert len({event.seq for event in events}) == len(events)
    assert _has_readable_decision_and_evidence(decision_events)

    upload_response = _post_reconcile(
        "/api/v1/reconcile/upload",
        bank_path=bank_path,
        clear_path=clear_path,
        bank_filename=bank_filename,
        clear_filename=clear_filename,
        scenario_type=scenario_type,
    )
    assert upload_response.status_code == 200

    stream_start = events[0].payload
    stream_done = events[-1].payload
    upload_data = upload_response.json()["data"]
    assert stream_start["scenario_type"] == scenario_type
    for key in (
        "total_bank_rows",
        "total_clear_rows",
        "auto_fixed_rows",
        "pending_ai_rows",
        "pending_human_rows",
    ):
        assert stream_done[key] == upload_data[key]


def _post_reconcile(
    path: str,
    *,
    bank_path: Path,
    clear_path: Path,
    bank_filename: str,
    clear_filename: str,
    scenario_type: str,
):
    with bank_path.open("rb") as bank_file, clear_path.open("rb") as clear_file:
        return client.post(
            path,
            headers=DEMO_HEADERS,
            data={"scenario_type": scenario_type},
            files={
                "bank_file": (
                    bank_filename,
                    bank_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "clear_file": (
                    clear_filename,
                    clear_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )


def _parse_sse_events(body: str) -> list[AgentStreamEvent]:
    frames = [frame for frame in body.split("\n\n") if frame]
    assert frames
    assert all(frame.startswith("data: ") for frame in frames)
    return [
        AgentStreamEvent.model_validate(json.loads(frame.removeprefix("data: ")))
        for frame in frames
    ]


def _has_readable_decision_and_evidence(events: Iterable[AgentStreamEvent]) -> bool:
    return any(
        event.payload.get("decision")
        and isinstance(event.payload.get("evidence"), list)
        and event.payload["evidence"]
        for event in events
    )
