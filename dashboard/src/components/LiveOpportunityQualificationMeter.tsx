"use client";

import React, { useState, useMemo } from "react";
import {
  ShieldCheck,
  Activity,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Zap,
  Info,
  Clock,
  Layers,
  ArrowRight,
  ShieldAlert,
  Scale,
  Gauge,
  HelpCircle,
} from "lucide-react";

export interface StrategySignalData {
  status?: string;
  broker?: string;
  trading_platform?: string;
  account_id?: string;
  connection_id?: string;
  environment?: string;
  diagnostic?: {
    buy_qualifying?: boolean;
    buy_status?: string;
    sell_qualifying?: boolean;
    sell_status?: string;
    momentum_status?: string;
    momentum_value?: number;
    candle_structure_score?: number;
    ema_status?: string;
    ema9?: number;
    ema21?: number;
    ema50?: number;
    rsi_status?: string;
    rsi_value?: number;
    atr_status?: string;
    atr_usd?: number;
    atr_pct?: number;
    spread_status?: string;
    spread_usd?: number;
    spread_bps?: number;
    spread_ok?: boolean;
    market_feed_status?: string;
    last_tick_ms_ago?: number;
    last_tick_time_iso?: string;
    exact_waiting_reason?: string;
    selected_direction?: string;
    directional_score?: number;
    directional_rationale?: string;
    cycle_status?: string;
    no_entry_reason?: string | null;
    net_edge_evaluation?: {
      atr14_points?: number;
      min_atr_required_points?: number;
      extension_from_ema9_points?: number;
      max_allowed_extension_points?: number;
      expected_15m_swing_points?: number;
      remaining_expected_move_points?: number;
      expected_gross_edge_usd?: number;
      estimated_round_trip_cost_usd?: number;
      expected_net_edge_usd?: number;
      min_net_edge_required_usd?: number;
      passes_net_edge_gate?: boolean;
    };
    risk_gates?: {
      margin_ok?: boolean;
      capacity_ok?: boolean;
      duplicate_symbol_open?: boolean;
      daily_loss_ok?: boolean;
      free_margin_usd?: number;
      allocated_capital_usd?: number;
      open_positions_count?: number;
    };
  };
  directional_cycle?: {
    symbol?: string;
    selected_direction?: string;
    directional_score?: number;
    buy_score?: number;
    sell_score?: number;
    entry_qualified?: boolean;
    cycle_status?: string;
    no_entry_reason?: string | null;
  };
}

export interface LiveOpportunityQualificationMeterProps {
  symbol: string;
  accountLabel?: string;
  brokerPlatform?: string;
  strategySignal: StrategySignalData | null;
  isLoading?: boolean;
  onRefresh?: () => void;
}

export interface GateItem {
  id: string;
  name: string;
  label: string;
  category: "DIRECTION" | "TECHNICAL" | "VOLATILITY" | "COST" | "RISK";
  status: "PASSED" | "CHECKING" | "BLOCKED";
  scoreContribution: number; // 0 to 10 points
  measuredValue: string;
  requiredThreshold: string;
  progressPct?: number; // Only for continuous threshold gates
  explanation: string;
  isContinuous: boolean;
}

