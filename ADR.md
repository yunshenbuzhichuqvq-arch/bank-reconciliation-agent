# Stage recon-hardening — Architectural Decisions

> 范围:补齐「阶段一·最小闭环」声称完成、实则欠做的两处引擎核心能力 —— (A) 架构 §2.3.1 三阶段匹配缺失的「阶段2 模糊匹配」;(B) 架构 §3.3/§6.7「RAG 无据不判定」护栏在默认基础 RAG 路径失效。
> 本 stage 本地编号 ADR-RH.1~6,收尾归档时映射 `decisions/ADR-078~083`。
> 现状全部 `accepted`(用户已 review 拍板)。关键决策:本 stage 合并 Gap A+B(单 PR);候选匹配走 AuditAgent 确认;ADR-RH.5 采用方案 **B**(维度正交,L2 改置信驱动,修订 ADR-013)。
> 关联历史:ADR-015(场景参数化引擎)、ADR-016(清算单边/cutoff,「无依据转人工」红线)、ADR-020(分支→Agent 路由泛化、零回归门禁、`t1_candidate`→`trace_context` 透传 pattern)、ADR-022(硬约束 C1–C6)、ADR-024(DecisionHook vs Fallback 边界)、ADR-039(Agent 输出 schema 一致性)、ADR-007(三级 Fallback)、ADR-009/010(增强 RAG 轻量默认与分层开关)、ADR-013(representative_score / best_rag_score / rag_low_score 语义)、ADR-029(熔断 RAG-only)。

---

## ADR-RH.1: 模糊匹配作为 ExceptionRouter 的「阶段2」补齐三阶段匹配
**Slug**: `fuzzy-match-stage-two-in-exception-router`
**Status**: accepted
**Date**: 2026-06-22

### Context
架构 §2.3.1 定义三阶段匹配:阶段1 精确(flow_id + amount)、阶段2 模糊(amount 相等 ∧ trade_time.date() 相等 ∧ counterparty LIKE → 候选匹配)、阶段3 单边残留(Anti-Join)。实现里 `ExceptionRouter.classify` 的主循环是 `for flow_id in bank.keys() | clear.keys()`,**纯按 flow_id 配对**;全 `src/` 无任何模糊配对逻辑。结果只有阶段1 + 阶段3,**阶段2 缺失**。后果:flow_id 对不上的同一笔交易(企业 ERP 凭证号 ≠ 银行流水号,真实银企对账常态)被误判成两条单边(`BANK_UNARRIVED` + `BOOK_UNRECORDED`)。该缺口被 mock 数据掩盖(`generate_mvp1_mock_excel` 两侧共用 flow_id)。架构 §11「有意收敛」清单未列模糊匹配,故属隐性遗漏。

### Options Considered
- **A. 在 `classify` 内新增「阶段2」二次配对(采纳倾向)** — 阶段1 精确(flow_id)后,对仍是单边残留的行,按 amount+date+对手方做跨 flow_id 二次配对;配上的标「候选匹配」,配不上的才是真单边。
  - Pros:归属正确(确定性计算层,§2.3 职责);flow_id 命中仍走阶段1 → 银企既有行为零漂移(满足 ADR-020 零回归门禁);三阶段集中一处。
  - Cons:`classify` 从「一轮 flow_id 遍历」变「精确→模糊→真单边」多遍,复杂度上升;模糊配对是跨 flow_id 的,无法用现有「单 flow_id facts→规则」直接表达,需在遍历外新增配对阶段。
- **B. 在 `reconciliation` 层新增独立模糊匹配 service** — 匹配职责拆出 ExceptionRouter。
  - Pros:职责更细分。
  - Cons:匹配逻辑分裂两处(flow_id 配对在 router、模糊配对在 service),与「三阶段匹配同属确定性层」的架构表述割裂;BranchResult 流转要重接。

### Decision
采用 **A**:模糊匹配作为 `classify` 的阶段2,在精确配对与单边判定之间插入跨 flow_id 二次配对。匹配键、歧义处理见 ADR-RH.3;候选匹配的状态/类型见 ADR-RH.2;下游 Agent 确认见 ADR-RH.4。零回归以银企既有全量测试全绿为门禁(承 ADR-020)。

