# RAG Quality Matrix Report

## Metadata

| Key | Value |
|---|---|
| Case Count | 120 |
| Top K | 5 |
| Real Backend Policy | `auto` |
| Evaluated At | 2026-07-08T09:44:49.643516Z |
| Best Real Backend | `bge_m3` |
| Best Real Mode | `hybrid` |

## Real Backend Requirement

| Key | Value |
|---|---|
| Required Backend | `bge_small` |
| Satisfied | Yes |
| Measured Real Backends | `bge_small`, `bge_m3` |
| Unavailable Real Backends | - |
| Not Run Real Backends | - |
| Reason | bge_small measured with trusted effective backend |

## Row Summary

| Backend | Eff Backend | Status | Selected Mode | Reason |
| --- | --- | --- | --- | --- |
| hash | hash | measured | hybrid_rerank | Highest NDCG@5 among eligible modes with no negative ranking |
| bge_small | bge_small | measured | dense | No mode improved ranking metrics over dense baseline; RAG ha |
| bge_m3 | bge_m3 | measured | hybrid | Highest NDCG@5 among eligible modes with no negative ranking |

## Global Metrics by Backend × Mode

### dense | Backend | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| hash | 0.1667 | 0.3875 | 0.2750 | 0.2824 |
| bge_small | 0.5417 | 0.6667 | 0.6389 | 0.6045 |
| bge_m3 | 0.5083 | 0.7333 | 0.6349 | 0.6271 |

### hybrid | Backend | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| hash | 0.3083 | 0.5625 | 0.4515 | 0.4448 |
| bge_small | 0.5333 | 0.7542 | 0.6603 | 0.6528 |
| bge_m3 | 0.5583 | 0.7542 | 0.6675 | 0.6552 |

### hybrid_rerank | Backend | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| hash | 0.4333 | 0.6583 | 0.5682 | 0.5528 |
| bge_small | 0.4500 | 0.6708 | 0.5853 | 0.5703 |
| bge_m3 | 0.4417 | 0.6750 | 0.5846 | 0.5689 |

## Deltas vs Dense

### hash
| Mode | Δ Hit@1 | Δ MRR | Δ NDCG@5 |
| --- | ---: | ---: | ---: |
| hybrid | +0.1417 | +0.1765 | +0.1623 |
| hybrid_rerank | +0.2667 | +0.2932 | +0.2704 |

### bge_small
| Mode | Δ Hit@1 | Δ MRR | Δ NDCG@5 |
| --- | ---: | ---: | ---: |
| hybrid | -0.0083 | +0.0214 | +0.0484 |
| hybrid_rerank | -0.0917 | -0.0536 | -0.0342 |

### bge_m3
| Mode | Δ Hit@1 | Δ MRR | Δ NDCG@5 |
| --- | ---: | ---: | ---: |
| hybrid | +0.0500 | +0.0326 | +0.0281 |
| hybrid_rerank | -0.0667 | -0.0503 | -0.0582 |

## Miss Buckets

Best real backend: `bge_m3`

| Scenario | Error Type | Cases | Misses | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BANK_CLEARING | AMOUNT_MISMATCH | 10 | 2 | 0.5000 | 0.8500 | 0.6533 | 0.6718 |
| BANK_CLEARING | CLEARING_FILE_EXCEPTION | 10 | 4 | 0.5000 | 0.7000 | 0.6083 | 0.6121 |
| BANK_CLEARING | CUTOFF_T1 | 10 | 3 | 0.6000 | 0.8000 | 0.7167 | 0.6894 |
| BANK_CLEARING | QUERY_REPLY | 10 | 1 | 0.6000 | 0.9000 | 0.7033 | 0.7238 |
| BANK_CLEARING | REFERENCE_MATCH | 10 | 1 | 0.6000 | 0.9500 | 0.7833 | 0.8131 |
| BANK_CLEARING | SINGLE_SIDE_MISSING | 10 | 7 | 0.1000 | 0.4000 | 0.2833 | 0.2938 |
| BANK_ENTERPRISE | AMOUNT_MISMATCH | 12 | 6 | 0.5833 | 0.6250 | 0.6528 | 0.5669 |
| BANK_ENTERPRISE | BANK_UNARRIVED | 12 | 5 | 0.5833 | 0.7083 | 0.6597 | 0.6117 |
| BANK_ENTERPRISE | BOOK_UNRECORDED | 12 | 3 | 0.9167 | 0.8750 | 0.9583 | 0.8844 |
| BANK_ENTERPRISE | DUPLICATE_BOOKING | 12 | 2 | 0.6667 | 0.8750 | 0.7778 | 0.8078 |
| BANK_ENTERPRISE | NARRATIVE_NAME_MISMATCH | 12 | 5 | 0.4167 | 0.6250 | 0.5028 | 0.5109 |

