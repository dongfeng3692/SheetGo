"""BaseTool — 所有工具的基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """所有工具的基类"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def parameters_schema(self) -> dict:
        """JSON Schema 格式的参数定义"""
        ...

    @property
    def definition(self) -> dict:
        """OpenAI function calling 格式的工具定义"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }

    @abstractmethod
    async def execute(self, **kwargs) -> Any: ...

    @property
    def safe_level(self) -> str:
        """安全级别: 'read' | 'write' | 'dangerous'"""
        return "read"

    @property
    def requires_confirmation(self) -> bool:
        """是否需要用户确认"""
        return self.safe_level != "read"
