from __future__ import annotations

import json

from bank_reconciliation_agent.core.llm.provider import LLMProvider, LLMUnavailable, get_llm_provider
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.core.prompts import load_prompt


class QueryRewriter:
    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        prompt_text: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        loaded_prompt_text, loaded_prompt_version = load_prompt("query_rewrite")
        self.provider = provider or get_llm_provider()
        self.prompt_text = prompt_text or loaded_prompt_text
        self.prompt_version = prompt_version or loaded_prompt_version
        self.last_llm_result = None

    def rewrite(self, query: str, *, scenario_type: str) -> str:
        messages = [
            {"role": "system", "content": self.prompt_text},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "query_rewrite",
                        "query": query,
                        "scenario_type": scenario_type,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        ]

        try:
            result = self.provider.complete(messages, temperature=0.0, response_format="json_object")
            self.last_llm_result = result
            payload = json.loads(result.text)
            rewritten_query = str(payload["rewritten_query"]).strip()
            if rewritten_query:
                return rewritten_query
        except (LLMUnavailable, json.JSONDecodeError, KeyError, TypeError, ValueError):
            log.warning(
                "query_rewrite_fallback",
                prompt_version=self.prompt_version,
                scenario_type=scenario_type,
            )
        return query
