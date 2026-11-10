from hmac import compare_digest
from fastapi import Header, HTTPException
from ..system_config import get_setting

def require_integration_token(x_integration_token: str = Header(default="")) -> None:
    expected = get_setting("INTEGRATION_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="尚未配置系统对接令牌")
    if not compare_digest(x_integration_token, expected):
        raise HTTPException(status_code=401, detail="系统对接令牌无效")
