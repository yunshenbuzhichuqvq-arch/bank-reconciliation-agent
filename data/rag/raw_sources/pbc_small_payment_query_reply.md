---
source_name: 小额支付系统业务处理手续公开材料摘录
source_url: https://www.pbc.gov.cn/eportal/fileDir/history_file/files/att_19041_2.pdf
source_type: pdf_excerpt
business_tags: single_side_missing, query_reply, error_handling
---

# 小额支付系统业务处理手续公开材料摘录

## 单笔业务查询查复

小额支付系统业务处理中，对存在疑问或差错的单笔业务，需要通过查询查复机制核实。查询查复强调发现疑问应查询，收到查询应回复，回复内容应详细、明确。

本项目抽象规则：`SINGLE_SIDE_MISSING` 代表银行端或清算端只有一侧存在流水，不能直接自动平账，应先进入待人工复核或后续追溯查询。

## 原始凭证和业务要素核对

涉及业务要素更正或差错确认时，应以原始凭证、原始交易记录和支付业务要素为依据。系统不能只根据摘要相似或单侧金额推断最终处理结论。

本项目抽象规则：单边缺失、跨日切和疑似漏记账需要保留原始流水号、金额、交易时间、渠道和来源文件。
