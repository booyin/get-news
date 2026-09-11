"""
Radar 业务代码调用 AI Gateway 的统一封装。
对应文档第57节：Radar只保存 GATEWAY_URL + GATEWAY_API_KEY，
不直接依赖 NVIDIA_API_KEY / OPENROUTER_API_KEY。
对应文档第11节：业务层只能调用 ai_gateway.chat(...)，不得直接写Provider API。
"""
import httpx
import json
import os
from dotenv import load_dotenv

load_dotenv()

GATEWAY_URL = "http://127.0.0.1:8000/v1"
GATEWAY_API_KEY = os.getenv("GATEWAY_API_KEY", "")


def gateway_chat(prompt: str, model: str = "radar-fast", timeout: float = 30.0) -> dict:
    """
    调用本地Gateway，返回 {"success": bool, "content": str, "error": str, "used_fallback": bool}
    """
    if not GATEWAY_API_KEY:
        return {"success": False, "content": "", "error": "GATEWAY_API_KEY not configured", "used_fallback": False}

    try:
        resp = httpx.post(
            f"{GATEWAY_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {GATEWAY_API_KEY}",
                "Content-Type": "application/json",
                "X-Client-Name": "radar",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return {"success": False, "content": "", "error": f"HTTP {resp.status_code}: {resp.text[:200]}", "used_fallback": False}

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        used_fallback = data.get("used_fallback", False)
        return {"success": True, "content": content, "error": "", "used_fallback": used_fallback}

    except Exception as e:
        return {"success": False, "content": "", "error": str(e), "used_fallback": False}