### Miss Samples

#### BANK_CLEARING / AMOUNT_MISMATCH

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| bc-r002-01 | 清算文件金额和核心系统入账金额不一致，运营人员应该先核对哪些字段 | clearing_amount_mismatch_playbook_001, clearing_amount_mismatch_playbook_002 | clearing_amount_mismatch_playbook_001, clearing_file_exception_playbook_004, clearing_reference_match_playbook_001, clearing_reconciliation_scope_001, clearing_single_side_playbook_001 | 1.0000 | 0.5000 |
| bc-r002-07 | 文件字段口径不同导致金额不一致，应参考清算对账字段还是自动结论边界 | clearing_amount_mismatch_playbook_003 | clearing_file_exception_playbook_004, clearing_amount_mismatch_playbook_001, clearing_reconciliation_scope_001, clearing_amount_mismatch_playbook_004, clearing_file_exception_playbook_003 | 0.0000 | 0.0000 |

#### BANK_CLEARING / CLEARING_FILE_EXCEPTION

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| bc-r004-05 | 清算文件校验失败后，报告需要说明是文件问题还是交易问题 | clearing_file_exception_playbook_003 | clearing_amount_mismatch_playbook_004, clearing_file_exception_playbook_001, clearing_amount_mismatch_playbook_001, clearing_reconciliation_scope_001, clearing_file_exception_playbook_004 | 0.0000 | 0.0000 |
| bc-r004-06 | 渠道上传的文件少了明细行，和单边缺失的边界怎么区分 | clearing_file_exception_playbook_001, clearing_file_exception_playbook_004 | clearing_amount_mismatch_playbook_004, clearing_single_side_playbook_001, clearing_file_exception_playbook_001, clearing_query_reply_playbook_001, clearing_reconciliation_scope_001 | 0.0000 | 0.5000 |
| bc-r004-08 | 字段缺损导致参考号无法匹配，系统应怎样提示补充文件 | clearing_file_exception_playbook_002 | clearing_query_reply_playbook_002, clearing_reference_match_playbook_002, clearing_file_exception_playbook_003, clearing_query_reply_playbook_001, clearing_reference_match_playbook_004 | 0.0000 | 0.0000 |
| bc-r004-10 | 收到补发文件后，原异常批次如何做证据归档 | clearing_file_exception_playbook_004, clearing_query_reply_playbook_003 | clearing_query_reply_playbook_004, clearing_amount_mismatch_playbook_004, clearing_file_exception_playbook_001, clearing_query_reply_playbook_003, clearing_file_exception_playbook_002 | 0.0000 | 0.5000 |

#### BANK_CLEARING / CUTOFF_T1

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| bc-r003-07 | 清算日期和核心入账日期跨了一天，如何区分正常 T+1 和异常缺失 | clearing_t1_supplement_playbook_001, clearing_cutoff_t1_guideline_001 | clearing_cutoff_t1_guideline_001, clearing_t1_supplement_playbook_002, clearing_reconciliation_scope_001, clearing_file_exception_playbook_004, clearing_amount_mismatch_playbook_001 | 1.0000 | 0.5000 |
| bc-r003-08 | 日切窗口内金额一致但日期不同，自动审核能否直接判定通过 | clearing_cutoff_t1_guideline_002, clearing_reconciliation_scope_002 | clearing_file_exception_playbook_004, clearing_cutoff_t1_guideline_001, clearing_t1_supplement_playbook_001, clearing_single_side_playbook_001, clearing_t1_supplement_playbook_003 | 0.0000 | 0.0000 |
| bc-r003-10 | 夜间批处理延迟导致清算单边，系统应如何记录追溯结果 | clearing_cutoff_t1_guideline_001, clearing_t1_supplement_playbook_001 | clearing_single_side_playbook_001, clearing_single_side_playbook_002, clearing_cutoff_t1_guideline_001, clearing_cutoff_t1_guideline_002, clearing_query_reply_playbook_001 | 0.0000 | 0.5000 |

#### BANK_CLEARING / QUERY_REPLY

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| bc-r005-05 | 发起清算查询时，必须带上哪些交易要素 | clearing_query_reply_playbook_002 | clearing_query_reply_playbook_001, clearing_reconciliation_scope_001, clearing_cutoff_t1_guideline_002, clearing_reference_match_playbook_001, clearing_single_side_playbook_001 | 0.0000 | 0.0000 |

