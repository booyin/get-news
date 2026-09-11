"""
AI Gateway 主入口。
对应文档第十五节：GET /health, GET /v1/models, POST /v1/chat/completions
对应文档第十八、十九节：Provider Router + 自动故障切换
"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import StreamingResponse
import json
import time
from pydantic import BaseModel
from app.gateway.auth import verify_gateway_key
from app.common.config import MODEL_ALIASES
from app.gateway.providers.openrouter import OpenRouterProvider
from app.gateway.providers.cloudflare import CloudflareProvider
from app.gateway.rate_limit import check_rate_limit
from app.gateway.usage import record_usage, get_today_usage

app = FastAPI(title="AI Gateway", version="0.1.0")
openrouter_provider = OpenRouterProvider()
cloudflare_provider = CloudflareProvider()

PROVIDERS = {
    "openrouter": openrouter_provider,
    "cloudflare": cloudflare_provider,
}


class ChatRequest(BaseModel):
    model: str
    messages: list[dict]
    stream: bool = False


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models(_: bool = Depends(verify_gateway_key)):
    data = []
    for alias, cfg in MODEL_ALIASES.items():
        data.append({
            "id": alias,
            "object": "model",
            "provider": cfg.get("provider"),
            "underlying_model": cfg.get("model", "auto"),
            "fallback_provider": cfg.get("fallback_provider"),
        })
    return {"object": "list", "data": data}


async def _resolve_chat(req: ChatRequest, client_name: str):
    """统一处理主力+兜底逻辑，返回 (result, used_fallback, alias_config)"""
    alias_config = MODEL_ALIASES.get(req.model)
    if not alias_config:
        raise HTTPException(status_code=400, detail=f"Unknown model alias: {req.model}")

    primary_provider = PROVIDERS.get(alias_config["provider"])
    primary_model = alias_config.get("model")
    result = await primary_provider.chat(req.messages, primary_model)

    used_fallback = False
    if not result.success:
        fallback_provider_name = alias_config.get("fallback_provider")
        fallback_model = alias_config.get("fallback_model")
        if fallback_provider_name and fallback_model:
            fallback_provider = PROVIDERS.get(fallback_provider_name)
            result = await fallback_provider.chat(req.messages, fallback_model)
            used_fallback = True

    provider_used = alias_config.get("fallback_provider") if used_fallback else alias_config.get("provider")
    record_usage(provider_used, client_name, result.success)

    if not result.success:
        raise HTTPException(status_code=502, detail=f"All providers failed. Last error: {result.error}")

    return result, used_fallback


def _sse_stream(content: str, model: str):
    """把完整内容包装成SSE分块流,兼容期望流式响应的客户端(如Cherry Studio)。
    注：我们的Provider本身不支持真流式，这里是一次性拿到完整内容后，
    伪装成流式协议格式吐出去，客户端体验上仍是逐字慢慢出现文字的效果需要
    进一步在Provider层实现真流式，这里先解决"客户端解析报错"的问题。
    """
    chunk_id = "chatcmpl-gw-stream"
    created = int(time.time())

    first_chunk = {
        "id": chunk_id, "object": "chat.completion.chunk", "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(first_chunk)}\n\n"

    content_chunk = {
        "id": chunk_id, "object": "chat.completion.chunk", "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(content_chunk)}\n\n"

    final_chunk = {
        "id": chunk_id, "object": "chat.completion.chunk", "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(
    req: ChatRequest,
    _: bool = Depends(verify_gateway_key),
    client_name: str = Depends(check_rate_limit),
):
    result, used_fallback = await _resolve_chat(req, client_name)

    if req.stream:
        return StreamingResponse(
            _sse_stream(result.content, req.model),
            media_type="text/event-stream",
        )

    return {
        "id": "chatcmpl-gw",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "used_fallback": used_fallback,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": result.content},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


@app.get("/v1")
async def v1_root():
    return {"status": "ok", "message": "AI Gateway v1 API. See /v1/models, /v1/chat/completions"}


@app.get("/v1/usage")
async def usage_today(_: bool = Depends(verify_gateway_key)):
    return get_today_usage()
