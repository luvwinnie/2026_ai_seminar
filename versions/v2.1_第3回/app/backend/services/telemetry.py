"""観測（06_AI設計書.md §5）。

Langfuse への送信は第3回では作らない（後の回）。LANGFUSE_* が無いときは何もせず、done の trace_id は null。
"""

import logging
import os

logger = logging.getLogger(__name__)

LANGFUSE_KEYS = ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")


def langfuse_configured() -> bool:
    return all(os.environ.get(key) for key in LANGFUSE_KEYS)


def start_trace(question: str) -> str | None:
    """1問1トレースの ID を返す。第3回は記録しないので、いつも None。"""
    if langfuse_configured():
        logger.warning("LANGFUSE_* が設定されていますが、第3回では Langfuse へ送りません（後の回で作る）")
    return None
