from typing import Literal

from faker import Faker

NarrativeTier = Literal["formal", "colloquial", "ambiguous"]

FORMAL = (
    "支付本月采购货款",
    "收到客户合同款项",
    "缴纳办公场地租金",
    "支付供应商服务费",
    "收到项目阶段验收款",
    "支付员工差旅报销款",
    "缴纳渠道结算手续费",
    "支付设备维护费用",
    "收到年度框架协议款",
    "支付物流运输费用",
)

COLLOQUIAL = (
    "张经理垫付款报一下",
    "小王那笔材料钱",
    "上周那单尾款到了",
    "先转给李总周转",
    "门店今天的款补上",
    "老客户回款一笔",
    "供应商催的那笔",
    "老板说先付一半",
    "上次活动费用结掉",
    "财务确认过的款",
)

AMBIGUOUS = (
    "退款",
    "往来款",
    "报销",
    "临时款项",
    "差额调整",
    "补付款",
    "尾款",
    "代收代付",
    "费用冲正",
    "账务调整",
)

_NARRATIVES: dict[NarrativeTier, tuple[str, ...]] = {
    "formal": FORMAL,
    "colloquial": COLLOQUIAL,
    "ambiguous": AMBIGUOUS,
}


def sample_narrative(tier: NarrativeTier, faker: Faker) -> str:
    return faker.random_element(_NARRATIVES[tier])
