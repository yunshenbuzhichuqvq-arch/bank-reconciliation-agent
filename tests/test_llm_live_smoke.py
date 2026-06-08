import json
import os

import pytest

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.llm.provider import DeepSeekProvider


@pytest.mark.live
def test_deepseek_live_smoke_returns_json() -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        pytest.skip("DEEPSEEK_API_KEY is not configured")

    provider = DeepSeekProvider(
        api_key=api_key,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
    )
    result = provider.complete(
        [{"role": "user", "content": '只返回 JSON：{"ok": true}'}],
        response_format="json_object",
    )

    assert json.loads(result.text)
    assert result.prompt_tokens >= 0
    assert result.completion_tokens >= 0
