"""
简易内存限流器：按客户端(X-Client-Name)做固定窗口限流。
对应文档第九节：1C1G硬件约束下不引入Redis等额外基础设施。
"""
import time
from collections import defaultdict
from fastapi import HTTPException, Header

# 每个客户端每分钟最多请求数
RATE_LIMIT_PER_MINUTE = 20

# {client_name: [timestamp1, timestamp2, ...]}
_request_log = defaultdict(list)


async def check_rate_limit(x_client_name: str = Header(default="unknown")):
    now = time.time()
    window_start = now - 60

    # 清理窗口外的旧记录
    _request_log[x_client_name] = [
        t for t in _request_log[x_client_name] if t > window_start
    ]

    if len(_request_log[x_client_name]) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for client '{x_client_name}': "
                    f"max {RATE_LIMIT_PER_MINUTE} requests/minute"
        )

    _request_log[x_client_name].append(now)
    return x_client_name
