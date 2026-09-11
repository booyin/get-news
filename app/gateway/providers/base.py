"""
Provider 抽象基类。
对应文档第十一节：业务层只调用 ai_gateway.chat(...)，
不得直接依赖具体 Provider 的 API 细节。
"""
from abc import ABC, abstractmethod


class ProviderResult:
    def __init__(self, success: bool, content: str = "", error: str = ""):
        self.success = success
        self.content = content
        self.error = error


class BaseProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def chat(self, messages: list[dict], model: str) -> ProviderResult:
        """调用上游模型，返回统一格式的结果"""
        raise NotImplementedError
