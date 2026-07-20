from __future__ import annotations

from dataclasses import dataclass
import uuid


@dataclass(slots=True)
class AppError(Exception):
    code: str
    user_message: str
    technical_detail: str = ""
    retryable: bool = False
    correlation_id: str = ""

    def __post_init__(self) -> None:
        self.correlation_id = self.correlation_id or str(uuid.uuid4())
        Exception.__init__(self, self.user_message)

    def display(self) -> str:
        suffix = "可稍后重试。" if self.retryable else "请联系技术支持。"
        return f"{self.user_message}\n{suffix}\n问题编号：{self.correlation_id[:8]}"


def normalize_error(exc: Exception, code: str = "CLIENT_OPERATION_FAILED") -> AppError:
    if isinstance(exc, AppError):
        return exc
    message = str(exc).lower()
    retryable = any(word in message for word in ("timeout", "timed out", "超时", "connect", "网络"))
    return AppError(code, "操作未能完成", str(exc), retryable)