#### BANK_CLEARING / REFERENCE_MATCH

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| bc-r006-08 | 参考号一致而日期跨日，是否需要结合 T+1 规则判断 | clearing_reference_match_playbook_001, clearing_cutoff_t1_guideline_001 | clearing_t1_supplement_playbook_002, clearing_cutoff_t1_guideline_001, clearing_file_exception_playbook_004, clearing_t1_supplement_playbook_001, clearing_cutoff_t1_guideline_002 | 0.0000 | 0.5000 |

#### BANK_CLEARING / SINGLE_SIDE_MISSING

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| bc-r001-02 | 核心有流水而清算文件缺少明细，单边缺失时应保留哪些证据 | clearing_single_side_playbook_001, clearing_query_reply_playbook_001 | clearing_amount_mismatch_playbook_004, clearing_file_exception_playbook_002, clearing_single_side_playbook_001, clearing_cutoff_t1_guideline_001, clearing_file_exception_playbook_001 | 0.0000 | 0.5000 |
| bc-r001-04 | 清算单边发生在普通工作日，不能用日切解释时下一步怎么处理 | clearing_single_side_playbook_001, clearing_query_reply_playbook_001 | clearing_cutoff_t1_guideline_001, clearing_single_side_playbook_001, clearing_reconciliation_scope_001, clearing_t1_supplement_playbook_001, clearing_reconciliation_scope_002 | 0.0000 | 0.5000 |
| bc-r001-05 | 只有一侧有参考号，另一侧查不到记录，人工复核前要收集什么材料 | clearing_query_reply_playbook_002 | clearing_single_side_playbook_001, clearing_reference_match_playbook_002, clearing_query_reply_playbook_001, clearing_reference_match_playbook_004, clearing_single_side_playbook_002 | 0.0000 | 0.0000 |
| bc-r001-07 | 核心入账已完成但渠道清算未出现，应如何判断是否在正常延迟范围内 | clearing_single_side_playbook_001 | clearing_t1_supplement_playbook_003, clearing_query_reply_playbook_003, clearing_cutoff_t1_guideline_001, clearing_file_exception_playbook_001, clearing_reconciliation_scope_002 | 0.0000 | 0.0000 |
| bc-r001-08 | 非日切窗口内出现单边交易，系统结论应避免自动平账还是直接挂起 | clearing_single_side_playbook_002 | clearing_single_side_playbook_001, clearing_cutoff_t1_guideline_001, clearing_t1_supplement_playbook_003, clearing_reconciliation_scope_001, clearing_reconciliation_scope_002 | 0.0000 | 0.0000 |

#### BANK_ENTERPRISE / AMOUNT_MISMATCH

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| be-r002-02 | 客户付款在两边都有记录，只是银行入账金额比企业登记金额少了一部分，这类差额怎么判断 | bank_enterprise_amount_mismatch_playbook_001, bank_enterprise_amount_mismatch_playbook_004 | bank_enterprise_amount_mismatch_playbook_004, bank_enterprise_cross_period_playbook_003, bank_enterprise_fee_tax_diff_playbook_001, bank_enterprise_amount_mismatch_playbook_003, bank_enterprise_amount_mismatch_playbook_002 | 1.0000 | 0.5000 |
| be-r002-06 | 银行扣了手续费后到账净额小于企业应收金额，怎么区分普通金额差异和手续费差异 | bank_enterprise_amount_mismatch_playbook_002, bank_enterprise_amount_mismatch_advanced_005 | bank_enterprise_amount_mismatch_playbook_002, bank_enterprise_fee_tax_diff_playbook_005, bank_enterprise_fee_tax_diff_playbook_001, bank_enterprise_fee_tax_diff_playbook_002, bank_enterprise_fee_tax_diff_playbook_003 | 1.0000 | 0.5000 |
| be-r002-07 | 同一笔资金两边日期和对手方一致但金额不相等，系统应给出什么处理路径 | bank_enterprise_amount_mismatch_playbook_001 | bank_enterprise_cross_period_playbook_001, unionpay_reconciliation_faq_001, bank_enterprise_duplicate_booking_advanced_002, bank_enterprise_fuzzy_match_playbook_003, bank_enterprise_exact_match_playbook_007 | 0.0000 | 0.0000 |
| be-r002-09 | 企业说差额是四舍五入造成的，银行流水金额仍不一致时如何处理 | bank_enterprise_amount_mismatch_playbook_005 | bank_enterprise_amount_mismatch_playbook_003, bank_enterprise_amount_mismatch_playbook_001, bank_enterprise_cross_period_playbook_001, bank_enterprise_fee_tax_diff_playbook_001, bank_enterprise_amount_mismatch_advanced_003 | 0.0000 | 0.0000 |
| be-r002-11 | 收款金额方向记反后看起来差额很大，应该按金额不平还是重复记账处理 | bank_enterprise_amount_mismatch_playbook_003 | bank_enterprise_fee_tax_diff_playbook_009, bank_enterprise_narrative_mismatch_advanced_004, bank_enterprise_amount_mismatch_advanced_003, bank_enterprise_amount_mismatch_advanced_002, bank_enterprise_duplicate_booking_playbook_004 | 0.0000 | 0.0000 |

