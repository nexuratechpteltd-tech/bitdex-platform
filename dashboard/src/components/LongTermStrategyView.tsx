import React, { useState, useEffect } from "react";
import {
  Compass,
  TrendingUp,
  TrendingDown,
  ShieldAlert,
  Clock,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  ArrowRight,
  Zap,
  Lock,
  Layers,
  ChevronRight,
  Info,
  X
} from "lucide-react";

interface LongTermCard {
  setup_id: string;
  symbol: string;
  exposure_type: string;
  direction: "BUY" | "SELL" | "NONE";
  status: "ANALYZING" | "WAITING" | "READY" | "EXPIRED";
  quant_score: number;
  max_score: number;
  entry_min: number;
  entry_max: number;
  stop_loss: number;
  take_profit: number;
  trailing_rule_json?: string;
  est_risk_usd: number;
  est_net_reward_usd: number;
  net_rr_ratio: number;
  qualification_reason: string;
  blocker_reason?: string;
  timeframe_context?: any;
  current_quote?: { bid: number; ask: number; spread: number };
}

interface PreflightModalState {
  isOpen: boolean;
  loading: boolean;
  card: LongTermCard | null;
  quoteSnapshot: any;
  preflightToken: string | null;
  rejectionReason: string | null;
  passed: boolean;
  executing: boolean;
  fillResult: any;
  ttlSeconds: number;
}

