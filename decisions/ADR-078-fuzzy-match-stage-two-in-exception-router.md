# ADR-078: 模糊匹配作为 ExceptionRouter 的「阶段2」补齐三阶段匹配

**Stage**: stage-recon-hardening
**Status**: accepted
**Date**: 2026-06-22
**Slug**: `fuzzy-match-stage-two-in-exception-router`

## Context

架构 §2.3.1 定义三阶段匹配:阶段1 精确(flow_id + amount)、阶段2 模糊(amount 相等 ∧ trade_time.date() 相等 ∧ counterparty LIKE → 候选匹配)、阶段3 单边残留(Anti-Join)。实现里 `ExceptionRouter.classify` 的主循环是 `for flow_id in bank.keys() | clear.keys()`,**纯按 flow_id 配对**;全 `src/` 无任何模糊配对逻辑。结果只有阶段1 + 阶段3,**阶段2 缺失**。后果:flow_id 对不上的同一笔交易(企业 ERP 凭证号 ≠ 银行流水号,真实银企对账常态)被误判成两条单边(`BANK_UNARRIVED` + `BOOK_UNRECORDED`)。该缺口被 mock 数据掩盖(`generate_mvp1_mock_excel` 两侧共用 flow_id)。架构 §11「有意收敛」清单未列模糊匹配,故属隐性遗漏。

## Decision

采用在 `classify` 内新增「阶段2」二次配对:阶段1 精确(flow_id)后,对仍是单边残留的行,按 amount+date+对手方做跨 flow_id 二次配对;配上的标「候选匹配」,配不上的才是真单边。匹配键、歧义处理见 ADR-080;候选匹配的状态/类型见 ADR-079;下游 Agent 确认见 ADR-081。flow_id 命中仍走阶段1,银企既有行为零漂移,零回归以银企既有全量测试全绿为门禁(承 ADR-020)。

## Consequences

- 负向:`classify` 从「一轮 flow_id 遍历」变「精确→模糊→真单边」多遍,确定性层逻辑变重;新增「候选匹配」语义会波及规则集合、状态机、下游 Agent、台账与前端标签。
- 正向:三阶段匹配名副其实;真实(flow_id 不一致)数据下不再虚增双边单边。
- 必须同步补 mock 数据(flow_id 不一致但实质同一笔的样例),否则模糊匹配重蹈测试盲区 —— 作为 task DoD 强约束。

## Alternatives Considered

- **在 `reconciliation` 层新增独立模糊匹配 service**(匹配职责拆出 ExceptionRouter):职责更细分,但匹配逻辑分裂两处(flow_id 配对在 router、模糊配对在 service),与「三阶段匹配同属确定性层」的架构表述割裂,BranchResult 流转要重接。否决。
