from bank_reconciliation_agent.core.security import create_access_token


def demo_bearer_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('demo_user')}"}
