# ADR-093: scenario 参数化的批次生成器 + 规模可配

> 归档自 stage faker-mock-data(scratchpad 原编号 ADR-FK.4)。本 stage 决策归档为 ADR-090(FK.1)/091(FK.2)/092(FK.3)/093(FK.4)/094(FK.5);正文 `ADR-FK.x` 即同 stage 决策,对应 ADR-(089+x)。

**Slug**: `scenario-parameterized-batch-generator`
**Status**: accepted
**Date**: 2026-06-24

### Context
现有三个生成器(legacy 银企 / mvp1 银企 / mvp2a3 清算)各自硬编码全部行。重建应共享一套「批次核心」,按 scenario 决定字段映射 / 异常集 / 摘要档,承 ADR-015(单场景引擎 Source A/B 抽象)、ADR-019(列契约 `BANK/CLEAR_REQUIRED_COLUMNS` 复用,不引 scenario-keyed 校验)。

### Options Considered
- **A. 三个生成器各自全量重写** — Cons: 批次 / 平账 / 注入逻辑重复三份,易漂移。
- **B. 共享批次核心 + scenario 参数 + 三个生成器为薄包装(采纳)** — 单一批次逻辑;`bank_enterprise` / `bank_clearing` 决定字段、异常集、摘要;保留三个对外签名 → call-site 不动。Pros: 逻辑单点;承既有场景抽象;churn 受控。Cons: 须把场景差异抽成参数。
- **规模**:`n_normal` 参数化(默认每场景 ~50 正常 + 既有异常集);测试传小值、demo 传大值 → 真实感与测试速度解耦。

### Decision
采用 **B** + `n_normal` 参数化。faker 依赖(dev/`zh_CN`)保留,用于实体字段生成。列契约 / 函数签名不变(承 ADR-019)。

### Consequences
- 负向:批次核心需吸收三场景差异,初次抽象有成本。
- 正向:单点维护;新增场景只加参数;测试与 demo 共用一套、规模解耦。

### 实现落地(TASK-FK.2/FK.3)
`build_batch(scenario, *, n_normal, seed, flow_prefix)` 为共享核心,按 `scenario in {bank_enterprise, bank_clearing}` 分发,非法 scenario `raise ValueError`。三个生成器为薄包装(legacy `flow_prefix="F1"`、mvp1 `flow_prefix="F"` 且保留 `include_fuzzy_sample`、mvp2a3 `scenario="bank_clearing"`)。`n_normal` 默认 12;测试按需传小值(如 `n_normal=3`)。落地中默认值取 12 而非 ADR 草案的 ~50,属规模微调、不影响结构契约。