### Consequences
- 负向:`classify` 引入新配对阶段,确定性层逻辑变重;新增「候选匹配」语义会波及规则集合、状态机、下游 Agent、台账与前端标签。
- 正向:三阶段匹配名副其实;真实(flow_id 不一致)数据下不再虚增双边单边。
- 必须同步补 mock 数据(flow_id 不一致但实质同一笔的样例),否则模糊匹配重蹈测试盲区 —— 作为 task DoD 强约束。

---

## ADR-RH.2: 候选匹配的异常类型与状态语义
**Slug**: `fuzzy-candidate-error-type-and-status`
**Status**: accepted
**Date**: 2026-06-22

### Context
架构 §2.3.1 阶段2 产出「候选匹配 → 人工/Agent 确认」,这是一个**新的中间态**:既非「已精确平账」,也非「确定单边」,而是「疑似同一笔、待确认」。现有 `error_type` 集合(`AMOUNT_MISMATCH`/`BANK_UNARRIVED`/`BOOK_UNRECORDED`/`NARRATIVE_NAME_MISMATCH`/`DUPLICATE_BOOKING`)均不表达该语义;`_to_match_result` 现仅产 `AUTO_FIXED`/`PENDING_HUMAN` 两态,而 `_summarize_match_results` 却统计 `PENDING_AI`(该状态从未被产出 → **死统计,恒为 0**)。

### Options Considered
- **A. 新增 `error_type=FUZZY_MATCH_CANDIDATE` + 规则 `BE-R007`,状态走 `PENDING_AI`(采纳倾向)** — 候选匹配作为独立异常类型进入 Agent 审计,激活既有 `PENDING_AI` 统计。
  - Pros:语义清晰、可追溯、可计量;复用既已存在却悬空的 `PENDING_AI` 状态(顺带修死统计);与「规则优先、AI 补充」一致 —— 确定性层只标候选,判定交 Agent。
  - Cons:`error_type` 集合、规则 YAML、前端 `ERROR_TYPE_LABEL`、台账列语义、schema 需同步新增一项。
- **B. 复用 `AMOUNT_MISMATCH` / `NARRATIVE_NAME_MISMATCH`** — 不新增类型。
  - Cons:语义混淆 —— 那两类的前提是 flow_id 已精确匹配,而候选匹配恰是 flow_id 对不上;会污染既有异常分布统计与规则语义。

### Decision
采用 **A**:新增 `FUZZY_MATCH_CANDIDATE` 异常类型 + 对应银企规则,候选匹配状态为 `PENDING_AI`,进入 AuditAgent 确认(ADR-RH.4)。具体规则 ID/优先级、schema 字段、前端标签为实现细节,留 spec/tasks。

### Consequences
- 负向:新增异常类型牵动「规则 YAML + schema + 台账 + 前端标签」多处,需保持一致(承 AGENTS 红线:schema 双产物同步)。
- 正向:`PENDING_AI` 死统计被激活,看板「待 AI 处理」计数变真实;异常分布多一类可解释信号。

---

## ADR-RH.3: 模糊匹配键与一对多歧义处理
**Slug**: `fuzzy-match-key-and-ambiguity`
**Status**: accepted
**Date**: 2026-06-22

### Context
架构 §2.3.1 阶段2 键为 amount 相等 ∧ date 相等 ∧ `counterparty LIKE`。两侧对手方字段不同名(`_bank_party_column` / `_clear_party_column`,承 ADR-015/016 场景化列映射)。模糊配对可能一对多(同金额、同日、对手方近似的多笔),确定性层若强行 1:1 配对会赌错,污染下游。

### Options Considered
- **A. 一对多则全部标候选、不自动配对(采纳倾向)** — 唯一候选才配对;出现多候选时,涉及行全部标 `FUZZY_MATCH_CANDIDATE` 转下游,不在确定性层选「哪一笔配哪一笔」。
  - Pros:符合「金额/状态不交给不确定逻辑」「无依据转人工」红线(ADR-016);确定性层只做能确定的事。
  - Cons:多候选场景把判定压力转移给 Agent/人工,自动平账率略降(诚实代价)。
- **B. 确定性层按相似度评分取最优 1:1** — 贪心配对。
  - Cons:相似度阈值/打分本身引入不确定性,等于在确定性层做了「该交给 Agent 的语义判断」,违背 §2.3 边界;错配难追溯。