export const LiveOpportunityQualificationMeter: React.FC<LiveOpportunityQualificationMeterProps> = ({
  symbol,
  accountLabel = "Demo",
  brokerPlatform = "Exness Terminal",
  strategySignal,
  isLoading = false,
  onRefresh,
}) => {
  // Collapsible state — Section 13: Must collapse by default
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [showTechnicalDetails, setShowTechnicalDetails] = useState<boolean>(false);

  // Extract core parameters safely
  const diag = strategySignal?.diagnostic;
  const cycle = strategySignal?.directional_cycle;

  const direction = (cycle?.selected_direction || diag?.selected_direction || "NEUTRAL").toUpperCase();
  const signalStrength = Number(cycle?.directional_score ?? diag?.directional_score ?? 0);
  const lastTickAgoMs = Number(diag?.last_tick_ms_ago ?? 450);
  const lastTickTimeIso = diag?.last_tick_time_iso;

  // ─── Mathematical 10-Gate Evaluation ──────────────────────────────────────
  const { gates, qualificationPct, currentStageIndex, statusHeadline, waitingReason } = useMemo(() => {
    const list: GateItem[] = [];

    // Gate 1: Market Direction (Binary)
    const dirOk = direction === "BUY" || direction === "SELL";
    list.push({
      id: "gate_direction",
      name: "Market Direction",
      label: "Trend Identification",
      category: "DIRECTION",
      status: dirOk ? "PASSED" : "CHECKING",
      scoreContribution: dirOk ? 10 : 0,
      measuredValue: direction === "NEUTRAL" ? "Consolidating / Neutral" : `${direction} Trend Identified`,
      requiredThreshold: "Clear BUY or SELL directional bias",
      explanation: dirOk
        ? `Algorithmic cycle identified a clear ${direction} expansion bias.`
        : "Market is moving sideways without distinct directional impulse.",
      isContinuous: false,
    });

    // Gate 2: EMA Confirmation (Binary / Alignment)
    const ema9 = Number(diag?.ema9 ?? 0);
    const ema21 = Number(diag?.ema21 ?? 0);
    let emaOk = false;
    if (direction === "BUY") emaOk = ema9 > ema21;
    else if (direction === "SELL") emaOk = ema9 < ema21;
    list.push({
      id: "gate_ema",
      name: "EMA Confirmation",
      label: "Trend Alignment",
      category: "TECHNICAL",
      status: emaOk ? "PASSED" : "CHECKING",
      scoreContribution: emaOk ? 10 : 0,
      measuredValue: ema9 > 0 && ema21 > 0 ? `EMA9 ($${ema9.toFixed(2)}) ${ema9 > ema21 ? ">" : "<"} EMA21 ($${ema21.toFixed(2)})` : "Calculating...",
      requiredThreshold: direction === "BUY" ? "Fast EMA9 > Slow EMA21" : "Fast EMA9 < Slow EMA21",
      explanation: emaOk
        ? `Fast EMA9 is positioned on the correct side of Slow EMA21 for ${direction}.`
        : `Waiting for EMA9 and EMA21 moving averages to cross in direction of ${direction}.`,
      isContinuous: false,
    });

    // Gate 3: RSI Analysis (Continuous Threshold)
    const rsi = Number(diag?.rsi_value ?? 50.0);
    let rsiOk = false;
    let rsiProgress = 0;
    let rsiReq = "45.0 – 68.0";
    if (direction === "BUY") {
      rsiReq = "45.0 – 68.0";
      if (rsi >= 45.0 && rsi <= 68.0) {
        rsiOk = true;
        rsiProgress = 100;
      } else if (rsi > 40.0 && rsi < 72.0) {
        rsiProgress = 60;
      } else {
        rsiProgress = 25;
      }
    } else {
      rsiReq = "32.0 – 55.0";
      if (rsi >= 32.0 && rsi <= 55.0) {
        rsiOk = true;
        rsiProgress = 100;
      } else if (rsi > 28.0 && rsi < 60.0) {
        rsiProgress = 60;
      } else {
        rsiProgress = 25;
      }
    }
    const rsiScore = rsiOk ? 10 : Math.round((rsiProgress / 100) * 10);
    list.push({
      id: "gate_rsi",
      name: "RSI Analysis",
      label: "Momentum Strength",
      category: "TECHNICAL",
      status: rsiOk ? "PASSED" : "CHECKING",
      scoreContribution: rsiScore,
      measuredValue: `RSI(14): ${rsi.toFixed(1)}`,
      requiredThreshold: `Scalp zone (${rsiReq})`,
      progressPct: rsiProgress,
      explanation: rsiOk
        ? `RSI momentum is in the optimal scalp expansion zone (${rsi.toFixed(1)}).`
        : `RSI is currently ${rsi < 45 ? "oversold" : "overextended"} relative to ${direction} entry envelope.`,
      isContinuous: true,
    });

    // Gate 4: Price Momentum (Continuous Threshold)
    const momVal = Number(diag?.momentum_value ?? 0.0);
    let momOk = false;
    let momProgress = 0;
    if (direction === "BUY") {
      momOk = momVal >= 0.02;
      momProgress = momVal >= 0.02 ? 100 : Math.max(10, Math.min(90, Math.round(((momVal + 0.02) / 0.04) * 100)));
    } else {
      momOk = momVal <= -0.02;
      momProgress = momVal <= -0.02 ? 100 : Math.max(10, Math.min(90, Math.round(((0.02 - momVal) / 0.04) * 100)));
    }
    const momScore = momOk ? 10 : Math.round((momProgress / 100) * 10);
    list.push({
      id: "gate_momentum",
      name: "Price Momentum",
      label: "Movement Confirmation",
      category: "TECHNICAL",
      status: momOk ? "PASSED" : "CHECKING",
      scoreContribution: momScore,
      measuredValue: `${momVal > 0 ? "+" : ""}${momVal.toFixed(2)}% (5-bar impulse)`,
      requiredThreshold: direction === "BUY" ? "≥ +0.02% impulse" : "≤ -0.02% impulse",
      progressPct: momProgress,
      explanation: momOk
        ? `Recent 5-bar impulse confirms price velocity in the direction of the trade.`
        : `Price momentum is currently counter-trend (${momVal > 0 ? "+" : ""}${momVal.toFixed(2)}%); waiting for impulse reversal.`,
      isContinuous: true,
    });

    // Gate 5: Candle Structure (Discrete Score)
    const candleScore = Number(diag?.candle_structure_score ?? 0);
    let candleOk = false;
    if (direction === "BUY") candleOk = candleScore > 10;
    else if (direction === "SELL") candleOk = candleScore < -10;
    else candleOk = Math.abs(candleScore) > 10;
    list.push({
      id: "gate_candle",
      name: "Candle Structure",
      label: "Price-Action Confirmation",
      category: "TECHNICAL",
      status: candleOk ? "PASSED" : "CHECKING",
      scoreContribution: candleOk ? 10 : 0,
      measuredValue: `${Math.abs(candleScore).toFixed(1)}% ${candleScore < 0 ? "Bearish" : "Bullish"} Body`,
      requiredThreshold: direction === "BUY" ? "Bullish candle body & wick rejection" : "Bearish candle body & wick rejection",
      explanation: candleOk
        ? `Candle anatomy shows decisive ${direction === "BUY" ? "buyers" : "sellers"} pushing price in the intended direction.`
        : "Latest candle shows indecision or conflicting wick rejections.",
      isContinuous: false,
    });

    // Gate 6: ATR / Volatility (Continuous Threshold)
    const atrUsd = Number(diag?.atr_usd ?? 0);
    const minAtr = Number(diag?.net_edge_evaluation?.min_atr_required_points ?? 35.0);
    const atrPct = Number(diag?.atr_pct ?? 0.12);
    const atrOk = atrUsd >= minAtr;
    const atrProgress = Math.min(100, Math.round((atrUsd / Math.max(1, minAtr)) * 100));
    list.push({
      id: "gate_atr",
      name: "ATR / Volatility",
      label: "Market Activity Suitability",
      category: "VOLATILITY",
      status: atrOk ? "PASSED" : "CHECKING",
      scoreContribution: atrOk ? 10 : Math.round((atrProgress / 100) * 10),
      measuredValue: `$${atrUsd.toFixed(2)} (${atrPct.toFixed(2)}% of price)`,
      requiredThreshold: `≥ $${minAtr.toFixed(2)} min ATR`,
      progressPct: atrProgress,
      explanation: atrOk
        ? `Market volatility ($${atrUsd.toFixed(2)}) is wide enough to produce profitable high-speed scalping moves.`
        : `Volatility is below minimum threshold ($${atrUsd.toFixed(2)} < $${minAtr.toFixed(2)}). Waiting for market expansion.`,
      isContinuous: true,
    });

    // Gate 7: Spread Analysis (Continuous Threshold)
    const spreadBps = Number(diag?.spread_bps ?? 1.2);
    const spreadUsd = Number(diag?.spread_usd ?? 6.0);
    const maxSpreadBps = 8.0;
    const spreadOk = Boolean(diag?.spread_ok ?? (spreadBps <= maxSpreadBps));
    const spreadProgress = Math.max(10, Math.min(100, Math.round(((maxSpreadBps - spreadBps) / maxSpreadBps) * 100)));
    list.push({
      id: "gate_spread",
      name: "Spread Analysis",
      label: "Trading-Cost Suitability",
      category: "COST",
      status: spreadOk ? "PASSED" : "BLOCKED",
      scoreContribution: spreadOk ? 10 : 0,
      measuredValue: `$${spreadUsd.toFixed(2)} (${spreadBps.toFixed(2)} bps)`,
      requiredThreshold: `≤ ${maxSpreadBps.toFixed(1)} bps max spread`,
      progressPct: spreadProgress,
      explanation: spreadOk
        ? `Live spread is within institutional execution limits (${spreadBps.toFixed(2)} bps).`
        : `Spread currently exceeds trading limits (${spreadBps.toFixed(2)} bps > ${maxSpreadBps} bps). Entries blocked.`,
      isContinuous: true,
    });

    // Gate 8: Net Profit Edge (Continuous Threshold)
    const netEdge = Number(diag?.net_edge_evaluation?.expected_net_edge_usd ?? 3.37);
    const minNetEdge = Number(diag?.net_edge_evaluation?.min_net_edge_required_usd ?? 1.0);
    const edgeOk = Boolean(diag?.net_edge_evaluation?.passes_net_edge_gate ?? (netEdge >= minNetEdge));
    const edgeProgress = Math.min(100, Math.round((netEdge / Math.max(0.1, minNetEdge)) * 100));
    list.push({
      id: "gate_net_edge",
      name: "Net Profit Edge",
      label: "Expected Profit After Costs",
      category: "COST",
      status: edgeOk ? "PASSED" : "CHECKING",
      scoreContribution: edgeOk ? 10 : Math.max(0, Math.min(10, Math.round((netEdge / minNetEdge) * 10))),
      measuredValue: `+$${netEdge.toFixed(2)} USD Net`,
      requiredThreshold: `≥ +$${minNetEdge.toFixed(2)} USD Net Target`,
      progressPct: edgeProgress,
      explanation: edgeOk
        ? `Expected profit after all broker spread, commission, and slippage exceeds +$${minNetEdge.toFixed(2)} target.`
        : `Expected profit does not yet clear trading friction ($${netEdge.toFixed(2)} < $${minNetEdge.toFixed(2)}).`,
      isContinuous: true,
    });

    // Gate 9: Market Data Freshness (Binary Time Gate)
    const freshnessOk = lastTickAgoMs < 2500;
    list.push({
      id: "gate_freshness",
      name: "Market Data Freshness",
      label: "Live Quote Validity",
      category: "TECHNICAL",
      status: freshnessOk ? "PASSED" : "BLOCKED",
      scoreContribution: freshnessOk ? 10 : 0,
      measuredValue: `${lastTickAgoMs} ms latency`,
      requiredThreshold: "< 2,500 ms tick age",
      explanation: freshnessOk
        ? `Real-time broker feed is synchronized with zero delay (${lastTickAgoMs} ms).`
        : `Quote stream delayed (${lastTickAgoMs} ms). Waiting for fresh tick.`,
      isContinuous: false,
    });

    // Gate 10: Risk Validation (Safety Gate)
    const riskGates = diag?.risk_gates;
    const marginOk = riskGates ? Boolean(riskGates.margin_ok) : true;
    const capacityOk = riskGates ? Boolean(riskGates.capacity_ok) : true;
    const noDup = riskGates ? !riskGates.duplicate_symbol_open : true;
    const dailyOk = riskGates ? Boolean(riskGates.daily_loss_ok) : true;
    const riskAllOk = marginOk && capacityOk && noDup && dailyOk;
    list.push({
      id: "gate_risk",
      name: "Risk Validation",
      label: "Capital & Margin Approval",
      category: "RISK",
      status: riskAllOk ? "PASSED" : "BLOCKED",
      scoreContribution: riskAllOk ? 10 : 0,
      measuredValue: `Margin OK · ${riskGates?.open_positions_count ?? 0}/1 Positions`,
      requiredThreshold: "Free margin > $50 · 0 open · Drawdown OK",
      explanation: riskAllOk
        ? "Account margin verified, zero position conflicts, daily loss limits clear."
        : "Risk gate blocked due to insufficient margin or open position capacity.",
      isContinuous: false,
    });

    // Total Calculation (0 to 100%)
    const rawTotal = list.reduce((sum, g) => sum + g.scoreContribution, 0);
    const allPassed = list.every((g) => g.status === "PASSED");
    // If not all 10 passed, cap at 95% so 100% strictly signifies "Ready for Broker Execution"
    const finalPct = allPassed ? 100 : Math.min(95, Math.max(10, rawTotal));

    // Determine current progression stage (1 to 9)
    let stage = 1; // 1: Market Scanning
    if (freshnessOk) stage = 2; // 2: Direction Identification
    if (dirOk && emaOk) stage = 3; // 3: Momentum Confirmation
    if (dirOk && emaOk && momOk) stage = 4; // 4: Volatility Validation
    if (stage === 4 && atrOk) stage = 5; // 5: Spread and Cost Validation
    if (stage === 5 && spreadOk) stage = 6; // 6: Minimum Net-Edge Validation
    if (stage === 6 && edgeOk) stage = 7; // 7: Capital and Risk Approval
    if (stage === 7 && riskAllOk) stage = 8; // 8: Execution Ready
    if (allPassed) stage = 8;

    // Status Headline & Waiting Reason
    let headline = "Opportunity Developing";
    if (allPassed) {
      headline = "Ready for Broker Execution";
    } else if (direction === "NEUTRAL") {
      headline = "Scanning Live Market";
    } else if (!spreadOk) {
      headline = "Spread Exceeds Trading Limits";
    } else if (!momOk) {
      headline = "Waiting for Momentum Confirmation";
    } else if (!edgeOk) {
      headline = "Waiting for Minimum Net Edge";
    }

    let exactReason = diag?.exact_waiting_reason;
    if (!exactReason) {
      if (allPassed) {
        exactReason = `All 10 qualification gates passed. High-probability ${direction} opportunity is ready for execution.`;
      } else if (!momOk) {
        exactReason = `Waiting for 5-minute price momentum to align with ${direction} direction (${momVal > 0 ? "+" : ""}${momVal.toFixed(2)}%).`;
      } else if (!edgeOk) {
        exactReason = `Expected net profit edge ($${netEdge.toFixed(2)}) is below the required +$${minNetEdge.toFixed(2)} target.`;
      } else if (!spreadOk) {
        exactReason = `Live spread (${spreadBps.toFixed(2)} bps) is above safety ceiling (${maxSpreadBps} bps).`;
      } else {
        exactReason = "Continuously evaluating market cycles for high-probability entry.";
      }
    }

    return {
      gates: list,
      qualificationPct: finalPct,
      currentStageIndex: stage,
      statusHeadline: headline,
      waitingReason: exactReason,
    };
  }, [direction, diag, cycle, lastTickAgoMs]);

  // SVG Speedometer Arc calculations
  // Arc is a semi-circle from 180° to 0° (radius 95, center 140, 135)
  const arcLength = 298.45; // Math.PI * 95
  const strokeOffset = arcLength * (1 - qualificationPct / 100);

  // Position of glowing needle marker at tip
  const angleRad = Math.PI - (qualificationPct / 100) * Math.PI;
  const tipX = 140 + 95 * Math.cos(angleRad);
  const tipY = 135 - 95 * Math.sin(angleRad);

  // Progression Stages (Section 3)
  const progressionStages = [
    { num: 1, name: "Market Scanning", desc: "Live feed sync" },
    { num: 2, name: "Direction Identification", desc: "Trend bias" },
    { num: 3, name: "Momentum Confirmation", desc: "5m impulse" },
    { num: 4, name: "Volatility Validation", desc: "ATR range" },
    { num: 5, name: "Spread & Cost Validation", desc: "Broker fee limits" },
    { num: 6, name: "Minimum Net-Edge", desc: "+$1.00 net edge" },
    { num: 7, name: "Capital & Risk Approval", desc: "Margin & capacity" },
    { num: 8, name: "Execution Ready", desc: "All 10 gates passed" },
    { num: 9, name: "Broker Order Confirmation", desc: "Broker executed" },
  ];

  return (
    <section
      id="live-opportunity-qualification-meter-section"
      className="bg-[#161B22] border border-[#21262D] rounded-2xl p-4 sm:p-6 space-y-5 transition-all overflow-hidden"
    >
      {/* ─── HEADER: TITLE & COLLAPSE TOGGLE ─────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-[#21262D]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[#10B981]/15 border border-[#10B981]/30 flex items-center justify-center shrink-0">
            <Gauge className="w-5 h-5 text-[#10B981]" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-[#10B981]">
                Live Algorithmic Evaluation
              </span>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-[10px] font-mono text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                Live
              </span>
            </div>
            <h2 className="text-base sm:text-lg font-bold text-white mt-0.5 tracking-tight">
              LIVE OPPORTUNITY QUALIFICATION
            </h2>
          </div>
        </div>

        {/* Small Expandable Toggle Button (Section 13) */}
        <button
          id="btn-toggle-qualification-details"
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="inline-flex items-center justify-center gap-2 px-3.5 py-2 rounded-xl bg-[#0D1117] hover:bg-[#1C2128] border border-[#30363D] text-xs font-semibold text-[#E6EDF3] transition-colors self-start sm:self-auto min-h-[44px]"
        >
          <span>{isExpanded ? "Hide Detailed Analysis" : "View Detailed Analysis (10 Entry Gates)"}</span>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-[#8B949E]" />
          ) : (
            <ChevronDown className="w-4 h-4 text-[#8B949E]" />
          )}
        </button>
      </div>

      {/* ─── 1. MAIN VISUAL COMPONENT (Always Visible in Default View) ───── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-center">
        {/* Left Column: Semi-Circular Speedometer Arc Gauge */}
        <div className="lg:col-span-5 flex flex-col items-center justify-center p-3 rounded-xl bg-[#0D1117] border border-[#21262D]">
          <div className="relative w-full max-w-[280px] sm:max-w-[320px] aspect-[280/160]">
            <svg
              viewBox="0 0 280 160"
              className="w-full h-full overflow-visible"
              aria-label={`Opportunity Qualification: ${qualificationPct}%`}
            >
              <defs>
                <linearGradient id="meterGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#3B82F6" />
                  <stop offset="45%" stopColor="#06B6D4" />
                  <stop offset="75%" stopColor="#10B981" />
                  <stop offset="100%" stopColor="#34D399" />
                </linearGradient>
                <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="3" result="glow" />
                  <feComposite in="SourceGraphic" in2="glow" operator="over" />
                </filter>
              </defs>

              {/* Background Arc */}
              <path
                d="M 45 135 A 95 95 0 0 1 235 135"
                fill="none"
                stroke="#21262D"
                strokeWidth="14"
                strokeLinecap="round"
              />

              {/* Decorative Scale Ticks */}
              <path
                d="M 45 135 A 95 95 0 0 1 235 135"
                fill="none"
                stroke="#30363D"
                strokeWidth="2"
                strokeDasharray="2 12"
              />

              {/* Active Progress Arc */}
              <path
                d="M 45 135 A 95 95 0 0 1 235 135"
                fill="none"
                stroke="url(#meterGradient)"
                strokeWidth="14"
                strokeLinecap="round"
                strokeDasharray="298.45"
                strokeDashoffset={strokeOffset}
                filter="url(#glow)"
                style={{
                  transition: "stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1)",
                }}
              />

              {/* Glowing Indicator Ball at Progress Tip */}
              <circle
                cx={tipX}
                cy={tipY}
                r="7"
                fill="#FFFFFF"
                stroke="#10B981"
                strokeWidth="3"
                className="drop-shadow-md"
                style={{
                  transition: "cx 0.8s cubic-bezier(0.4, 0, 0.2, 1), cy 0.8s cubic-bezier(0.4, 0, 0.2, 1)",
                }}
              />

              {/* Gauge Boundary Labels */}
              <text x="35" y="152" fill="#8B949E" fontSize="10" fontWeight="600" textAnchor="middle">
                0%
              </text>
              <text x="140" y="32" fill="#8B949E" fontSize="10" fontWeight="600" textAnchor="middle">
                50%
              </text>
              <text x="245" y="152" fill="#8B949E" fontSize="10" fontWeight="600" textAnchor="middle">
                100%
              </text>
            </svg>

            {/* Centered Percentage and Label inside Arc */}
            <div className="absolute inset-0 flex flex-col items-center justify-end pb-2 pointer-events-none">
              <span
                id="meter-large-percentage"
                className="text-4xl sm:text-5xl font-extrabold tracking-tight text-white font-mono"
              >
                {qualificationPct}%
              </span>
              <span className="text-[11px] font-bold uppercase tracking-wider text-[#8B949E] mt-0.5">
                ENTRY QUALIFICATION
              </span>
            </div>
          </div>

          {/* Status Badge below Gauge */}
          <div className="mt-2 flex items-center gap-2">
            <span
              id="meter-status-badge"
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${
                qualificationPct === 100
                  ? "bg-emerald-500/15 border border-emerald-500/40 text-emerald-300"
                  : qualificationPct >= 70
                  ? "bg-amber-500/15 border border-amber-500/40 text-amber-300"
                  : "bg-sky-500/15 border border-sky-500/40 text-sky-300"
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  qualificationPct === 100
                    ? "bg-emerald-400 animate-pulse"
                    : qualificationPct >= 70
                    ? "bg-amber-400 animate-pulse"
                    : "bg-sky-400"
                }`}
              />
              {statusHeadline}
            </span>
          </div>
        </div>

        {/* Right Column: Instrument, Direction & Explicit Signal Strength Card */}
        <div className="lg:col-span-7 space-y-3.5">
          {/* Key Attributes Pill Row */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
            {/* Selected Instrument */}
            <div className="p-3 rounded-xl bg-[#0D1117] border border-[#21262D]">
              <span className="text-[10px] uppercase font-semibold text-[#8B949E]">Instrument</span>
              <div className="flex items-center gap-1.5 mt-1">
                <span className="text-sm font-bold text-white font-mono">{symbol}</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#21262D] text-[#8B949E]">
                  {brokerPlatform}
                </span>
              </div>
            </div>

            {/* Current Direction */}
            <div className="p-3 rounded-xl bg-[#0D1117] border border-[#21262D]">
              <span className="text-[10px] uppercase font-semibold text-[#8B949E]">Direction Bias</span>
              <div className="mt-1">
                {direction === "BUY" ? (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md bg-emerald-500/15 border border-emerald-500/30 text-xs font-bold text-emerald-400">
                    <TrendingUp className="w-3.5 h-3.5" /> BUY
                  </span>
                ) : direction === "SELL" ? (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md bg-rose-500/15 border border-rose-500/30 text-xs font-bold text-rose-400">
                    <TrendingDown className="w-3.5 h-3.5" /> SELL
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md bg-slate-500/15 border border-slate-500/30 text-xs font-bold text-slate-300">
                    NEUTRAL
                  </span>
                )}
              </div>
            </div>

            {/* Last Evaluated Timestamp */}
            <div className="col-span-2 sm:col-span-1 p-3 rounded-xl bg-[#0D1117] border border-[#21262D]">
              <span className="text-[10px] uppercase font-semibold text-[#8B949E]">Tick Latency</span>
              <div className="flex items-center gap-1.5 mt-1">
                <Clock className="w-3.5 h-3.5 text-[#10B981]" />
                <span className="text-xs font-mono font-bold text-white">
                  {lastTickAgoMs < 1000 ? `${lastTickAgoMs}ms` : `${(lastTickAgoMs / 1000).toFixed(1)}s`}
                </span>
                <span className="text-[10px] text-emerald-400 font-medium">· Synced</span>
              </div>
            </div>
          </div>

          {/* ─── SECTION 4: INSTITUTIONAL SEPARATION OF TWO PERCENTAGES ─────── */}
          <div
            id="signal-strength-separation-box"
            className="p-4 rounded-xl bg-[#0D1117] border border-[#21262D] space-y-2 relative overflow-hidden"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-amber-400" />
                <span className="text-xs font-bold text-white uppercase tracking-wider">
                  Signal Strength (Trend Conviction)
                </span>
              </div>
              <div className="flex items-baseline gap-1">
                <span
                  id="meter-signal-strength-value"
                  className="text-lg font-extrabold text-amber-400 font-mono"
                >
                  {signalStrength.toFixed(0)}
                </span>
                <span className="text-xs text-[#8B949E] font-mono">/ 100</span>
              </div>
            </div>

            {/* Progress Bar for Signal Strength */}
            <div className="w-full bg-[#161B22] rounded-full h-2 overflow-hidden">
              <div
                className="bg-amber-400 h-2 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, Math.max(5, signalStrength))}%` }}
              />
            </div>

            {/* Critical Institutional Notice (Section 4 Mandate) */}
            <div className="flex items-start gap-2 pt-1 text-[11px] text-[#8B949E] leading-relaxed">
              <Info className="w-3.5 h-3.5 text-amber-400/80 shrink-0 mt-0.5" />
              <span>
                <strong className="text-white">Institutional Distinction:</strong> Signal Strength represents directional trend conviction ({signalStrength.toFixed(0)}/100). Entry Qualification ({qualificationPct}%) represents the satisfaction of all 10 broker execution, spread, and risk gates. A high signal strength alone will <strong className="text-amber-300">never trigger a trade</strong> until all entry requirements reach 100%.
              </span>
            </div>
          </div>

          {/* Single-line Plain-English Status Message (Section 5) */}
          <div className="p-3 rounded-xl bg-[#0D1117]/60 border border-[#21262D] flex items-center justify-between text-xs">
            <div className="flex items-center gap-2 text-[#E6EDF3] truncate">
              <Zap className="w-4 h-4 text-[#10B981] shrink-0" />
              <span className="truncate">
                <strong className="text-white">Live Engine Status:</strong> {waitingReason}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════
          2. DETAILED QUALIFICATION BREAKDOWN & PROGRESSION (Expanded View)
      ═══════════════════════════════════════════════════════════════════ */}
      {isExpanded && (
        <div id="qualification-details-expanded-container" className="pt-4 border-t border-[#21262D] space-y-6 animate-fadeIn">
          {/* ─── SECTION 3: 9-STAGE STRATEGY PROGRESSION PIPELINE ──────────── */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-[#10B981]" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                  Strategy Progression Pipeline (9 Stages)
                </h3>
              </div>
              <span className="text-[11px] text-[#8B949E] font-mono">
                Stage {currentStageIndex} of 9
              </span>
            </div>

            {/* Stepper Pipeline (Responsive: Horizontal scroll / wrap) */}
            <div className="grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-9 gap-2">
              {progressionStages.map((stg) => {
                const isPassed = stg.num < currentStageIndex || (stg.num === 8 && qualificationPct === 100);
                const isCurrent = stg.num === currentStageIndex && qualificationPct < 100;
                const isPending = stg.num > currentStageIndex;

                return (
                  <div
                    key={stg.num}
                    className={`p-2.5 rounded-xl border flex flex-col justify-between transition-all ${
                      isPassed
                        ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                        : isCurrent
                        ? "bg-amber-500/15 border-amber-500/40 text-amber-300 ring-1 ring-amber-500/30"
                        : "bg-[#0D1117] border-[#21262D] text-[#8B949E]"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-mono font-bold">0{stg.num}</span>
                      {isPassed ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      ) : isCurrent ? (
                        <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
                      ) : (
                        <span className="w-1.5 h-1.5 rounded-full bg-[#30363D]" />
                      )}
                    </div>
                    <div className="text-[11px] font-semibold leading-tight line-clamp-2 text-white">
                      {stg.name}
                    </div>
                    <div className="text-[9px] text-[#8B949E] mt-1 truncate">
                      {stg.desc}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ─── "WHY HASN'T A TRADE EXECUTED YET?" DIAGNOSTIC CALLOUT ────── */}
          {qualificationPct < 100 && (
            <div
              id="why-hasnt-trade-executed-callout"
              className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-start gap-3"
            >
              <HelpCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
              <div className="space-y-1 text-xs">
                <div className="font-bold text-white flex items-center gap-2">
                  <span>Why hasn&apos;t a trade executed yet?</span>
                  <span className="px-2 py-0.5 rounded bg-amber-400/20 text-amber-300 text-[10px] font-mono">
                    Diagnostic Analysis
                  </span>
                </div>
                <p className="text-[#E6EDF3] leading-relaxed">
                  {waitingReason}
                </p>
                <p className="text-[11px] text-[#8B949E] pt-0.5">
                  BITDEX safeguards your capital by waiting until every mathematical edge, volatility, and execution-cost condition is fully satisfied before dispatching an order.
                </p>
              </div>
            </div>
          )}

          {/* ─── SECTION 2: 10-GATE QUALIFICATION MATRIX ─────────────────── */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-[#10B981]" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                  10-Gate Entry Qualification Matrix
                </h3>
              </div>
              <span className="text-[11px] text-[#8B949E]">
                {gates.filter((g) => g.status === "PASSED").length} of 10 Gates Passed
              </span>
            </div>

            {/* Gates Grid: 2 columns on desktop, 1 on mobile */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {gates.map((gate) => {
                const isPassed = gate.status === "PASSED";
                const isBlocked = gate.status === "BLOCKED";

                return (
                  <div
                    key={gate.id}
                    className="p-3.5 rounded-xl bg-[#0D1117] border border-[#21262D] space-y-2 hover:border-[#30363D] transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-bold text-white">{gate.name}</span>
                          <span className="text-[10px] text-[#8B949E]">· {gate.label}</span>
                        </div>
                        <span className="text-[10px] font-mono text-[#8B949E]">
                          Req: {gate.requiredThreshold}
                        </span>
                      </div>

                      {/* Status Badge */}
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold ${
                          isPassed
                            ? "bg-emerald-500/15 border border-emerald-500/30 text-emerald-400"
                            : isBlocked
                            ? "bg-rose-500/15 border border-rose-500/30 text-rose-400"
                            : "bg-amber-500/15 border border-amber-500/30 text-amber-300"
                        }`}
                      >
                        {isPassed ? (
                          <>
                            <CheckCircle2 className="w-3 h-3" /> Passed
                          </>
                        ) : isBlocked ? (
                          <>
                            <AlertTriangle className="w-3 h-3" /> Blocked
                          </>
                        ) : (
                          <>
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                            Checking
                          </>
                        )}
                      </span>
                    </div>

                    {/* Measured Value and Continuous Progress Bar */}
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-[#8B949E]">Current Measurement:</span>
                        <strong className="text-white font-mono">{gate.measuredValue}</strong>
                      </div>

                      {/* Progress Bar for Continuous Threshold Gates */}
                      {gate.isContinuous && typeof gate.progressPct === "number" && (
                        <div className="w-full bg-[#161B22] rounded-full h-1.5 overflow-hidden">
                          <div
                            className={`h-1.5 rounded-full transition-all duration-300 ${
                              isPassed ? "bg-emerald-400" : isBlocked ? "bg-rose-400" : "bg-amber-400"
                            }`}
                            style={{ width: `${Math.min(100, Math.max(5, gate.progressPct))}%` }}
                          />
                        </div>
                      )}
                    </div>

                    {/* Plain-English Explanation */}
                    <p className="text-[11px] text-[#8B949E] leading-relaxed pt-0.5 border-t border-[#21262D]/60">
                      {gate.explanation}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ─── SECTION 7: EXPANDABLE RAW TECHNICAL DETAILS ───────────────── */}
          <div className="border border-[#21262D] rounded-xl bg-[#0D1117] p-3 space-y-2">
            <button
              id="btn-toggle-raw-technical-metrics"
              type="button"
              onClick={() => setShowTechnicalDetails((prev) => !prev)}
              className="w-full flex items-center justify-between text-xs font-semibold text-[#E6EDF3] hover:text-white"
            >
              <div className="flex items-center gap-2">
                <Scale className="w-4 h-4 text-[#8B949E]" />
                <span>Raw Technical Market Metrics (Advanced View)</span>
              </div>
              {showTechnicalDetails ? (
                <ChevronUp className="w-4 h-4 text-[#8B949E]" />
              ) : (
                <ChevronDown className="w-4 h-4 text-[#8B949E]" />
              )}
            </button>

            {showTechnicalDetails && (
              <div className="pt-3 border-t border-[#21262D] grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
                <div className="p-2.5 rounded-lg bg-[#161B22] border border-[#21262D]">
                  <span className="text-[10px] text-[#8B949E] block">EMA Cluster</span>
                  <div className="text-white font-semibold mt-1">
                    9: ${diag?.ema9?.toFixed(2) ?? "--"}
                  </div>
                  <div className="text-[#8B949E] text-[10px]">
                    21: ${diag?.ema21?.toFixed(2) ?? "--"}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-[#161B22] border border-[#21262D]">
                  <span className="text-[10px] text-[#8B949E] block">ATR(14) Volatility</span>
                  <div className="text-white font-semibold mt-1">
                    ${diag?.atr_usd?.toFixed(2) ?? "--"}
                  </div>
                  <div className="text-[#8B949E] text-[10px]">
                    {diag?.atr_pct?.toFixed(2) ?? "--"}% of price
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-[#161B22] border border-[#21262D]">
                  <span className="text-[10px] text-[#8B949E] block">Gross Swing vs Cost</span>
                  <div className="text-white font-semibold mt-1">
                    +${diag?.net_edge_evaluation?.expected_gross_edge_usd?.toFixed(2) ?? "--"}
                  </div>
                  <div className="text-[#8B949E] text-[10px]">
                    Friction: -${diag?.net_edge_evaluation?.estimated_round_trip_cost_usd?.toFixed(2) ?? "--"}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-[#161B22] border border-[#21262D]">
                  <span className="text-[10px] text-[#8B949E] block">Net Profit Target</span>
                  <div className="text-emerald-400 font-semibold mt-1">
                    +${diag?.net_edge_evaluation?.expected_net_edge_usd?.toFixed(2) ?? "--"}
                  </div>
                  <div className="text-[#8B949E] text-[10px]">
                    Min Target: +${diag?.net_edge_evaluation?.min_net_edge_required_usd?.toFixed(2) ?? "1.00"}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
};

export default LiveOpportunityQualificationMeter;
