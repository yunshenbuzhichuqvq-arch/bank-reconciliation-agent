# ADR-019: 清算 mock 数据与 scenario-keyed 列校验(复用现有列契约)

- Status: Accepted (2026-06-09)
- Deciders: 用户(确认), Claude Code(提案)
- Related: scripts/generate_mock_excel.py(generate_mvp2a3_mock_excel / BANK_CLEARING_EXPECTED_BRANCHES), services/reconciliation.py(列校验), services/transactions.py(trade_time 归一化), mock_data/mvp2a3_core.xlsx, mock_data/mvp2a3_clearing.xlsx, decisions/ADR-015, decisions/ADR-017

## Context

`reconciliation` 列校验写死 `BANK_REQUIRED_COLUMNS`(银行流水字段)/ `CLEAR_REQUIRED_COLUMNS`(清算字段),为单场景设计。清算场景 Source A=银行核心(`CORE_LEDGER`)、Source B=清算端/通道(`CLEARING_FILE`/`CHANNEL_FILE`),字段集与银企不同(需 `settlement_date`、跨日切单号键等)。`mock_data/` 现有 xlsx 服务银企 demo。2a-3 需清算端到端样本(清算单边 + 跨日切)。

## Options

- **A. 复用现有列契约 + 仅交付清算 mock 生成器(采纳)** — 清算 A 侧(核心)复用 `BANK_REQUIRED_COLUMNS`、B 侧(清算端)复用 `CLEAR_REQUIRED_COLUMNS`(经核对已含 `trade_date`/`trade_time`/`settlement_date`/`reference_no`/`merchant_order_no`/`voucher_no` 等 T+1 所需字段);本 stage 仅新增清算 mock 生成器 + fixtures + `EXPECTED_BRANCHES`。Pros: 列校验零改动=回归面最小;最少代码;清算端列天然适配跨日切键。Cons: 沿用 `bank/clear` 命名错位(技术债,承 ADR-015);未来清算若需独有列再引注册表。
- **B. scenario-keyed 列校验注册表** — 为清算单独定义列必填集并按 scenario 分发。Pros: 语义更清晰、可演进。Cons: 改动列校验路径有回归面;现有清算端列已够用,属过度设计(YAGNI)。
- **C. 不造 mock、仅单测桩** — Cons: 无端到端可演示样本,违 PRD 可演示要求。

## Decision

采用 **A**。清算复用现有列契约(`bank_file`→`BANK_REQUIRED_COLUMNS`=核心 A;`clear_file`→`CLEAR_REQUIRED_COLUMNS`=清算端 B),**不引入 scenario-keyed 列校验**。本 stage 仅交付:`scripts/generate_mock_excel.py` 增清算 mock 生成(核心×清算端),含 BC-R001 单边 + BC-R003 跨日切(有候选 / 无候选)+ 正常配平 / 自动平账 fixtures,固定 `BANK_CLEARING_EXPECTED_BRANCHES`(承 ADR-017 单号贯通约定)。

## Consequences

- 负向:沿用 `bank/clear` 列命名错位(技术债,承 ADR-015);清算样本须人工设计两侧单号贯通以支撑 T+1 候选匹配(承 ADR-017)。
- 列校验零改动,银企/清算共用同一契约,回归面最小。
- 清算 `trade_time` 为裸时刻串(`HH:MM`),持久化时 `transactions._to_datetime` 借 `trade_date`(`date_hint`)补全为 datetime;银企的完整 datetime 串走原路径不受影响(stage 收尾补直测,见 review 2a3.10)。本 stage 无 DDL 变更。
- 提供清算端到端固定样本,集成测试与本地演示复用。
