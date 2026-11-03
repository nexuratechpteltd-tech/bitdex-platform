"""
BITDEX Binance USD(S)-M Futures Adapter
========================================
Dedicated adapter for Binance USD(S)-M Futures (Testnet & Mainnet).
Completely separate from Binance Spot implementation.

Safety Controls:
- Hard-locked live trading: live_trading_locked=True prevents any Mainnet execution.
- Strict isolation of Testnet (https://testnet.binancefuture.com) vs Mainnet (https://fapi.binance.com).
- Dynamic clock skew synchronization with automatic retry on -1021.
- Error normalization for rate limits (429, -1003), insufficient margin (-2019), and auth failures.
- Symbol filter parsing and rounding (tickSize, stepSize, minNotional).
"""

import time
import hmac
import hashlib
import math
import logging
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlencode
import httpx

logger = logging.getLogger("bitdex.futures.adapter")


class BinanceFuturesError(Exception):
    """Base exception for Binance Futures adapter."""
    def __init__(self, message: str, code: Optional[int] = None, status_code: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class BinanceFuturesAuthError(BinanceFuturesError):
    """Authentication or signature failure."""
    pass


class BinanceFuturesRateLimitError(BinanceFuturesError):
    """Rate limit exceeded (HTTP 429 or Binance -1003)."""
    def __init__(self, message: str, retry_after: int = 60, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class BinanceFuturesClockSkewError(BinanceFuturesError):
    """Timestamp outside recvWindow or ahead of server time (-1021)."""
    pass


class BinanceFuturesMarginError(BinanceFuturesError):
    """Margin insufficient or invalid leverage (-2019, etc.)."""
    pass


class BinanceFuturesOrderRejectedError(BinanceFuturesError):
    """Order rejected by exchange filters or rules."""
    pass


class BinanceFuturesAdapter:
    """
    Dedicated adapter for Binance USD(S)-M Futures.
    Supports Testnet and Mainnet endpoints with strict safety separation.
    """

    ENDPOINTS = {
        "testnet": {
            "rest": "https://testnet.binancefuture.com",
            "ws": "wss://stream.binancefuture.com",
        },
        "mainnet": {
            "rest": "https://fapi.binance.com",
            "ws": "wss://fstream.binance.com",
        }
    }

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        environment: str = "testnet",
        live_trading_locked: bool = True,
        recv_window: int = 5000,
        timeout: float = 10.0,
    ):
        env_norm = environment.strip().lower()
        if env_norm not in ("testnet", "mainnet"):
            raise ValueError(f"Invalid environment '{environment}'. Must be 'testnet' or 'mainnet'.")
        
        self.environment = env_norm
        self.base_url = self.ENDPOINTS[self.environment]["rest"]
        self.ws_url = self.ENDPOINTS[self.environment]["ws"]
        self.api_key = api_key or ""
        self.api_secret = api_secret or ""
        self.live_trading_locked = live_trading_locked
        self.recv_window = recv_window
        self.timeout = timeout
        
        # Clock skew tracking: server_time - local_time
        self._time_offset_ms: int = 0
        self._clock_synced: bool = False
        
        # In-memory exchangeInfo filter cache: symbol -> filter_dict
        self._exchange_info_cache: Dict[str, Dict[str, Any]] = {}
        self._last_info_fetch_ms: int = 0
        self._cache_ttl_ms: int = 60_000  # 1 minute cache for exchangeInfo

    # ─────────────────────────────────────────────────────────────
    # Time and Signing Utilities
    # ─────────────────────────────────────────────────────────────

    def _get_timestamp_ms(self) -> int:
        """Return current timestamp in milliseconds corrected by clock offset."""
        local_ms = int(time.time() * 1000)
        return local_ms + self._time_offset_ms

    def sync_clock(self) -> int:
        """
        Query GET /fapi/v1/time and calculate clock offset between client and Binance.
        Returns the offset in milliseconds.
        """
        url = f"{self.base_url}/fapi/v1/time"
        t0 = int(time.time() * 1000)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url)
                t1 = int(time.time() * 1000)
                if resp.status_code == 200:
                    data = resp.json()
                    server_time = data.get("serverTime", 0)
                    # Latency estimate
                    round_trip = max(1, t1 - t0)
                    estimated_server_time = server_time - (round_trip // 2)
                    self._time_offset_ms = estimated_server_time - t0
                    self._clock_synced = True
                    logger.info("Futures adapter clock synced with %s: offset=%d ms (latency=%d ms)",
                                self.base_url, self._time_offset_ms, round_trip)
                    return self._time_offset_ms
                else:
                    self._handle_error_response(resp)
        except Exception as e:
            logger.warning("Clock sync failed with %s: %s", self.base_url, str(e))
            if isinstance(e, BinanceFuturesError):
                raise
            raise BinanceFuturesError(f"Failed to sync clock: {str(e)}")

    def _sign_params(self, params: Dict[str, Any]) -> str:
        """Generate HMAC-SHA256 signature for parameters dictionary."""
        if not self.api_secret:
            raise BinanceFuturesAuthError("API secret is required for signed requests.")
        
        if not self._clock_synced:
            try:
                self.sync_clock()
            except Exception as e:
                logger.warning("Auto clock sync failed, using local time: %s", str(e))
        
        params["timestamp"] = self._get_timestamp_ms()
        params["recvWindow"] = self.recv_window
        
        query_str = urlencode([(k, v) for k, v in params.items() if v is not None])
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_str.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        return f"{query_str}&signature={signature}"

    def _get_headers(self, signed: bool = False) -> Dict[str, str]:
        """Headers required by Binance Futures."""
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "BITDEX-Futures-Engine/1.0",
        }
        if signed or self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        return headers

    def _handle_error_response(self, resp: httpx.Response):
        """Parse error payload and raise appropriate normalized exception."""
        status_code = resp.status_code
        retry_after = 60
        if "Retry-After" in resp.headers:
            try:
                retry_after = int(resp.headers["Retry-After"])
            except (ValueError, TypeError):
                retry_after = 60
        
        try:
            payload = resp.json()
            code = payload.get("code")
            msg = payload.get("msg", resp.text)
        except Exception:
            payload = {}
            code = None
            msg = resp.text

        err_msg = f"Binance Futures error (HTTP {status_code}, code {code}): {msg}"

        if status_code == 429 or code == -1003:
            raise BinanceFuturesRateLimitError(err_msg, retry_after=retry_after, code=code, status_code=status_code)
        
        if code in (-1021, -1022):
            raise BinanceFuturesClockSkewError(err_msg, code=code, status_code=status_code)
        
        if code in (-2014, -2015, -1002, -2011):
            raise BinanceFuturesAuthError(err_msg, code=code, status_code=status_code)
        
        if code in (-2019, -4028, -4001, -4004):
            raise BinanceFuturesMarginError(err_msg, code=code, status_code=status_code)
        
        if code in (-5022, -2010) or "Order would immediately match and take" in msg or "POST ONLY" in msg:
            raise BinanceFuturesOrderRejectedError(f"POST_ONLY_REJECTED: Order would cross book and execute as taker (code {code}): {msg}", code=code, status_code=status_code)
        
        if code in (-1013, -1111, -2010, -4003, -4014):
            raise BinanceFuturesOrderRejectedError(err_msg, code=code, status_code=status_code)
        
        raise BinanceFuturesError(err_msg, code=code, status_code=status_code)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
        retry_on_clock_skew: bool = True
    ) -> Any:
        """Execute HTTP request against Binance Futures REST API."""
        params = params.copy() if params else {}
        url = f"{self.base_url}{path}"
        headers = self._get_headers(signed=signed)
        
        if signed:
            query_or_body = self._sign_params(params)
            if method.upper() in ("GET", "DELETE"):
                full_url = f"{url}?{query_or_body}"
                data_body = None
            else:
                full_url = url
                data_body = query_or_body
        else:
            if method.upper() in ("GET", "DELETE"):
                qs = urlencode([(k, v) for k, v in params.items() if v is not None])
                full_url = f"{url}?{qs}" if qs else url
                data_body = None
            else:
                full_url = url
                data_body = urlencode([(k, v) for k, v in params.items() if v is not None])

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(
                    method=method.upper(),
                    url=full_url,
                    headers=headers,
                    content=data_body,
                )
                
                if resp.status_code == 200:
                    return resp.json()
                
                self._handle_error_response(resp)
        except BinanceFuturesClockSkewError as cse:
            if retry_on_clock_skew:
                logger.warning("Clock skew detected (%s). Resyncing clock and retrying...", str(cse))
                self.sync_clock()
                return self._request(method, path, params, signed, retry_on_clock_skew=False)
            raise
        except httpx.RequestError as re:
            raise BinanceFuturesError(f"HTTP transport failure to {url}: {str(re)}")

    # ─────────────────────────────────────────────────────────────
    # Market Data & Exchange Filters
    # ─────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """GET /fapi/v1/ping - test connectivity."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(f"{self.base_url}/fapi/v1/ping")
                return resp.status_code == 200
        except Exception:
            return False

    def get_server_time(self) -> int:
        """GET /fapi/v1/time - get exchange server time."""
        res = self._request("GET", "/fapi/v1/time")
        return res.get("serverTime", 0)

    def get_exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """GET /fapi/v1/exchangeInfo - retrieve market rules and filters."""
        now = int(time.time() * 1000)
        if not self._exchange_info_cache or (now - self._last_info_fetch_ms > self._cache_ttl_ms):
            res = self._request("GET", "/fapi/v1/exchangeInfo")
            cache_map = {}
            for s in res.get("symbols", []):
                sym_name = s.get("symbol")
                cache_map[sym_name] = s
            self._exchange_info_cache = cache_map
            self._last_info_fetch_ms = now
        
        if symbol:
            sym_clean = symbol.upper()
            if sym_clean in self._exchange_info_cache:
                return {"symbols": [self._exchange_info_cache[sym_clean]]}
            raise BinanceFuturesError(f"Symbol '{symbol}' not found in Binance Futures exchangeInfo.")
        
        return {"symbols": list(self._exchange_info_cache.values())}

    def get_symbol_filters(self, symbol: str) -> Dict[str, Any]:
        """Extract PRICE_FILTER, LOT_SIZE, MIN_NOTIONAL filters for a symbol."""
        info = self.get_exchange_info(symbol=symbol)
        sym_info = info["symbols"][0]
        filters = {}
        for f in sym_info.get("filters", []):
            filters[f.get("filterType")] = f
            
        lot_size = filters.get("LOT_SIZE", {})
        price_filter = filters.get("PRICE_FILTER", {})
        min_notional = filters.get("MIN_NOTIONAL", {})
        market_lot = filters.get("MARKET_LOT_SIZE", {})
        
        return {
            "symbol": sym_info.get("symbol"),
            "status": sym_info.get("status"),
            "baseAsset": sym_info.get("baseAsset"),
            "quoteAsset": sym_info.get("quoteAsset"),
            "min_qty": float(lot_size.get("minQty", 0.001)),
            "max_qty": float(lot_size.get("maxQty", 1000.0)),
            "step_size": float(lot_size.get("stepSize", 0.001)),
            "min_price": float(price_filter.get("minPrice", 0.1)),
            "max_price": float(price_filter.get("maxPrice", 1000000.0)),
            "tick_size": float(price_filter.get("tickSize", 0.1)),
            "min_notional": float(min_notional.get("notional", 5.0)),
            "market_min_qty": float(market_lot.get("minQty", lot_size.get("minQty", 0.001))),
            "market_step_size": float(market_lot.get("stepSize", lot_size.get("stepSize", 0.001))),
        }

    def validate_and_clamp_order(
        self,
        symbol: str,
        quantity: float,
        price: Optional[float] = None
    ) -> Tuple[float, Optional[float]]:
        """
        Validate and clamp quantity and price according to Binance Futures LOT_SIZE and PRICE_FILTER.
        Returns (clamped_qty, clamped_price).
        """
        filters = self.get_symbol_filters(symbol)
        
        # Round quantity to step_size precision
        step = filters["step_size"]
        if step > 0:
            decimals = max(0, int(round(-math.log10(step))))
            clamped_qty = math.floor(quantity / step) * step
            clamped_qty = round(clamped_qty, decimals)
        else:
            clamped_qty = quantity
            
        if clamped_qty < filters["min_qty"]:
            raise BinanceFuturesOrderRejectedError(
                f"Quantity {clamped_qty} is below symbol minimum {filters['min_qty']} {filters['baseAsset']}."
            )
        if clamped_qty > filters["max_qty"]:
            raise BinanceFuturesOrderRejectedError(
                f"Quantity {clamped_qty} exceeds symbol maximum {filters['max_qty']} {filters['baseAsset']}."
            )

        clamped_price = None
        if price is not None:
            tick = filters["tick_size"]
            if tick > 0:
                p_decimals = max(0, int(round(-math.log10(tick))))
                clamped_price = round(round(price / tick) * tick, p_decimals)
            else:
                clamped_price = price
                
            if clamped_price < filters["min_price"]:
                raise BinanceFuturesOrderRejectedError(
                    f"Price {clamped_price} is below symbol minimum {filters['min_price']}."
                )
            if clamped_price > filters["max_price"]:
                raise BinanceFuturesOrderRejectedError(
                    f"Price {clamped_price} exceeds symbol maximum {filters['max_price']}."
                )
            
            notional = clamped_qty * clamped_price
            if notional < filters["min_notional"]:
                raise BinanceFuturesOrderRejectedError(
                    f"Notional ${notional:.2f} is below symbol minimum notional ${filters['min_notional']:.2f}."
                )

        return clamped_qty, clamped_price

    def get_mark_price(self, symbol: str) -> Dict[str, Any]:
        """GET /fapi/v1/premiumIndex - get mark price and funding rate."""
        params = {"symbol": symbol.upper()}
        res = self._request("GET", "/fapi/v1/premiumIndex", params=params)
        return {
            "symbol": res.get("symbol"),
            "mark_price": float(res.get("markPrice", 0.0)),
            "index_price": float(res.get("indexPrice", 0.0)),
            "funding_rate": float(res.get("lastFundingRate", 0.0)),
            "next_funding_time": int(res.get("nextFundingTime", 0)),
            "time": int(res.get("time", 0)),
        }

    def get_ticker_price(self, symbol: str) -> float:
        """GET /fapi/v1/ticker/price - get latest market price."""
        params = {"symbol": symbol.upper()}
        res = self._request("GET", "/fapi/v1/ticker/price", params=params)
        return float(res.get("price", 0.0))

    # ─────────────────────────────────────────────────────────────
    # Account & Margin Operations
    # ─────────────────────────────────────────────────────────────

    def get_account_balance(self) -> List[Dict[str, Any]]:
        """GET /fapi/v2/balance - retrieve wallet balances."""
        return self._request("GET", "/fapi/v2/balance", signed=True)

    def get_account_information(self) -> Dict[str, Any]:
        """GET /fapi/v2/account - retrieve detailed futures account stats."""
        return self._request("GET", "/fapi/v2/account", signed=True)

    def get_position_risk(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """GET /fapi/v2/positionRisk - get current position risk."""
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._request("GET", "/fapi/v2/positionRisk", params=params, signed=True)

    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """POST /fapi/v1/leverage - set initial leverage."""
        if leverage < 1 or leverage > 10:
            raise BinanceFuturesError(f"Leverage {leverage}x violates safety cap (max 10x).")
        params = {
            "symbol": symbol.upper(),
            "leverage": leverage
        }
        return self._request("POST", "/fapi/v1/leverage", params=params, signed=True)

    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED") -> Dict[str, Any]:
        """
        POST /fapi/v1/marginType - set ISOLATED or CROSSED margin.
        If error -4046 ('No need to change margin type'), return success dict.
        """
        mtype = margin_type.upper()
        if mtype not in ("ISOLATED", "CROSSED"):
            raise BinanceFuturesError(f"Invalid margin type '{margin_type}'. Must be ISOLATED or CROSSED.")
        
        params = {
            "symbol": symbol.upper(),
            "marginType": mtype
        }
        try:
            return self._request("POST", "/fapi/v1/marginType", params=params, signed=True)
        except BinanceFuturesError as bfe:
            if bfe.code == -4046:
                logger.info("Margin type for %s is already %s.", symbol, mtype)
                return {"code": 200, "msg": f"Margin type is already {mtype}"}
            raise

    # ─────────────────────────────────────────────────────────────
    # Order Execution & Safety Hard-Lock
    # ─────────────────────────────────────────────────────────────

    def submit_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: Optional[str] = None,
        reduce_only: bool = False,
        working_type: Optional[str] = "MARK_PRICE",
        client_order_id: Optional[str] = None,
        position_side: str = "BOTH",
    ) -> Dict[str, Any]:
        """
        POST /fapi/v1/order - Submit a futures order.
        
        CRITICAL SAFETY CHECK:
        If environment is Mainnet AND live_trading_locked is True, execution is strictly blocked.
        """
        if self.environment == "mainnet" and self.live_trading_locked:
            raise RuntimeError(
                "CRITICAL SAFETY LOCK: Live trading on Binance Futures Mainnet is locked. "
                "No live orders can be dispatched."
            )

        side_clean = side.upper()
        if side_clean not in ("BUY", "SELL"):
            raise ValueError(f"Invalid order side '{side}'. Must be BUY or SELL.")
        
        type_clean = order_type.upper()
        # Section 4: Support POST_ONLY and LIMIT_MAKER by translating to LIMIT with timeInForce="GTX"
        if type_clean in ("POST_ONLY", "LIMIT_MAKER"):
            type_clean = "LIMIT"
            time_in_force = "GTX"

        valid_types = ("LIMIT", "MARKET", "STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET")
        if type_clean not in valid_types:
            raise ValueError(f"Unsupported order type '{order_type}'. Must be one of {valid_types}.")

        # Quantity and price filter validation
        clamped_qty, clamped_price = self.validate_and_clamp_order(symbol, quantity, price)

        params: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side_clean,
            "type": type_clean,
            "quantity": clamped_qty,
            "positionSide": position_side.upper(),
        }

        if clamped_price is not None:
            params["price"] = clamped_price

        if stop_price is not None:
            _, clamped_stop = self.validate_and_clamp_order(symbol, clamped_qty, stop_price)
            params["stopPrice"] = clamped_stop
            if working_type:
                params["workingType"] = working_type.upper()

        if type_clean in ("LIMIT", "STOP", "TAKE_PROFIT"):
            params["timeInForce"] = time_in_force or "GTC"

        if reduce_only:
            params["reduceOnly"] = "true"

        if client_order_id:
            # Binance client order ID limit: 36 chars alphanumeric
            sanitized_coid = "".join(c for c in str(client_order_id) if c.isalnum() or c in ("-", "_"))[:36]
            params["newClientOrderId"] = sanitized_coid

        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """DELETE /fapi/v1/order - cancel an active order."""
        if not order_id and not client_order_id:
            raise ValueError("Either order_id or client_order_id must be provided to cancel an order.")
        
        params: Dict[str, Any] = {"symbol": symbol.upper()}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["origClientOrderId"] = client_order_id
            
        return self._request("DELETE", "/fapi/v1/order", params=params, signed=True)

    def query_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """GET /fapi/v1/order - check an order's status."""
        if not order_id and not client_order_id:
            raise ValueError("Either order_id or client_order_id must be provided to query an order.")
        
        params: Dict[str, Any] = {"symbol": symbol.upper()}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["origClientOrderId"] = client_order_id
            
        return self._request("GET", "/fapi/v1/order", params=params, signed=True)

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """GET /fapi/v1/openOrders - get all current open orders."""
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._request("GET", "/fapi/v1/openOrders", params=params, signed=True)

    def get_all_orders(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """GET /fapi/v1/allOrders - get all account orders."""
        params = {
            "symbol": symbol.upper(),
            "limit": min(limit, 1000)
        }
        return self._request("GET", "/fapi/v1/allOrders", params=params, signed=True)

    def get_income_history(
        self,
        symbol: Optional[str] = None,
        income_type: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        GET /fapi/v1/income - get funding fees, realized pnl, commissions, etc.
        income_type: 'TRANSFER', 'WELCOME_BONUS', 'REALIZED_PNL', 'FUNDING_FEE', 'COMMISSION', 'INSURANCE_CLEAR'
        """
        params: Dict[str, Any] = {"limit": min(limit, 1000)}
        if symbol:
            params["symbol"] = symbol.upper()
        if income_type:
            params["incomeType"] = income_type.upper()
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
            
        return self._request("GET", "/fapi/v1/income", params=params, signed=True)
