"""
Cloudflare Workers AI Provider（兜底）。
对应文档第十八、十九节：自动故障切换。
认证方式与 OpenRouter 不同：Account ID + API Token，
调用格式是 /ai/run/{model}，返回结构也不是 OpenAI 格式，需要转换。
"""
import httpx
from .base import BaseProvider, ProviderResult
from app.common.config import CLOUDFLARE_BASE_URL, CLOUDFLARE_API_TOKEN, MAX_RETRIES


class CloudflareProvider(BaseProvider):
    name = "cloudflare"

    def __init__(self):
        self.api_token = CLOUDFLARE_API_TOKEN
        self.base_url = CLOUDFLARE_BASE_URL

    async def chat(self, messages: list[dict], model: str) -> ProviderResult:
        if not self.api_token:
            return ProviderResult(success=False, error="CLOUDFLARE_API_TOKEN not configured")

        url = f"{self.base_url}/run/{model}"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        # Cloudflare Workers AI 接受 OpenAI 风格的 messages 数组
        payload = {"messages": messages}

        max_retries = MAX_RETRIES.get("cloudflare", 1)
        last_error = ""

        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(max_retries + 1):
                try:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        if not data.get("success", False):
                            last_error = f"Cloudflare error: {data.get('errors')}"
                            continue
                        # Cloudflare 返回格式: {"result": {"response": "..."}, "success": true}
                        raw_content = data.get("result", {}).get("response", "")
                        if raw_content is None:
                            raw_content = ""
                        elif not isinstance(raw_content, str):
                            import json as _json
                            raw_content = _json.dumps(raw_content)
                        return ProviderResult(success=True, content=raw_content)
                    else:
                        last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                except httpx.RequestError as e:
                    last_error = f"Request error: {str(e)}"

        return ProviderResult(success=False, error=last_error)
