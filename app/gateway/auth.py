"""
Gateway 鉴权。
对应文档第二十二、二十三节：
公网必须带 Authorization: Bearer <GATEWAY_API_KEY>
Provider Key 与 Gateway Key 严格分离，客户端永远拿不到 Provider Key。
"""
from fastapi import Header, HTTPException
from app.common.config import GATEWAY_API_KEY


async def verify_gateway_key(authorization: str = Header(default="")):
    if not GATEWAY_API_KEY:
        raise HTTPException(status_code=500, detail="Gateway key not configured")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    if token != GATEWAY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return True
