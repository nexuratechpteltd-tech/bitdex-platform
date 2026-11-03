"""
BITDEX Market Data Integrity Service (Phase 8/9)
================================================
Single source of truth for *verifiable* live market data.

Feeds
-----
* Binance Spot  — WebSocket combined stream `<sym>@ticker` (24h rolling stats), auto-reconnect.
* Bitget Spot   — WebSocket v2 public `ticker` channel, auto-reconnect + 25s ping.
* CoinGecko     — REST `/coins/markets` polling (market capitalisation), rate-limit aware.
* FX / Metals   — Yahoo Finance chart endpoint via forex_market_data (indicative composite), polled.

Every record carries: symbol, provider, market/venue, price, provider timestamp, server receipt
timestamp, last successful update, data age, connection state and verification status, and is
classified LIVE / DELAYED / STALE / UNAVAILABLE.  Stale data is never reported as LIVE, and no
price is ever substituted from another instrument or provider.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

import httpx

try:
    import websockets  # type: ignore
except Exception:  # pragma: no cover
    websockets = None

logger = logging.getLogger("market_integrity")

TRACKED_CRYPTO = [
    "BTC", "ETH", "SOL", "BNB", "ADA", "DOGE", "XRP", "AVAX",
    "DOT", "LINK", "NEAR", "LTC", "ATOM", "UNI", "APT", "BCH",
]
COINGECKO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "ADA": "cardano", "DOGE": "dogecoin", "XRP": "ripple", "AVAX": "avalanche-2",
    "DOT": "polkadot", "LINK": "chainlink", "NEAR": "near", "LTC": "litecoin",
    "ATOM": "cosmos", "UNI": "uniswap", "APT": "aptos", "BCH": "bitcoin-cash",
}
TRACKED_FX = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "USD/CHF", "XAU/USD", "XAG/USD"]

# Configurable thresholds (seconds / percent)
CRYPTO_LIVE_MAX_SEC = float(os.getenv("MD_CRYPTO_LIVE_MAX_SEC", "15"))
CRYPTO_DELAYED_MAX_SEC = float(os.getenv("MD_CRYPTO_DELAYED_MAX_SEC", "120"))
MCAP_LIVE_MAX_SEC = float(os.getenv("MD_MCAP_LIVE_MAX_SEC", "300"))
MCAP_DELAYED_MAX_SEC = float(os.getenv("MD_MCAP_DELAYED_MAX_SEC", "1800"))
DISCREPANCY_THRESHOLD_PCT = float(os.getenv("MD_DISCREPANCY_THRESHOLD_PCT", "0.50"))
COINGECKO_POLL_SEC = float(os.getenv("MD_COINGECKO_POLL_SEC", "120"))
FX_POLL_SEC = float(os.getenv("MD_FX_POLL_SEC", "60"))


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


def classify(age: Optional[float], live_max: float, delayed_max: float, connected: bool = True) -> str:
    if age is None:
        return "UNAVAILABLE"
    if age <= live_max and connected:
        return "LIVE"
    if age <= delayed_max:
        return "DELAYED"
    return "STALE"


class ProviderState:
    def __init__(self, name: str, transport: str, endpoint: str):
        self.name = name
        self.transport = transport
        self.endpoint = endpoint
        self.connection_state = "INITIALISING"
        self.connected_since: Optional[float] = None
        self.last_message_ts: Optional[float] = None
        self.last_success_ts: Optional[float] = None
        self.messages_received = 0
        self.reconnects = 0
        self.rate_limit_events = 0
        self.failures: Deque[Dict[str, Any]] = deque(maxlen=20)
        self.subscriptions: List[str] = []

    def fail(self, kind: str, detail: str) -> None:
        # never store credentials — only exception class / HTTP status
        self.failures.append({"ts_utc": _iso(time.time()), "kind": kind, "detail": detail[:200]})

    def to_dict(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "provider": self.name,
            "transport": self.transport,
            "endpoint": self.endpoint,
            "connection_state": self.connection_state,
            "connected_since_utc": _iso(self.connected_since),
            "active_subscriptions": len(self.subscriptions),
            "subscriptions": self.subscriptions,
            "messages_received": self.messages_received,
            "last_message_utc": _iso(self.last_message_ts),
            "last_message_age_sec": round(now - self.last_message_ts, 1) if self.last_message_ts else None,
            "last_successful_update_utc": _iso(self.last_success_ts),
            "reconnects": self.reconnects,
            "rate_limit_events": self.rate_limit_events,
            "recent_failures": list(self.failures),
        }


class MarketIntegrityService:
    def __init__(self) -> None:
        self.records: Dict[str, Dict[str, Any]] = {}  # key = f"{provider}:{symbol}"
        self.providers: Dict[str, ProviderState] = {
            "binance_spot": ProviderState("binance_spot", "websocket", "wss://stream.binance.com:9443/stream"),
            "bitget_spot": ProviderState("bitget_spot", "websocket", "wss://ws.bitget.com/v2/ws/public"),
            "coingecko": ProviderState("coingecko", "rest_poll", "https://api.coingecko.com/api/v3/coins/markets"),
            "yahoo_fx_metals": ProviderState("yahoo_fx_metals", "rest_poll", "https://query1.finance.yahoo.com/v8/finance/chart"),
        }
        self._tasks: List[asyncio.Task] = []
        self.started_at: Optional[float] = None

    # ── lifecycle ──────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._tasks:
            return
        self.started_at = time.time()
        loop = asyncio.get_event_loop()
        self._tasks = [
            loop.create_task(self._binance_ws()),
            loop.create_task(self._bitget_ws()),
            loop.create_task(self._coingecko_poll()),
            loop.create_task(self._fx_poll()),
            loop.create_task(self._watchdog()),
        ]
        logger.info("Market integrity service started")

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks = []

    # ── record helpers ─────────────────────────────────────────────────────
    def _put(self, provider: str, symbol: str, market: str, price: Optional[float],
             provider_ts: Optional[float], extra: Optional[Dict[str, Any]] = None) -> None:
        now = time.time()
        rec = self.records.get(f"{provider}:{symbol}", {})
        rec.update({
            "symbol": symbol,
            "provider": provider,
            "market": market,
            "price": price,
            "provider_ts": provider_ts,
            "receipt_ts": now,
            "last_success_ts": now if price is not None else rec.get("last_success_ts"),
        })
        if extra:
            rec.update(extra)
        self.records[f"{provider}:{symbol}"] = rec

    def _thresholds(self, provider: str):
        if provider == "coingecko":
            return MCAP_LIVE_MAX_SEC, MCAP_DELAYED_MAX_SEC
        if provider == "yahoo_fx_metals":
            return 20.0, 900.0
        return CRYPTO_LIVE_MAX_SEC, CRYPTO_DELAYED_MAX_SEC

    def view(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        now = time.time()
        prov = rec["provider"]
        pstate = self.providers.get(prov)
        connected = bool(pstate and pstate.connection_state in ("CONNECTED", "POLLING"))
        ref_ts = rec.get("provider_ts") or rec.get("receipt_ts")
        age = round(now - ref_ts, 1) if ref_ts and rec.get("price") is not None else None
        live_max, delayed_max = self._thresholds(prov)
        state = classify(age, live_max, delayed_max, connected)
        if prov == "yahoo_fx_metals" and rec.get("market_open") is False and state == "LIVE":
            state = "DELAYED"
        out = {
            "symbol": rec["symbol"],
            "provider": prov,
            "market": rec.get("market"),
            "price": rec.get("price") if state != "UNAVAILABLE" else None,
            "provider_timestamp_utc": _iso(rec.get("provider_ts")),
            "server_receipt_utc": _iso(rec.get("receipt_ts")),
            "last_successful_update_utc": _iso(rec.get("last_success_ts")),
            "data_age_sec": age,
            "connection_state": pstate.connection_state if pstate else "UNKNOWN",
            "data_state": state,
            "verification_status": "VERIFIED_PROVIDER_FEED" if state == "LIVE" else (
                "PROVIDER_FEED_NOT_CURRENT" if state in ("DELAYED", "STALE") else "NO_DATA"),
        }
        for k in ("change_24h_pct", "volume_24h_base", "volume_24h_quote", "high_24h", "low_24h",
                  "bid", "ask", "market_cap_usd", "market_cap_rank", "bid_ask_derivation", "market_open"):
            if k in rec:
                out[k] = rec[k] if state != "UNAVAILABLE" else None
        return out

    # ── Binance WebSocket ──────────────────────────────────────────────────
    async def _binance_ws(self) -> None:
        p = self.providers["binance_spot"]
        streams = "/".join(f"{s.lower()}usdt@ticker" for s in TRACKED_CRYPTO)
        url = f"{p.endpoint}?streams={streams}"
        p.subscriptions = [f"{s}USDT@ticker" for s in TRACKED_CRYPTO]
        backoff = 1.0
        while True:
            try:
                p.connection_state = "CONNECTING"
                async with websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=2**22) as ws:
                    p.connection_state = "CONNECTED"
                    p.connected_since = time.time()
                    backoff = 1.0
                    async for raw in ws:
                        msg = json.loads(raw)
                        d = msg.get("data") or {}
                        if d.get("e") != "24hrTicker":
                            continue
                        p.messages_received += 1
                        p.last_message_ts = p.last_success_ts = time.time()
                        sym = d["s"]
                        self._put("binance_spot", sym, "Binance Spot", float(d["c"]), int(d["E"]) / 1000.0, {
                            "change_24h_pct": float(d["P"]),
                            "volume_24h_base": float(d["v"]),
                            "volume_24h_quote": float(d["q"]),
                            "high_24h": float(d["h"]),
                            "low_24h": float(d["l"]),
                            "bid": float(d["b"]) if d.get("b") else None,
                            "ask": float(d["a"]) if d.get("a") else None,
                        })
            except asyncio.CancelledError:
                raise
            except Exception as e:  # reconnect with exponential backoff
                p.connection_state = "RECONNECTING"
                p.reconnects += 1
                if "429" in str(e) or "418" in str(e):
                    p.rate_limit_events += 1
                p.fail("websocket", f"{type(e).__name__}: {str(e)[:120]}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    # ── Bitget WebSocket ───────────────────────────────────────────────────
    async def _bitget_ws(self) -> None:
        p = self.providers["bitget_spot"]
        args = [{"instType": "SPOT", "channel": "ticker", "instId": f"{s}USDT"} for s in TRACKED_CRYPTO]
        p.subscriptions = [a["instId"] + "@ticker" for a in args]
        backoff = 1.0
        while True:
            try:
                p.connection_state = "CONNECTING"
                async with websockets.connect(p.endpoint, ping_interval=None, max_size=2**22) as ws:
                    await ws.send(json.dumps({"op": "subscribe", "args": args}))
                    p.connection_state = "CONNECTED"
                    p.connected_since = time.time()
                    backoff = 1.0

                    async def pinger():
                        while True:
                            await asyncio.sleep(25)
                            await ws.send("ping")

                    ping_task = asyncio.create_task(pinger())
                    try:
                        async for raw in ws:
                            if raw == "pong":
                                continue
                            msg = json.loads(raw)
                            if msg.get("event") == "error":
                                p.fail("subscribe", str(msg.get("msg"))[:150])
                                continue
                            for d in msg.get("data") or []:
                                if "lastPr" not in d:
                                    continue
                                p.messages_received += 1
                                p.last_message_ts = p.last_success_ts = time.time()
                                ts = int(d.get("ts") or msg.get("ts") or 0) / 1000.0 or None
                                self._put("bitget_spot", d["instId"], "Bitget Spot", float(d["lastPr"]), ts, {
                                    "change_24h_pct": round(float(d.get("change24h") or 0) * 100, 3) if d.get("change24h") not in (None, "") else None,
                                    "volume_24h_base": float(d["baseVolume"]) if d.get("baseVolume") else None,
                                    "volume_24h_quote": float(d["quoteVolume"]) if d.get("quoteVolume") else None,
                                    "high_24h": float(d["high24h"]) if d.get("high24h") else None,
                                    "low_24h": float(d["low24h"]) if d.get("low24h") else None,
                                    "bid": float(d["bidPr"]) if d.get("bidPr") else None,
                                    "ask": float(d["askPr"]) if d.get("askPr") else None,
                                })
                    finally:
                        ping_task.cancel()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                p.connection_state = "RECONNECTING"
                p.reconnects += 1
                p.fail("websocket", f"{type(e).__name__}: {str(e)[:120]}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    # ── CoinGecko market cap ───────────────────────────────────────────────
    async def _coingecko_poll(self) -> None:
        p = self.providers["coingecko"]
        ids = ",".join(COINGECKO_IDS.values())
        rev = {v: k for k, v in COINGECKO_IDS.items()}
        p.subscriptions = [f"{k}:market_cap" for k in COINGECKO_IDS]
        api_key = os.getenv("COINGECKO_API_KEY")  # optional demo/pro key, never logged
        headers = {"accept": "application/json"}
        if api_key:
            headers["x-cg-demo-api-key"] = api_key
        delay = COINGECKO_POLL_SEC
        while True:
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    r = await c.get(p.endpoint, params={"vs_currency": "usd", "ids": ids}, headers=headers)
                if r.status_code == 429:
                    p.rate_limit_events += 1
                    p.connection_state = "RATE_LIMITED"
                    p.fail("http", "429 rate limited")
                    delay = min(delay * 2, 900)
                elif r.status_code != 200:
                    p.connection_state = "DEGRADED"
                    p.fail("http", f"HTTP {r.status_code}")
                else:
                    p.connection_state = "POLLING"
                    p.messages_received += 1
                    p.last_message_ts = p.last_success_ts = time.time()
                    delay = COINGECKO_POLL_SEC
                    for row in r.json():
                        sym = rev.get(row.get("id"))
                        if not sym:
                            continue
                        lu = row.get("last_updated")
                        pts = datetime.fromisoformat(lu.replace("Z", "+00:00")).timestamp() if lu else None
                        self._put("coingecko", sym, "CoinGecko aggregate (USD)", row.get("current_price"), pts, {
                            "market_cap_usd": row.get("market_cap"),
                            "market_cap_rank": row.get("market_cap_rank"),
                            "change_24h_pct": row.get("price_change_percentage_24h"),
                            "volume_24h_quote": row.get("total_volume"),
                        })
            except asyncio.CancelledError:
                raise
            except Exception as e:
                p.connection_state = "DEGRADED"
                p.fail("http", type(e).__name__)
            await asyncio.sleep(delay)

    # ── FX / metals polling ────────────────────────────────────────────────
    async def _fx_poll(self) -> None:
        from .forex_market_data import forex_market_data
        p = self.providers["yahoo_fx_metals"]
        p.subscriptions = list(TRACKED_FX)
        while True:
            ok = 0
            for sym in TRACKED_FX:
                try:
                    t = await forex_market_data.fetch_ticker(sym)
                    pts = None
                    if t.get("provider_ts_utc"):
                        pts = datetime.fromisoformat(t["provider_ts_utc"]).timestamp()
                    sess = t.get("session") or {}
                    self._put("yahoo_fx_metals", sym, "Yahoo Finance FX/metals composite (indicative)", t.get("mid"), pts, {
                        "change_24h_pct": t.get("change_24h"),
                        "high_24h": t.get("high_24h"),
                        "low_24h": t.get("low_24h"),
                        "bid_ask_derivation": t.get("bid_ask_derivation"),
                        "market_open": bool(sess.get("market_open", True)),
                    })
                    ok += 1
                except Exception as e:
                    p.fail("http", f"{sym}: {type(e).__name__}")
                    rec = self.records.get(f"yahoo_fx_metals:{sym}")
                    if rec is None:
                        self._put("yahoo_fx_metals", sym, "Yahoo Finance FX/metals composite (indicative)", None, None)
            if ok:
                p.connection_state = "POLLING"
                p.messages_received += ok
                p.last_message_ts = p.last_success_ts = time.time()
            else:
                p.connection_state = "DEGRADED"
            await asyncio.sleep(FX_POLL_SEC)

    # ── Watchdog: flag silent sockets so they are reconnected ─────────────
    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(10)
            now = time.time()
            for name in ("binance_spot", "bitget_spot"):
                p = self.providers[name]
                if p.connection_state == "CONNECTED" and p.last_message_ts and now - p.last_message_ts > 60:
                    p.connection_state = "SILENT"
                    p.fail("watchdog", "no messages for >60s")

    # ── public API ─────────────────────────────────────────────────────────
    def quotes(self, provider: Optional[str] = None, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        out = []
        wanted = {s.upper().replace("/", "") for s in symbols} if symbols else None
        for rec in self.records.values():
            if provider and rec["provider"] != provider:
                continue
            if wanted and rec["symbol"].upper().replace("/", "") not in wanted \
                    and rec["symbol"].upper().replace("USDT", "") not in wanted:
                continue
            out.append(self.view(rec))
        return sorted(out, key=lambda r: (r["provider"], r["symbol"]))

    def get(self, provider: str, symbol: str) -> Optional[Dict[str, Any]]:
        rec = self.records.get(f"{provider}:{symbol}")
        return self.view(rec) if rec else None

    def discrepancies(self) -> List[Dict[str, Any]]:
        """Binance vs Bitget last-trade comparison. Only LIVE-vs-LIVE pairs are judged; small
        last-trade / bid-ask differences under the configurable threshold are normal, not errors."""
        out = []
        for s in TRACKED_CRYPTO:
            sym = f"{s}USDT"
            a, b = self.get("binance_spot", sym), self.get("bitget_spot", sym)
            if not a or not b or a["price"] is None or b["price"] is None:
                out.append({"symbol": sym, "status": "NOT_COMPARABLE",
                            "reason": "one or both providers have no current quote"})
                continue
            if a["data_state"] != "LIVE" or b["data_state"] != "LIVE":
                out.append({"symbol": sym, "status": "NOT_COMPARABLE",
                            "reason": f"binance={a['data_state']} bitget={b['data_state']}"})
                continue
            diff = abs(a["price"] - b["price"]) / a["price"] * 100
            out.append({
                "symbol": sym,
                "binance_price": a["price"], "bitget_price": b["price"],
                "binance_provider_ts_utc": a["provider_timestamp_utc"],
                "bitget_provider_ts_utc": b["provider_timestamp_utc"],
                "difference_percent": round(diff, 4),
                "threshold_percent": DISCREPANCY_THRESHOLD_PCT,
                "status": "ALIGNED" if diff <= DISCREPANCY_THRESHOLD_PCT else "DISCREPANCY_WARNING",
            })
        return out

    def monitor(self) -> Dict[str, Any]:
        all_quotes = self.quotes()
        by_state: Dict[str, int] = {"LIVE": 0, "DELAYED": 0, "STALE": 0, "UNAVAILABLE": 0}
        for q in all_quotes:
            by_state[q["data_state"]] = by_state.get(q["data_state"], 0) + 1
        disc = self.discrepancies()
        stale = [q for q in all_quotes if q["data_state"] in ("STALE", "UNAVAILABLE")]
        provider_states = [p.connection_state for p in self.providers.values()]
        if all(s in ("CONNECTED", "POLLING") for s in provider_states) and not stale:
            health = "OPTIMAL"
        elif any(s in ("CONNECTED", "POLLING") for s in provider_states):
            health = "DEGRADED"
        else:
            health = "OFFLINE"
        return {
            "status": "SUCCESS",
            "timestamp_utc": _iso(time.time()),
            "service_started_utc": _iso(self.started_at),
            "overall_health": health,
            "thresholds": {
                "crypto_live_max_sec": CRYPTO_LIVE_MAX_SEC,
                "crypto_delayed_max_sec": CRYPTO_DELAYED_MAX_SEC,
                "market_cap_live_max_sec": MCAP_LIVE_MAX_SEC,
                "market_cap_delayed_max_sec": MCAP_DELAYED_MAX_SEC,
                "fx_live_max_sec": 20.0,
                "fx_delayed_max_sec": 900.0,
                "cross_provider_discrepancy_pct": DISCREPANCY_THRESHOLD_PCT,
            },
            "providers": {k: v.to_dict() for k, v in self.providers.items()},
            "data_state_counts": by_state,
            "stale_or_unavailable": stale,
            "cross_provider_discrepancies": disc,
            "discrepancy_warnings": [d for d in disc if d.get("status") == "DISCREPANCY_WARNING"],
            "api_failures": {k: list(v.failures) for k, v in self.providers.items() if v.failures},
            "rate_limits": {k: v.rate_limit_events for k, v in self.providers.items()},
            "quotes": all_quotes,
        }


market_integrity = MarketIntegrityService()