### Decision
采用 **A**:匹配键为 amount 相等 ∧ date 相等 ∧ 对手方 LIKE(复用现有场景化列映射);唯一候选才配对,一对多则全部标候选转 AuditAgent。LIKE 的具体归一化(掩码/子串口径)为实现细节,留 spec/tasks。

### Consequences
- 负向:多候选不自动配对 → 这类样本进 Agent/人工,自动化率不虚高(可接受、且诚实)。
- 正向:确定性层零误配,所有模糊判定可追溯到 Agent 决策与证据。

---

## ADR-RH.4: AuditAgent 候选匹配确认契约与回流语义
**Slug**: `audit-agent-fuzzy-candidate-confirmation`
**Status**: accepted
**Date**: 2026-06-22

### Context
规划问答已定:候选匹配走 AuditAgent 确认(而非直接转人工)。AuditAgent 现仅吃单笔异常 + RAG 证据,输出 `decision ∈ {AUTO_FIXED, PENDING_HUMAN, UNRESOLVED}`(ADR-039 schema、ADR-022 C1–C6)。候选确认是新任务:判「这两笔是否同一笔交易」,需让 Agent 看到**配对的另一笔**,并把确认结果回流到正确分支。ADR-020 已有可复用 pattern:BC-R003 把 `state.t1_candidate` 透传进 `trace_context` 驱动 Agent 叙述。

### Options Considered
- **A. 复用 ADR-020 透传 pattern,新增候选确认任务类型(采纳倾向)** — 模糊候选把「配对的另一笔」经 state 透传进 AuditAgent 的确认上下文;AuditAgent 输出确认/否决并回流。
  - Pros:复用既有编排与透传机制,无需新增 Agent;与 BC-R003 一脉相承,可解释。
  - Cons:AuditAgent prompt 需扩「候选确认」指令分支;state 与路由集合需登记新分支(承 ADR-020「路由集合是新真相源」约束)。
- **B. 新增独立 MatchConfirmAgent** — 专职候选确认。
  - Cons:违「主链路只 2 个 Agent」(架构 §2.4);编排复制,过度设计。

### Decision
采用 **A**。回流语义:确认同一笔且金额相等 → `AUTO_FIXED`(平账);确认同一笔但金额不等 → 转 `AMOUNT_MISMATCH` 分支处理;否决(非同一笔)→ 退回真单边(`BANK_UNARRIVED`/`BOOK_UNRECORDED`);Agent 低置信或无据 → `PENDING_HUMAN`(承 ADR-022 C2「无据不判定」与 ADR-RH.5 护栏)。候选确认须带 evidence(对齐 §3.3)。prompt 文案、state 字段名、路由集合登记为实现细节,留 spec/tasks。

### Consequences
- 负向:AuditAgent 承担第二种任务,prompt 复杂度上升,需版本化(承 ADR-008 prompt 版本管理)与 schema 一致性测试(ADR-039)。
- 正向:模糊候选的判定有 RAG 依据、有置信度、可追溯,直接展示「规则确定性 + AI 语义判断」边界这一核心信号。
- 候选确认回流到 `AMOUNT_MISMATCH` 时会复用既有审计链路,需保证不产生二次 fallback 循环(实现期验证)。

---

## ADR-RH.5: RAG「无据地板」与「弱据 fallback 阈值」分层 —— 接回 §6.7 护栏并厘清与 ADR-007/013 的冲突
**Slug**: `rag-no-evidence-floor-vs-fallback-threshold`
**Status**: accepted
**Date**: 2026-06-22

### Context
架构 §3.3/§6.7 规定:相似度低于阈值(Dense<0.5 ∧ Reranker<0.3)= 无据 → AuditAgent 必须 `PENDING_HUMAN`,且**不触发 Fallback**。但实现存在两条方向相反的低分路径:
1. retriever `_passes_threshold` 过滤 —— 主链路 `workflow.py:397` 硬传 `min_score=0.0`,且 `enable_rag_reranker` 默认 `False`,dense 分支阈值实为 0;config 的 `rag_dense_min_score=0.5` 定义了却未在主链路使用。
2. `fallback.l1_requires_l2` = `confidence<0.85 OR best_rag_score<rag_low_score(0.5)` —— 承 ADR-007/013,**RAG 低分触发 L1→L2 few-shot 补救**。

