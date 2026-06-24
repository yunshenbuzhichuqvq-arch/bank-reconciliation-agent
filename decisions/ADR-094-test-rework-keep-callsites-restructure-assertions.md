# ADR-094: 测试改造策略——保调用点,只改集合 / 计数 / 字面量断言

> 归档自 stage faker-mock-data(scratchpad 原编号 ADR-FK.5)。本 stage 决策归档为 ADR-090(FK.1)/091(FK.2)/092(FK.3)/093(FK.4)/094(FK.5);正文 `ADR-FK.x` 即同 stage 决策,对应 ADR-(089+x)。

**Slug**: `test-rework-keep-callsites-restructure-assertions`
**Status**: accepted
**Date**: 2026-06-24

### Context
~20 个测试 import 生成器 / `EXPECTED_BRANCHES`。重建后多数 call-site(取数据集 → 遍历异常子集断言分支)**不变**;但少数硬编码「数据集 == 全集 / `len == N` / `summary == 某字面量`」的断言,会因正常多数加入 + 摘要真实化而失效。

### Options Considered
- **A. 全量重写测试** — Cons: 回归面最大、丢失既有覆盖、易引入新错。
- **B. 保调用点、定向改断言(采纳)** — 「== 全集」改「异常子集 ⊆ 结果 且其余 `AUTO_FIXED`」;字面量摘要断言改结构 / 关系断言;计数按 `n_normal + 异常数`。**新增**:正常多数自动平账断言、异常计数断言、字段多样性守护(堵初版盲区)。Pros: 保留覆盖、改动定向可审。Cons: 须逐文件识别受影响断言。

### Decision
采用 **B**。受影响断言逐处改为结构 / 子集 / 计数断言;补正常平账 + 异常计数 + 多样性守护测试。

### Consequences
- 负向:需逐文件核对受影响断言,Codex 须在 Report Back 列出所有被改测试与改法。
- 正向:测试更贴业务语义、防形式修复、防多样性回归;调用点保稳定。

### 实现落地(TASK-FK.2/FK.3/FK.4)
受影响断言(`test_generate_mock_excel` / `test_mvp2a3_mock_fixtures` / `test_reconciliation_upload` / `test_mvp2b1~3_e2e` / `test_mvp2a3_clearing_e2e`)统一改为「子集 + 其余 `AUTO_FIXED` / 从 df 推导计数 / 字面量摘要→非空」,调用点保留。新增 `test_mock_batch_structure.py`(正常全 `AUTO_FIXED`、异常计数、`nunique > 1` 多样性、同 seed 确定性)。全套 385 passed / 4 skipped、`ruff` 干净。遗留一处非阻断 nit:`test_mvp2b3_checkpoint_e2e.py` 中 BANK_ENTERPRISE `auto_fixed_rows` 用魔法数 `13`(=12+1,值正确)而非符号常量,与紧邻 BANK_CLEARING 用 `DEFAULT_BANK_CLEARING_NORMAL_ROWS + 1` 风格不一致。
