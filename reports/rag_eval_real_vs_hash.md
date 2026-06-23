# RAG Real Embedding vs Hash Evaluation

## Scope

- Eval set: `data/rag_eval_set.json`
- Cases: 120 total, with 60 bank-enterprise cases and 60 bank-clearing cases.
- Evaluation口径: `min_score=0.0`, measuring ranking quality only.
- Gate policy: report only. No recall hard gate was added.
- Labeling rule: expected chunks were assigned from query-to-chunk content relevance only; retrieval outputs were not used to choose labels.

## Commands Run

```bash
uv run python -m scripts.eval_rag --embedding-backend hash --report reports/rag_eval.md --json-report reports/rag_eval_metrics.json
uv run python -m scripts.eval_rag --embedding-backend bge_m3 --report reports/rag_eval_bge_m3.md --json-report reports/rag_eval_bge_m3_metrics.json
uv run python -m scripts.eval_rag --embedding-backend bge_small --report reports/rag_eval_bge_small.md --json-report reports/rag_eval_bge_small_metrics.json
uv run pytest -m embedding_real -v
```

## Ranking Metrics

| Backend | Scenario | Cases | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| hash | BANK_CLEARING | 60 | 0.2000 | 0.4500 | 0.3106 | 0.3283 |
| hash | BANK_ENTERPRISE | 60 | 0.1333 | 0.3250 | 0.2394 | 0.2365 |
| hash | weighted total | 120 | 0.1667 | 0.3875 | 0.2750 | 0.2824 |
| bge_m3 | BANK_CLEARING | 60 | 0.4000 | 0.7167 | 0.5686 | 0.5788 |
| bge_m3 | BANK_ENTERPRISE | 60 | 0.6167 | 0.7500 | 0.7011 | 0.6754 |
| bge_m3 | weighted total | 120 | 0.5083 | 0.7333 | 0.6349 | 0.6271 |
| bge_small | BANK_CLEARING | 60 | 0.5167 | 0.7000 | 0.6394 | 0.6119 |
| bge_small | BANK_ENTERPRISE | 60 | 0.5667 | 0.6333 | 0.6383 | 0.5970 |
| bge_small | weighted total | 120 | 0.5417 | 0.6667 | 0.6389 | 0.6045 |

## Comparison Notes

- bge-m3 beats hash on weighted Hit@1, Recall@5, MRR, and NDCG@5 after semantic relabeling.
- bge-small also beats hash on all weighted metrics; it is slightly higher on Hit@1/MRR, while bge-m3 is higher on Recall@5/NDCG@5.
- Recall@5 is not saturated: hash 0.3875, bge-m3 0.7333, bge-small 0.6667.

## Dense Floor Recheck

Calibration method: query all eval cases with `top_k=5` and `min_score=0.0`, collect scores where retrieved chunks match `expected_chunk_ids`, then compare against an unrelated query (`今天天气怎么样，适合出门吗`) across both scenarios.

| Backend | Correct hit min | Unrelated max | Current floor | Result |
| --- | ---: | ---: | ---: | --- |
| bge_m3 | 0.5611 | 0.4565 | 0.510 | keep existing floor |
| bge_small | 0.5622 | 0.4457 | 0.507 | keep existing floor |

Both existing floors remain between unrelated-query maximum scores and correct-hit minimum scores, so `src/bank_reconciliation_agent/core/config.py` did not need a floor change.

## Desaturation Statistics

- BANK_ENTERPRISE changed cases: 60 / 60.
- BANK_CLEARING changed cases: 29 / 60 (targeted audit of obvious semantic mismatches).
- BANK_ENTERPRISE single expected max count: 2 (acceptance threshold: <= 3).
- BANK_CLEARING single expected max count: 3.

## Label Change Log