现状:`min_score=0` 使低分 hit 不被过滤、进入 `rag_items`;`rag_items` 非空 → 不走 `not rag_items` 的人工闸,转而被 `l1_requires_l2` 的 `score<0.5` 命中走 L2 fallback。**结果:§6.7「无据→人工、不 fallback」被 ADR-007/013「低分→fallback」覆盖,「无据不判定」护栏在默认基础 RAG 路径形同虚设**(hash 伪嵌入下检索几乎总能返回非零分 chunk,无命中仅在结果完全为空时触发)。核实:hash 嵌入为 128 维 sha256 分桶 + L2 归一化,`score=1/(1+距离)`,字面重合≈1.0、正交≈0.33,故 0.5 地板在 hash 下**确能过滤**字面不相关项 —— 接回阈值是真修复,非形式主义。

### Options Considered
- **A. 双阈值分层(floor < low_score)** — 引入「无据地板 floor」作 retriever `min_score`(主链路),与「弱据 fallback 阈值 `rag_low_score=0.5`」分层。`score<floor`→无据→`PENDING_HUMAN`;`floor≤score<low_score`→弱据→L2(ADR-007);`score≥low_score`→L1。
  - Pros:§6.7 与 ADR-007 共存、语义层次最清晰、保留 RAG 弱分触发 L2。
  - Cons:需新增并校准一个 floor 阈值;架构 §6.7「Dense<0.5」判据须改为「<floor」对齐文档(走 main 文档对齐批次)。
- **B. 维度正交:RAG 分数管「有据」、Agent 置信管「准度」(采纳倾向)** — retriever `min_score` 接回 0.5 地板(复用 `rag_dense_min_score`);低分 hit 被过滤,全过滤则 `rag_items` 空 → 现有 `not rag_items` → `PENDING_HUMAN`(§6.7);**L2 触发改为仅 `confidence<0.85`**,从 `l1_requires_l2` 移除 `score<low_score` 分支。
  - Pros:语义最干净正交(分数=有没有据→人工;置信=判得准不准→L2/L3);§6.7 护栏优先;不需新阈值。
  - Cons:**修订 ADR-013**(`l1_requires_l2` 低分语义,旧条目部分 superseded);L2 不再被 RAG 弱分单独触发,属行为变化,须零回归评估(few-shot 仍由低置信触发,机制不废)。
- **C. 维持现状 + 改文档** — 承认「低分→L2」既定行为,改架构 §6.7 去掉「无据不 fallback」。
  - Pros:不改代码、不动 ADR-007/013。
  - Cons:削弱「无据不判定」核心护栏(§3.3),与本 stage 初衷相悖。**不推荐**。

### Decision
采用 **B**(用户拍板):RAG 分数只判「有没有据」—— retriever 工作流主链路 `min_score` 接回 `rag_dense_min_score`(0.5),低于地板的 hit 被过滤;过滤后为空 → 现有 `not rag_items` 路径 → `PENDING_HUMAN`(§6.7,不触发 fallback)。L2 fallback 触发改为**仅 `confidence < CONFIDENCE_THRESHOLD(0.85)`** —— 即从 `l1_requires_l2` 移除 `best_rag_score < rag_low_score` 分支。此举**修订 ADR-013**:其 `l1_requires_l2` 的「RAG 低分触发 L2」语义部分 superseded(fallback 状态机结构与 L2/L3 链不变,仅触发条件由「分数+置信」收敛为「置信」)。`best_rag_score` 因此 orphan,随之删除;`rag_low_score` 在 `scripts/eval_rag.py` 的 `triggers_l1_to_l2` 口径同步更新。retriever 调试 API(`/rag/search`)保留传 `min_score=0` 看全部的能力,仅工作流主链路用配置阈值。阈值比较对齐 §6.7「<地板 无据」语义(即 `>=` 地板)。

**地板值校准(2026-06-22 修订,实测驱动)**:实测 hash 占位嵌入(`HashEmbeddingFunction`)下**正确命中规则分数仅 0.35–0.43、正交基线≈0.33**,架构 §6.7 的 0.5 是**真实语义嵌入口径**,直接套用会误杀全部有据、使主链路一概转人工(SSE `_has_readable_decision_and_evidence` 断言已正确暴露该退化)。故 `rag_dense_min_score` 默认值由 0.5 **校准**到 hash 嵌入实际判别值(有据最低分与正交基线之间,约 0.34,RH.6 评测兜底),0.5 留作真实嵌入参考。**不改 SSE 断言**(校准后有据场景 evidence 非空自然通过;改断言去接受空 evidence 等于掩盖「全转人工」退化,已否决)。

