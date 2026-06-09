# ADR-015: scenario_type 参数化接入对账引擎(最小参数化)

- Status: Accepted (2026-06-09)
- Deciders: 用户(拍板:Option A), Claude Code(提案)
- Related: api/v1/reconcile.py, services/reconciliation.py, services/exception_router.py, services/rule_engine.py, services/workflow.py, services/task.py, services/queue.py, services/ledger.py, overall-architecture.md §5.3, decisions/ADR-012

## Context

现状对账引擎单场景硬编码:`reconciliation.upload()` 不收 scenario,`scenario_type` 写死 `"BANK_ENTERPRISE"`;列校验写死 `BANK_REQUIRED_COLUMNS` / `CLEAR_REQUIRED_COLUMNS`;`rule_engine` 模块单例写死 `rules/bank_enterprise.yaml`。但 DB/RAG 管线已具 scenario 维度(`ReconciliationState.scenario_type`、retriever 按 scenario 选 collection,2a-2 ADR-012 铺好)。2a-3 引入第二场景 `BANK_CLEARING`,必须让 scenario 从 API 贯穿到 workflow。架构 §5.3 要求「PreCheckNode 按 `scenario_type` 选规则库与异常分支集合;引擎只认 Source A/B」。

注:代码内 `bank`/`clear` 命名与架构 `Source A`/`Source B` 抽象错位(CLAUDE.md §3.8 点名「曾炸 17 文件冲突」的方向分歧)。

## Options

- **A. 最小参数化(采纳)** — scenario_type 作为 upload 入参贯穿 `upload→match→workflow`;列校验/规则库/mock/RAG 按 scenario 注册分发;缺省 `BANK_ENTERPRISE` → 银企零回归;保留 `bank`/`clear` 内部命名作为技术债。Pros: 改动收敛、零回归、可逆、对齐架构「按场景分发」。Cons: `bank/clear ↔ A/B` 命名错位债务延续,易误读(尤其 present_side 方向)。
- **B. 并行清算路径** — 独立清算分类器/编排,银企链路一行不动。Pros: 银企回归风险最低。Cons: 逻辑重复、把双轨分歧固化在代码、背离「通用引擎」愿景。
- **C. 彻底 Source A/B 重构** — `bank/clear` 全量重命名为 `source_a/source_b`。Pros: 最干净、最贴架构。Cons: 爆炸半径最大、回归风险高,对「副链路最小闭环」明显过度。

## Decision

采用 **A**(用户拍板)。scenario_type 从 API/service 入参贯穿;按 scenario 分发规则文件路径、RAG 知识/collection、mock;**列校验复用现有列契约**(清算端列集已含 settlement_date/单号等 T+1 字段,见 ADR-019);缺省 `BANK_ENTERPRISE`。`bank/clear` 内部命名本 stage **不重命名**,登记为技术债;以 `A/B ↔ bank/clear ↔ 核心/清算端` 映射 + 代码注释缓解(见 `rules/bank_clearing.yaml`、`exception_router._present_side` 注释)。

## Consequences

- 负向:命名错位继续存在;清算端单边在引擎里是 `present_side == "A"`(清算端=clear_row=B 侧存在、核心=bank_row=A 侧缺失,经 `_present_side` 反转),易误判,以映射表 + 代码注释显式化(stage 收尾补注释,见 review 2a3.9)。
- API 契约新增 `scenario_type`(可选,默认 `BANK_ENTERPRISE`);本 stage 仅后端贯穿,前端场景切换留后。
- 需改 reconciliation / exception_router / rule_engine / workflow 数处,但无大规模重命名。