| Case | Query | Old expected | New expected | Reason |
| --- | --- | --- | --- | --- |
| be-r002-01 | 银行流水和企业账簿都能找到同一笔交易，但两个金额不一样，审核时应该优先查什么依据 | `unionpay_reconciliation_faq_001` | `bank_enterprise_amount_mismatch_playbook_001` | 按金额差异子语义重标到金额 playbook/advanced（拆分、冲正、汇率、尾差、升级），替换泛 FAQ。 |
| be-r002-02 | 客户付款在两边都有记录，只是银行入账金额比企业登记金额少了一部分，这类差额怎么判断 | `unionpay_reconciliation_faq_001` | `bank_enterprise_amount_mismatch_playbook_001, bank_enterprise_amount_mismatch_playbook_004` | 按金额差异子语义重标到金额 playbook/advanced（拆分、冲正、汇率、尾差、升级），替换泛 FAQ。 |
| be-r002-03 | 一笔收款被企业按发票合并登记，银行侧显示的到账金额对不上，应该参考哪些规则 | `unionpay_reconciliation_faq_001` | `bank_enterprise_amount_mismatch_advanced_003, bank_enterprise_amount_mismatch_playbook_004` | 按金额差异子语义重标到金额 playbook/advanced（拆分、冲正、汇率、尾差、升级），替换泛 FAQ。 |
| be-r002-04 | 退款或冲正抵减以后净额和原交易金额有差异，能不能直接平账 | `unionpay_reconciliation_faq_001` | `bank_enterprise_amount_mismatch_advanced_002` | 按金额差异子语义重标到金额 playbook/advanced（拆分、冲正、汇率、尾差、升级），替换泛 FAQ。 |
| be-r002-05 | 外币业务因为汇率重估导致账面金额和银行金额不一致，复核时要留哪些证据 | `unionpay_reconciliation_faq_001` | `bank_enterprise_amount_mismatch_advanced_004, bank_enterprise_amount_mismatch_playbook_005` | 按金额差异子语义重标到金额 playbook/advanced（拆分、冲正、汇率、尾差、升级），替换泛 FAQ。 |
| be-r002-06 | 银行扣了手续费后到账净额小于企业应收金额，怎么区分普通金额差异和手续费差异 | `unionpay_reconciliation_faq_001` | `bank_enterprise_amount_mismatch_playbook_002, bank_enterprise_amount_mismatch_advanced_005` | 按金额差异子语义重标到金额 playbook/advanced（拆分、冲正、汇率、尾差、升级），替换泛 FAQ。 |
| be-r002-07 | 同一笔资金两边日期和对手方一致但金额不相等，系统应给出什么处理路径 | `unionpay_reconciliation_faq_001` | `bank_enterprise_amount_mismatch_playbook_001` | 按金额差异子语义重标到金额 playbook/advanced（拆分、冲正、汇率、尾差、升级），替换泛 FAQ。 |
| be-r002-08 | 多笔发票对应一笔回款时总额差一点，是否需要拆分核对后再判断 | `unionpay_reconciliation_faq_001` | `bank_enterprise_amount_mismatch_advanced_003, bank_enterprise_amount_mismatch_playbook_004` | 按金额差异子语义重标到金额 playbook/advanced（拆分、冲正、汇率、尾差、升级），替换泛 FAQ。 |
| be-r002-09 | 企业说差额是四舍五入造成的，银行流水金额仍不一致时如何处理 | `unionpay_reconciliation_faq_001` | `bank_enterprise_amount_mismatch_playbook_005` | 按金额差异子语义重标到金额 playbook/advanced（拆分、冲正、汇率、尾差、升级），替换泛 FAQ。 |
| be-r002-10 | 金额差异超过人工复核阈值时，自动审核应如何升级并保留来源 | `unionpay_reconciliation_faq_001` | `bank_enterprise_amount_mismatch_advanced_001, bank_enterprise_amount_mismatch_advanced_006` | 按金额差异子语义重标到金额 playbook/advanced（拆分、冲正、汇率、尾差、升级），替换泛 FAQ。 |
| be-r004-01 | 金额和日期能对应上，但银行摘要里的付款方名称和企业账簿里的客户名称不一致，怎么核验 | `pbc_epayment_guideline_002` | `bank_enterprise_narrative_mismatch_playbook_001` | 按摘要/户名不符子语义重标到主体、别名、规范化、冲正、闭环证据 chunk。 |
| be-r004-02 | 客户使用简称付款，企业账上是全称，摘要相似时能不能自动确认匹配 | `pbc_small_payment_query_reply_002` | `bank_enterprise_narrative_mismatch_playbook_002` | 按摘要/户名不符子语义重标到主体、别名、规范化、冲正、闭环证据 chunk。 |
| be-r004-03 | 同名关联公司之间发生付款，户名看起来接近但主体不同，应查哪些原始资料 | `pbc_small_payment_query_reply_002` | `bank_enterprise_narrative_mismatch_advanced_001` | 按摘要/户名不符子语义重标到主体、别名、规范化、冲正、闭环证据 chunk。 |
| be-r004-04 | 银行流水里有经办人姓名，企业凭证里是公司名称，审核时如何判断摘要户名不符 | `pbc_epayment_guideline_002` | `bank_enterprise_narrative_mismatch_advanced_003` | 按摘要/户名不符子语义重标到主体、别名、规范化、冲正、闭环证据 chunk。 |
| be-r004-05 | 付款用途字段和合同编号对不上，但金额相同，是否可以直接平账 | `pbc_epayment_guideline_001` | `bank_enterprise_narrative_mismatch_playbook_004` | 按摘要/户名不符子语义重标到主体、别名、规范化、冲正、闭环证据 chunk。 |
| be-r004-06 | 银行摘要包含特殊字符和英文缩写，企业名称是中文全称，规范化后还要保留什么证据 | `pbc_small_payment_query_reply_002` | `bank_enterprise_narrative_mismatch_advanced_002, bank_enterprise_narrative_mismatch_playbook_005` | 按摘要/户名不符子语义重标到主体、别名、规范化、冲正、闭环证据 chunk。 |
| be-r004-07 | 退款冲正的备注和原交易摘要不同，系统应该怎样避免误判为普通户名不符 | `pbc_epayment_guideline_001` | `bank_enterprise_narrative_mismatch_playbook_003` | 按摘要/户名不符子语义重标到主体、别名、规范化、冲正、闭环证据 chunk。 |
| be-r004-08 | 只凭摘要里几个关键词相似就匹配两笔流水，会有什么审计风险 | `pbc_small_payment_query_reply_002` | `bank_enterprise_narrative_mismatch_playbook_002, pbc_small_payment_query_reply_002` | 按摘要/户名不符子语义重标到主体、别名、规范化、冲正、闭环证据 chunk。 |
| be-r004-09 | 户名不一致同时疑似重复提交，应先参考摘要规则还是重复记账规则 | `pbc_epayment_guideline_002` | `bank_enterprise_narrative_mismatch_advanced_004` | 按摘要/户名不符子语义重标到主体、别名、规范化、冲正、闭环证据 chunk。 |
| be-r004-10 | 客户名称和备注都不一致但流水号相同，复核闭环要记录哪些处理依据 | `pbc_epayment_guideline_001` | `bank_enterprise_narrative_mismatch_advanced_005, pbc_epayment_guideline_002` | 按摘要/户名不符子语义重标到主体、别名、规范化、冲正、闭环证据 chunk。 |
| be-r005-01 | 企业已经入账并有凭证，但银行流水暂时没有到账记录，下一步应该怎么查 | `pbc_small_payment_query_reply_001, unionpay_reconciliation_faq_002` | `bank_enterprise_bank_unarrived_playbook_001` | 按企业已记银行未达方向重标到未达、票据、清算时限、查复、账龄升级 chunk。 |
| be-r005-02 | 客户说款项已经汇出，企业账上也登记了，银行侧未达时能不能先自动平账 | `unionpay_reconciliation_faq_002` | `bank_enterprise_bank_unarrived_playbook_001, bank_enterprise_bank_unarrived_playbook_003` | 按企业已记银行未达方向重标到未达、票据、清算时限、查复、账龄升级 chunk。 |
| be-r005-03 | 跨行转账在途导致银行未到账，规则要求保留哪些查询查复材料 | `pbc_small_payment_query_reply_001` | `bank_enterprise_bank_unarrived_advanced_002, bank_enterprise_bank_unarrived_playbook_004` | 按企业已记银行未达方向重标到未达、票据、清算时限、查复、账龄升级 chunk。 |
| be-r005-04 | 票据或汇票还没有兑付，企业已记收款时应按什么路径处理 | `unionpay_reconciliation_faq_002` | `bank_enterprise_bank_unarrived_advanced_001` | 按企业已记银行未达方向重标到未达、票据、清算时限、查复、账龄升级 chunk。 |
| be-r005-05 | 跨境清算延迟造成银行端缺流水，系统应如何判断是否仍在正常时间窗口内 | `unionpay_reconciliation_faq_002` | `bank_enterprise_bank_unarrived_advanced_002` | 按企业已记银行未达方向重标到未达、票据、清算时限、查复、账龄升级 chunk。 |
| be-r005-06 | 长期挂账的银行未达款项超过预警期限，应该怎样升级复核 | `pbc_small_payment_query_reply_002` | `bank_enterprise_bank_unarrived_advanced_004, bank_enterprise_bank_unarrived_advanced_005` | 按企业已记银行未达方向重标到未达、票据、清算时限、查复、账龄升级 chunk。 |
| be-r005-07 | 只有企业账簿记录，没有银行回单，审核结论应要求补哪些字段 | `pbc_small_payment_query_reply_001, unionpay_reconciliation_faq_002` | `bank_enterprise_bank_unarrived_playbook_003, bank_enterprise_bank_unarrived_playbook_005` | 按企业已记银行未达方向重标到未达、票据、清算时限、查复、账龄升级 chunk。 |
| be-r005-08 | 银行未到账和跨期入账看起来都发生在月末，应该如何区分 | `unionpay_reconciliation_faq_002` | `bank_enterprise_bank_unarrived_advanced_003, bank_enterprise_cross_period_playbook_002` | 按企业已记银行未达方向重标到未达、票据、清算时限、查复、账龄升级 chunk。 |
| be-r005-09 | 企业凭证真实性需要核验时，单边未达规则对证据有什么要求 | `pbc_small_payment_query_reply_001` | `bank_enterprise_bank_unarrived_playbook_003` | 按企业已记银行未达方向重标到未达、票据、清算时限、查复、账龄升级 chunk。 |
| be-r005-10 | 后续银行到账后需要闭环这笔未达项，任务里应保存哪些追踪信息 | `pbc_small_payment_query_reply_001, unionpay_reconciliation_faq_002` | `bank_enterprise_bank_unarrived_playbook_005` | 按企业已记银行未达方向重标到未达、票据、清算时限、查复、账龄升级 chunk。 |
| be-r006-01 | 银行流水已经入账，但企业账簿没有对应记录，这种企业未记账应怎么处理 | `pbc_small_payment_query_reply_002, unionpay_reconciliation_faq_002` | `bank_enterprise_book_unrecorded_playbook_001` | 按银行已入企业未记方向重标到补记、费用、利息、代收、方向边界、闭环 chunk。 |
| be-r006-02 | 账户管理费被银行自动扣收，企业没有做费用凭证，审核时应该参考哪条规则 | `unionpay_reconciliation_faq_002` | `bank_enterprise_book_unrecorded_advanced_001` | 按银行已入企业未记方向重标到补记、费用、利息、代收、方向边界、闭环 chunk。 |
| be-r006-03 | 银行结息已经到账，企业账上还没有确认利息收入，需要补哪些凭证 | `pbc_small_payment_query_reply_001` | `bank_enterprise_book_unrecorded_advanced_002` | 按银行已入企业未记方向重标到补记、费用、利息、代收、方向边界、闭环 chunk。 |
| be-r006-04 | 代收款项先进入银行账户但业务系统未确认收入，能不能直接自动补记 | `pbc_small_payment_query_reply_002` | `bank_enterprise_book_unrecorded_advanced_003` | 按银行已入企业未记方向重标到补记、费用、利息、代收、方向边界、闭环 chunk。 |
| be-r006-05 | 银行有回单企业漏导入流水时，系统应怎样区分漏记和文件重复下载 | `unionpay_reconciliation_faq_002` | `bank_enterprise_book_unrecorded_playbook_004` | 按银行已入企业未记方向重标到补记、费用、利息、代收、方向边界、闭环 chunk。 |
| be-r006-06 | 银行已扣短信费，企业账面没有费用记录，这类小额扣费怎么闭环 | `pbc_small_payment_query_reply_002` | `bank_enterprise_book_unrecorded_advanced_001` | 按银行已入企业未记方向重标到补记、费用、利息、代收、方向边界、闭环 chunk。 |
| be-r006-07 | 企业未入账和银行未到账方向相反，审核说明里应如何写清楚 | `pbc_small_payment_query_reply_001` | `bank_enterprise_book_unrecorded_advanced_004` | 按银行已入企业未记方向重标到补记、费用、利息、代收、方向边界、闭环 chunk。 |
| be-r006-08 | 银行端出现一笔收入，企业凭证还没生成，应该要求业务部门补什么材料 | `unionpay_reconciliation_faq_002, pbc_small_payment_query_reply_002` | `bank_enterprise_book_unrecorded_advanced_003, bank_enterprise_book_unrecorded_playbook_001` | 按银行已入企业未记方向重标到补记、费用、利息、代收、方向边界、闭环 chunk。 |
| be-r006-09 | 月末银行已入账但企业下月才记账，应按企业未入账还是跨期处理 | `pbc_small_payment_query_reply_001` | `bank_enterprise_book_unrecorded_advanced_004, bank_enterprise_cross_period_playbook_003` | 按银行已入企业未记方向重标到补记、费用、利息、代收、方向边界、闭环 chunk。 |
| be-r006-10 | 补记账完成后，审计台账需要记录哪些结果字段 | `unionpay_reconciliation_faq_002` | `bank_enterprise_book_unrecorded_playbook_005` | 按银行已入企业未记方向重标到补记、费用、利息、代收、方向边界、闭环 chunk。 |
| be-r008-01 | 企业账簿里同一客户同日同金额出现两条记录，银行只有一笔到账，怎么识别重复记账 | `pbc_epayment_guideline_001` | `bank_enterprise_duplicate_booking_advanced_001, bank_enterprise_duplicate_booking_playbook_001` | 按重复记账识别、冲正边界、跨期边界、候选边界和冲销归档重标。 |
| be-r008-02 | 同一笔收款被批量导入了两次，审核时应该查流水号还是凭证号 | `pbc_epayment_guideline_001` | `bank_enterprise_duplicate_booking_playbook_002, bank_enterprise_duplicate_booking_playbook_003` | 按重复记账识别、冲正边界、跨期边界、候选边界和冲销归档重标。 |
| be-r008-03 | 隔日再次提交了相同金额和相同对手方的付款，是否属于重复入账 | `pbc_epayment_guideline_002` | `bank_enterprise_duplicate_booking_advanced_002` | 按重复记账识别、冲正边界、跨期边界、候选边界和冲销归档重标。 |
| be-r008-04 | 一笔冲正和一笔重复记账金额相同，系统应如何区分两种情况 | `pbc_epayment_guideline_001` | `bank_enterprise_duplicate_booking_playbook_004` | 按重复记账识别、冲正边界、跨期边界、候选边界和冲销归档重标。 |
| be-r008-05 | 同日同额同对手的两条企业记录都没有独立银行流水，应按什么规则处理 | `pbc_epayment_guideline_002` | `bank_enterprise_duplicate_booking_advanced_001, bank_enterprise_duplicate_booking_playbook_002` | 按重复记账识别、冲正边界、跨期边界、候选边界和冲销归档重标。 |
| be-r008-06 | 重复确认后需要冲销其中一笔，审计证据应该保留哪些内容 | `pbc_epayment_guideline_001` | `bank_enterprise_duplicate_booking_advanced_005, bank_enterprise_duplicate_booking_playbook_005` | 按重复记账识别、冲正边界、跨期边界、候选边界和冲销归档重标。 |
| be-r008-07 | 跨期入账和重复记账都出现两条相似记录，如何判断不是正常跨期 | `pbc_epayment_guideline_002` | `bank_enterprise_duplicate_booking_advanced_003, bank_enterprise_cross_period_playbook_001` | 按重复记账识别、冲正边界、跨期边界、候选边界和冲销归档重标。 |
| be-r008-08 | 批量导入失败后重新上传导致凭证重复，处理闭环有什么要求 | `pbc_epayment_guideline_001` | `bank_enterprise_duplicate_booking_playbook_003` | 按重复记账识别、冲正边界、跨期边界、候选边界和冲销归档重标。 |
| be-r008-09 | 企业账上两条记录流水号相同但摘要略有不同，能不能自动认定重复 | `pbc_epayment_guideline_002` | `bank_enterprise_duplicate_booking_playbook_002` | 按重复记账识别、冲正边界、跨期边界、候选边界和冲销归档重标。 |
| be-r008-10 | 候选匹配和重复记账都涉及相似流水，规则边界在哪里 | `pbc_epayment_guideline_001` | `bank_enterprise_duplicate_booking_advanced_004, bank_enterprise_fuzzy_match_playbook_004` | 按重复记账识别、冲正边界、跨期边界、候选边界和冲销归档重标。 |
| be-r002-11 | 收款金额方向记反后看起来差额很大，应该按金额不平还是重复记账处理 | `bank_enterprise_amount_mismatch_playbook_001, bank_enterprise_amount_mismatch_playbook_002` | `bank_enterprise_amount_mismatch_playbook_003` | 按金额差异子语义重标到金额 playbook/advanced（拆分、冲正、汇率、尾差、升级），替换泛 FAQ。 |
| be-r002-12 | 双方都有流水但差额原因暂时说不清，审计结论需要包含哪些字段 | `bank_enterprise_amount_mismatch_playbook_003` | `bank_enterprise_amount_mismatch_advanced_006, bank_enterprise_amount_mismatch_playbook_001` | 按金额差异子语义重标到金额 playbook/advanced（拆分、冲正、汇率、尾差、升级），替换泛 FAQ。 |
| be-r005-11 | 付款渠道返回处理中，企业已做账但银行未落账，是否可以等待 T+1 再确认 | `bank_enterprise_bank_unarrived_playbook_001, bank_enterprise_bank_unarrived_playbook_004` | `bank_enterprise_bank_unarrived_playbook_002, bank_enterprise_bank_unarrived_playbook_004` | 按企业已记银行未达方向重标到未达、票据、清算时限、查复、账龄升级 chunk。 |
| be-r005-12 | 银行端缺失的流水如果无法查复，最终应转入哪类人工处理 | `bank_enterprise_bank_unarrived_playbook_002` | `bank_enterprise_bank_unarrived_advanced_005, bank_enterprise_bank_unarrived_playbook_004` | 按企业已记银行未达方向重标到未达、票据、清算时限、查复、账龄升级 chunk。 |
| be-r006-12 | 长期未补记的银行已入账项目，什么时候需要升级人工复核 | `bank_enterprise_book_unrecorded_playbook_003` | `bank_enterprise_book_unrecorded_advanced_005, bank_enterprise_book_unrecorded_playbook_003` | 按银行已入企业未记方向重标到补记、费用、利息、代收、方向边界、闭环 chunk。 |
| be-r008-11 | 发现重复记账后，自动建议应指向冲销还是转人工复核 | `bank_enterprise_duplicate_booking_playbook_001, bank_enterprise_duplicate_booking_playbook_002` | `bank_enterprise_duplicate_booking_advanced_005, bank_enterprise_duplicate_booking_playbook_005` | 按重复记账识别、冲正边界、跨期边界、候选边界和冲销归档重标。 |
| be-r008-12 | 银行只有一笔资金，企业有两笔同额应收确认，系统要怎么给出解释 | `bank_enterprise_duplicate_booking_playbook_004` | `bank_enterprise_duplicate_booking_advanced_004` | 按重复记账识别、冲正边界、跨期边界、候选边界和冲销归档重标。 |
| bc-r002-03 | 手续费按净额入账后造成清算金额差异，应如何区分手续费原因 | `clearing_amount_mismatch_playbook_003` | `clearing_amount_mismatch_playbook_002` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r002-04 | 退款冲正已经发生但清算明细仍显示原金额，如何判断金额偏差 | `clearing_amount_mismatch_playbook_004` | `clearing_amount_mismatch_playbook_003` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r002-08 | 核心入账金额和清算应收金额差几分钱，舍入差异要不要人工复核 | `clearing_amount_mismatch_playbook_004` | `clearing_amount_mismatch_playbook_001` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r002-09 | 清算金额不平同时存在文件异常迹象，应该先定位金额规则还是文件完整性 | `clearing_amount_mismatch_playbook_002` | `clearing_amount_mismatch_playbook_004, clearing_file_exception_playbook_001` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r001-03 | 渠道侧返回成功但清算批次里没有这笔记录，是否需要发起查询 | `clearing_single_side_playbook_002` | `clearing_single_side_playbook_001, clearing_query_reply_playbook_001` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r001-06 | 清算单边和文件缺失都可能导致少一笔，怎样区分交易缺失和文件异常 | `clearing_t1_supplement_playbook_003` | `clearing_single_side_playbook_001, clearing_file_exception_playbook_001` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r003-03 | T+1 已经补记到核心系统后，原来的日切单边应如何确认闭环 | `clearing_t1_supplement_playbook_001` | `clearing_t1_supplement_playbook_002` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r003-04 | 日切后仍没有补齐清算记录，系统应给出什么待补齐结论 | `clearing_t1_supplement_playbook_002` | `clearing_t1_supplement_playbook_003` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r003-05 | 跨日切交易归属不清时，需要核对交易时间还是清算日期 | `clearing_t1_supplement_playbook_003` | `clearing_cutoff_t1_guideline_002, clearing_t1_supplement_playbook_001` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r003-08 | 日切窗口内金额一致但日期不同，自动审核能否直接判定通过 | `clearing_t1_supplement_playbook_002` | `clearing_cutoff_t1_guideline_002, clearing_reconciliation_scope_002` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r003-10 | 夜间批处理延迟导致清算单边，系统应如何记录追溯结果 | `clearing_cutoff_t1_guideline_002` | `clearing_cutoff_t1_guideline_001, clearing_t1_supplement_playbook_001` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r004-02 | 同一个清算文件被重复导入两次，系统如何识别文件异常 | `clearing_file_exception_playbook_001` | `clearing_file_exception_playbook_002` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r004-03 | 清算文件格式不对，关键字段缺失，能不能继续做自动结论 | `clearing_file_exception_playbook_002` | `clearing_file_exception_playbook_003` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r004-04 | 文件日期和实际清算日期不一致，审核时应核对哪些口径 | `clearing_file_exception_playbook_003` | `clearing_file_exception_playbook_004` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r004-06 | 渠道上传的文件少了明细行，和单边缺失的边界怎么区分 | `clearing_file_exception_playbook_004` | `clearing_file_exception_playbook_001, clearing_file_exception_playbook_004` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r004-07 | 重复文件导入造成金额翻倍，应先按文件异常还是金额差异处理 | `clearing_file_exception_playbook_004` | `clearing_file_exception_playbook_002, clearing_amount_mismatch_playbook_004` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r004-10 | 收到补发文件后，原异常批次如何做证据归档 | `clearing_file_exception_playbook_003` | `clearing_file_exception_playbook_004, clearing_query_reply_playbook_003` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r005-03 | 渠道回复说交易成功但核心没有入账，查复材料应如何归档 | `clearing_query_reply_playbook_002` | `clearing_query_reply_playbook_003` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r005-04 | 查询超时没有收到回复，系统下一步应该怎么处理 | `clearing_query_reply_playbook_002` | `clearing_query_reply_playbook_004` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r005-05 | 发起清算查询时，必须带上哪些交易要素 | `clearing_query_reply_playbook_003` | `clearing_query_reply_playbook_002` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r005-06 | 查复内容不明确，只说处理中，能不能作为自动平账依据 | `clearing_query_reply_playbook_003` | `clearing_query_reply_playbook_001, clearing_query_reply_playbook_003` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r005-08 | 渠道回执与原交易金额不一致，应转到金额差异还是继续查询查复 | `clearing_query_reply_playbook_004` | `clearing_query_reply_playbook_003, clearing_amount_mismatch_playbook_001` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r006-02 | 渠道参考号被截断，核心系统里多了前导零，怎样判断仍是同一笔 | `clearing_reference_match_playbook_001` | `clearing_reference_match_playbook_002` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r006-03 | 一笔清算记录对应多笔核心入账，参考号匹配应该如何处理 | `clearing_reference_match_playbook_002` | `clearing_reference_match_playbook_003` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r006-04 | 多笔清算明细合并成一笔核心流水，参考号一致但金额拆分不同怎么办 | `clearing_reference_match_playbook_002` | `clearing_reference_match_playbook_003` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r006-05 | 参考号相似但不是完全一致时，弱匹配有什么风险 | `clearing_reference_match_playbook_003` | `clearing_reference_match_playbook_004` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r006-06 | 清算参考号缺失，只能靠金额和时间匹配，是否需要人工确认 | `clearing_reference_match_playbook_003` | `clearing_reference_match_playbook_004` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r006-07 | 补零后的参考号能匹配上，但对手信息不一致，应如何复核 | `clearing_reference_match_playbook_004` | `clearing_reference_match_playbook_002, clearing_reference_match_playbook_004` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r006-08 | 参考号一致而日期跨日，是否需要结合 T+1 规则判断 | `clearing_reference_match_playbook_004` | `clearing_reference_match_playbook_001, clearing_cutoff_t1_guideline_001` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r006-09 | 一对多匹配后仍有尾差，应该转金额差异还是保留参考号匹配结论 | `clearing_reference_match_playbook_001` | `clearing_reference_match_playbook_003, clearing_amount_mismatch_playbook_001` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |
| bc-r006-10 | 弱匹配确认后，台账需要保存哪些匹配依据 | `clearing_reference_match_playbook_002, clearing_reference_match_playbook_004` | `clearing_reference_match_playbook_004` | 清算抽查修正明显相邻错标，按文件异常、T+1、查复、参考号等直接语义重标。 |

## Risks / Follow-up

- Default CI still does not cover real model paths; real embedding remains covered by opt-in `embedding_real` and manual eval reports.
- Some individual business questions still miss despite improved weighted metrics; future recall-gate work should inspect those misses before locking thresholds.
- No recall hard gate, reranker change, or query rewrite change was introduced in this task.
