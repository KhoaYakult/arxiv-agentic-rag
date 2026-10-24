"""
app/api/auth.py
================
Xac thuc API key don gian cho ban deploy cong khai (chua co tai khoan nguoi dung).

Cach dung: routes.py gan `require_api_key` lam dependency cho router "protected".
Neu settings.app_api_key rong (dev local) -> khong kiem tra gi. Neu co gia tri ->
moi request vao route protected phai gui header `X-API-Key` bang dung gia tri do,
neu khong tra 401. /health va /health/db KHONG qua dependency nay (load-balancer
va Vercel cron can goi duoc ma khong co key).
"""

import hmac

from fastapi import Header, HTTPException, status

from app.config import settings


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """FastAPI dependency: 401 neu app_api_key duoc bat ma header X-API-Key sai/thieu."""
    expected = settings.app_api_key
    if not expected:
        return

    # compare_digest chong timing attack; encode ra bytes vi no nem TypeError
    # neu so sanh str co ky tu non-ASCII.
    supplied = (x_api_key or "").encode("utf-8")
    if not hmac.compare_digest(supplied, expected.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thieu hoac sai header X-API-Key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
