export interface NormalizedPosition {
  ticket: string;
  symbol: string;
  direction: "BUY" | "SELL" | "UNAVAILABLE";
  volume_lots: number | null;
  entry_price: number | null;
  current_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  pnl_usd: number | null;
  open_time: string | null;
  close_time?: string | null;
  status: "OPEN" | "PENDING" | "CLOSED";
  market_type?: string;
  exchange?: string;
  origin?: string;
}

export function extractNumeric(val: any): number | null {
  if (val === null || val === undefined || val === "") return null;
  const num = typeof val === "number" ? val : parseFloat(String(val).replace(/[^0-9.-]/g, ""));
  return isNaN(num) || !isFinite(num) ? null : num;
}

export function normalizePosition(
  raw: any,
  defaultStatus: "OPEN" | "PENDING" | "CLOSED" = "OPEN"
): NormalizedPosition {
  if (!raw || typeof raw !== "object") {
    return {
      ticket: "UNAVAILABLE",
      symbol: "UNAVAILABLE",
      direction: "UNAVAILABLE",
      volume_lots: null,
      entry_price: null,
      current_price: null,
      stop_loss: null,
      take_profit: null,
      pnl_usd: null,
      open_time: null,
      close_time: null,
      status: defaultStatus,
    };
  }

  // Direction resolution
  let direction: "BUY" | "SELL" | "UNAVAILABLE" = "UNAVAILABLE";
  const rawSide = String(raw.side || raw.direction || raw.type || "").toUpperCase();
  if (rawSide.includes("BUY") || rawSide === "LONG") {
    direction = "BUY";
  } else if (rawSide.includes("SELL") || rawSide === "SHORT") {
    direction = "SELL";
  }

  // Ticket resolution
  const ticket = String(raw.ticket || raw.position_id || raw.order_id || raw.id || "UNASSIGNED");

  // Symbol resolution
  const symbol = String(raw.symbol || raw.pair || raw.instrument || "UNAVAILABLE");

  // Volume resolution (size vs volume_lots vs qty)
  const volume_lots = extractNumeric(raw.volume_lots ?? raw.size ?? raw.qty ?? raw.quantity ?? raw.volume);

  // Price resolutions
  const entry_price = extractNumeric(raw.entry_price ?? raw.price ?? raw.open_price ?? raw.avg_price);
  const current_price = extractNumeric(
    raw.current_price ?? raw.mark_price ?? raw.exit_price ?? raw.last_price
  );
  const stop_loss = extractNumeric(raw.stop_loss ?? raw.sl ?? raw.stopPrice);
  const take_profit = extractNumeric(raw.take_profit ?? raw.tp);

  // P&L resolution
  let pnl_usd = extractNumeric(raw.pnl_usd ?? raw.unrealized_pnl ?? raw.realized_pnl ?? raw.pnl);
  if (raw.status === "CLOSED" && extractNumeric(raw.realized_pnl) !== null) {
    pnl_usd = extractNumeric(raw.realized_pnl);
  }

  // Status resolution
  let status: "OPEN" | "PENDING" | "CLOSED" = defaultStatus;
  const rawStatus = String(raw.status || "").toUpperCase();
  if (rawStatus === "CLOSED" || raw.closed_at_utc) {
    status = "CLOSED";
  } else if (rawStatus === "PENDING" || rawStatus === "WORKING" || rawStatus === "NEW") {
    status = "PENDING";
  } else if (rawStatus === "OPEN") {
    status = "OPEN";
  }

  return {
    ticket,
    symbol,
    direction,
    volume_lots,
    entry_price,
    current_price,
    stop_loss,
    take_profit,
    pnl_usd,
    open_time: raw.opened_at_utc || raw.open_time || raw.created_at || raw.timestamp || null,
    close_time: raw.closed_at_utc || raw.close_time || null,
    status,
    market_type: raw.market_type || undefined,
    exchange: raw.exchange || undefined,
    origin: raw.origin || undefined,
  };
}

export function formatCurrencyValue(val: number | null | undefined, decimals = 2): string {
  if (val === null || val === undefined || typeof val !== "number" || isNaN(val) || !isFinite(val)) {
    return "Unavailable";
  }
  return "$" + val.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export function formatVolumeValue(val: number | null | undefined, decimals = 2): string {
  if (val === null || val === undefined || typeof val !== "number" || isNaN(val) || !isFinite(val)) {
    return "Unavailable";
  }
  return val.toFixed(decimals);
}

export function formatPnlValue(val: number | null | undefined): {
  text: string;
  isPositive: boolean;
  isUnavailable: boolean;
} {
  if (val === null || val === undefined || typeof val !== "number" || isNaN(val) || !isFinite(val)) {
    return { text: "Unavailable", isPositive: false, isUnavailable: true };
  }
  const isPos = val >= 0;
  return {
    text: `${isPos ? "+" : ""}$${Math.abs(val).toFixed(2)}`,
    isPositive: isPos,
    isUnavailable: false,
  };
}
