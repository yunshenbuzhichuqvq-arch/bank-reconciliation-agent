from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "bench_agent_latency.py"


def test_bench_agent_latency_script_outputs_latency_comparison() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "ExtractionAgent" in output
    assert "RAG" in output
    assert "average_ms" in output
    assert "ratio" in output
    assert "ADR-032" in output
    assert "provider=" in output
    assert "fake provider" in output.lower()
    assert "measured ratio" in output.lower()