#### BANK_ENTERPRISE / BANK_UNARRIVED

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| be-r005-02 | 客户说款项已经汇出，企业账上也登记了，银行侧未达时能不能先自动平账 | bank_enterprise_bank_unarrived_playbook_001, bank_enterprise_bank_unarrived_playbook_003 | bank_enterprise_bank_unarrived_playbook_001, bank_enterprise_exact_match_playbook_001, pbc_small_payment_query_reply_001, bank_enterprise_exact_match_playbook_006, bank_enterprise_amount_mismatch_playbook_004 | 1.0000 | 0.5000 |
| be-r005-03 | 跨行转账在途导致银行未到账，规则要求保留哪些查询查复材料 | bank_enterprise_bank_unarrived_advanced_002, bank_enterprise_bank_unarrived_playbook_004 | bank_enterprise_bank_unarrived_playbook_002, bank_enterprise_bank_unarrived_advanced_003, bank_enterprise_bank_unarrived_advanced_002, bank_enterprise_cross_period_playbook_002, pbc_small_payment_query_reply_001 | 0.0000 | 0.5000 |
| be-r005-07 | 只有企业账簿记录，没有银行回单，审核结论应要求补哪些字段 | bank_enterprise_bank_unarrived_playbook_003, bank_enterprise_bank_unarrived_playbook_005 | bank_enterprise_book_unrecorded_playbook_001, bank_enterprise_book_unrecorded_playbook_005, bank_enterprise_book_unrecorded_playbook_002, bank_enterprise_narrative_mismatch_playbook_004, bank_enterprise_bank_unarrived_playbook_001 | 0.0000 | 0.0000 |
| be-r005-11 | 付款渠道返回处理中，企业已做账但银行未落账，是否可以等待 T+1 再确认 | bank_enterprise_bank_unarrived_playbook_002, bank_enterprise_bank_unarrived_playbook_004 | bank_enterprise_bank_unarrived_playbook_002, bank_enterprise_cross_period_playbook_004, bank_enterprise_bank_unarrived_playbook_001, bank_enterprise_bank_unarrived_advanced_002, bank_enterprise_bank_unarrived_advanced_001 | 1.0000 | 0.5000 |
| be-r005-12 | 银行端缺失的流水如果无法查复，最终应转入哪类人工处理 | bank_enterprise_bank_unarrived_advanced_005, bank_enterprise_bank_unarrived_playbook_004 | pbc_small_payment_query_reply_001, unionpay_reconciliation_faq_002, unionpay_reconciliation_faq_001, bank_enterprise_book_unrecorded_playbook_001, bank_enterprise_amount_mismatch_playbook_001 | 0.0000 | 0.0000 |

#### BANK_ENTERPRISE / BOOK_UNRECORDED

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| be-r006-09 | 月末银行已入账但企业下月才记账，应按企业未入账还是跨期处理 | bank_enterprise_book_unrecorded_advanced_004, bank_enterprise_cross_period_playbook_003 | bank_enterprise_cross_period_playbook_003, bank_enterprise_bank_unarrived_advanced_003, bank_enterprise_bank_unarrived_playbook_002, bank_enterprise_cross_period_playbook_004, bank_enterprise_cross_period_playbook_001 | 1.0000 | 0.5000 |
| be-r006-11 | 银行流水存在但企业系统漏导入批次文件，怎样避免误判为清算文件异常 | bank_enterprise_book_unrecorded_playbook_001, bank_enterprise_book_unrecorded_playbook_004 | unionpay_reconciliation_faq_001, bank_enterprise_book_unrecorded_playbook_004, bank_enterprise_duplicate_booking_playbook_003, bank_enterprise_book_unrecorded_playbook_002, bank_enterprise_narrative_mismatch_playbook_005 | 0.0000 | 0.5000 |
| be-r006-12 | 长期未补记的银行已入账项目，什么时候需要升级人工复核 | bank_enterprise_book_unrecorded_advanced_005, bank_enterprise_book_unrecorded_playbook_003 | bank_enterprise_book_unrecorded_advanced_005, bank_enterprise_bank_unarrived_advanced_004, bank_enterprise_amount_mismatch_advanced_006, bank_enterprise_book_unrecorded_playbook_002, bank_enterprise_book_unrecorded_advanced_001 | 1.0000 | 0.5000 |