### Consequences
- 负向:触及 ADR-007/013 的 fallback 触发逻辑,属跨 ADR 演进,须 superseded 标注 + 全量回归。
- 负向(嵌入局限,实测暴露):hash 占位嵌入(MVP-0 避免下载模型的实现)无语义、分数压在 0.33–0.43 窄带,「无据地板」区分度有限,只能挡近正交的完全无关,无法干净区分「弱相关」与「无关」。**完整语义级「无据不判定」依赖真实嵌入(增强 RAG,ADR-009 默认关)**;本 stage 在默认基础 RAG 上做到「接回机制 + 校准地板挡完全无关 + 评测兜底」,并诚实记录此边界。
- 正向:「无据不判定」在默认路径从「形同虚设(min_score=0,hash 伪嵌入几乎总返回非零分)」恢复为「挡完全无关」;§6.7 与 ADR-007/013 的低分语义冲突被显式厘清。
- 阈值有效性与校准值以 ADR-RH.6 评测兜底。

---

## ADR-RH.6: 阈值校准与防形式修复的验收口径
**Slug**: `rag-threshold-calibration-and-eval-gate`
**Status**: rejected (deferred to future stage)
**Date**: 2026-06-22 (rejected 2026-06-23)

> **移出本 stage(用户拍板 2026-06-23)**:RAG 评测集与对账模拟数据均未定稿,在临时数据上锁定硬召回闸(0.64/0.93)属「流沙钉门柱」。本 stage 不带自动 recall 闸;待语料 + 测试模拟数据定稿后,单独 stage 引入闸并校准 dense/hybrid 口径。floor + L2 fallback(RH.5/ADR-082)作为 Gap B 运行时护栏保留。rejected 不归档 decisions/。

### Context
ADR-RH.5 接回 0.5 地板,但在 hash 伪嵌入 + 现有 corpus 上,0.5 是否「既不误杀有据(Recall 不掉)、又能挡无关(无据触发人工)」需用真实评测兜底,否则可能形式正确而效果失真(ADR-013 已警示轻量分数需校准)。项目已有 `scripts/eval_rag.py` + RAG 评测集(承 ADR-034/038、V1-1 eval)。

### Options Considered
- **A. 以现有评测集 + 新增无据/弱据用例作为 DoD 闸(采纳倾向)** — 复用 `eval_rag.py` 验 Recall@5 不回归;新增「无关 query → 无命中 → PENDING_HUMAN」用例;新增「弱据仍能触发 L2(选 A)/低置信仍触发 L2(选 B)」回归用例,防 floor 误杀 fallback。
  - Pros:用可测指标兜住护栏有效性;复用既有评测资产。
  - Cons:需补少量评测样本与用例。
- **B. 仅人工抽样核对** — 不入自动化。
  - Cons:不可复跑、易回归,违 DoD「可复制运行」。

### Decision
采用 **A**:阈值变更的 DoD 必须含 `uv run python -m scripts.eval_rag`(或等价)Recall@5 不回归 + 无据→人工用例 + fallback 未被 floor 误杀的回归用例。阈值取值若经评测需微调,在实现期回填本 ADR。

### Consequences
- 负向:评测样本与用例需新增维护。
- 正向:Gap B 的修复有量化验收,杜绝「接了阈值但实际无过滤/或误杀 fallback」两类形式修复。

---

## ADR-RH.7: 召回评测闸以 hybrid 检索为口径,诚实记录默认 dense-only 召回限制(修订 RH.6/ADR-083)
**Slug**: `rag-eval-gate-hybrid-measurement`
**Status**: rejected (moot — gate deferred with RH.6)
**Date**: 2026-06-23

> **随 RH.6 一并移出本 stage**:本决策(召回闸以 hybrid 为口径)依附于召回闸;闸既已移出,本条作废。dense/hybrid 口径之争留待未来 stage 连同闸一起定。实测留痕:当前语料下银企 dense-only recall@5=0.5667、hybrid=0.7417;清算 dense=0.9333、hybrid=0.9583(120 例临时评测集,2026-06-23)。rejected 不归档 decisions/。

