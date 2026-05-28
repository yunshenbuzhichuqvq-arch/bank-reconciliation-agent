---
source_name: 银联一窗办清算对账公开 FAQ 摘录
source_url: https://pcs.unionpay.com/ycb/pcweb/NEWbzzx/cjwt/ywcp/jcyw/dj/FKYW/art/2024/art_bc798a9bee334e5d8a19286b66bbfe61.html
source_type: html_excerpt
business_tags: amount_mismatch, single_side_missing, clearing_file_exception
---

# 银联一窗办清算对账公开 FAQ 摘录

## 清算文件流水与资金核对不平

公开 FAQ 提到，清算文件流水与资金核对不平、对账文件缺失、流水缺失等问题属于清算文件异常处理范围，需要通过指定服务路径提交处理。

本项目抽象规则：`AMOUNT_MISMATCH` 表示同一 `flow_id` 在银行端和清算端均存在，但标准金额不一致；系统应保留银行端金额、清算端金额和差异金额，并进入待 AI 审计。

## 对账文件或流水缺失

对账文件缺失或流水缺失会导致双端无法闭环核验。此类异常不能用单侧数据直接确认平账，需要保留缺失侧、来源文件和处理路径。

本项目抽象规则：`SINGLE_SIDE_MISSING` 需要输出缺失方向、已有侧金额和来源依据；后续可进入查询查复、T+1 追溯或人工复核。