#### BANK_ENTERPRISE / DUPLICATE_BOOKING

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| be-r008-05 | 同日同额同对手的两条企业记录都没有独立银行流水，应按什么规则处理 | bank_enterprise_duplicate_booking_advanced_001, bank_enterprise_duplicate_booking_playbook_002 | bank_enterprise_book_unrecorded_playbook_001, bank_enterprise_exact_match_playbook_005, bank_enterprise_duplicate_booking_advanced_001, bank_enterprise_book_unrecorded_advanced_001, bank_enterprise_cross_period_playbook_001 | 0.0000 | 0.5000 |
| be-r008-12 | 银行只有一笔资金，企业有两笔同额应收确认，系统要怎么给出解释 | bank_enterprise_duplicate_booking_advanced_004 | bank_enterprise_amount_mismatch_advanced_003, bank_enterprise_duplicate_booking_advanced_001, pbc_small_payment_query_reply_001, bank_enterprise_amount_mismatch_playbook_003, bank_enterprise_fuzzy_match_playbook_004 | 0.0000 | 0.0000 |

#### BANK_ENTERPRISE / NARRATIVE_NAME_MISMATCH

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| be-r004-06 | 银行摘要包含特殊字符和英文缩写，企业名称是中文全称，规范化后还要保留什么证据 | bank_enterprise_narrative_mismatch_advanced_002, bank_enterprise_narrative_mismatch_playbook_005 | bank_enterprise_narrative_mismatch_advanced_002, bank_enterprise_narrative_mismatch_advanced_005, bank_enterprise_narrative_mismatch_playbook_002, bank_enterprise_exact_match_playbook_003, bank_enterprise_narrative_mismatch_playbook_001 | 1.0000 | 0.5000 |
| be-r004-08 | 只凭摘要里几个关键词相似就匹配两笔流水，会有什么审计风险 | bank_enterprise_narrative_mismatch_playbook_002, pbc_small_payment_query_reply_002 | bank_enterprise_narrative_mismatch_playbook_005, bank_enterprise_narrative_mismatch_playbook_001, bank_enterprise_exact_match_playbook_005, bank_enterprise_duplicate_booking_playbook_004, bank_enterprise_fuzzy_match_playbook_002 | 0.0000 | 0.0000 |
| be-r004-10 | 客户名称和备注都不一致但流水号相同，复核闭环要记录哪些处理依据 | bank_enterprise_narrative_mismatch_advanced_005, pbc_epayment_guideline_002 | bank_enterprise_book_unrecorded_playbook_005, bank_enterprise_duplicate_booking_playbook_002, bank_enterprise_narrative_mismatch_playbook_001, bank_enterprise_exact_match_playbook_003, unionpay_reconciliation_faq_002 | 0.0000 | 0.0000 |
| be-r004-11 | 银行端摘要缺少合同信息，企业端凭证有合同号，应该如何补充核对 | bank_enterprise_narrative_mismatch_playbook_001, bank_enterprise_narrative_mismatch_playbook_002 | bank_enterprise_narrative_mismatch_playbook_004, bank_enterprise_amount_mismatch_playbook_001, bank_enterprise_bank_unarrived_playbook_005, bank_enterprise_amount_mismatch_playbook_003, bank_enterprise_bank_unarrived_playbook_001 | 0.0000 | 0.0000 |
| be-r004-12 | 代付代收场景下实际付款人和账面客户不同，是否需要转人工确认 | bank_enterprise_narrative_mismatch_playbook_003 | bank_enterprise_narrative_mismatch_advanced_003, bank_enterprise_book_unrecorded_advanced_003, bank_enterprise_book_unrecorded_advanced_005, bank_enterprise_amount_mismatch_playbook_004, bank_enterprise_bank_unarrived_playbook_003 | 0.0000 | 0.0000 |
