# RAG Quality Matrix Report

## Metadata

| Key | Value |
|---|---|
| Case Count | 120 |
| Top K | 5 |
| Real Backend Policy | `auto` |
| Evaluated At | 2026-07-08T14:47:32.825285Z |
| Best Real Backend | `bge_m3` |
| Best Real Mode | `dense` |

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
| bge_m3 | bge_m3 | measured | dense | No mode improved ranking metrics over dense baseline; RAG ha |

## Global Metrics by Backend × Mode

### dense | Backend | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| hash | 0.1750 | 0.3792 | 0.2808 | 0.2827 |
| bge_small | 0.5917 | 0.7875 | 0.7126 | 0.6948 |
| bge_m3 | 0.6333 | 0.8250 | 0.7353 | 0.7209 |

### hybrid | Backend | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| hash | 0.3333 | 0.5667 | 0.4678 | 0.4590 |
| bge_small | 0.5500 | 0.7875 | 0.6869 | 0.6850 |
| bge_m3 | 0.6167 | 0.7875 | 0.7221 | 0.7007 |

### hybrid_rerank | Backend | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| hash | 0.5333 | 0.7000 | 0.6443 | 0.6168 |
| bge_small | 0.5500 | 0.7167 | 0.6606 | 0.6336 |
| bge_m3 | 0.5667 | 0.7208 | 0.6731 | 0.6412 |

## Deltas vs Dense

### hash
| Mode | Δ Hit@1 | Δ MRR | Δ NDCG@5 |
| --- | ---: | ---: | ---: |
| hybrid | +0.1583 | +0.1869 | +0.1763 |
| hybrid_rerank | +0.3583 | +0.3635 | +0.3342 |

### bge_small
| Mode | Δ Hit@1 | Δ MRR | Δ NDCG@5 |
| --- | ---: | ---: | ---: |
| hybrid | -0.0417 | -0.0257 | -0.0098 |
| hybrid_rerank | -0.0417 | -0.0521 | -0.0612 |

### bge_m3
| Mode | Δ Hit@1 | Δ MRR | Δ NDCG@5 |
| --- | ---: | ---: | ---: |
| hybrid | -0.0167 | -0.0132 | -0.0202 |
| hybrid_rerank | -0.0667 | -0.0622 | -0.0798 |

## Miss Buckets

Best real backend: `bge_m3`

| Scenario | Error Type | Cases | Misses | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BANK_CLEARING | AMOUNT_MISMATCH | 10 | 2 | 0.5000 | 0.9000 | 0.6733 | 0.7019 |
| BANK_CLEARING | CLEARING_FILE_EXCEPTION | 10 | 3 | 0.6000 | 0.8000 | 0.7083 | 0.7071 |
| BANK_CLEARING | CUTOFF_T1 | 10 | 2 | 0.6000 | 0.9000 | 0.7167 | 0.7385 |
| BANK_CLEARING | QUERY_REPLY | 10 | 0 | 0.5000 | 1.0000 | 0.6833 | 0.7591 |
| BANK_CLEARING | REFERENCE_MATCH | 10 | 1 | 0.6000 | 0.9500 | 0.7583 | 0.8019 |
| BANK_CLEARING | SINGLE_SIDE_MISSING | 10 | 8 | 0.3000 | 0.3500 | 0.3833 | 0.3113 |
| BANK_ENTERPRISE | AMOUNT_MISMATCH | 12 | 3 | 0.6667 | 0.8333 | 0.7778 | 0.7373 |
| BANK_ENTERPRISE | BANK_UNARRIVED | 12 | 3 | 0.8333 | 0.8750 | 0.8958 | 0.8259 |
| BANK_ENTERPRISE | BOOK_UNRECORDED | 12 | 3 | 1.0000 | 0.8750 | 1.0000 | 0.8931 |
| BANK_ENTERPRISE | DUPLICATE_BOOKING | 12 | 0 | 0.8333 | 1.0000 | 0.8819 | 0.9043 |
| BANK_ENTERPRISE | NARRATIVE_NAME_MISMATCH | 12 | 6 | 0.4167 | 0.5833 | 0.5278 | 0.4990 |

### Miss Samples

