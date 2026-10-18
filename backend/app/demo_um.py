"""Generate stable UM identifiers for local demo accounts only."""


def demo_um_no(account_id: str) -> str:
    if not account_id.startswith("DEMO-"):
        raise ValueError("UM 演示号只允许用于 DEMO- 测试账号")
    return f"UM-{account_id.removeprefix('DEMO-')}"
