"""UIコントロール・イベントバス — チャットAIからブラウザ画面を操作するための橋渡し。

MCP ツール(ui_navigate / ui_open_report)が publish() したイベントを、
ブラウザ(フロントエンドの UiControlBridge)が GET /api/ui/events の SSE で受け取る。

- 購読は thread-safe な queue.Queue(MCP ツールは threadpool で実行されるため)
- 単一利用者のローカルアプリ前提なので、接続中の全ブラウザへブロードキャストする
"""
from __future__ import annotations

import queue
import threading

_subscribers: set[queue.Queue] = set()
_lock = threading.Lock()


def subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=100)
    with _lock:
        _subscribers.add(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _lock:
        _subscribers.discard(q)


def publish(event: dict) -> int:
    """イベントを全購読者へ配る。届いた購読者数を返す(0=画面が開かれていない)。"""
    with _lock:
        subs = list(_subscribers)
    delivered = 0
    for q in subs:
        try:
            q.put_nowait(event)
            delivered += 1
        except queue.Full:
            pass
    return delivered


def subscriber_count() -> int:
    with _lock:
        return len(_subscribers)
