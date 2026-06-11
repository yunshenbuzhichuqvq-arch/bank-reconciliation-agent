import json
import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from bank_reconciliation_agent.core.config import settings


class LLMResult(BaseModel):
    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str


class LLMUnavailable(RuntimeError):
    """Raised when the configured LLM provider cannot return a usable response."""


class LLMProvider(Protocol):
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: Literal["text", "json_object"] = "json_object",
    ) -> LLMResult: ...


class FakeLLMProvider:
    model = "fake-llm"
    prompt_tokens = 128
    completion_tokens = 64

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: Literal["text", "json_object"] = "json_object",
    ) -> LLMResult:
        del temperature, response_format
        content = "\n".join(message.get("content", "") for message in messages).lower()
        payload = self._payload_for(content)
        return LLMResult(
            text=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            model=self.model,
        )

    def _payload_for(self, content: str) -> dict[str, object]:
        if '"task": "query_rewrite"' in content or "query_rewrite" in content or "改写" in content:
            return self._query_rewrite_payload(content)
        if '"task": "memory_summary"' in content or "memory_summary" in content:
            return self._memory_summary_payload(content)
        if '"task": "extraction"' in content or "extraction" in content:
            return self._extraction_payload()
        if '"task": "trace"' in content:
            return self._trace_payload(content)
        if '"task": "audit"' in content or "audit" in content:
            return self._audit_payload(content)
        if "extract" in content or "提取" in content:
            return self._extraction_payload()
        if "trace" in content or "追溯" in content or "跨日" in content or "t+1" in content:
            return self._trace_payload(content)
        return self._audit_payload(content)

    def _query_rewrite_payload(self, content: str) -> dict[str, object]:
        query = "规则检索"
        try:
            for line in reversed(content.splitlines()):
                payload = json.loads(line)
                if isinstance(payload, dict) and payload.get("task") == "query_rewrite":
                    query = str(payload.get("query") or query)
                    break
        except json.JSONDecodeError:
            pass
        return {"rewritten_query": f"{query} 对账 规则"}

    def _extraction_payload(self) -> dict[str, object]:
        return {
            "agent": "extraction",
            "standard_type": "REVERSAL",
            "original_flow_id": "FLOW-ORIGINAL-001",
            "cleaned_remark": "识别到冲正线索，待后续规则核验",
            "confidence": 0.92,
        }

    def _memory_summary_payload(self, content: str) -> dict[str, object]:
        flow_ids = sorted(set(re.findall(r"flow_id[=\": ]+([A-Z0-9\-]+)", content)))
        kept = " ".join(f"flow_id={flow_id}" for flow_id in flow_ids[:16])
        return {
            "summary_text": f"HIGH retained PENDING_HUMAN retained {kept}".strip()
        }

    def _trace_payload(self, content: str) -> dict[str, object]:
        if '"cutoff_t1_context": null' in content:
            return {
                "agent": "trace",
                "trace_found": False,
                "related_flow_ids": [],
                "trace_summary": "疑似跨日切，待 T+1 补齐",
                "confidence": 0.2,
            }
        if '"cutoff_t1_context"' in content:
            return {
                "agent": "trace",
                "trace_found": True,
                "related_flow_ids": ["FLOW-T1-001"],
                "trace_summary": "发现 T+1 已配对线索，核心次日补记已命中",
                "confidence": 0.9,
            }
        return {
            "agent": "trace",
            "trace_found": True,
            "related_flow_ids": ["FLOW-T1-001"],
            "trace_summary": "发现 T+1 追溯线索，建议人工核验关联流水",
            "confidence": 0.9,
        }

    def _audit_payload(self, content: str) -> dict[str, object]:
        reason = "Fake provider 返回固定审计结论，用于离线确定性测试"
        if '"related_flow_ids": []' in content:
            reason = "疑似跨日切，当前待 T+1 补齐后复核，建议先转人工跟进。"
        elif '"related_flow_ids": [' in content:
            reason = "发现 T+1 已配对线索，核心次日补记已命中，建议人工复核后平账。"
        if "be-r002" in content or "amount_mismatch" in content:
            reason = "银行端与企业端金额不一致，Fake provider 建议人工复核。"
        if (
            reason == "Fake provider 返回固定审计结论，用于离线确定性测试"
            and ("bc-r001" in content or "clearing_single_side" in content)
        ):
            reason = "清算单边异常，需结合来源流水与规则依据人工复核。"
        if reason == "Fake provider 返回固定审计结论，用于离线确定性测试" and (
            "bc-r003" in content
            or "cutoff_cross_day" in content
            or "跨日切" in content
            or "t+1" in content
        ):
            if '"related_flow_ids": []' in content or "待 t+1 补齐" in content:
                reason = "疑似跨日切，当前待 T+1 补齐后复核，建议先转人工跟进。"
            elif (
                '"related_flow_ids": [' in content
                or "t+1 已配对" in content
                or "flow-core-t1" in content
            ):
                reason = "发现 T+1 已配对线索，核心次日补记已命中，建议人工复核后平账。"
        return {
            "agent": "audit",
            "decision": "PENDING_HUMAN",
            "risk_level": "MEDIUM",
            "reason": reason,
            "ai_suggestion": "PENDING_HUMAN",
            "evidence": ["fake-rag-evidence"],
            "confidence": 0.88,
        }


class DeepSeekProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str = "https://api.deepseek.com",
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._client = client

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: Literal["text", "json_object"] = "json_object",
    ) -> LLMResult:
        if not self.api_key:
            raise LLMUnavailable("DeepSeek API key is not configured")

        try:
            request_kwargs: dict[str, object] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "stream": False,
            }
            if response_format == "json_object":
                request_kwargs["response_format"] = {"type": "json_object"}
            response = self._client_or_create().chat.completions.create(**request_kwargs)
        except Exception as exc:
            raise LLMUnavailable("DeepSeek request failed") from exc

        message = response.choices[0].message
        usage = getattr(response, "usage", None)
        return LLMResult(
            text=message.content or "",
            prompt_tokens=getattr(usage, "prompt_tokens", 0) if usage is not None else 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) if usage is not None else 0,
            model=self.model,
        )

    def _client_or_create(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except Exception as exc:
            raise LLMUnavailable("OpenAI SDK is not installed") from exc

        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=30.0,
        )
        return self._client


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    if settings.llm_provider == "deepseek":
        return DeepSeekProvider(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
            base_url=settings.deepseek_base_url,
        )
    raise LLMUnavailable(f"Unsupported LLM provider: {settings.llm_provider}")