#### BANK_CLEARING / AMOUNT_MISMATCH

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| bc-r002-06 | 清算对账时发现渠道金额比核心入账少，是否可以直接改核心账 | clearing_reference_match_playbook_001, clearing_amount_mismatch_playbook_001 | clearing_amount_mismatch_playbook_001, clearing_amount_mismatch_playbook_002, clearing_amount_mismatch_playbook_003, clearing_single_side_playbook_001, clearing_reconciliation_scope_001 | 1.0000 | 0.5000 |
| bc-r002-09 | 清算金额不平同时存在文件异常迹象，应该先定位金额规则还是文件完整性 | clearing_amount_mismatch_playbook_004, clearing_file_exception_playbook_001 | clearing_amount_mismatch_playbook_001, clearing_reconciliation_scope_001, clearing_amount_mismatch_playbook_002, clearing_file_exception_playbook_004, clearing_amount_mismatch_playbook_004 | 0.0000 | 0.5000 |

#### BANK_CLEARING / CLEARING_FILE_EXCEPTION

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| bc-r004-06 | 渠道上传的文件少了明细行，和单边缺失的边界怎么区分 | clearing_file_exception_playbook_001, clearing_file_exception_playbook_004 | clearing_amount_mismatch_playbook_004, clearing_file_exception_playbook_001, clearing_single_side_playbook_001, clearing_file_exception_playbook_003, clearing_single_side_playbook_002 | 0.0000 | 0.5000 |
| bc-r004-08 | 字段缺损导致参考号无法匹配，系统应怎样提示补充文件 | clearing_file_exception_playbook_002 | clearing_reference_match_playbook_002, clearing_file_exception_playbook_003, clearing_t1_supplement_playbook_002, clearing_reference_match_playbook_004, clearing_file_exception_playbook_001 | 0.0000 | 0.0000 |
| bc-r004-10 | 收到补发文件后，原异常批次如何做证据归档 | clearing_file_exception_playbook_004, clearing_query_reply_playbook_003 | clearing_file_exception_playbook_001, clearing_single_side_playbook_002, clearing_query_reply_playbook_004, clearing_query_reply_playbook_003, clearing_file_exception_playbook_003 | 0.0000 | 0.5000 |

#### BANK_CLEARING / CUTOFF_T1

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| bc-r003-08 | 日切窗口内金额一致但日期不同，自动审核能否直接判定通过 | clearing_cutoff_t1_guideline_002, clearing_reconciliation_scope_002 | clearing_cutoff_t1_guideline_001, clearing_t1_supplement_playbook_001, clearing_cutoff_t1_guideline_002, clearing_file_exception_playbook_004, clearing_t1_supplement_playbook_003 | 0.0000 | 0.5000 |
| bc-r003-10 | 夜间批处理延迟导致清算单边，系统应如何记录追溯结果 | clearing_cutoff_t1_guideline_001, clearing_t1_supplement_playbook_001 | clearing_single_side_playbook_002, clearing_single_side_playbook_001, clearing_cutoff_t1_guideline_001, clearing_t1_supplement_playbook_003, clearing_t1_supplement_playbook_004 | 0.0000 | 0.5000 |

#### BANK_CLEARING / REFERENCE_MATCH

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| bc-r006-09 | 一对多匹配后仍有尾差，应该转金额差异还是保留参考号匹配结论 | clearing_reference_match_playbook_003, clearing_amount_mismatch_playbook_001 | clearing_reference_match_playbook_001, clearing_reference_match_playbook_003, clearing_reference_match_playbook_004, clearing_reference_match_playbook_002, clearing_amount_mismatch_playbook_003 | 0.0000 | 0.5000 |

#### BANK_CLEARING / SINGLE_SIDE_MISSING

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| bc-r001-02 | 核心有流水而清算文件缺少明细，单边缺失时应保留哪些证据 | clearing_single_side_playbook_001, clearing_query_reply_playbook_001 | clearing_single_side_playbook_002, clearing_file_exception_playbook_001, clearing_amount_mismatch_playbook_004, clearing_t1_supplement_playbook_002, clearing_file_exception_playbook_002 | 0.0000 | 0.0000 |
| bc-r001-03 | 渠道侧返回成功但清算批次里没有这笔记录，是否需要发起查询 | clearing_single_side_playbook_001, clearing_query_reply_playbook_001 | clearing_query_reply_playbook_001, clearing_query_reply_playbook_003, clearing_query_reply_playbook_002, clearing_amount_mismatch_playbook_004, clearing_file_exception_playbook_001 | 1.0000 | 0.5000 |
| bc-r001-04 | 清算单边发生在普通工作日，不能用日切解释时下一步怎么处理 | clearing_single_side_playbook_001, clearing_query_reply_playbook_001 | clearing_cutoff_t1_guideline_001, clearing_single_side_playbook_001, clearing_t1_supplement_playbook_001, clearing_cutoff_t1_guideline_002, clearing_file_exception_playbook_004 | 0.0000 | 0.5000 |
| bc-r001-06 | 清算单边和文件缺失都可能导致少一笔，怎样区分交易缺失和文件异常 | clearing_single_side_playbook_001, clearing_file_exception_playbook_001 | clearing_file_exception_playbook_001, clearing_file_exception_playbook_003, clearing_file_exception_playbook_004, clearing_amount_mismatch_playbook_004, clearing_amount_mismatch_playbook_001 | 1.0000 | 0.5000 |
| bc-r001-07 | 核心入账已完成但渠道清算未出现，应如何判断是否在正常延迟范围内 | clearing_single_side_playbook_001 | clearing_amount_mismatch_playbook_001, clearing_file_exception_playbook_001, clearing_t1_supplement_playbook_003, clearing_query_reply_playbook_004, clearing_amount_mismatch_playbook_002 | 0.0000 | 0.0000 |

