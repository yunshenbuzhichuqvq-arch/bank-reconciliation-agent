# ADR-017: 跨日切(CUTOFF_CROSS_DAY)T+1 主动追溯机制

- Status: Accepted (2026-06-09)
- Deciders: 用户(确认:Option A + T+1 主动追溯), Claude Code(提案)
- Related: services/exception_router.py(in_cutoff_window / _find_t1_candidate), services/workflow.py, agents/trace_agent.py, core/config.py(cutoff_window), requirements-analysis.md §3.3, overall-architecture.md §5.2(BC-R003), decisions/ADR-007

## Context

需求 §3.3:跨系统日切时间不同导致当天看似单边、次日补齐,「需识别时间窗口并追溯 T+1 流水」。架构 §5.2 BC-R003:交易时间在日切窗口(22:00–24:00)→ `CUTOFF_CROSS_DAY` → TraceAgent T+1 追溯。用户已选「T+1 主动追溯」(非仅打标)。需定:(1)日切窗口判定;(2)T+1 配对数据来源与匹配键;(3)TraceAgent 角色与 Fallback 衔接。

## Options(核心子决策:T+1 数据来源)

- **A. 单次上传内跨多日(采纳)** — 上传的清算/核心数据本身含 T 与 T+1 行;对「清算端单边且 `trade_time ∈ 日切窗口」者,在已传 Source A(核心)内按 [金额相等 + 单号一致 + 核心记账日 = T+1] 找候选,命中则从 `CLEARING_SINGLE_SIDE` 重判为 `CUTOFF_CROSS_DAY`(已配对)。Pros: 不破坏单次上传模型;mock 单文件即可表达;确定性候选 + Agent 解释,可单测。Cons: 要求 mock 含跨日切样本且两侧单号贯通;匹配质量依赖单号字段。
- **B. 独立 T+1 上传(第二批文件/任务)** — 次日单独上传再跨任务追溯。Pros: 最贴近真实跨日切操作。Cons: 多任务编排 + 跨任务数据模型,明显超最小闭环。

## Decision

采 **A**(用户已确认)。判定与角色固定如下:

- 新增 fact `in_cutoff_window` = 清算端 `trade_time` 落 `[22:00, 24:00)`;日切窗口阈值入 `config`(`settings.cutoff_window`,默认 `22:00-24:00`,可调)。
- 命中窗口的清算端单边 → BC-R003。**T+1 候选匹配为确定性预处理**(在 `exception_router` 层完成),匹配键 = 金额相等(Decimal)+ 单号一致(`reference_no`/`merchant_order_no`/`voucher_no` 任一贯通)+ 对侧核心记账日 = T+1,数据域限本次上传的 Source A。命中候选随 `BranchResult.t1_candidate` 携带。
- BC-R003 纳入 workflow `TRACE_BRANCHES`(承 ADR-020),**TraceAgent 负责 T+1 追溯并产出叙述与置信度证据**(承 ADR-007 三级 Fallback):候选命中 → 「T+1 已配对/可平」;无候选 → BC-R003 仍成立,给出「疑似跨日切、待 T+1 补齐」结论并转人工。

## Consequences

- 负向:匹配键依赖两侧单号可关联;若数据单号不通,T+1 追溯命中率下降(BC-R003 仍判定,处置退化为「待补齐→人工」)。mock 须固定单号贯通约定。
- 这是本 stage **唯一实质新增业务逻辑**(时间窗口 fact + T+1 候选预处理),非纯配置。
- `config` 增日切窗口项;窗口边界可单测(21:59 / 22:00 / 23:59 / 00:00);`24:00` 归一化为 `00:00` 并按跨午夜时刻比较。
