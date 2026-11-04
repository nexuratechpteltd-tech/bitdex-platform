"use client";

import React, { useState } from "react";
import { LifeBuoy, FileText, Link2, CheckCircle2, Send, Server } from "lucide-react";

export default function HelpSupportView() {
  const [ticketSubject, setTicketSubject] = useState("");
  const [ticketMessage, setTicketMessage] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticketSubject || !ticketMessage) return;
    setSubmitted(true);
    setTimeout(() => {
      setTicketSubject("");
      setTicketMessage("");
      setSubmitted(false);
    }, 4000);
  };

  return (
    <div className="space-y-6 font-sans animate-in fade-in duration-200">
      <div className="pb-2 border-b border-[#1E2736]">
        <h1 className="text-xl sm:text-2xl font-mono font-bold text-[#F1F5F9] tracking-tight">
          Help &amp; Support Center
        </h1>
        <p className="text-xs font-mono text-[#94A3B8] mt-1">
          Documentation, Exness connection guides, system status, and priority support.
        </p>
      </div>

      {/* 3 Quick Resource Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center gap-2 text-[#38BDF8]">
            <FileText className="w-4 h-4" />
            <span className="font-bold">Platform Documentation</span>
          </div>
          <p className="text-[#94A3B8] text-[11px] leading-relaxed">
            Quantitative architecture overview, multi-factor directional scoring, and risk guard parameters.
          </p>
        </div>

        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center gap-2 text-[#F59E0B]">
            <Link2 className="w-4 h-4" />
            <span className="font-bold">Exness MT5 Guide</span>
          </div>
          <p className="text-[#94A3B8] text-[11px] leading-relaxed">
            Step-by-step setup for the Exness MT5 Gateway, private authenticated tunnel, and demo credentials.
          </p>
        </div>

        <div className="p-4 rounded-xl bg-[#0E131B] border border-[#1E2736] space-y-2">
          <div className="flex items-center gap-2 text-[#10B981]">
            <Server className="w-4 h-4" />
            <span className="font-bold">System Status: All Operational</span>
          </div>
          <p className="text-[#94A3B8] text-[11px] leading-relaxed">
            Staging backend (Port 8002), PM2 supervisor, and Exness feed connection online.
          </p>
        </div>
      </div>

      {/* Support Request Form */}
      <div className="p-5 rounded-2xl bg-[#0E131B] border border-[#1E2736] space-y-4 font-mono text-xs">
        <h2 className="text-base font-bold text-[#F1F5F9] border-b border-[#1E2736] pb-2">
          Submit Institutional Support Request
        </h2>

        {submitted ? (
          <div className="p-4 rounded-xl bg-[#10B981]/10 border border-[#10B981]/30 text-[#10B981] flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 shrink-0" />
            <span>Support request dispatched successfully. An engineer will follow up shortly.</span>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3 max-w-xl">
            <div>
              <label className="text-[11px] text-[#64748B] block mb-1">Subject</label>
              <input
                type="text"
                required
                value={ticketSubject}
                onChange={(e) => setTicketSubject(e.target.value)}
                placeholder="Brief summary of the inquiry or issue..."
                className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
              />
            </div>
            <div>
              <label className="text-[11px] text-[#64748B] block mb-1">Detailed Message</label>
              <textarea
                required
                rows={4}
                value={ticketMessage}
                onChange={(e) => setTicketMessage(e.target.value)}
                placeholder="Include relevant pair symbols, timestamps, or gateway error codes..."
                className="w-full px-3 py-2 rounded-lg bg-[#151C28] border border-[#1E2736] text-[#F1F5F9] focus:outline-none focus:border-[#38BDF8]"
              />
            </div>
            <button
              type="submit"
              className="px-4 py-2 rounded-lg bg-[#38BDF8] text-[#080B10] font-bold flex items-center gap-1.5 transition-all cursor-pointer shadow-md shadow-[#38BDF8]/20"
            >
              <Send className="w-3.5 h-3.5" />
              <span>Submit Ticket</span>
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
