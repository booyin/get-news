"""
OpenRouter Provider。
对应文档第十三、十四节：
- 默认只用免费模型（:free 后缀 或 pricing 字段为0）
- 不得自动切换到收费模型
"""
import httpx
from .base import BaseProvider, ProviderResult
from app.common.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, MAX_RETRIES


class OpenRouterProvider(BaseProvider):
    name = "openrouter"

    def __init__(self):
        self.api_key = OPENROUTER_API_KEY
        self.base_url = OPENROUTER_BASE_URL
        self._free_models_cache = None

    async def chat(self, messages: list[dict], model: str) -> ProviderResult:
        if not self.api_key:
            return ProviderResult(success=False, error="OPENROUTER_API_KEY not configured")

        # 硬闸门：只允许调用 :free 模型（对应文档第十四节）
        if not model.endswith(":free") and model != "openrouter/free":
            return ProviderResult(
                success=False,
                error=f"Refused: '{model}' is not a free model. Cost policy forbids paid calls."
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": model, "messages": messages}

        max_retries = MAX_RETRIES.get("openrouter", 1)
        last_error = ""

        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(max_retries + 1):
                try:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_content = data["choices"][0]["message"].get("content")
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

    async def list_models(self) -> list[dict]:
        """拉取 OpenRouter 全部模型列表"""
        url = f"{self.base_url}/models"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json().get("data", [])

    async def list_free_models(self) -> list[str]:
        """筛出真正免费的模型ID（pricing字段为0，比只认:free后缀更可靠）"""
        models = await self.list_models()
        free_ids = []
        for m in models:
            pricing = m.get("pricing", {})
            try:
                if float(pricing.get("prompt", "1")) == 0 and float(pricing.get("completion", "1")) == 0:
                    free_ids.append(m["id"])
            except (ValueError, TypeError):
                continue
        return free_ids
