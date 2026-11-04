"use client";

import React, { useState, useEffect, useRef } from "react";
import { Search, X, TrendingUp, TrendingDown, Clock, Activity, AlertCircle } from "lucide-react";

export interface PairItem {
  canonical_symbol: string;
  symbol?: string;
  name?: string;
  asset_class?: string;
  market?: string;
  price?: number;
  bid?: number;
  ask?: number;
  spread?: number;
  change_24h?: number;
  high_24h?: number;
  low_24h?: number;
  data_status?: "LIVE" | "STALE" | "DISCONNECTED" | "UNAVAILABLE";
  last_update?: string;
}

interface PairSearchSelectorProps {
  pairs: PairItem[];
  onSelectPair: (pair: PairItem) => void;
  isOpen: boolean;
  onClose: () => void;
}

export default function PairSearchSelector({
  pairs,
  onSelectPair,
  isOpen,
  onClose,
}: PairSearchSelectorProps) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery("");
    }
  }, [isOpen]);

  // Global Ctrl+K / Cmd+K listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (isOpen) onClose();
      } else if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const filteredPairs = pairs.filter((p) => {
    const sym = (p.canonical_symbol || p.symbol || "").toLowerCase();
    const name = (p.name || "").toLowerCase();
    const cat = (p.asset_class || p.market || "").toLowerCase();
    const q = query.toLowerCase().trim();
    return sym.includes(q) || name.includes(q) || cat.includes(q);
  });

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-12 sm:pt-20 px-3 bg-[#080B10]/80 backdrop-blur-md animate-in fade-in duration-150">
      <div
        className="fixed inset-0"
        onClick={onClose}
      />
      <div className="relative w-full max-w-2xl bg-[#0E131B] border border-[#1E2736] rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] z-10">
        {/* Search Input Bar */}
        <div className="p-3.5 sm:p-4 border-b border-[#1E2736] flex items-center gap-3 bg-[#151C28]/60">
          <Search className="w-5 h-5 text-[#94A3B8] shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search instrument by symbol or asset class (e.g., BTC, XAU, EUR)..."
            className="flex-1 bg-transparent text-sm sm:text-base font-mono text-[#F1F5F9] placeholder-[#64748B] focus:outline-none"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="p-1 rounded text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#1E2736]"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <span className="hidden sm:inline text-[10px] font-mono text-[#64748B] px-2 py-0.5 rounded border border-[#1E2736] bg-[#0E131B]">
            ESC
          </span>
        </div>

        {/* Results List */}
        <div className="flex-1 overflow-y-auto divide-y divide-[#1E2736] p-2">
          {filteredPairs.length === 0 ? (
            <div className="p-8 text-center text-xs font-mono text-[#64748B] space-y-2">
              <AlertCircle className="w-6 h-6 mx-auto text-[#64748B]" />
              <p>No verified instruments match "{query}"</p>
              <p className="text-[11px] text-[#475569]">Prices are strictly streamed from verified broker/exchange market feeds.</p>
            </div>
          ) : (
            filteredPairs.map((pair, idx) => {
              const sym = pair.canonical_symbol || pair.symbol || "UNKNOWN";
              const cat = pair.asset_class || pair.market || "CFD";
              const price = pair.price;
              const change = pair.change_24h ?? 0;
              const isPositive = change >= 0;
              const spread = pair.spread;

              return (
                <div
                  key={idx}
                  className="p-3 sm:p-3.5 hover:bg-[#151C28] transition-colors rounded-xl group"
                >
                  {/* DESKTOP 4-ZONE GRID (>= 640px) */}
                  <div className="hidden sm:grid grid-cols-[minmax(140px,1.5fr)_minmax(110px,1fr)_minmax(100px,1fr)_104px] gap-3 items-center">
                    {/* Zone 1: Pair & Category */}
                    <div className="min-w-0 pr-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-sm text-[#F1F5F9] group-hover:text-[#38BDF8] transition-colors truncate">
                          {sym}
                        </span>
                        <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-[#151C28] text-[#94A3B8] border border-[#1E2736] shrink-0">
                          {cat}
                        </span>
                      </div>
                      <div className="text-[11px] text-[#94A3B8] truncate mt-0.5">
                        {pair.name || `${sym} Perpetual`}
                      </div>
                    </div>

                    {/* Zone 2: Current Price & Spread */}
                    <div className="text-right sm:text-left">
                      <div className="text-xs font-mono font-bold text-[#F1F5F9] tabular-nums">
                        {typeof price === "number"
                          ? price >= 10
                            ? `$${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                            : `$${price.toFixed(4)}`
                          : <span className="text-[#64748B]">Unavailable</span>}
                      </div>
                      <div className="text-[10px] font-mono text-[#64748B] tabular-nums mt-0.5">
                        {spread !== undefined ? `Spread: ${spread.toFixed(1)} pts` : "Spread: --"}
                      </div>
                    </div>

                    {/* Zone 3: 24h Move */}
                    <div className="text-right">
                      <span
                        className={`inline-flex items-center gap-0.5 text-xs font-mono font-bold tabular-nums px-2 py-0.5 rounded border ${
                          isPositive
                            ? "bg-[#10B981]/12 text-[#10B981] border-[#10B981]/30"
                            : "bg-[#F43F5E]/12 text-[#F43F5E] border-[#F43F5E]/30"
                        }`}
                      >
                        {isPositive ? "+" : ""}{change.toFixed(2)}%
                      </span>
                    </div>

                    {/* Zone 4: CTA Button (Fixed 96px width) */}
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => {
                          onSelectPair(pair);
                          onClose();
                        }}
                        className="w-[96px] h-8 rounded-lg bg-[#38BDF8]/10 hover:bg-[#38BDF8] text-[#38BDF8] hover:text-[#080B10] text-xs font-mono font-bold border border-[#38BDF8]/30 transition-all flex items-center justify-center gap-1 cursor-pointer"
                      >
                        <Activity className="w-3 h-3" />
                        <span>Analyse</span>
                      </button>
                    </div>
                  </div>

                  {/* MOBILE 3-ROW TOUCH CARD (< 640px) */}
                  <div className="sm:hidden space-y-2.5">
                    {/* Row 1: Symbol & Category */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-base text-[#F1F5F9]">
                          {sym}
                        </span>
                        <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-[#151C28] text-[#94A3B8] border border-[#1E2736]">
                          {cat}
                        </span>
                      </div>
                      <span
                        className={`text-xs font-mono font-bold tabular-nums px-2 py-0.5 rounded border ${
                          isPositive
                            ? "bg-[#10B981]/12 text-[#10B981] border-[#10B981]/30"
                            : "bg-[#F43F5E]/12 text-[#F43F5E] border-[#F43F5E]/30"
                        }`}
                      >
                        {isPositive ? "+" : ""}{change.toFixed(2)}%
                      </span>
                    </div>

                    {/* Row 2: Metrics */}
                    <div className="flex items-center justify-between text-xs font-mono text-[#94A3B8] bg-[#151C28] p-2 rounded-lg border border-[#1E2736]">
                      <div>
                        <span className="text-[10px] text-[#64748B] block">Price</span>
                        <span className="font-bold text-[#F1F5F9] tabular-nums">
                          {typeof price === "number"
                            ? price >= 10
                              ? `$${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                              : `$${price.toFixed(4)}`
                            : "Unavailable"}
                        </span>
                      </div>
                      <div className="text-right">
                        <span className="text-[10px] text-[#64748B] block">Spread</span>
                        <span className="text-[#94A3B8] tabular-nums">
                          {spread !== undefined ? `${spread.toFixed(1)} pts` : "--"}
                        </span>
                      </div>
                    </div>

                    {/* Row 3: Full-width 44px Touch Button */}
                    <button
                      type="button"
                      onClick={() => {
                        onSelectPair(pair);
                        onClose();
                      }}
                      className="w-full h-11 rounded-xl bg-[#38BDF8] text-[#080B10] font-mono font-bold text-xs flex items-center justify-center gap-2 shadow-md shadow-[#38BDF8]/20 transition-all cursor-pointer"
                    >
                      <Activity className="w-4 h-4" />
                      <span>Analyse Instrument</span>
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer info */}
        <div className="p-3 bg-[#080B10] border-t border-[#1E2736] text-[11px] font-mono text-[#64748B] flex items-center justify-between">
          <span>Live market feeds • Zero synthetic fallback</span>
          <span className="text-[#38BDF8]">BITDEX Quantitative Terminal</span>
        </div>
      </div>
    </div>
  );
}