export default function LongTermStrategyView({ token }: { token: string }) {
  const [opportunities, setOpportunities] = useState<LongTermCard[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [sharedEquity, setSharedEquity] = useState<number>(5000.20);
  const [selectedAssetFilter, setSelectedAssetFilter] = useState<string>("ALL");

  const [modal, setModal] = useState<PreflightModalState>({
    isOpen: false,
    loading: false,
    card: null,
    quoteSnapshot: null,
    preflightToken: null,
    rejectionReason: null,
    passed: false,
    executing: false,
    fillResult: null,
    ttlSeconds: 15
  });

  const fetchOpportunities = async () => {
    try {
      setRefreshing(true);
      const res = await fetch("/api/v1/saas/longterm/opportunities", {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setOpportunities(data.opportunities || []);
        if (data.shared_equity) setSharedEquity(data.shared_equity);
      }
    } catch (e) {
      console.error("Failed to load long-term opportunities", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchOpportunities();
    const interval = setInterval(fetchOpportunities, 25000);
    return () => clearInterval(interval);
  }, [token]);

  // Handle Preflight Check Modal
  const handleOpenPreflight = async (card: LongTermCard) => {
    setModal({
      isOpen: true,
      loading: true,
      card,
      quoteSnapshot: null,
      preflightToken: null,
      rejectionReason: null,
      passed: false,
      executing: false,
      fillResult: null,
      ttlSeconds: 15
    });

    try {
      const res = await fetch(`/api/v1/saas/longterm/opportunities/${card.setup_id}/preflight`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          setup_id: card.setup_id,
          account_id: "17000660016",
          symbol: card.symbol,
          side: card.direction.toLowerCase(),
          volume: card.symbol.includes("BTC") ? 0.01 : 0.02,
          entry_price: card.current_quote?.ask || card.entry_max,
          sl_price: card.stop_loss,
          tp_price: card.take_profit
        })
      });

      const data = await res.json();
      setModal(prev => ({
        ...prev,
        loading: false,
        passed: data.preflight_passed,
        preflightToken: data.preflight_token,
        rejectionReason: data.rejection_reason,
        quoteSnapshot: data.quote_snapshot,
        ttlSeconds: data.quote_snapshot?.ttl_sec || 15
      }));
    } catch (e: any) {
      setModal(prev => ({
        ...prev,
        loading: false,
        passed: false,
        rejectionReason: e.message || "Failed to execute preflight checks."
      }));
    }
  };

  // Execute Confirmed Trade
  const handleConfirmExecute = async () => {
    if (!modal.card || !modal.preflightToken) return;
    setModal(prev => ({ ...prev, executing: true }));

    try {
      const res = await fetch(`/api/v1/saas/longterm/opportunities/${modal.card.setup_id}/execute`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          preflight_token: modal.preflightToken,
          setup_id: modal.card.setup_id,
          account_id: "17000660016",
          symbol: modal.card.symbol,
          side: modal.card.direction.toLowerCase(),
          volume: modal.card.symbol.includes("BTC") ? 0.01 : 0.02,
          entry_price: modal.quoteSnapshot?.ask || modal.card.entry_max,
          sl_price: modal.card.stop_loss,
          tp_price: modal.card.take_profit,
          user_confirmed: true
        })
      });

      const data = await res.json();
      if (res.ok) {
        setModal(prev => ({
          ...prev,
          executing: false,
          fillResult: data.fill
        }));
        fetchOpportunities();
      } else {
        setModal(prev => ({
          ...prev,
          executing: false,
          rejectionReason: data.detail || "Broker order rejected."
        }));
      }
    } catch (e: any) {
      setModal(prev => ({
        ...prev,
        executing: false,
        rejectionReason: e.message || "Execution communication failure."
      }));
    }
  };

  return (
    <div className="space-y-6">
      {/* ─── 1. Header Banner & Engine Telemetry ─── */}
      <div className="rounded-xl border border-[#21262D] bg-[#0D1117] p-4 sm:p-5">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Compass className="w-5 h-5 text-[#10B981]" />
              <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight">
                Long-Term Strategy Engine
              </h2>
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
                HTF STRUCTURE & RETEST
              </span>
            </div>
            <p className="text-xs text-[#8B949E] mt-1 leading-relaxed">
              Multi-timeframe institutional analysis (D1 Macro Bias &rarr; H4 Key BOS/S&R &rarr; H1 Retest Trigger). Requires explicit operator review before submitting orders.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="px-3 py-1.5 rounded-lg bg-[#161B22] border border-[#21262D] text-xs">
              <span className="text-[#8B949E]">Shared Demo Equity: </span>
              <span className="font-mono font-bold text-white">${sharedEquity.toFixed(2)}</span>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-[#161B22] border border-[#21262D] text-xs">
              <span className="text-[#8B949E]">Min Net Target: </span>
              <span className="font-mono font-bold text-[#10B981]">&ge; 1.80 R</span>
            </div>
            <button
              onClick={fetchOpportunities}
              disabled={refreshing}
              className="p-2 rounded-lg bg-[#161B22] hover:bg-[#21262D] border border-[#21262D] text-[#8B949E] hover:text-white transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin text-[#10B981]" : ""}`} />
            </button>
          </div>
        </div>
      </div>

      {/* ─── 2. Opportunity Cards Grid ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {loading ? (
          <div className="col-span-full p-8 text-center text-xs text-[#8B949E] border border-[#21262D] rounded-xl bg-[#0D1117]">
            Evaluating institutional D1/H4/H1 structures...
          </div>
        ) : opportunities.length === 0 ? (
          <div className="col-span-full p-8 text-center text-xs text-[#8B949E] border border-[#21262D] rounded-xl bg-[#0D1117]">
            No instruments configured for Long-Term monitoring. Enable symbols in the Watchlist Manager.
          </div>
        ) : (
          opportunities.map(card => {
            const isReady = card.status === "READY";
            const isWaiting = card.status === "WAITING";
            const isAnalyzing = card.status === "ANALYZING";
            const isExpired = card.status === "EXPIRED";
            const isBuy = card.direction === "BUY";
            const isSell = card.direction === "SELL";

            return (
              <div
                key={card.setup_id}
                className={`rounded-xl border transition-all ${
                  isReady
                    ? "border-[#10B981]/50 bg-[#0D1117] shadow-lg shadow-[#10B981]/5"
                    : "border-[#21262D] bg-[#0D1117]"
                } p-4 sm:p-5 flex flex-col justify-between`}
              >
                <div>
                  {/* Card Header */}
                  <div className="flex items-center justify-between pb-3 border-b border-[#21262D]">
                    <div className="flex items-center gap-2">
                      <span className="text-base font-bold text-white font-mono">
                        {card.symbol}
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-[#21262D] text-[#8B949E] border border-[#30363D]">
                        CFD
                      </span>
                      {isBuy && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
                          <TrendingUp className="w-3 h-3" /> BUY
                        </span>
                      )}
                      {isSell && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/15 text-rose-400 border border-rose-500/30">
                          <TrendingDown className="w-3 h-3" /> SELL
                        </span>
                      )}
                    </div>

                    <div>
                      {isReady && (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-[#10B981]/20 text-[#10B981] border border-[#10B981]/40 animate-pulse">
                          <CheckCircle2 className="w-3.5 h-3.5" /> READY TO TRADE
                        </span>
                      )}
                      {isWaiting && (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
                          <Clock className="w-3.5 h-3.5" /> WAITING
                        </span>
                      )}
                      {isAnalyzing && (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-[#21262D] text-[#8B949E] border border-[#30363D]">
                          <Layers className="w-3.5 h-3.5" /> ANALYZING
                        </span>
                      )}
                      {isExpired && (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                          <AlertTriangle className="w-3.5 h-3.5" /> EXPIRED
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Pricing & Structure Info */}
                  <div className="py-3.5 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                    <div>
                      <span className="text-[#8B949E] block text-[11px]">Live Price</span>
                      <span className="font-mono text-white font-semibold">
                        {card.current_quote?.bid ? `$${card.current_quote.bid.toLocaleString()}` : "—"}
                      </span>
                    </div>
                    <div>
                      <span className="text-[#8B949E] block text-[11px]">Spread</span>
                      <span className="font-mono text-[#8B949E]">
                        {card.current_quote?.spread ?? "—"}
                      </span>
                    </div>
                    <div>
                      <span className="text-[#8B949E] block text-[11px]">Quant Score</span>
                      <span className="font-mono font-bold text-white">
                        {card.quant_score} / {card.max_score}
                      </span>
                    </div>
                    <div>
                      <span className="text-[#8B949E] block text-[11px]">Net R:R</span>
                      <span className={`font-mono font-bold ${card.net_rr_ratio >= 1.80 ? "text-[#10B981]" : "text-white"}`}>
                        {card.net_rr_ratio ? `${card.net_rr_ratio} R` : "—"}
                      </span>
                    </div>
                  </div>

                  {/* Timeframe Context Breakdown */}
                  {card.timeframe_context && (
                    <div className="p-2.5 rounded-lg bg-[#161B22] border border-[#21262D] text-xs space-y-1 mb-3">
                      <div className="flex justify-between">
                        <span className="text-[#8B949E]">D1 Macro Trend:</span>
                        <span className="font-semibold text-white">{card.timeframe_context.d1_bias || "—"}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#8B949E]">H4 Market Structure:</span>
                        <span className="font-semibold text-white">{card.timeframe_context.h4_structure || "—"}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#8B949E]">H1 Retest Trigger:</span>
                        <span className="font-semibold text-white">{card.timeframe_context.h1_trigger || "—"}</span>
                      </div>
                    </div>
                  )}

                  {/* Trade Parameters */}
                  <div className="p-3 rounded-lg bg-[#161B22]/50 border border-[#21262D] space-y-1.5 text-xs font-mono">
                    <div className="flex justify-between">
                      <span className="text-[#8B949E]">Proposed Entry Range:</span>
                      <span className="text-white">
                        {card.entry_min ? `${card.entry_min} - ${card.entry_max}` : "Pending Trigger"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#8B949E]">Stop Loss (H4 Invalidation):</span>
                      <span className="text-rose-400">{card.stop_loss || "—"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#8B949E]">Take Profit (H4 Liquidity):</span>
                      <span className="text-[#10B981]">{card.take_profit || "—"}</span>
                    </div>
                    <div className="flex justify-between pt-1 border-t border-[#21262D]/60">
                      <span className="text-[#8B949E]">Planned Monetary Risk (0.25%):</span>
                      <span className="text-white font-semibold">
                        {card.est_risk_usd ? `$${card.est_risk_usd.toFixed(2)}` : "—"}
                      </span>
                    </div>
                  </div>

                  {/* Explanation / Blocker Reason */}
                  <div className="mt-3 text-xs">
                    {card.blocker_reason ? (
                      <p className="text-amber-400 flex items-start gap-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                        <span>{card.blocker_reason}</span>
                      </p>
                    ) : (
                      <p className="text-[#10B981] flex items-start gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                        <span>{card.qualification_reason}</span>
                      </p>
                    )}
                  </div>
                </div>

                {/* Card Action Button */}
                <div className="mt-4 pt-3 border-t border-[#21262D]">
                  {isReady ? (
                    <button
                      type="button"
                      onClick={() => handleOpenPreflight(card)}
                      className="w-full py-2.5 px-4 rounded-lg bg-[#10B981] hover:bg-[#059669] text-[#0D1117] font-bold text-xs transition-colors flex items-center justify-center gap-2 shadow-lg shadow-[#10B981]/15"
                    >
                      <span>REVIEW & EXECUTE TRADE (PRE-FLIGHT)</span>
                      <ArrowRight className="w-4 h-4" />
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled
                      className="w-full py-2 px-4 rounded-lg bg-[#161B22] text-[#8B949E] text-xs font-semibold cursor-not-allowed border border-[#21262D] text-center"
                    >
                      EXECUTION DISABLED — AWAITING CONFLUENCE
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* ─── 3. Pre-Flight 11-Step Execution Confirmation Modal ─── */}
      {modal.isOpen && modal.card && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#0D1117] border border-[#21262D] rounded-2xl max-w-lg w-full overflow-hidden shadow-2xl">
            <div className="p-4 sm:p-5 border-b border-[#21262D] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldAlert className="w-5 h-5 text-[#10B981]" />
                <h3 className="font-bold text-white text-base">
                  Pre-Flight Execution Verification
                </h3>
              </div>
              <button
                onClick={() => setModal(prev => ({ ...prev, isOpen: false }))}
                className="text-[#8B949E] hover:text-white p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4 text-xs">
              {modal.loading ? (
                <div className="p-8 text-center text-[#8B949E]">
                  Running live 7-point pre-flight checks at broker...
                </div>
              ) : modal.fillResult ? (
                <div className="p-6 text-center space-y-3">
                  <CheckCircle2 className="w-10 h-10 text-[#10B981] mx-auto" />
                  <h4 className="font-bold text-white text-base">Order Filled at Exness Demo</h4>
                  <p className="text-[#8B949E]">
                    Position ID #{modal.fillResult.position_id} successfully opened with broker-confirmed SL and TP legs.
                  </p>
                  <button
                    onClick={() => setModal(prev => ({ ...prev, isOpen: false }))}
                    className="px-4 py-2 bg-[#161B22] border border-[#21262D] rounded-lg text-white font-semibold text-xs mt-2"
                  >
                    Done
                  </button>
                </div>
              ) : (
                <>
                  <div className="rounded-lg bg-[#161B22] p-3 border border-[#21262D] space-y-1.5 font-mono">
                    <div className="flex justify-between">
                      <span className="text-[#8B949E]">Instrument:</span>
                      <span className="text-white font-bold">{modal.card.symbol} [CFD]</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#8B949E]">Side / Volume:</span>
                      <span className={modal.card.direction === "BUY" ? "text-[#10B981] font-bold" : "text-rose-400 font-bold"}>
                        {modal.card.direction} (0.01 Lots)
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#8B949E]">Live Broker Quote:</span>
                      <span className="text-white">
                        Bid: {modal.quoteSnapshot?.bid} | Ask: {modal.quoteSnapshot?.ask} (Sprd: {modal.quoteSnapshot?.spread})
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#8B949E]">Stop Loss:</span>
                      <span className="text-rose-400">{modal.card.stop_loss}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#8B949E]">Take Profit:</span>
                      <span className="text-[#10B981]">{modal.card.take_profit}</span>
                    </div>
                  </div>

                  {modal.passed ? (
                    <div className="p-3 rounded-lg bg-[#10B981]/10 border border-[#10B981]/30 text-[#10B981] space-y-1">
                      <div className="font-bold flex items-center gap-1.5">
                        <CheckCircle2 className="w-4 h-4" />
                        <span>All 7 Pre-Flight Gates Passed</span>
                      </div>
                      <p className="text-[11px] text-[#C9D1D9]">
                        Quote locked for {modal.ttlSeconds}s. Submit requires explicit user confirmation.
                      </p>
                    </div>
                  ) : (
                    <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 space-y-1">
                      <div className="font-bold flex items-center gap-1.5">
                        <AlertTriangle className="w-4 h-4" />
                        <span>Pre-Flight Check Rejected</span>
                      </div>
                      <p className="text-[11px] text-[#C9D1D9]">
                        {modal.rejectionReason}
                      </p>
                    </div>
                  )}

                  <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#21262D]">
                    <button
                      type="button"
                      onClick={() => setModal(prev => ({ ...prev, isOpen: false }))}
                      className="px-4 py-2 rounded-lg bg-[#161B22] text-[#8B949E] hover:text-white font-semibold"
                    >
                      Cancel / Abort
                    </button>
                    {modal.passed && (
                      <button
                        type="button"
                        onClick={handleConfirmExecute}
                        disabled={modal.executing}
                        className="px-4 py-2 rounded-lg bg-[#10B981] hover:bg-[#059669] text-[#0D1117] font-bold shadow-lg shadow-[#10B981]/20 flex items-center gap-2"
                      >
                        {modal.executing ? (
                          <>
                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            <span>Submitting Order...</span>
                          </>
                        ) : (
                          <span>CONFIRM & SUBMIT LIVE ORDER</span>
                        )}
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
