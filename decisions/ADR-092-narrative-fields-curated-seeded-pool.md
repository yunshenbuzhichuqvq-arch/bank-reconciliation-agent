# ADR-092: 叙述字段(摘要 / 附言 / remark)真实化 = 人工策划 seeded 三档池

> 归档自 stage faker-mock-data(scratchpad 原编号 ADR-FK.3)。本 stage 决策归档为 ADR-090(FK.1)/091(FK.2)/092(FK.3)/093(FK.4)/094(FK.5);正文 `ADR-FK.x` 即同 stage 决策,对应 ADR-(089+x)。

**Slug**: `narrative-fields-curated-seeded-pool`
**Status**: accepted(replaces 初版 FK.3 的「faker 依赖 + 白名单」)
**Date**: 2026-06-24

### Context
摘要 / 附言是自由文本,正是确定性规则啃不动、**必须 LLM 上场**的地方(模糊摘要结构化、对手方与用途的语义判断,PRD §3.2;BE-R004 名称 / 叙述不符)。模板化摘要(现状 `remark="MVP-1 自动平账样例"`)会把 LLM 价值藏起来。纯 Faker 文本是无意义中文,给不了金融语义。

### Options Considered
- **A. 纯 Faker text** — Cons: 无意义、非金融语义,达不到目的。
- **B. LLM 生成摘要** — Pros: 最真实。Cons: 数据生成引入 LLM 成本 + 不确定性,违可复现;过度。
- **C. 人工策划 seeded 三档摘要池 + Faker 填实体(采纳)** — 三档:正式规范 / 口语化 / 歧义缺信息。Pros: 领域真实、可复现、零运行成本;异常案例配歧义档,逼出 LLM 推理价值。Cons: 维护一份语料。

### Decision
采用 **C**。正常行从正式 / 口语档采样;异常行(尤其 NARRATIVE_NAME_MISMATCH)配歧义 / 口语摘要,与注入异常对齐。实体字段(公司名 / 账号 / 银行名)仍由 Faker 生成。

### Consequences
- 负向:新增一份策划摘要语料需维护。
- 正向:摘要真实多样、含口语与歧义,demo 中 LLM 的「读懂模糊叙述」价值可见。

### 实现落地(TASK-FK.1)
新增 `scripts/mock_narratives.py`:`FORMAL` / `COLLOQUIAL` / `AMBIGUOUS` 三组语料(各 10 条)+ `sample_narrative(tier, faker)`,确定性受传入 faker 实例 seed 控制。生成器正常行按 `index % 2` 在正式/口语档间采样,异常行(F2003/F2006/F2007/F2008、CORE3003 等)配歧义档。单测 `test_mock_narratives.py` 守三档量达标、采样属对应档、同 seed 可复现。