#### BANK_ENTERPRISE / AMOUNT_MISMATCH

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| be-r002-06 | 银行扣了手续费后到账净额小于企业应收金额，怎么区分普通金额差异和手续费差异 | bank_enterprise_amount_mismatch_playbook_002, bank_enterprise_amount_mismatch_advanced_005 | bank_enterprise_amount_mismatch_playbook_002, bank_enterprise_fee_tax_diff_playbook_001, bank_enterprise_fee_tax_diff_playbook_005, bank_enterprise_fee_tax_diff_playbook_002, bank_enterprise_fee_tax_diff_playbook_006 | 1.0000 | 0.5000 |
| be-r002-09 | 企业说差额是四舍五入造成的，银行流水金额仍不一致时如何处理 | bank_enterprise_amount_mismatch_playbook_005 | bank_enterprise_amount_mismatch_playbook_001, bank_enterprise_amount_mismatch_playbook_003, bank_enterprise_amount_mismatch_playbook_002, bank_enterprise_amount_mismatch_playbook_004, bank_enterprise_fee_tax_diff_playbook_001 | 0.0000 | 0.0000 |
| be-r002-12 | 双方都有流水但差额原因暂时说不清，审计结论需要包含哪些字段 | bank_enterprise_amount_mismatch_advanced_006, bank_enterprise_amount_mismatch_playbook_001 | unionpay_reconciliation_faq_001, bank_enterprise_amount_mismatch_playbook_001, unionpay_reconciliation_faq_002, bank_enterprise_narrative_mismatch_playbook_004, bank_enterprise_bank_unarrived_playbook_005 | 0.0000 | 0.5000 |

#### BANK_ENTERPRISE / BANK_UNARRIVED

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| be-r005-03 | 跨行转账在途导致银行未到账，规则要求保留哪些查询查复材料 | bank_enterprise_bank_unarrived_advanced_002, bank_enterprise_bank_unarrived_playbook_004 | bank_enterprise_bank_unarrived_playbook_002, bank_enterprise_bank_unarrived_advanced_002, bank_enterprise_bank_unarrived_advanced_003, bank_enterprise_bank_unarrived_playbook_005, bank_enterprise_bank_unarrived_playbook_003 | 0.0000 | 0.5000 |
| be-r005-07 | 只有企业账簿记录，没有银行回单，审核结论应要求补哪些字段 | bank_enterprise_bank_unarrived_playbook_003, bank_enterprise_bank_unarrived_playbook_005 | bank_enterprise_book_unrecorded_playbook_002, bank_enterprise_book_unrecorded_playbook_005, bank_enterprise_book_unrecorded_playbook_001, bank_enterprise_bank_unarrived_playbook_005, bank_enterprise_book_unrecorded_advanced_001 | 0.0000 | 0.5000 |
| be-r005-11 | 付款渠道返回处理中，企业已做账但银行未落账，是否可以等待 T+1 再确认 | bank_enterprise_bank_unarrived_playbook_002, bank_enterprise_bank_unarrived_playbook_004 | bank_enterprise_bank_unarrived_playbook_002, bank_enterprise_cross_period_playbook_004, bank_enterprise_bank_unarrived_advanced_002, bank_enterprise_bank_unarrived_playbook_001, bank_enterprise_bank_unarrived_playbook_003 | 1.0000 | 0.5000 |

