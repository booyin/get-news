"""
统一配置加载：环境变量 + YAML
对应文档第十一节：业务代码不得直接写 Provider API，
所有配置通过这里集中管理。
"""
import os
from dotenv import load_dotenv

load_dotenv()

GATEWAY_API_KEY = os.getenv("GATEWAY_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_BASE_URL = f"https://api.cloudflare.com/client/v4/accounts/{os.getenv('CLOUDFLARE_ACCOUNT_ID', '')}/ai"

# 文档第十四节：免费模型硬闸门
COST_POLICY = {
    "allow_paid_models": False,
    "max_cost_usd_per_day": 0,
    "max_cost_usd_per_run": 0,
    "paid_fallback": False,
}

# 文档第二十节：禁止无限重试
MAX_RETRIES = {
    "openrouter": 1,
    "cloudflare": 1,  # 阶段9接入后启用
}

# 文档第十七节：Model Alias，客户端只认别名，不直接依赖真实模型名
MODEL_ALIASES = {
    "radar-fast": {
        "provider": "openrouter",
        "model": "cohere/north-mini-code:free",
        "fallback_provider": "cloudflare",
        "fallback_model": "@cf/meta/llama-3.2-3b-instruct",
    },
    "radar-smart": {
        "provider": "openrouter",
        "model": "inclusionai/ling-3.0-flash-fin:free",
        "fallback_provider": "cloudflare",
        "fallback_model": "@cf/zai-org/glm-4.7-flash",
    },
    "radar-free": {
        "provider": "openrouter",
        "model": "openrouter/free",
        "fallback_provider": "cloudflare",
        "fallback_model": "@cf/meta/llama-3.2-3b-instruct",
    },
}
