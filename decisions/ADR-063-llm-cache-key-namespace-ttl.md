# ADR-063: 缓存键构成、命名空间与失效策略

- Status: Accepted (2026-06-20)
- Deciders: 用户(拍板), Claude Code(提案)
- Related: src/bank_reconciliation_agent/core/llm/cache.py(_cache_key), src/bank_reconciliation_agent/core/config.py(llm_cache_ttl_seconds), decisions/ADR-062(provider 层 memoization), decisions/ADR-050(emitter 泄漏教训 → 键须有生命周期)

## Context
承 ADR-062 选 provider 层 memoization。key 要稳定可复现、随 prompt 版本自动失效、且不能让 Redis 无界堆积(呼应 ADR-050 emitter 泄漏教训)。

## Options Considered
- **key 是否显式拼 `prompt_version`**:
  - 仅靠 system prompt 文本隐式带入(prompt 升版即换文本即换哈希)。Pros:无冗余、单一真相源;Cons:key 不含可读版本号。
  - 额外把 `prompt_version` 拼进 key。Pros:可读;Cons:与 messages 里的 prompt 文本重复,两处不一致时反而有歧义。
- **失效策略**:
  - 仅靠 prompt 文本变更自然失效(无 TTL)。Pros:命中率最高;Cons:键无界堆积,重蹈 ADR-059 follow-up 覆辙。
  - 加 TTL。Pros:防堆积;Cons:TTL 内 prompt 文件回滚到旧版会命中旧缓存(内容一致即应一致,可接受)。

## Decision
- key = `llmcache:v1:{sha256(model | temperature | response_format | messages_json)}`;**不单独拼 `prompt_version`**(system prompt 文本已在 messages 内,升版天然 miss)。
- key 前缀带 schema 版本 `v1`,将来键格式演进可整体失效不撞旧键。
- **加 TTL**:`settings.llm_cache_ttl_seconds`,默认 7 天(`604800`),防无界增长。

## Consequences
- 正面:prompt 升版自动 miss、无需手动清缓存;`v1` 前缀给键格式留演进余地;TTL 兜住堆积。
- 负面:TTL 内 prompt 回滚会命中旧版缓存(语义上内容一致即应一致,接受);7 天为拍脑袋初值,需按实际命中/容量调。