#### BANK_ENTERPRISE / BOOK_UNRECORDED

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| be-r006-08 | 银行端出现一笔收入，企业凭证还没生成，应该要求业务部门补什么材料 | bank_enterprise_book_unrecorded_advanced_003, bank_enterprise_book_unrecorded_playbook_001 | bank_enterprise_book_unrecorded_advanced_003, bank_enterprise_bank_unarrived_playbook_003, bank_enterprise_bank_unarrived_playbook_005, bank_enterprise_bank_unarrived_playbook_001, bank_enterprise_book_unrecorded_advanced_002 | 1.0000 | 0.5000 |
| be-r006-09 | 月末银行已入账但企业下月才记账，应按企业未入账还是跨期处理 | bank_enterprise_book_unrecorded_advanced_004, bank_enterprise_cross_period_playbook_003 | bank_enterprise_cross_period_playbook_003, bank_enterprise_bank_unarrived_advanced_003, bank_enterprise_cross_period_playbook_002, bank_enterprise_cross_period_playbook_001, bank_enterprise_bank_unarrived_playbook_002 | 1.0000 | 0.5000 |
| be-r006-12 | 长期未补记的银行已入账项目，什么时候需要升级人工复核 | bank_enterprise_book_unrecorded_advanced_005, bank_enterprise_book_unrecorded_playbook_003 | bank_enterprise_book_unrecorded_advanced_005, bank_enterprise_bank_unarrived_advanced_004, bank_enterprise_amount_mismatch_advanced_006, bank_enterprise_bank_unarrived_advanced_005, bank_enterprise_book_unrecorded_advanced_001 | 1.0000 | 0.5000 |

#### BANK_ENTERPRISE / NARRATIVE_NAME_MISMATCH

| ID | Query | Expected Chunks | Retrieved Chunks | Hit@1 | Recall@5 |
| --- | --- | --- | --- | ---: | ---: |
| be-r004-05 | 付款用途字段和合同编号对不上，但金额相同，是否可以直接平账 | bank_enterprise_narrative_mismatch_playbook_004 | bank_enterprise_exact_match_playbook_003, bank_enterprise_amount_mismatch_playbook_004, bank_enterprise_exact_match_playbook_006, bank_enterprise_exact_match_playbook_002, bank_enterprise_exact_match_playbook_005 | 0.0000 | 0.0000 |
| be-r004-06 | 银行摘要包含特殊字符和英文缩写，企业名称是中文全称，规范化后还要保留什么证据 | bank_enterprise_narrative_mismatch_advanced_002, bank_enterprise_narrative_mismatch_playbook_005 | bank_enterprise_narrative_mismatch_advanced_002, bank_enterprise_narrative_mismatch_advanced_005, bank_enterprise_narrative_mismatch_playbook_002, bank_enterprise_narrative_mismatch_playbook_001, bank_enterprise_narrative_mismatch_playbook_004 | 1.0000 | 0.5000 |
| be-r004-08 | 只凭摘要里几个关键词相似就匹配两笔流水，会有什么审计风险 | bank_enterprise_narrative_mismatch_playbook_002, pbc_small_payment_query_reply_002 | bank_enterprise_narrative_mismatch_playbook_001, bank_enterprise_narrative_mismatch_advanced_004, bank_enterprise_exact_match_playbook_003, bank_enterprise_fuzzy_match_playbook_002, bank_enterprise_exact_match_playbook_001 | 0.0000 | 0.0000 |
| be-r004-10 | 客户名称和备注都不一致但流水号相同，复核闭环要记录哪些处理依据 | bank_enterprise_narrative_mismatch_advanced_005, pbc_epayment_guideline_002 | bank_enterprise_narrative_mismatch_advanced_005, bank_enterprise_duplicate_booking_playbook_002, bank_enterprise_duplicate_booking_playbook_005, bank_enterprise_book_unrecorded_playbook_005, bank_enterprise_book_unrecorded_playbook_002 | 1.0000 | 0.5000 |
| be-r004-11 | 银行端摘要缺少合同信息，企业端凭证有合同号，应该如何补充核对 | bank_enterprise_narrative_mismatch_playbook_001, bank_enterprise_narrative_mismatch_playbook_002 | bank_enterprise_narrative_mismatch_playbook_004, bank_enterprise_book_unrecorded_playbook_002, pbc_small_payment_query_reply_002, bank_enterprise_book_unrecorded_playbook_001, bank_enterprise_book_unrecorded_playbook_005 | 0.0000 | 0.0000 |
