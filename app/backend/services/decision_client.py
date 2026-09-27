"""判断モデル(Jev)のクライアント — 文章ではなく「型付きの判断」を返すモデルを呼ぶ。

Jev(TypeSafe)は「状態(state)」と「質問(questions)」を受け取り、質問ごとに型付きの答えと確率を返す。
同じ state への質問は1回のリクエストで並列に評価される(1件の報告書に何問聞いても1往復)。

  Choice : 選択肢から1つ   → choice / probabilities / confidence
  Score  : 段階のどこか     → score(確率で重みづけした段階)/ legend / probabilities / confidence
  Noul   : 真である確率     → noul。0.5 は「中くらい」ではなく「五分五分」。段階を聞くなら Score を使う

使い方の原則(公式ドキュメントと各社の実践から):
  - コードで計算できることは聞かない。1問に1つの判断だけ。選択肢には「その他」を入れる
  - 閾値はプロンプトではなくコードに置き、自分のデータで決める(services/triage_thresholds.json)
  - confidence は「迷いの少なさ」で、正しさの保証ではない。重い判断は人か LLM へ回す
  - state は判断に要る項目だけにする(無関係な文が多いほど精度が落ちる)

接続先(環境変数):
  TYPESAFE_API_KEY があれば TypeSafe の System One API(https://api.typesafe.ai/v1/systemone)、
  無ければ OPENROUTER_API_KEY で OpenRouter の Decisions API(https://openrouter.ai/api/alpha/decisions)。
  DECISION_MODEL でモデルを指定。既定は版を固定したもの(OpenRouter は typesafe/jev-1.13-20260917、
  TypeSafe は jev-1.13.0)。閾値はこの版で測ったので、jev-latest のように動く名前は使わない(公式の Models の勧め)。
  DECISION_ZDR=1(既定)なら、OpenRouter にデータを残さない経路(provider.zdr)だけを使うよう頼む。
  DECISION_CACHE_TTL(秒、既定 600)の間は、同じモデル・同じ state・同じ質問の答えを使い回す(0 で無効)。
  ※ state は外部サービスに送られる。秘密情報や個人情報を入れない。ログにも本文は出さない。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/alpha/decisions"
_TYPESAFE_URL = os.getenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai").rstrip("/") + "/v1/systemone"
_RETRY_STATUS = {429, 500, 502, 503, 529}
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)   # 普段は 0.1〜0.5 秒。長く待たずに再試行する
_MAX_RETRY_AFTER = 10.0                           # Retry-After が長すぎるときの上限(秒)
PINNED = {"openrouter": "typesafe/jev-1.13-20260917", "typesafe": "jev-1.13.0"}


class DecisionError(RuntimeError):
    """判断モデルを呼べなかった(未設定・認証・検証エラー・再試行切れ)。"""


# ------------------------------------------------------------------ 質問の組み立て
def choice(instructions: str, criteria: dict[str, str | dict | None]) -> dict:
    """選択肢から1つ選ぶ質問。criteria は {選択肢名: 説明}。
    紛らわしい選択肢は、説明を {"what": 何か, "not_for": 何ではないか} のように形をそろえた dict にする
    (公式の Choice の勧め。フィールド名は API の決まりではなく、こちらで選ぶ)。"""
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def score(instructions: str, levels: list[str]) -> dict:
    """段階(2〜10)で評価する質問。levels は低い順の説明。"""
    return {"type": "score", "instructions": instructions, "criteria": levels}


def noul(instructions: str, true: str, false: str) -> dict:
    """真である確率を聞く質問。true / false はそれぞれの意味(instructions と向きをそろえる)。"""
    return {"type": "noul", "instructions": instructions, "criteria": {"true": true, "false": false}}


# ------------------------------------------------------------------ 答え
@dataclass
class Answer:
    type: str                        # choice / score / noul
    value: str | float               # choice の選択肢名、score の値、noul の確率
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float | None = None  # noul には無い
    legend: dict[str, str] | None = None

    @property
    def p_top(self) -> float:
        """1位の確率。確率が無ければ confidence で代える(テストの差し替えなど)。"""
        if self.type == "noul":
            return float(self.value)
        if self.probabilities:
            return float(max(self.probabilities.values()))
        return float(self.confidence or 0.0)

    @property
    def margin(self) -> float:
        """1位と2位の確率の差。confidence は1位の確率と選択肢の数だけで決まり、2位の近さを見ないので、
        採るかどうかはこの差も見る(confidence ≒ (選択肢の数×1位の確率−1)/(選択肢の数−1))。"""
        if self.type == "noul":
            return abs(2 * float(self.value) - 1)
        ps = sorted((float(v) for v in self.probabilities.values()), reverse=True)
        if not ps:
            return float(self.confidence or 0.0)
        return ps[0] - (ps[1] if len(ps) > 1 else 0.0)

    @property
    def top_level(self) -> int | None:
        """Score の最も確率の高い段階(0 始まり)。"""
        if self.type != "score" or not self.probabilities:
            return None
        return int(max(self.probabilities, key=self.probabilities.get))

    def to_dict(self) -> dict:
        d = {"type": self.type, "value": self.value, "probabilities": self.probabilities,
             "confidence": self.confidence}
        if self.legend:
            d["legend"] = self.legend
        return d


@dataclass
class DecisionResult:
    answers: dict[str, Answer]
    model: str
    latency_ms: int
    input_tokens: int = 0
    cost_usd: float = 0.0
    request_id: str | None = None
    cached: bool = False

    def meta(self) -> dict:
        return {"model": self.model, "latency_ms": self.latency_ms, "input_tokens": self.input_tokens,
                "cost_usd": self.cost_usd, "request_id": self.request_id, "cached": self.cached}


def _parse_answer(raw: dict) -> Answer:
    t = raw.get("type")
    if t == "choice":
        return Answer("choice", raw["choice"], raw.get("probabilities") or {}, raw.get("confidence"))
    if t == "score":
        return Answer("score", float(raw["score"]), raw.get("probabilities") or {}, raw.get("confidence"),
                      raw.get("legend"))
    if t == "noul":
        return Answer("noul", float(raw["noul"]))
    raise DecisionError(f"未知の答えの型: {t}")


# ------------------------------------------------------------------ 接続
def _endpoint() -> tuple[str, str, str] | None:
    """(url, api_key, model)。どちらのキーも無ければ None。"""
    ts = os.getenv("TYPESAFE_API_KEY", "").strip()
    if ts:
        return _TYPESAFE_URL, ts, os.getenv("DECISION_MODEL") or PINNED["typesafe"]
    orkey = os.getenv("OPENROUTER_API_KEY", "").strip()
    if orkey:
        return _OPENROUTER_URL, orkey, os.getenv("DECISION_MODEL") or PINNED["openrouter"]
    return None


def is_configured() -> bool:
    return _endpoint() is not None


def backend_name() -> str:
    ep = _endpoint()
    if ep is None:
        return "none"
    return "typesafe" if ep[0] == _TYPESAFE_URL else "openrouter"


def model_name() -> str | None:
    ep = _endpoint()
    return ep[2] if ep else None


def model_family(name: str | None) -> str | None:
    """版の比べ用。typesafe/jev-1.13-20260917・jev-1.13.0 → jev-1.13(同じ重み)。"""
    if not name:
        return None
    n = name.split("/")[-1].lstrip("~")
    parts = n.split("-")
    if len(parts) >= 2 and parts[0] == "jev":
        return "jev-" + ".".join(parts[1].split(".")[:2])
    return n


def zdr_enabled() -> bool:
    return os.getenv("DECISION_ZDR", "1").lower() not in ("0", "false", "no")


# 同じ入力の答えを短い間だけ使い回す(もう一度判定・提案の押し直しで、費用も答えの揺れも出さない)
_cache: OrderedDict[str, tuple[float, "DecisionResult"]] = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_MAX = 512


def _cache_ttl() -> float:
    try:
        return float(os.getenv("DECISION_CACHE_TTL", "600"))
    except ValueError:
        return 600.0


def _cache_key(model: str, state, questions: dict) -> str:
    raw = json.dumps([model, state, questions], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


# 呼び出しの記録(件数・トークン・費用)。/api/triage/status で見せる
_ledger = {"calls": 0, "errors": 0, "cache_hits": 0, "input_tokens": 0, "cost_usd": 0.0, "latency_ms_total": 0}
_ledger_lock = threading.Lock()


def ledger() -> dict:
    with _ledger_lock:
        d = dict(_ledger)
    d["avg_latency_ms"] = round(d["latency_ms_total"] / d["calls"]) if d["calls"] else None
    return d


def decide(state: str | dict | list, questions: dict[str, dict], *, retries: int = 3,
           session_id: str | None = None, use_cache: bool = True) -> DecisionResult:
    """state に対して questions をまとめて聞く(1往復)。429/529 等は指数バックオフで再試行する
    (Retry-After があればそれに従う)。同じ入力は DECISION_CACHE_TTL 秒のあいだ使い回す。"""
    ep = _endpoint()
    if ep is None:
        raise DecisionError("判断モデルのキー(TYPESAFE_API_KEY か OPENROUTER_API_KEY)がありません")
    url, key, model = ep
    ttl = _cache_ttl() if use_cache else 0
    ckey = _cache_key(model, state, questions) if ttl > 0 else None
    if ckey:
        with _cache_lock:
            hit = _cache.get(ckey)
            if hit and time.monotonic() - hit[0] < ttl:
                _cache.move_to_end(ckey)
                _ledger["cache_hits"] += 1
                r = hit[1]
                return DecisionResult(answers=r.answers, model=r.model, latency_ms=0, input_tokens=0,
                                      cost_usd=0.0, request_id=r.request_id, cached=True)
    body: dict = {"model": model, "state": state, "questions": questions}
    if url == _OPENROUTER_URL:
        if zdr_enabled():
            # データを残さない経路だけを使う。TypeSafe の経路は対応している(2026-09-27 に確認)
            body["provider"] = {"zdr": True, "data_collection": "deny"}
        if session_id:
            body["session_id"] = session_id[:256]   # 同じ判定の呼び出しをまとめて追える(本文ではない)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    delay = 0.5
    last_error = ""
    for attempt in range(retries + 1):
        t0 = time.monotonic()
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                r = client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}"
        else:
            if r.status_code == 200:
                data = r.json()
                ms = int((time.monotonic() - t0) * 1000)
                usage = data.get("usage") or {}
                result = DecisionResult(
                    answers={k: _parse_answer(v) for k, v in (data.get("answers") or {}).items()},
                    model=data.get("model", model),
                    latency_ms=ms,
                    input_tokens=int(usage.get("input_tokens") or 0),
                    cost_usd=float(usage.get("cost") or 0.0),
                    request_id=data.get("id") or data.get("request_id"),
                )
                with _ledger_lock:
                    _ledger["calls"] += 1
                    _ledger["input_tokens"] += result.input_tokens
                    _ledger["cost_usd"] += result.cost_usd
                    _ledger["latency_ms_total"] += ms
                # 本文(state)はログに出さない。追跡には request id を使う
                logger.info("decision ok model=%s questions=%d %dms id=%s",
                            result.model, len(questions), ms, result.request_id)
                if ckey:
                    with _cache_lock:
                        _cache[ckey] = (time.monotonic(), result)
                        _cache.move_to_end(ckey)
                        while len(_cache) > _CACHE_MAX:
                            _cache.popitem(last=False)
                return result
            last_error = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code not in _RETRY_STATUS:
                break
            wait = _retry_after(r.headers.get("retry-after"))
            if wait is not None and attempt < retries:
                time.sleep(wait)
                continue
        if attempt < retries:
            time.sleep(delay)
            delay *= 2
    with _ledger_lock:
        _ledger["errors"] += 1
    raise DecisionError(f"判断モデルの呼び出しに失敗しました({last_error})")


def _retry_after(value: str | None) -> float | None:
    """Retry-After(秒)を読む。無い・読めないときは None(指数バックオフに任せる)。"""
    if not value:
        return None
    try:
        return max(0.0, min(float(value), _MAX_RETRY_AFTER))
    except ValueError:
        return None
