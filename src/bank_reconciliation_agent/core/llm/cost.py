from decimal import Decimal


TOKENS_PER_MILLION = Decimal("1000000")
DEEPSEEK_V4_PRO_INPUT_CACHE_MISS_USD_PER_1M = Decimal("0.435")
DEEPSEEK_V4_PRO_OUTPUT_USD_PER_1M = Decimal("0.87")


def compute_cost(prompt_tokens: int, completion_tokens: int) -> Decimal:
    prompt_cost = (
        Decimal(prompt_tokens) * DEEPSEEK_V4_PRO_INPUT_CACHE_MISS_USD_PER_1M
    ) / TOKENS_PER_MILLION
    completion_cost = (
        Decimal(completion_tokens) * DEEPSEEK_V4_PRO_OUTPUT_USD_PER_1M
    ) / TOKENS_PER_MILLION
    return prompt_cost + completion_cost