### Context
RH.8 修复「扩库(236bf90)导致银企 Recall@5 回归」时,实际改动是给评测主路径 `eval_rag._evaluate_case` 加 `enable_hybrid=True`(一行),把召回闸的检索口径从 **dense-only 改为 hybrid(BM25+RRF)**,数字从 0.5667 恢复到 0.7417;**未改 dense-only 排序本身**。而生产 workflow 主链路 `_retrieve_rag_response` 仍 `enable_hybrid=settings.enable_rag_hybrid`(默认 `False`,承 ADR-009/010 增强 RAG 默认关)=dense-only。Mode E 审查发现:**召回闸量的路径(hybrid)≠ 线上默认跑的路径(dense-only)**;扩库导致的 dense-only 召回回归既没修、也不再被闸测量。这与 RH.6/ADR-083「评测兜底默认基础 RAG 路径」的隐含前提脱钩,属「不改基线数值、但换量法」的潜在挪门柱。用户拍板:**接受闸以 hybrid 为口径,但走 Mode D 合法化 + 诚实记录默认路径限制**,而非默许一行静默翻 flag。

### Options Considered
- **A. 退回真修 dense-only** — 闸恢复测 dense-only,并真正把 dense-only 银企 Recall 修到 ≥0.64(改分块/去重/top-k 或回退扩库)。
  - Pros:闸测的就是线上跑的,ADR-083 反形式语义最纯。
  - Cons:hash 占位嵌入无语义,dense-only 召回受限是 ADR-082 已记的结构性局限,纯靠语料工程未必稳定够到 0.64;可能反复。
- **B. 接受闸测 hybrid + Mode D 合法化(采纳,用户拍板)** — 显式声明召回闸以 hybrid 为口径,诚实记录默认 dense-only 召回更低且不被该闸覆盖,说明为何可接受。
  - Pros:hybrid 反映检索栈在正确配置下的真实质量,把「检索栈回归」与「hash 嵌入无语义」两件事解耦,闸不再被 hash 噪声干扰;决策与限制留痕、不掩盖。
  - Cons:**召回闸不再认证线上默认路径**;默认 dense-only 的真实召回回归可能不被该闸抓到,须靠其他护栏(无据地板 + Agent 置信 + 人工)兜安全。
- **C. 生产默认开 hybrid** — `enable_rag_hybrid=True` 让线上与 eval 对齐。
  - Cons:运行时架构变更,与 ADR-009/010「增强 RAG 轻量默认关」冲突,需性能/成本评估;超本 stage 收尾范围。

### Decision
采用 **B**。明确:
1. **召回闸口径**:`eval_rag` 的 Recall@5 闸(ADR-083 的 `assert_recall_baselines`)以 **hybrid(BM25+RRF)** 检索为口径,衡量的是**检索栈在 hybrid 配置下的排序质量不回归**,而非线上默认 dense-only 路径的召回。基线 0.64/0.93 不下调(RH.8 已守)。
2. **诚实记录的限制**:线上默认配置(`enable_rag_hybrid=False` + hash 占位嵌入)下,银企 dense-only Recall@5 在扩库后约 0.5667,**低于闸值、且不被该闸覆盖**。读 PR/eval 数字须按「hybrid 口径」理解,不能当作默认路径的召回保证。
3. **为何可接受**:(a) 默认路径的安全由**无据地板(ADR-082)+ C2「无据不判定」+ Agent 置信 + 人工复核**兜底——弱召回更多走 `PENDING_HUMAN`,而非错误自动平账;(b) 残余风险(低召回下高分错 chunk 越过地板 → 取到错证据)由 Agent 置信与人工 PENDING 复核约束,显式承认;(c) 默认路径的真实召回提升依赖真实嵌入(ADR-009 增强 RAG)或开启 hybrid,列为 follow-up。

### Consequences
- 负向:召回闸与线上默认路径解耦——默认 dense-only 的真实召回回归**可能通过该闸而不被发现**;质量监控对默认路径出现盲区,须在文档/PR 显式标注口径。
- 负向:残余「错证据」风险(见 Decision 3b)依赖下游 Agent/人工,不由检索闸消除。
- 正向:闸不再被 hash 占位嵌入的无语义噪声干扰,稳定衡量检索栈质量;RH.8 的实现被合法化为本决策的落地,而非隐性挪门柱;限制与残余风险留痕可追溯。
- Follow-up:真实嵌入接入 / 评估默认开 hybrid(走独立 ADR);可考虑补一条 dense-only 召回的**观测指标(非闸)**,让默认路径回归可见但不阻断。
