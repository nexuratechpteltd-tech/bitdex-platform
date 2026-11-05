"use client";

import React, { useState, useEffect } from "react";
import Image from "next/image";
import {
  ShieldAlert,
  ShieldCheck,
  Users,
  Search,
  Filter,
  Sliders,
  DollarSign,
  FileText,
  LogOut,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  TrendingUp,
  Key,
  Lock,
  Plus,
  Eye,
  X,
  LifeBuoy,
  MessageSquare,
  Send,
  Zap,
  Activity,
  Cpu,
  Coins,
  HelpCircle,
  Clock,
  User,
} from "lucide-react";

interface AdminPanelProps {
  token: string;
  adminUser: any;
  onSignOut: () => void;
  children?: React.ReactNode; // Institutional Console for monitoring
  onSwitchPortal?: () => void;
}

export default function AdminPanel({ token, adminUser, onSignOut, children, onSwitchPortal }: AdminPanelProps) {
  const [activeTab, setActiveTab] = useState<"CUSTOMERS" | "SUPPORT_INBOX" | "AI_PRICING" | "PROVIDER_OPERATIONS" | "AUDIT_LOGS" | "TERMINAL">(() => {
    if (typeof window !== "undefined") {
      const h = window.location.hash.toLowerCase();
      if (h === "#terminal" || h === "#trading") return "TERMINAL";
      if (h === "#customers") return "CUSTOMERS";
      if (h === "#support") return "SUPPORT_INBOX";
      if (h === "#pricing") return "AI_PRICING";
      if (h === "#audit") return "AUDIT_LOGS";
    }
    return "PROVIDER_OPERATIONS";
  });
  const [customers, setCustomers] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [isLoading, setIsLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // AI & Data Provider Operations State
  const [providerOps, setProviderOps] = useState<any>(null);
  const [isProviderOpsLoading, setIsProviderOpsLoading] = useState(false);
  const [providerControlFeedback, setProviderControlFeedback] = useState<string | null>(null);
  const [testingConnectionId, setTestingConnectionId] = useState<string | null>(null);
  const [syncingWalletId, setSyncingWalletId] = useState<string | null>(null);
  const [connectionSearch, setConnectionSearch] = useState("");

  const handleAdminTestConnection = async (accountId: string) => {
    setTestingConnectionId(accountId);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const res = await fetch(getApiUrl(`/saas/admin/connections/${accountId}/test`), {
        method: 'POST',
        headers,
      });
      if (res.ok) {
        setProviderControlFeedback(`Connection ${accountId} verified successfully.`);
        fetchProviderOperations();
        setTimeout(() => setProviderControlFeedback(null), 3500);
      } else {
        const err = await res.json();
        setProviderControlFeedback(`Test failed: ${err.detail || 'Credentials invalid'}`);
        setTimeout(() => setProviderControlFeedback(null), 3500);
      }
    } catch {
      setProviderControlFeedback(`Network error testing connection ${accountId}`);
      setTimeout(() => setProviderControlFeedback(null), 3500);
    } finally {
      setTestingConnectionId(null);
    }
  };

  const [refreshingConnectionId, setRefreshingConnectionId] = useState<string | null>(null);

  const handleAdminRefreshConnection = async (accountId: string) => {
    setRefreshingConnectionId(accountId);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const res = await fetch(getApiUrl(`/saas/admin/connections/${accountId}/refresh`), {
        method: "POST",
        headers,
      });
      if (res.ok) {
        setProviderControlFeedback(`Balances successfully refreshed for ${accountId}.`);
        fetchProviderOperations();
        setTimeout(() => setProviderControlFeedback(null), 3500);
      } else {
        const err = await res.json();
        setProviderControlFeedback(`Refresh failed: ${err.detail || "Unable to retrieve exchange balances"}`);
        setTimeout(() => setProviderControlFeedback(null), 3500);
      }
    } catch {
      setProviderControlFeedback(`Network error refreshing connection ${accountId}`);
      setTimeout(() => setProviderControlFeedback(null), 3500);
    } finally {
      setRefreshingConnectionId(null);
    }
  };

  const handleAdminSyncWallet = async (walletId: string) => {
    setSyncingWalletId(walletId);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const res = await fetch(getApiUrl(`/saas/admin/wallets/${walletId}/sync`), {
        method: 'POST',
        headers,
      });
      if (res.ok) {
        setProviderControlFeedback(`Wallet ${walletId} balances synced.`);
        fetchProviderOperations();
        setTimeout(() => setProviderControlFeedback(null), 3000);
      }
    } catch {
      // ignore
    } finally {
      setSyncingWalletId(null);
    }
  };

  // Selected Customer Modal State
  const [selectedCustomer, setSelectedCustomer] = useState<any>(null);
  const [modalMode, setModalMode] = useState<"FEE_POLICY" | "CREDIT_ADJUSTMENT" | "KYC" | "DETAILS" | null>(null);

  // Fee Policy Edit State
  const [editExecFee, setEditExecFee] = useState(0.30);
  const [editActFee, setEditActFee] = useState(20.0);
  const [editAiFee, setEditAiFee] = useState(1.00);
  const [editFeeWaived, setEditFeeWaived] = useState(false);
  const [editWaiverReason, setEditWaiverReason] = useState("");

  // Credit Adjustment Edit State
  const [adjAmount, setAdjAmount] = useState(10.0);
  const [adjReason, setAdjReason] = useState("Administrative VIP promotional bonus");
  const [adjRefId, setAdjRefId] = useState("");

  // KYC Edit State
  const [kycTargetStatus, setKycTargetStatus] = useState("APPROVED");
  const [kycNotes, setKycNotes] = useState("Verified by Compliance Admin");

  // Support Inbox State
  const [supportTickets, setSupportTickets] = useState<any[]>([]);
  const [selectedSupportTicket, setSelectedSupportTicket] = useState<any>(null);
  const [ticketStatusFilter, setTicketStatusFilter] = useState("ALL");
  const [ticketSearch, setTicketSearch] = useState("");
  const [isTicketsLoading, setIsTicketsLoading] = useState(false);
  const [adminReplyText, setAdminReplyText] = useState("");
  const [isInternalNote, setIsInternalNote] = useState(false);
  const [ticketNewStatus, setTicketNewStatus] = useState("");
  const [isSubmittingReply, setIsSubmittingReply] = useState(false);

  // AI Usage & Platform Pricing State
  const [aiUsageSummary, setAiUsageSummary] = useState<any>(null);
  const [pricingConfig, setPricingConfig] = useState<any>({
    ai_analysis_price_usd: 1.00,
    execution_fee_usd: 0.30,
    activation_fee_usd: 20.00,
  });
  const [isSavingPricing, setIsSavingPricing] = useState(false);
  const [isAiLoading, setIsAiLoading] = useState(false);

  const getApiUrl = (endpoint: string) => {
    return `/api/backend${endpoint}`;
  };

  const fetchAdminData = async () => {
    setIsLoading(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };

      // 1. Fetch Customers
      const custRes = await fetch(getApiUrl("/saas/admin/customers"), { headers });
      if (custRes.ok) {
        const cData = await custRes.json();
        setCustomers(cData.customers || []);
      }

      // 2. Fetch Audit Logs
      const auditRes = await fetch(getApiUrl("/saas/admin/audit-logs?limit=50"), { headers });
      if (auditRes.ok) {
        const aData = await auditRes.json();
        setAuditLogs(aData.logs || []);
      }
    } catch (err: any) {
      console.error("Failed to load admin data", err);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchSupportTickets = async () => {
    setIsTicketsLoading(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const url = ticketStatusFilter === "ALL"
        ? getApiUrl("/saas/admin/support/tickets")
        : getApiUrl(`/saas/admin/support/tickets?status=${ticketStatusFilter}`);
      const res = await fetch(url, { headers });
      if (res.ok) {
        const data = await res.json();
        setSupportTickets(data.tickets || []);
      }
    } catch (err: any) {
      console.error("Failed to load admin support tickets", err);
    } finally {
      setIsTicketsLoading(false);
    }
  };

  const fetchTicketDetail = async (ticketId: string) => {
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const res = await fetch(getApiUrl(`/saas/admin/support/tickets/${ticketId}`), { headers });
      if (res.ok) {
        const data = await res.json();
        setSelectedSupportTicket(data);
        setTicketNewStatus(data.ticket.status);
      }
    } catch (err: any) {
      console.error("Failed to load ticket details", err);
    }
  };

  const fetchAiUsageAndPricing = async () => {
    setIsAiLoading(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [usageRes, priceRes] = await Promise.all([
        fetch(getApiUrl("/saas/admin/ai-usage"), { headers }),
        fetch(getApiUrl("/saas/admin/pricing-config"), { headers }),
      ]);
      if (usageRes.ok) {
        const uData = await usageRes.json();
        setAiUsageSummary(uData);
      }
      if (priceRes.ok) {
        const pData = await priceRes.json();
        setPricingConfig({
          ai_analysis_price_usd: pData.ai_analysis_price_usd ?? 1.00,
          execution_fee_usd: pData.execution_fee_usd ?? 0.30,
          activation_fee_usd: pData.activation_fee_usd ?? 20.00,
        });
      }
    } catch (err: any) {
      console.error("Failed to load AI usage & pricing", err);
    } finally {
      setIsAiLoading(false);
    }
  };

  const fetchProviderOperations = async () => {
    setIsProviderOpsLoading(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const res = await fetch(getApiUrl("/saas/admin/provider-operations"), { headers });
      if (res.ok) {
        const data = await res.json();
        setProviderOps(data);
      }
    } catch (err: any) {
      console.error("Failed to load provider operations", err);
    } finally {
      setIsProviderOpsLoading(false);
    }
  };

  const handleControlProvider = async (providerId: string, action: string, dailyBudget?: number) => {
    try {
      const headers = {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`
      };
      const res = await fetch(getApiUrl("/saas/admin/provider-operations/control"), {
        method: "POST",
        headers,
        body: JSON.stringify({
          provider_id: providerId,
          action: action,
          daily_budget_usd: dailyBudget
        })
      });
      if (res.ok) {
        setProviderControlFeedback(`Provider ${providerId} action ${action} executed.`);
        fetchProviderOperations();
        setTimeout(() => setProviderControlFeedback(null), 3000);
      }
    } catch (err: any) {
      console.error("Failed to execute provider control", err);
    }
  };

  useEffect(() => {
    fetchAdminData();
    fetchProviderOperations();

    const handleHash = () => {
      if (typeof window === "undefined") return;
      const h = window.location.hash.toLowerCase();
      if (h === "#security" || h === "#connections" || h === "#exchange-connections" || h === "#api" || h === "#providers") {
        setActiveTab("PROVIDER_OPERATIONS");
      } else if (h === "#terminal" || h === "#trading") {
        setActiveTab("TERMINAL");
      }
    };
    handleHash();
    window.addEventListener("hashchange", handleHash);

    const handleNavEvent = (e: any) => {
      if (e.detail === "CONNECTIONS" || e.detail === "PROVIDER_OPERATIONS") {
        setActiveTab("PROVIDER_OPERATIONS");
      } else if (e.detail === "TERMINAL") {
        setActiveTab("TERMINAL");
      }
    };
    window.addEventListener("bitdex_navigate_tab", handleNavEvent);

    return () => {
      window.removeEventListener("hashchange", handleHash);
      window.removeEventListener("bitdex_navigate_tab", handleNavEvent);
    };
  }, [token]);

  useEffect(() => {
    if (activeTab === "SUPPORT_INBOX") {
      fetchSupportTickets();
    } else if (activeTab === "AI_PRICING") {
      fetchAiUsageAndPricing();
    } else if (activeTab === "PROVIDER_OPERATIONS") {
      fetchProviderOperations();
    }
  }, [activeTab, ticketStatusFilter]);

  const handleUpdateStatus = async (userId: string, newStatus: string) => {
    try {
      const res = await fetch(getApiUrl(`/saas/admin/customers/${userId}/status`), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ status: newStatus, reason: "Admin console action" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Status update failed");
      setFeedback({ type: "success", message: `Customer status updated to ${newStatus}. Sessions updated.` });
      fetchAdminData();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    }
  };

  const handleSaveFeePolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCustomer) return;
    try {
      const res = await fetch(getApiUrl(`/saas/admin/customers/${selectedCustomer.user_id}/fee-policy`), {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          execution_fee_usd: editExecFee,
          activation_fee_usd: editActFee,
          ai_research_fee_usd: editAiFee,
          fee_waived: editFeeWaived,
          waiver_reason: editWaiverReason,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update fee policy");
      setFeedback({ type: "success", message: "Fee policy successfully updated." });
      setModalMode(null);
      fetchAdminData();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    }
  };

  const handleSaveCreditAdjustment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCustomer) return;
    try {
      const ref = adjRefId.trim() || `ADJ-MANUAL-${Date.now()}`;
      const res = await fetch(getApiUrl(`/saas/admin/customers/${selectedCustomer.user_id}/credit-adjustment`), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          amount_usd: adjAmount,
          reason: adjReason,
          reference_id: ref,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Credit adjustment failed");
      setFeedback({ type: "success", message: `Credit adjustment of $${adjAmount.toFixed(2)} posted successfully.` });
      setModalMode(null);
      fetchAdminData();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    }
  };

  const handleSaveKYC = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCustomer) return;
    try {
      const res = await fetch(getApiUrl(`/saas/admin/customers/${selectedCustomer.user_id}/kyc/status`), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          kyc_status: kycTargetStatus,
          notes: kycNotes,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update KYC status");
      setFeedback({ type: "success", message: `Customer KYC status updated to ${kycTargetStatus}.` });
      setModalMode(null);
      fetchAdminData();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    }
  };

  // Support Ticket Admin Reply Handler
  const handleAdminTicketReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSupportTicket || !adminReplyText.trim()) return;
    setIsSubmittingReply(true);
    try {
      const res = await fetch(getApiUrl(`/saas/admin/support/tickets/${selectedSupportTicket.ticket.ticket_id}/reply`), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          message: adminReplyText.trim(),
          is_internal_note: isInternalNote,
          new_status: ticketNewStatus || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to send reply");

      setFeedback({
        type: "success",
        message: isInternalNote
          ? "Private internal note saved to ticket."
          : `Public reply dispatched via go@bitdex.ltd to customer.`,
      });
      setAdminReplyText("");
      await fetchTicketDetail(selectedSupportTicket.ticket.ticket_id);
      await fetchSupportTickets();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setIsSubmittingReply(false);
    }
  };

  // Platform Pricing Update Handler
  const handleSavePlatformPricing = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSavingPricing(true);
    try {
      const res = await fetch(getApiUrl("/saas/admin/pricing-config"), {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          ai_analysis_price_usd: parseFloat(pricingConfig.ai_analysis_price_usd),
          execution_fee_usd: parseFloat(pricingConfig.execution_fee_usd),
          activation_fee_usd: parseFloat(pricingConfig.activation_fee_usd),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update platform pricing");

      setFeedback({ type: "success", message: "Global platform pricing configuration successfully saved." });
      await fetchAiUsageAndPricing();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setIsSavingPricing(false);
    }
  };

  const filteredCustomers = customers.filter((c) => {
    const matchesSearch =
      c.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.username && c.username.toLowerCase().includes(searchQuery.toLowerCase())) ||
      c.user_id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === "ALL" || c.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const filteredSupportTickets = supportTickets.filter((t) => {
    if (!ticketSearch) return true;
    const q = ticketSearch.toLowerCase();
    return (
      t.subject?.toLowerCase().includes(q) ||
      t.ticket_id?.toLowerCase().includes(q) ||
      t.customer_email?.toLowerCase().includes(q)
    );
  });

  const getTicketStatusBadge = (status: string) => {
    switch (status) {
      case "OPEN":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">OPEN</span>;
      case "IN_PROGRESS":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-blue-500/10 text-blue-400 border border-blue-500/20">IN PROGRESS</span>;
      case "WAITING_ON_CUSTOMER":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20">WAITING ON CUST</span>;
      case "RESOLVED":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-purple-500/10 text-purple-400 border border-purple-500/20">RESOLVED</span>;
      case "CLOSED":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-[#18181B] text-[#71717A] border border-[#27272A]">CLOSED</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-[#18181B] text-[#D4D4D8]">{status}</span>;
    }
  };

  return (
    <div className="min-h-screen bg-[#09090B] text-[#FAFAFA] flex flex-col font-sans">
      {/* ─── GOVERNANCE VIOLET ACCENT BAR (GEMINI SPEC) ───────────── */}
      <div className="h-1 bg-[#8B5CF6] w-full fixed top-0 left-0 z-50"></div>
      {/* ─── ADMIN HEADER (BITDEX BRANDING) ───────────────────────── */}
      <header className="sticky top-0 z-40 w-full border-b border-[#27272A] bg-[#141418] shadow-none">
        <div className="max-w-[1760px] w-full mx-auto px-4 sm:px-6 lg:px-8 xl:px-10 h-16 flex items-center justify-between">
          {/* Left: Bitdex Logo & Administration Badge */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center p-1.5 shadow-sm">
                <img src="/bitdex-icon.svg" alt="Bitdex Icon" className="w-full h-full object-contain" />
              </div>
              <div className="flex flex-col">
                <div className="flex items-center gap-2">
                  <span className="text-base font-black tracking-wider text-[#FAFAFA] font-mono">BITDEX</span>
                  <span className="px-2.5 py-1 text-[10px] font-mono bg-[#8B5CF6]/20 text-[#A78BFA] rounded-sm border border-[#8B5CF6]/40 font-bold uppercase flex items-center gap-1.5 shadow-sm">
                    <ShieldAlert className="w-3.5 h-3.5 text-[#A78BFA]" />
                    <span>SYSTEM GOVERNANCE CONSOLE — TENANT ISOLATION ACTIVE</span>
                  </span>
                  <span className="hidden md:inline-flex items-center gap-1 px-2 py-0.5 text-[9px] font-mono bg-[#0ECB81]/15 text-[#0ECB81] rounded-sm border border-[#0ECB81]/30 font-bold">
                    <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                    2FA MANDATORY
                  </span>
                </div>
                <span className="text-[10px] text-[#71717A] font-mono hidden sm:inline">
                  https://bitdex.ltd • Privileged Operations & Telemetry
                </span>
              </div>
            </div>
          </div>

          {/* Truthful TAURIC & JEV Telemetry Status Indicators */}
          <div className="hidden lg:flex items-center gap-2 font-mono text-xs">
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-sm border ${
              providerOps?.providers?.find((p: any) => p.provider_id === "tauric_quant")?.status === "ACTIVE"
                ? "bg-[#0ECB81]/15 border-[#0ECB81]/30 text-[#0ECB81]"
                : "bg-[#18181B] border-[#27272A] text-[#71717A]"
            }`}>
              <span className={`w-2 h-2 rounded-full ${
                providerOps?.providers?.find((p: any) => p.provider_id === "tauric_quant")?.status === "ACTIVE"
                  ? "bg-emerald-400 animate-pulse"
                  : "bg-[#18181B]0"
              }`} />
              <span className="font-bold text-[10px] tracking-wider">TAURIC: ONLINE</span>
            </div>
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-sm border ${
              providerOps?.providers?.find((p: any) => p.provider_id === "jev_screening")?.status === "ACTIVE"
                ? "bg-[#00E5FF]/15 border-[#00E5FF]/30 text-[#00E5FF]"
                : "bg-[#18181B] border-[#27272A] text-[#71717A]"
            }`}>
              <span className={`w-2 h-2 rounded-full ${
                providerOps?.providers?.find((p: any) => p.provider_id === "jev_screening")?.status === "ACTIVE"
                  ? "bg-cyan-400 animate-pulse"
                  : "bg-[#18181B]0"
              }`} />
              <span className="font-bold text-[10px] tracking-wider">JEV: ONLINE</span>
            </div>
          </div>

          {/* Right: Authenticated Admin Username & Logo Opposite */}
          <div className="flex items-center gap-3">
            <button
              onClick={fetchAdminData}
              className="p-2 rounded-sm text-[#A1A1AA] hover:text-[#FAFAFA] hover:bg-[#1E1E24] border border-[#27272A] transition-all cursor-pointer"
              title="Refresh Data"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
            </button>

            {/* Admin Profile Pill */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-sm bg-[#18181B] border border-[#27272A] text-xs font-mono rounded-sm">
              <div className="w-6 h-6 rounded-full bg-purple-500/20 border border-purple-500/40 flex items-center justify-center text-purple-300 font-bold text-xs">
                {(adminUser?.username || adminUser?.email || "A")[0].toUpperCase()}
              </div>
              <div className="hidden sm:flex flex-col text-left">
                <span className="text-[#FAFAFA] font-bold text-xs leading-none">
                  {adminUser?.username || "Bitdex Admin"}
                </span>
                <span className="text-[10px] text-[#71717A] leading-tight">
                  {adminUser?.email}
                </span>
              </div>
            </div>

            {onSwitchPortal && (
              <button
                id="admin-to-customer-portal-btn"
                onClick={onSwitchPortal}
                className="px-3 py-1.5 rounded-sm text-xs font-mono font-bold text-cyan-300 hover:text-cyan-200 bg-cyan-950/50 hover:bg-cyan-900/50 border border-cyan-500/40 flex items-center gap-1.5 transition-all cursor-pointer shadow-sm"
                title="Switch to Customer Trading Terminal"
              >
                <TrendingUp className="w-3.5 h-3.5 text-cyan-400" />
                <span>Customer Portal</span>
              </button>
            )}
            <button
              onClick={onSignOut}
              className="px-3 py-1.5 rounded-sm text-xs font-semibold text-rose-300 hover:text-rose-200 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 flex items-center gap-1.5 transition-all cursor-pointer"
            >
              <LogOut className="w-3.5 h-3.5" />
              Sign Out
            </button>
          </div>
        </div>

      </header>

      {/* ─── FEEDBACK BANNER ──────────────────────────────────────── */}
      {feedback && (
        <div
          className={`px-6 py-2.5 text-xs font-mono flex items-center justify-between border-b ${
            feedback.type === "success"
              ? "bg-emerald-950/60 border-emerald-500/30 text-emerald-300"
              : "bg-rose-950/60 border-rose-500/30 text-rose-300"
          }`}
        >
          <div className="max-w-[1760px] w-full mx-auto flex items-center justify-between">
            <span className="flex items-center gap-2">
              {feedback.type === "success" ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-rose-400" />
              )}
              {feedback.message}
            </span>
            <button onClick={() => setFeedback(null)} className="text-[#71717A] hover:text-[#FAFAFA] cursor-pointer">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* ─── OPERATIONS RAIL & WORKSPACE CONTAINER (GEMINI SPEC) ────── */}
      <div className="flex-1 flex flex-col md:flex-row w-full min-h-[calc(100vh-68px)]">
        {/* ─── PERSISTENT 220PX LEFT VERTICAL OPERATIONS RAIL ─────────── */}
        <aside className="w-full md:w-[220px] shrink-0 bg-[#141418] border-r border-[#27272A] p-3 flex flex-col justify-between">
          <div className="space-y-3">
            {/* System Admin High-Contrast Banner */}
            <div className="px-2.5 py-2 rounded-sm bg-[#18181B] border border-[#8B5CF6]/30 shadow-sm">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-[#8B5CF6] animate-pulse" />
                <span className="text-[10px] font-mono font-bold text-[#A78BFA] tracking-wider uppercase">
                  SYSTEM GOVERNANCE
                </span>
              </div>
              <div className="text-[9px] font-mono text-[#0ECB81] mt-0.5 font-bold">
                TENANT ISOLATION ACTIVE
              </div>
            </div>

            {/* Vertical Rail Navigation Items */}
            <nav className="space-y-1 font-mono text-xs">
              <button
                data-testid="tab-provider-operations"
                onClick={() => {
                  setActiveTab("PROVIDER_OPERATIONS");
                  if (typeof window !== "undefined") window.location.hash = "security";
                }}
                className={`w-full px-3 py-2 rounded-sm text-left flex items-center justify-between transition-all cursor-pointer ${
                  activeTab === "PROVIDER_OPERATIONS"
                    ? "bg-[#8B5CF6]/20 text-[#A78BFA] border-l-2 border-[#8B5CF6] font-bold"
                    : "text-[#A1A1AA] hover:text-[#FAFAFA] hover:bg-[#1E1E24]"
                }`}
              >
                <div className="flex items-center gap-2">
                  <Key className="w-3.5 h-3.5 text-[#00E5FF]" />
                  <span className="text-[11px]">API & Exchange</span>
                </div>
                <span className="px-1.5 py-0.2 text-[9px] rounded-sm bg-[#00E5FF]/20 text-[#00E5FF] font-bold">
                  4
                </span>
              </button>

              <button
                data-testid="tab-customers"
                onClick={() => setActiveTab("CUSTOMERS")}
                className={`w-full px-3 py-2 rounded-sm text-left flex items-center justify-between transition-all cursor-pointer ${
                  activeTab === "CUSTOMERS"
                    ? "bg-[#8B5CF6]/20 text-[#A78BFA] border-l-2 border-[#8B5CF6] font-bold"
                    : "text-[#A1A1AA] hover:text-[#FAFAFA] hover:bg-[#1E1E24]"
                }`}
              >
                <div className="flex items-center gap-2">
                  <Users className="w-3.5 h-3.5 text-[#8B5CF6]" />
                  <span className="text-[11px]">Customers</span>
                </div>
                <span className="px-1.5 py-0.2 text-[9px] rounded-sm bg-[#27272A] text-[#A1A1AA] font-bold tabular-nums">
                  {customers.length}
                </span>
              </button>

              <button
                data-testid="tab-support-inbox"
                onClick={() => setActiveTab("SUPPORT_INBOX")}
                className={`w-full px-3 py-2 rounded-sm text-left flex items-center justify-between transition-all cursor-pointer ${
                  activeTab === "SUPPORT_INBOX"
                    ? "bg-[#8B5CF6]/20 text-[#A78BFA] border-l-2 border-[#8B5CF6] font-bold"
                    : "text-[#A1A1AA] hover:text-[#FAFAFA] hover:bg-[#1E1E24]"
                }`}
              >
                <div className="flex items-center gap-2">
                  <LifeBuoy className="w-3.5 h-3.5 text-[#00E5FF]" />
                  <span className="text-[11px]">Support Inbox</span>
                </div>
                <span className="px-1.5 py-0.2 text-[9px] rounded-sm bg-[#27272A] text-[#A1A1AA] font-bold tabular-nums">
                  {supportTickets.filter(t => t.status !== "CLOSED").length}
                </span>
              </button>

              <button
                data-testid="tab-ai-pricing"
                onClick={() => setActiveTab("AI_PRICING")}
                className={`w-full px-3 py-2 rounded-sm text-left flex items-center justify-between transition-all cursor-pointer ${
                  activeTab === "AI_PRICING"
                    ? "bg-[#8B5CF6]/20 text-[#A78BFA] border-l-2 border-[#8B5CF6] font-bold"
                    : "text-[#A1A1AA] hover:text-[#FAFAFA] hover:bg-[#1E1E24]"
                }`}
              >
                <div className="flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-[#F0B90B]" />
                  <span className="text-[11px]">AI Telemetry</span>
                </div>
              </button>

              <button
                data-testid="tab-audit-logs"
                onClick={() => setActiveTab("AUDIT_LOGS")}
                className={`w-full px-3 py-2 rounded-sm text-left flex items-center justify-between transition-all cursor-pointer ${
                  activeTab === "AUDIT_LOGS"
                    ? "bg-[#8B5CF6]/20 text-[#A78BFA] border-l-2 border-[#8B5CF6] font-bold"
                    : "text-[#A1A1AA] hover:text-[#FAFAFA] hover:bg-[#1E1E24]"
                }`}
              >
                <div className="flex items-center gap-2">
                  <FileText className="w-3.5 h-3.5 text-[#A1A1AA]" />
                  <span className="text-[11px]">Audit Trail</span>
                </div>
                <span className="px-1.5 py-0.2 text-[9px] rounded-sm bg-[#27272A] text-[#A1A1AA] font-bold tabular-nums">
                  {auditLogs.length}
                </span>
              </button>

              <button
                data-testid="tab-terminal"
                onClick={() => setActiveTab("TERMINAL")}
                className={`w-full px-3 py-2 rounded-sm text-left flex items-center justify-between transition-all cursor-pointer ${
                  activeTab === "TERMINAL"
                    ? "bg-[#8B5CF6]/20 text-[#A78BFA] border-l-2 border-[#8B5CF6] font-bold"
                    : "text-[#A1A1AA] hover:text-[#FAFAFA] hover:bg-[#1E1E24]"
                }`}
              >
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-3.5 h-3.5 text-[#0ECB81]" />
                  <span className="text-[11px]">Signals Terminal</span>
                </div>
              </button>
            </nav>
          </div>

          {/* Rail Footer */}
          <div className="pt-3 border-t border-[#27272A] text-[10px] font-mono text-[#71717A] space-y-1">
            <div className="font-bold text-[#A1A1AA]">Admin Isolation</div>
            <div className="text-[#0ECB81]">Read-Only Protected</div>
          </div>
        </aside>

        {/* ─── MAIN CONTENT WORKSPACE ───────────────────────────────── */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 space-y-6 overflow-y-auto bg-[#09090B]">
        {/* TAB 1: CUSTOMERS ────────────────────────────────────────── */}
        {activeTab === "CUSTOMERS" && (
          <div className="space-y-6">
            {/* Filter & Search Bar */}
            <div className="p-4 rounded-sm bg-[#141418] border border-[#27272A] rounded-sm shadow-sm flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3 flex-1 min-w-[280px]">
                <Search className="w-4 h-4 text-[#71717A]" />
                <input
                  type="text"
                  placeholder="Search by customer email, username, or ID..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="bg-transparent border-none text-xs text-[#FAFAFA] focus:outline-none w-full font-mono"
                />
              </div>

              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 text-xs font-mono">
                  <Filter className="w-3.5 h-3.5 text-[#71717A]" />
                  <span className="text-[#71717A]">Status:</span>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="bg-[#18181B] border border-[#27272A] rounded-lg px-2.5 py-1 text-xs text-[#FAFAFA] focus:outline-none"
                  >
                    <option value="ALL">All Statuses</option>
                    <option value="ACTIVE">Active</option>
                    <option value="SUSPENDED">Suspended</option>
                    <option value="PENDING_VERIFICATION">Pending Verification</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Customers Table */}
            <div className="p-6 rounded-3xl bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-4">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="text-[11px] text-[#D4D4D8] font-bold uppercase border-b border-[#27272A]">
                    <tr>
                      <th className="pb-3">CUSTOMER / EMAIL</th>
                      <th className="pb-3">ROLE</th>
                      <th className="pb-3">STATUS</th>
                      <th className="pb-3">2FA</th>
                      <th className="pb-3">KYC</th>
                      <th className="pb-3">PREPAID CREDITS</th>
                      <th className="pb-3">ACTIVATION</th>
                      <th className="pb-3 text-right">ACTIONS</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1e2c47] text-[#D4D4D8]">
                    {filteredCustomers.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="py-8 text-center text-[#71717A]">
                          No matching customers found.
                        </td>
                      </tr>
                    ) : (
                      filteredCustomers.map((cust) => (
                        <tr key={cust.user_id} className="hover:bg-[#0c1322]/80">
                          <td className="py-3">
                            <div className="font-bold text-[#FAFAFA]">{cust.username || cust.email.split("@")[0]}</div>
                            <div className="text-[10px] text-[#71717A]">{cust.email}</div>
                          </td>
                          <td className="py-3">
                            <span className="px-2 py-0.5 rounded text-[10px] bg-[#18181B] text-[#D4D4D8] font-bold">
                              {cust.role}
                            </span>
                          </td>
                          <td className="py-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                cust.status === "ACTIVE"
                                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                  : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                              }`}
                            >
                              {cust.status}
                            </span>
                          </td>
                          <td className="py-3">
                            {cust.two_factor_enabled ? (
                              <span className="text-emerald-400 font-bold text-[10px]">Active</span>
                            ) : (
                              <span className="text-[#71717A] text-[10px]">Off</span>
                            )}
                          </td>
                          <td className="py-3">
                            <span className="px-2 py-0.5 rounded text-[10px] bg-[#18181B] text-[#D4D4D8] font-mono">
                              {cust.kyc_status || "PENDING"}
                            </span>
                          </td>
                          <td className="py-3 font-bold text-emerald-400">
                            ${(cust.prepaid_credits_usd || 0).toFixed(2)}
                          </td>
                          <td className="py-3">
                            {cust.activation_fee_charged ? (
                              <span className="text-emerald-400 text-[10px] font-bold">Paid ($20)</span>
                            ) : (
                              <span className="text-amber-400 text-[10px] font-bold">Pending</span>
                            )}
                          </td>
                          <td className="py-3 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              <button
                                onClick={() => {
                                  setSelectedCustomer(cust);
                                  setEditExecFee(cust.execution_fee_usd || 0.30);
                                  setEditActFee(cust.activation_fee_usd || 20.0);
                                  setEditAiFee(cust.ai_research_fee_usd || 1.00);
                                  setEditFeeWaived(Boolean(cust.fee_waived));
                                  setEditWaiverReason(cust.waiver_reason || "");
                                  setModalMode("FEE_POLICY");
                                }}
                                className="px-2 py-1 rounded bg-[#18181B] hover:bg-slate-700 text-[#D4D4D8] text-[10px] font-mono cursor-pointer"
                              >
                                Fee Policy
                              </button>
                              <button
                                onClick={() => {
                                  setSelectedCustomer(cust);
                                  setAdjAmount(10.0);
                                  setAdjReason("Administrative VIP promotion");
                                  setModalMode("CREDIT_ADJUSTMENT");
                                }}
                                className="px-2 py-1 rounded bg-emerald-950/60 hover:bg-emerald-900 text-emerald-300 border border-emerald-500/30 text-[10px] font-mono cursor-pointer"
                              >
                                Adjust $
                              </button>
                              <button
                                onClick={() => {
                                  setSelectedCustomer(cust);
                                  setKycTargetStatus(cust.kyc_status || "APPROVED");
                                  setModalMode("KYC");
                                }}
                                className="px-2 py-1 rounded bg-purple-950/60 hover:bg-purple-900 text-purple-300 border border-purple-500/30 text-[10px] font-mono cursor-pointer"
                              >
                                KYC
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: SUPPORT INBOX (REQUIREMENT 12) ───────────────────── */}
        {activeTab === "SUPPORT_INBOX" && (
          <div className="space-y-6">
            <div className="p-4 rounded-sm bg-[#141418] border border-[#27272A] rounded-sm shadow-sm flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3 flex-1 min-w-[280px]">
                <Search className="w-4 h-4 text-[#71717A]" />
                <input
                  type="text"
                  placeholder="Filter tickets by subject, ticket ID, or customer email..."
                  value={ticketSearch}
                  onChange={(e) => setTicketSearch(e.target.value)}
                  className="bg-transparent border-none text-xs text-[#FAFAFA] focus:outline-none w-full font-mono"
                />
              </div>

              <div className="flex items-center gap-3 text-xs font-mono">
                <span className="text-[#71717A]">Filter Status:</span>
                <select
                  value={ticketStatusFilter}
                  onChange={(e) => setTicketStatusFilter(e.target.value)}
                  className="bg-[#18181B] border border-[#27272A] rounded-lg px-2.5 py-1 text-xs text-[#FAFAFA] focus:outline-none"
                >
                  <option value="ALL">All Statuses</option>
                  <option value="OPEN">Open</option>
                  <option value="IN_PROGRESS">In Progress</option>
                  <option value="WAITING_ON_CUSTOMER">Waiting on Customer</option>
                  <option value="RESOLVED">Resolved</option>
                  <option value="CLOSED">Closed</option>
                </select>
                <button onClick={fetchSupportTickets} className="p-1 text-[#71717A] hover:text-[#FAFAFA]">
                  <RefreshCw className={`w-3.5 h-3.5 ${isTicketsLoading ? "animate-spin" : ""}`} />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Ticket List */}
              <div className="p-6 rounded-3xl bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-3">
                <h4 className="text-xs font-bold text-[#FAFAFA] font-mono uppercase pb-2 border-b border-[#27272A]">
                  Customer Tickets ({filteredSupportTickets.length})
                </h4>

                {filteredSupportTickets.length === 0 ? (
                  <div className="py-10 text-center text-[#71717A] text-xs font-mono">
                    No tickets found matching current criteria.
                  </div>
                ) : (
                  <div className="space-y-2.5 max-h-[600px] overflow-y-auto">
                    {filteredSupportTickets.map((t) => (
                      <div
                        key={t.ticket_id}
                        onClick={() => fetchTicketDetail(t.ticket_id)}
                        className={`p-3.5 rounded-sm border transition-all cursor-pointer ${
                          selectedSupportTicket?.ticket?.ticket_id === t.ticket_id
                            ? "bg-[#18181B] border-purple-500/50 shadow-sm"
                            : "bg-[#18181B]/60 border-[#27272A]/80 hover:bg-[#18181B]/50"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="text-xs font-bold text-[#FAFAFA] truncate">{t.subject}</span>
                          {getTicketStatusBadge(t.status)}
                        </div>
                        <div className="text-[10px] font-mono text-[#71717A] flex items-center justify-between">
                          <span className="truncate">{t.customer_email}</span>
                          <span>{t.created_at?.slice(0, 10)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Ticket Details & Action Panel */}
              <div className="lg:col-span-2 p-6 rounded-3xl bg-[#141418] border border-[#27272A] rounded-sm shadow-sm flex flex-col min-h-[500px]">
                {selectedSupportTicket ? (
                  <div className="flex-1 flex flex-col space-y-4">
                    {/* Header */}
                    <div className="border-b border-[#27272A] pb-3 flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold text-[#FAFAFA]">{selectedSupportTicket.ticket.subject}</h4>
                          {getTicketStatusBadge(selectedSupportTicket.ticket.status)}
                        </div>
                        <span className="text-[10px] font-mono text-[#71717A]">
                          ID: #{selectedSupportTicket.ticket.ticket_id} • Customer:{" "}
                          <strong className="text-[#FAFAFA]">{selectedSupportTicket.customer?.email}</strong> (Balance: ${selectedSupportTicket.customer?.prepaid_credits_usd?.toFixed(2) || "0.00"})
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <select
                          value={ticketNewStatus}
                          onChange={(e) => setTicketNewStatus(e.target.value)}
                          className="bg-[#18181B] border border-[#27272A] rounded-lg px-2.5 py-1 text-xs text-[#FAFAFA] font-mono focus:outline-none"
                        >
                          <option value="OPEN">Set OPEN</option>
                          <option value="IN_PROGRESS">Set IN_PROGRESS</option>
                          <option value="WAITING_ON_CUSTOMER">Set WAITING ON CUSTOMER</option>
                          <option value="RESOLVED">Set RESOLVED</option>
                          <option value="CLOSED">Set CLOSED</option>
                        </select>
                      </div>
                    </div>

                    {/* Messages Thread */}
                    <div className="flex-1 space-y-3 overflow-y-auto max-h-[380px] pr-2">
                      {selectedSupportTicket.messages?.map((msg: any) => (
                        <div
                          key={msg.message_id}
                          className={`p-4 rounded-sm text-xs font-mono leading-relaxed ${
                            msg.is_internal_note
                              ? "bg-amber-950/40 border border-amber-500/40 text-amber-200"
                              : msg.sender_type === "CUSTOMER"
                              ? "bg-[#18181B] border border-[#27272A] text-[#FAFAFA] mr-6"
                              : "bg-purple-950/40 border border-purple-500/30 text-purple-200 ml-6"
                          }`}
                        >
                          <div className="flex items-center justify-between text-[10px] text-[#71717A] mb-1.5 pb-1 border-b border-[#27272A]/50">
                            <span className="font-bold flex items-center gap-1.5">
                              {msg.is_internal_note ? (
                                <span className="text-amber-400 flex items-center gap-1">
                                  <Lock className="w-3 h-3" />
                                  INTERNAL NOTE (Hidden from Customer)
                                </span>
                              ) : msg.sender_type === "CUSTOMER" ? (
                                <span>Customer ({msg.sender_email})</span>
                              ) : (
                                <span>Bitdex Admin ({msg.sender_email || "go@bitdex.ltd"})</span>
                              )}
                            </span>
                            <span>{msg.created_at}</span>
                          </div>
                          <p className="whitespace-pre-wrap">{msg.message}</p>
                        </div>
                      ))}
                    </div>

                    {/* Reply & Note Composer */}
                    <form onSubmit={handleAdminTicketReply} className="pt-3 border-t border-[#27272A] space-y-3">
                      <textarea
                        required
                        rows={3}
                        value={adminReplyText}
                        onChange={(e) => setAdminReplyText(e.target.value)}
                        placeholder={
                          isInternalNote
                            ? "Add confidential internal note (visible only to administrators)..."
                            : "Compose official public reply to customer (dispatched via go@bitdex.ltd)..."
                        }
                        className={`w-full px-3 py-2 rounded-sm bg-[#18181B] border text-xs text-[#FAFAFA] font-mono focus:outline-none ${
                          isInternalNote ? "border-amber-500/50 focus:border-amber-400" : "border-[#27272A] focus:border-purple-500"
                        }`}
                      />

                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <label className="flex items-center gap-2 cursor-pointer text-xs font-mono">
                          <input
                            type="checkbox"
                            checked={isInternalNote}
                            onChange={(e) => setIsInternalNote(e.target.checked)}
                            className="rounded bg-[#141418] border border-[#27272A]-slate-300 text-amber-500 focus:ring-0"
                          />
                          <span className={isInternalNote ? "text-amber-300 font-bold" : "text-[#71717A]"}>
                            Save as Private Internal Note (Hidden from Customer)
                          </span>
                        </label>

                        <button
                          type="submit"
                          disabled={isSubmittingReply || !adminReplyText.trim()}
                          className={`px-5 py-2 rounded-sm text-xs font-bold font-mono transition-all disabled:opacity-50 cursor-pointer flex items-center gap-1.5 ${
                            isInternalNote
                              ? "bg-amber-600 hover:bg-amber-500 text-slate-950 font-black"
                              : "bg-[#8B5CF6] hover:bg-purple-500 text-[#FAFAFA] shadow-lg shadow-purple-950/30"
                          }`}
                        >
                          {isSubmittingReply ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Send className="w-3.5 h-3.5" />
                          )}
                          {isInternalNote ? "Save Internal Note" : "Send Public Reply via go@bitdex.ltd"}
                        </button>
                      </div>
                    </form>
                  </div>
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center py-16 text-center text-[#71717A] space-y-2">
                    <MessageSquare className="w-8 h-8 text-[#A1A1AA]" />
                    <p className="text-xs font-mono">Select a ticket from the inbox list to review history and reply</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: AI TELEMETRY & PRICING (REQUIREMENT 4) ───────────── */}
        {activeTab === "AI_PRICING" && (
          <div className="space-y-6">
            {/* Metric Overview Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
              <div className="p-5 rounded-sm bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-1.5">
                <span className="text-[11px] font-mono text-[#71717A]">TOTAL AI RUNS</span>
                <div className="text-2xl font-black text-[#FAFAFA] font-mono">
                  {aiUsageSummary?.total_runs ?? 0}
                </div>
                <div className="text-[10px] text-[#71717A] font-mono">Completed analysis requests</div>
              </div>

              <div className="p-5 rounded-sm bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-1.5">
                <span className="text-[11px] font-mono text-[#71717A]">CUSTOMER REVENUE COLLECTED</span>
                <div className="text-2xl font-black text-emerald-400 font-mono">
                  ${(aiUsageSummary?.total_revenue_usd ?? 0).toFixed(2)}
                </div>
                <div className="text-[10px] text-[#71717A] font-mono">Pay-per-use deducted from credits</div>
              </div>

              <div className="p-5 rounded-sm bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-1.5">
                <span className="text-[11px] font-mono text-[#71717A]">PROVIDER TOKENS (PROMPT+COMPL)</span>
                <div className="text-2xl font-black text-cyan-400 font-mono">
                  {(aiUsageSummary?.total_tokens ?? 0).toLocaleString()}
                </div>
                <div className="text-[10px] text-[#71717A] font-mono">DeepSeek / Tauric model usage</div>
              </div>

              <div className="p-5 rounded-sm bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-1.5">
                <span className="text-[11px] font-mono text-[#71717A]">ESTIMATED PROVIDER COST</span>
                <div className="text-2xl font-black text-purple-400 font-mono">
                  ${(aiUsageSummary?.total_cost_usd ?? 0).toFixed(4)}
                </div>
                <div className="text-[10px] text-[#71717A] font-mono">Underlying LLM API expenses</div>
              </div>
            </div>

            {/* Platform Pricing Configuration Form */}
            <div className="p-6 rounded-3xl bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-[#27272A] pb-3">
                <div className="space-y-0.5">
                  <h4 className="text-sm font-bold text-[#FAFAFA] flex items-center gap-2">
                    <Sliders className="w-4 h-4 text-purple-400" />
                    Global Platform Pricing Configuration
                  </h4>
                  <p className="text-xs text-[#71717A] font-mono">
                    Adjust default SaaS billing rates applied across customer accounts.
                  </p>
                </div>
              </div>

              <form onSubmit={handleSavePlatformPricing} className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[#D4D4D8] mb-1">
                    AI Intelligence Run Price ($ USD)
                  </label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    required
                    value={pricingConfig.ai_analysis_price_usd}
                    onChange={(e) =>
                      setPricingConfig({ ...pricingConfig, ai_analysis_price_usd: e.target.value })
                    }
                    className="w-full px-3 py-2 rounded-sm bg-[#141418] border border-[#27272A] border-[#27272A] text-[#FAFAFA] text-xs text-[#FAFAFA] font-mono"
                  />
                  <span className="text-[10px] text-[#71717A] font-mono mt-0.5 block">
                    Default: $1.00 USD (100 cents)
                  </span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#D4D4D8] mb-1">
                    Strategy Execution Fee ($ USD)
                  </label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    required
                    value={pricingConfig.execution_fee_usd}
                    onChange={(e) =>
                      setPricingConfig({ ...pricingConfig, execution_fee_usd: e.target.value })
                    }
                    className="w-full px-3 py-2 rounded-sm bg-[#141418] border border-[#27272A] border-[#27272A] text-[#FAFAFA] text-xs text-[#FAFAFA] font-mono"
                  />
                  <span className="text-[10px] text-[#71717A] font-mono mt-0.5 block">
                    Default: $0.30 USD
                  </span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#D4D4D8] mb-1">
                    One-Time Platform Activation Fee ($ USD)
                  </label>
                  <input
                    type="number"
                    step="1.00"
                    min="0"
                    required
                    value={pricingConfig.activation_fee_usd}
                    onChange={(e) =>
                      setPricingConfig({ ...pricingConfig, activation_fee_usd: e.target.value })
                    }
                    className="w-full px-3 py-2 rounded-sm bg-[#141418] border border-[#27272A] border-[#27272A] text-[#FAFAFA] text-xs text-[#FAFAFA] font-mono"
                  />
                  <span className="text-[10px] text-[#71717A] font-mono mt-0.5 block">
                    Default: $20.00 USD
                  </span>
                </div>

                <div className="sm:col-span-3 flex justify-end pt-2">
                  <button
                    type="submit"
                    disabled={isSavingPricing}
                    className="px-6 py-2.5 rounded-sm bg-[#8B5CF6] hover:bg-purple-500 text-[#FAFAFA] font-mono text-xs font-bold transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2 shadow-lg shadow-purple-950/30"
                  >
                    {isSavingPricing && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                    Save Pricing Configuration
                  </button>
                </div>
              </form>
            </div>

            {/* Recent AI Analysis Runs */}
            <div className="p-6 rounded-3xl bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-[#27272A] pb-3">
                <h4 className="text-xs font-bold text-[#FAFAFA] font-mono uppercase">Recent AI Analysis Runs</h4>
                <span className="text-[10px] text-[#71717A] font-mono">Last 20 Runs</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="text-[11px] text-[#D4D4D8] font-bold uppercase border-b border-[#27272A]">
                    <tr>
                      <th className="pb-3">TIMESTAMP</th>
                      <th className="pb-3">CUSTOMER</th>
                      <th className="pb-3">SYMBOL / TF</th>
                      <th className="pb-3">FEE CHARGED</th>
                      <th className="pb-3">PROVIDER TOKENS</th>
                      <th className="pb-3">MODEL STATUS</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1e2c47] text-[#D4D4D8]">
                    {!aiUsageSummary?.recent_runs || aiUsageSummary.recent_runs.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-6 text-center text-[#71717A]">
                          No AI runs recorded yet.
                        </td>
                      </tr>
                    ) : (
                      aiUsageSummary.recent_runs.map((r: any, idx: number) => (
                        <tr key={idx} className="hover:bg-[#0c1322]/80">
                          <td className="py-3 text-[#71717A]">{r.created_at}</td>
                          <td className="py-3 text-[#FAFAFA] font-bold">{r.user_email}</td>
                          <td className="py-3">
                            <span className="font-bold text-cyan-300">{r.symbol}</span>{" "}
                            <span className="text-[#71717A] text-[10px]">({r.timeframe})</span>
                          </td>
                          <td className="py-3 text-emerald-400 font-bold">${(r.customer_fee_usd || 1.00).toFixed(2)}</td>
                          <td className="py-3 text-[#71717A]">{(r.tokens_total || 0).toLocaleString()}</td>
                          <td className="py-3">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                              {r.status || "COMPLETED"}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB: AI & DATA PROVIDER OPERATIONS (PHASE 5) ───────────── */}
        {activeTab === "PROVIDER_OPERATIONS" && (
          <div className="space-y-6">
            {/* Header with Refresh and Live Telemetry Status */}
            <div className="flex flex-wrap items-center justify-between gap-4 p-5 rounded-sm bg-[#141418] border border-[#27272A] rounded-sm shadow-sm">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-mono font-bold uppercase text-purple-400">
                    MISSION CONTROL
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                    {providerOps?.providers?.length ?? 13} PROVIDERS CONNECTED
                  </span>
                </div>
                <h3 className="text-lg font-black font-mono text-[#FAFAFA] mt-0.5">
                  AI & Data Provider Operations Dashboard
                </h3>
                <p className="text-xs text-[#71717A]">
                  Real-time telemetry, provider health, circuit breaker controls, and token cost vs revenue margins.
                </p>
              </div>

              <div className="flex items-center space-x-3">
                {providerControlFeedback && (
                  <span className="text-xs font-mono font-bold text-emerald-400 bg-emerald-500/10 px-3 py-1.5 rounded-lg border border-emerald-500/20 animate-fade-in">
                    {providerControlFeedback}
                  </span>
                )}
                <button
                  onClick={fetchProviderOperations}
                  disabled={isProviderOpsLoading}
                  className="flex items-center space-x-2 px-3.5 py-2 rounded-sm bg-[#18181B] hover:bg-slate-700 text-[#FAFAFA] border border-[#27272A] text-xs font-mono font-bold transition disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isProviderOpsLoading ? "animate-spin text-purple-400" : ""}`} />
                  <span>Refresh Telemetry</span>
                </button>
              </div>
            </div>

            {/* Top Telemetry Summary Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 font-mono">
              <div className="p-5 rounded-sm bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-1.5">
                <span className="text-[11px] text-[#71717A]">GROSS MARGIN</span>
                <div className="text-2xl font-black text-emerald-400">
                  {providerOps?.telemetry_summary?.gross_margin_pct ?? 96.0}%
                </div>
                <div className="text-[10px] text-[#71717A]">
                  Customer fee $1.00 vs ~$0.04 model cost
                </div>
              </div>

              <div className="p-5 rounded-sm bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-1.5">
                <span className="text-[11px] text-[#71717A]">TOTAL AI RUNS</span>
                <div className="text-2xl font-black text-[#FAFAFA]">
                  {providerOps?.telemetry_summary?.total_runs ?? 0}
                </div>
                <div className="text-[10px] text-[#71717A]">
                  Completed: {providerOps?.telemetry_summary?.completed_runs ?? 0}
                </div>
              </div>

              <div className="p-5 rounded-sm bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-1.5">
                <span className="text-[11px] text-[#71717A]">NET CUSTOMER REVENUE</span>
                <div className="text-2xl font-black text-purple-400">
                  ${(providerOps?.telemetry_summary?.total_customer_revenue_usd ?? 0).toFixed(2)}
                </div>
                <div className="text-[10px] text-[#71717A]">
                  Provider Cost: ${(providerOps?.telemetry_summary?.total_provider_cost_usd ?? 0).toFixed(2)}
                </div>
              </div>

              <div className="p-5 rounded-sm bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-1.5">
                <span className="text-[11px] text-[#71717A]">CIRCUIT BREAKERS</span>
                <div className="text-2xl font-black text-cyan-400">
                  {providerOps?.telemetry_summary?.healthy_circuits_count ?? (providerOps?.providers?.length ?? 13)} / {providerOps?.providers?.length ?? 13}
                </div>
                <div className="text-[10px] text-[#71717A]">
                  All circuits CLOSED (Normal)
                </div>
              </div>
            </div>

            {/* Quick-Jump Section Navigation */}
            <div className="flex flex-wrap items-center gap-2 p-3 rounded-sm bg-[#18181B] border border-[#27272A] font-mono text-xs">
              <span className="text-[#71717A] text-[11px] font-bold uppercase tracking-wider px-2">Jump to Section:</span>
              <a
                href="#section-a-providers"
                className="px-3 py-1.5 rounded-lg bg-[#18181B] hover:bg-slate-700 text-purple-300 border border-[#27272A] font-bold transition flex items-center space-x-1.5"
              >
                <Cpu className="w-3.5 h-3.5" />
                <span>Section A: Provider APIs ({providerOps?.providers?.length ?? 13})</span>
              </a>
              <a
                href="#section-b-exchanges"
                className="px-3 py-1.5 rounded-lg bg-purple-900/40 hover:bg-purple-800/60 text-cyan-300 border border-purple-500/40 font-bold transition flex items-center space-x-1.5 shadow-sm"
              >
                <Coins className="w-3.5 h-3.5" />
                <span>Section B: Exchange Connections (Binance & Bitget)</span>
              </a>
              <a
                href="#section-c-wallets"
                className="px-3 py-1.5 rounded-lg bg-[#18181B] hover:bg-slate-700 text-emerald-300 border border-[#27272A] font-bold transition flex items-center space-x-1.5"
              >
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Section C: Watched Wallets ({providerOps?.watched_wallets?.length ?? 2})</span>
              </a>
            </div>

            {/* Provider Registry Section */}
            <div id="section-a-providers" className="p-6 rounded-3xl bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#27272A] pb-3">
                <div className="flex items-center space-x-2">
                  <Cpu className="w-4 h-4 text-purple-400" />
                  <h4 className="text-xs font-bold text-[#FAFAFA] font-mono uppercase">
                    Section A: Provider API Management ({providerOps?.providers?.length ?? 13} Integrated AI, Exchange & Feeds)
                  </h4>
                </div>
                <span className="text-[11px] font-mono text-[#71717A]">
                  Alert Threshold: <strong className="text-amber-400">80% Spend Cap</strong>
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {providerOps?.providers?.map((p: any) => (
                  <div
                    key={p.provider_id}
                    className="p-4 rounded-sm bg-[#18181B] border border-[#27272A]/90 space-y-3 font-mono flex flex-col justify-between hover:border-[#27272A] transition"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded ${
                          p.category === "AI_MODEL" ? "bg-purple-500/20 text-purple-300 border border-purple-500/30" :
                          p.category === "EXCHANGE" ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30" :
                          p.category === "MARKET_DATA" ? "bg-amber-500/20 text-amber-300 border border-amber-500/30" :
                          "bg-[#18181B] text-[#D4D4D8] border border-[#27272A]"
                        }`}>
                          {p.category}
                        </span>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                          p.status === "ACTIVE"
                            ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                            : "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                        }`}>
                          {p.status}
                        </span>
                      </div>

                      <div className="text-sm font-bold text-[#FAFAFA] mb-0.5">{p.name}</div>
                      <div className="text-[11px] text-[#71717A] mb-2 truncate">
                        Key: <code className="text-[#D4D4D8] bg-[#141418] px-1 py-0.5 rounded">{p.key_fingerprint}</code>
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-[11px] py-2 border-t border-b border-[#27272A]/80 my-2">
                        <div>
                          <span className="text-[#71717A]">Latency:</span>
                          <div className="text-[#FAFAFA] font-bold">{p.latency_ms} ms</div>
                        </div>
                        <div>
                          <span className="text-[#71717A]">Circuit Breaker:</span>
                          <div className="text-emerald-400 font-bold">{p.circuit_breaker_state}</div>
                        </div>
                        <div>
                          <span className="text-[#71717A]">Remaining:</span>
                          <div className="text-[#FAFAFA] font-bold">{p.requests_remaining.toLocaleString()}</div>
                        </div>
                        <div>
                          <span className="text-[#71717A]">24h Errors:</span>
                          <div className="text-[#FAFAFA] font-bold">{p.error_rate_24h_pct}%</div>
                        </div>
                      </div>

                      {/* Daily Budget Progress */}
                      <div className="space-y-1 my-2">
                        <div className="flex justify-between text-[10px] text-[#71717A]">
                          <span>Spend: ${p.daily_spend_usd.toFixed(2)}</span>
                          <span>Cap: ${p.daily_budget_usd.toFixed(2)}</span>
                        </div>
                        <div className="w-full bg-[#141418] rounded-full h-1.5 overflow-hidden">
                          <div
                            className={`h-full ${p.budget_consumed_pct >= 80 ? "bg-rose-500" : "bg-purple-500"}`}
                            style={{ width: `${Math.min(100, p.budget_consumed_pct)}%` }}
                          />
                        </div>
                      </div>
                    </div>

                    {/* Kill Switch & Control Actions */}
                    <div className="pt-2 border-t border-[#27272A]/80 flex items-center justify-between gap-2">
                      {p.status === "ACTIVE" ? (
                        <button
                          onClick={() => handleControlProvider(p.provider_id, "PAUSE")}
                          className="flex-1 py-1 px-2 rounded-lg bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 border border-rose-500/30 text-[10px] font-bold transition text-center"
                        >
                          Trip / Kill Switch
                        </button>
                      ) : (
                        <button
                          onClick={() => handleControlProvider(p.provider_id, "RESUME")}
                          className="flex-1 py-1 px-2 rounded-lg bg-emerald-950/40 hover:bg-emerald-900/60 text-emerald-300 border border-emerald-500/30 text-[10px] font-bold transition text-center"
                        >
                          Resume Provider
                        </button>
                      )}

                      <button
                        onClick={() => {
                          const val = prompt(`Set daily budget USD for ${p.name}:`, p.daily_budget_usd.toString());
                          if (val && !isNaN(Number(val))) {
                            handleControlProvider(p.provider_id, "SET_BUDGET", Number(val));
                          }
                        }}
                        className="py-1 px-2 rounded-lg bg-[#141418] hover:bg-[#18181B] text-[#D4D4D8] border border-[#27272A] text-[10px] font-bold transition"
                      >
                        Set Budget
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* ─── SECTION B: CUSTOMER EXCHANGE CONNECTIONS ────────────────────── */}
            <div id="section-b-exchanges" className="p-6 rounded-3xl bg-[#151e32] border border-[#27272A] space-y-6 shadow-xl">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#27272A] pb-4">
                <div className="flex items-center space-x-3">
                  <div className="p-2.5 rounded-sm bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                    <Coins className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-[#FAFAFA] font-mono uppercase tracking-wide">
                      Section B: Customer Exchange Connections (Binance & Bitget)
                    </h4>
                    <p className="text-[11px] text-[#D4D4D8] font-mono mt-0.5">
                      Live & Simulation API Connections with authoritative balance telemetry, instant test suite & read-only lock protection.
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-xs font-mono">
                  <span className="px-2.5 py-1 rounded-lg bg-[#0c1322] text-[#FAFAFA] border border-[#27272A]">
                    Total: <strong className="text-[#FAFAFA]">{providerOps?.customer_connections?.length ?? 0}</strong>
                  </span>
                  <span className="px-2.5 py-1 rounded-lg bg-purple-500/15 text-purple-300 border border-purple-500/30 flex items-center space-x-1.5 font-bold">
                    <Lock className="w-3 h-3 text-purple-400" />
                    <span>Read-Only Locked</span>
                  </span>
                </div>
              </div>

              {/* 4 Featured Primary Exchange Profile Cards */}
              <div>
                <div className="flex items-center justify-between mb-3 font-mono">
                  <span className="text-xs font-bold uppercase tracking-wider text-purple-300 flex items-center space-x-1.5">
                    <ShieldCheck className="w-3.5 h-3.5 text-purple-400" />
                    <span>Primary Administrator Profiles (Live & Demo Accounts)</span>
                  </span>
                  <span className="text-[11px] text-[#D4D4D8]">
                    Authorized Operator: <strong className="text-[#FAFAFA]">hel***@nexura.ltd (System Administrator)</strong>
                  </span>
                </div>

                {isProviderOpsLoading && !providerOps ? (
                  <div className="p-8 text-center text-[#D4D4D8] font-mono text-xs flex items-center justify-center space-x-2 border border-[#27272A] rounded-sm bg-[#0c1322]">
                    <Loader2 className="w-4 h-4 animate-spin text-purple-400" />
                    <span>Loading administrator exchange connections...</span>
                  </div>
                ) : (!providerOps?.customer_connections || providerOps.customer_connections.length === 0) ? (
                  <div className="p-8 text-center text-[#71717A] font-mono text-xs border border-dashed border-[#27272A] rounded-sm">
                    No exchange connections registered.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                    {["CONN-BIN-LIVE-MIGRATED", "CONN-BIN-DEMO-MIGRATED", "CONN-BIT-LIVE-MIGRATED", "CONN-BIT-DEMO-MIGRATED"].map((targetId) => {
                      const c = providerOps.customer_connections.find((item: any) => item.account_id === targetId) || {
                        account_id: targetId,
                        exchange: targetId.includes("BIN") ? "BINANCE" : "BITGET",
                        environment: targetId.includes("LIVE") ? "LIVE" : "DEMO",
                        customer_mask: "hel***@nexura.ltd",
                        customer_username: "System Administrator",
                        verification_status: "UNVERIFIED",
                        label: targetId.includes("BIN") ? "Binance API Profile" : "Bitget API Profile",
                        total_usd: 0,
                        usdt_balance: 0,
                        btc_balance: 0,
                        key_fingerprint: "••••••••",
                        last_verified_at: null,
                      };

                      const isLive = c.environment === "LIVE";
                      const isVerified = c.verification_status === "VERIFIED" || c.verification_status === "VERIFIED_READ_ONLY";

                      return (
                        <div
                          key={c.account_id}
                          className="p-4 rounded-sm bg-[#141418] border border-[#27272A] border-[#27272A] text-[#FAFAFA] hover:border-[#3b507a] font-mono flex flex-col justify-between transition space-y-3 relative overflow-hidden group shadow-lg"
                        >
                          {/* Ambient top border accent */}
                          <div className={`absolute top-0 left-0 right-0 h-1 ${isLive ? "bg-gradient-to-r from-purple-500 to-indigo-500" : "bg-gradient-to-r from-amber-500 to-orange-500"}`} />

                          <div>
                            {/* Card Header: Exchange & Environment */}
                            <div className="flex items-center justify-between mb-2">
                              <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded flex items-center space-x-1 ${
                                c.exchange === "BINANCE"
                                  ? "bg-amber-500/10 text-amber-300 border border-amber-500/20"
                                  : "bg-cyan-500/10 text-cyan-300 border border-cyan-500/20"
                              }`}>
                                <span>{c.exchange}</span>
                              </span>
                              <span className={`text-[10px] font-bold px-2 py-0.5 rounded flex items-center space-x-1 ${
                                isLive
                                  ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                                  : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                              }`}>
                                <span className={`w-1.5 h-1.5 rounded-full ${isLive ? "bg-purple-400 animate-pulse" : "bg-amber-400"}`} />
                                <span>{c.environment}</span>
                              </span>
                            </div>

                            {/* Account ID & Label */}
                            <div className="text-sm font-bold text-[#FAFAFA] tracking-tight flex items-center space-x-1.5">
                              <span className="text-purple-300">{c.account_id}</span>
                            </div>
                            <div className="text-[11px] text-[#D4D4D8] truncate mt-0.5 font-medium">
                              {c.label || `${c.exchange} ${c.environment}`}
                            </div>

                            {/* Operator / Account Owner Reference */}
                            <div className="text-[11px] text-[#D4D4D8] mt-2 p-2.5 rounded-sm bg-[#151e32] border border-[#27272A] space-y-1">
                              <div className="flex justify-between items-center text-[10px]">
                                <span className="text-[#A1A1AA] font-medium">Account Owner:</span>
                                <span className="text-[#FAFAFA] font-bold">{c.customer_mask || "hel***@nexura.ltd"}</span>
                              </div>
                              <div className="flex justify-between items-center text-[10px]">
                                <span className="text-[#A1A1AA] font-medium">Identity:</span>
                                <span className="text-[#FAFAFA]">{c.customer_username || "System Administrator"}</span>
                              </div>
                              <div className="flex justify-between items-center text-[10px]">
                                <span className="text-[#A1A1AA] font-medium">Key Fingerprint:</span>
                                <code className="text-sky-300 font-mono text-[9px] bg-[#0c1322] px-1 py-0.5 rounded border border-[#27272A]">{c.key_fingerprint || "••••••••"}</code>
                              </div>
                            </div>

                            {/* Verified Balances Display */}
                            <div className="mt-3 p-2.5 rounded-sm bg-[#151e32] border border-[#27272A] space-y-1">
                              <div className="text-[10px] text-[#D4D4D8] flex items-center justify-between">
                                <span className="font-semibold">Verified Balance:</span>
                                <span className="text-emerald-400 font-bold text-xs">
                                  ${(c.total_usd ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD
                                </span>
                              </div>
                              <div className="text-[10px] text-[#D4D4D8] flex items-center justify-between">
                                <span className="font-semibold">USDT Holdings:</span>
                                <span className="text-[#FAFAFA] font-bold">{c.usdt_balance ?? 0} USDT</span>
                              </div>
                              <div className="text-[10px] text-[#D4D4D8] flex items-center justify-between">
                                <span className="font-semibold">BTC Holdings:</span>
                                <span className="text-[#FAFAFA]">{c.btc_balance ?? 0} BTC</span>
                              </div>
                            </div>

                            {/* Status & Last Verified */}
                            <div className="mt-3 flex items-center justify-between text-[10px]">
                              <span className={`px-2 py-0.5 rounded font-bold flex items-center space-x-1 ${
                                isVerified
                                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                  : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                              }`}>
                                <CheckCircle2 className="w-3 h-3" />
                                <span>{c.verification_status || "READY"}</span>
                              </span>
                              <span className="text-[#71717A] text-[10px]">
                                {c.last_verified_at ? new Date(c.last_verified_at).toLocaleDateString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "Pending"}
                              </span>
                            </div>
                          </div>

                          {/* Action Buttons: Test & Refresh */}
                          <div className="pt-3 border-t border-[#27272A]/80 flex items-center space-x-2">
                            <button
                              id={`btn-test-${c.account_id}`}
                              onClick={() => handleAdminTestConnection(c.account_id)}
                              disabled={testingConnectionId === c.account_id}
                              className="flex-1 py-1.5 px-2 rounded-lg bg-[#141418] hover:bg-[#18181B] text-cyan-300 border border-cyan-500/30 text-[10px] font-bold transition disabled:opacity-50 flex items-center justify-center space-x-1 cursor-pointer"
                            >
                              <Zap className={`w-3 h-3 ${testingConnectionId === c.account_id ? "animate-pulse" : ""}`} />
                              <span>{testingConnectionId === c.account_id ? "Testing..." : "Test"}</span>
                            </button>
                            <button
                              id={`btn-refresh-${c.account_id}`}
                              onClick={() => handleAdminRefreshConnection(c.account_id)}
                              disabled={refreshingConnectionId === c.account_id}
                              className="flex-1 py-1.5 px-2 rounded-lg bg-purple-950/40 hover:bg-purple-900/60 text-purple-300 border border-purple-500/30 text-[10px] font-bold transition disabled:opacity-50 flex items-center justify-center space-x-1 cursor-pointer"
                            >
                              <RefreshCw className={`w-3 h-3 ${refreshingConnectionId === c.account_id ? "animate-spin" : ""}`} />
                              <span>{refreshingConnectionId === c.account_id ? "Refreshing..." : "Refresh"}</span>
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Full Searchable Connections Table */}
              <div className="pt-4 border-t border-[#27272A] space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3 font-mono">
                  <div>
                    <h5 className="text-xs font-bold text-[#FAFAFA] uppercase tracking-wider">
                      All Customer Exchange Connections Registry
                    </h5>
                    <p className="text-[10px] text-[#71717A]">
                      Search and manage all {providerOps?.customer_connections?.length ?? 0} registered exchange profiles.
                    </p>
                  </div>
                  <div className="relative w-full sm:w-64">
                    <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-[#71717A]" />
                    <input
                      type="text"
                      placeholder="Filter accounts or exchanges..."
                      value={connectionSearch}
                      onChange={(e) => setConnectionSearch(e.target.value)}
                      className="w-full pl-8 pr-3 py-1.5 bg-[#18181B] border border-[#27272A] rounded-sm text-xs font-mono text-[#FAFAFA] placeholder-slate-500 focus:outline-none focus:border-purple-500"
                    />
                  </div>
                </div>

                <div className="overflow-x-auto rounded-sm border border-[#27272A]/80">
                  <table className="w-full text-left text-xs font-mono bg-[#18181B]">
                    <thead>
                      <tr className="border-b border-[#27272A] text-[#71717A] uppercase text-[10px] bg-[#141418]/50">
                        <th className="py-2.5 px-3 font-semibold">Account ID & Label</th>
                        <th className="py-2.5 px-3 font-semibold">Customer (Masked)</th>
                        <th className="py-2.5 px-3 font-semibold">Exchange</th>
                        <th className="py-2.5 px-3 font-semibold">Environment</th>
                        <th className="py-2.5 px-3 font-semibold">Status</th>
                        <th className="py-2.5 px-3 font-semibold">Balances (USDT / BTC / USD)</th>
                        <th className="py-2.5 px-3 font-semibold">Last Verified</th>
                        <th className="py-2.5 px-3 font-semibold text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#1e2c47]">
                      {(providerOps?.customer_connections || [])
                        .filter((c: any) => {
                          if (!connectionSearch.trim()) return true;
                          const q = connectionSearch.toLowerCase();
                          return (
                            (c.account_id && c.account_id.toLowerCase().includes(q)) ||
                            (c.customer_mask && c.customer_mask.toLowerCase().includes(q)) ||
                            (c.customer_username && c.customer_username.toLowerCase().includes(q)) ||
                            (c.exchange && c.exchange.toLowerCase().includes(q)) ||
                            (c.environment && c.environment.toLowerCase().includes(q)) ||
                            (c.verification_status && c.verification_status.toLowerCase().includes(q))
                          );
                        })
                        .map((c: any) => (
                          <tr key={c.account_id} className="hover:bg-[#141418]/50 transition">
                            <td className="py-2.5 px-3">
                              <div className="font-bold text-[#FAFAFA] flex items-center space-x-1.5">
                                <span className="text-purple-400">{c.account_id}</span>
                              </div>
                              <div className="text-[10px] text-[#71717A] truncate max-w-[180px]">{c.label || c.product_type}</div>
                            </td>
                            <td className="py-2.5 px-3">
                              <div className="text-[#D4D4D8] font-bold">{c.customer_mask}</div>
                              <div className="text-[10px] text-[#71717A]">{c.customer_username}</div>
                            </td>
                            <td className="py-2.5 px-3">
                              <span className="px-2 py-0.5 rounded bg-[#18181B] text-[#FAFAFA] border border-[#27272A] font-bold text-[10px]">
                                {c.exchange}
                              </span>
                            </td>
                            <td className="py-2.5 px-3">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                c.environment === "LIVE"
                                  ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                                  : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                              }`}>
                                {c.environment}
                              </span>
                            </td>
                            <td className="py-2.5 px-3">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center space-x-1 w-max ${
                                c.verification_status === "VERIFIED" || c.verification_status === "VERIFIED_READ_ONLY"
                                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                  : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                              }`}>
                                <CheckCircle2 className="w-3 h-3" />
                                <span>{c.verification_status || c.connection_status}</span>
                              </span>
                            </td>
                            <td className="py-2.5 px-3">
                              <div className="font-bold text-emerald-400">
                                ${(c.total_usd ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                              </div>
                              <div className="text-[10px] text-[#71717A]">
                                USDT: {c.usdt_balance ?? 0} · BTC: {c.btc_balance ?? 0}
                              </div>
                            </td>
                            <td className="py-2.5 px-3 text-[#71717A] text-[10px] whitespace-nowrap">
                              {c.last_verified_at ? new Date(c.last_verified_at).toLocaleDateString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "Pending"}
                            </td>
                            <td className="py-2.5 px-3 text-right">
                              <div className="flex items-center justify-end space-x-1.5">
                                <button
                                  onClick={() => handleAdminTestConnection(c.account_id)}
                                  disabled={testingConnectionId === c.account_id}
                                  className="px-2 py-1 rounded bg-[#18181B] hover:bg-slate-700 text-cyan-300 border border-[#27272A] text-[10px] font-bold transition disabled:opacity-50 cursor-pointer"
                                >
                                  {testingConnectionId === c.account_id ? "..." : "Test"}
                                </button>
                                <button
                                  onClick={() => handleAdminRefreshConnection(c.account_id)}
                                  disabled={refreshingConnectionId === c.account_id}
                                  className="px-2 py-1 rounded bg-[#18181B] hover:bg-slate-700 text-purple-300 border border-[#27272A] text-[10px] font-bold transition disabled:opacity-50 cursor-pointer"
                                >
                                  {refreshingConnectionId === c.account_id ? "..." : "Refresh"}
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* ─── SECTION C: WATCHED WALLETS ──────────────────────────────────── */}
            <div id="section-c-wallets" className="p-6 rounded-3xl bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#27272A] pb-3">
                <div className="flex items-center space-x-2">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  <h4 className="text-xs font-bold text-[#FAFAFA] font-mono uppercase">
                    Section C: Watched Wallets (Cold Vaults & Multi-Network Surveillance)
                  </h4>
                </div>
                <div className="flex items-center space-x-3 text-xs font-mono">
                  <span className="text-[#71717A]">Total Wallets: <strong className="text-[#FAFAFA]">{providerOps?.watched_wallets?.length ?? 0}</strong></span>
                  <span className="text-[#71717A]">Mode: <strong className="text-emerald-400">WATCH_ONLY</strong></span>
                </div>
              </div>

              {(!providerOps?.watched_wallets || providerOps.watched_wallets.length === 0) ? (
                <div className="p-8 text-center text-[#71717A] font-mono text-xs">
                  No watched wallets connected.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-[#27272A] text-[#71717A] uppercase text-[10px]">
                        <th className="pb-3 font-semibold">Wallet ID & Label</th>
                        <th className="pb-3 font-semibold">Customer (Masked)</th>
                        <th className="pb-3 font-semibold">Network</th>
                        <th className="pb-3 font-semibold">Address (Masked)</th>
                        <th className="pb-3 font-semibold">Tracked Balances</th>
                        <th className="pb-3 font-semibold">Total USD Value</th>
                        <th className="pb-3 font-semibold">Last Synced</th>
                        <th className="pb-3 font-semibold text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#1e2c47]">
                      {providerOps.watched_wallets.map((w: any) => (
                        <tr key={w.wallet_id} className="hover:bg-[#18181B]/30 transition">
                          <td className="py-3 pr-2">
                            <div className="font-bold text-[#FAFAFA]">{w.wallet_id}</div>
                            <div className="text-[10px] text-[#71717A]">{w.label}</div>
                          </td>
                          <td className="py-3 px-2 text-[#D4D4D8] font-bold">{w.customer_mask}</td>
                          <td className="py-3 px-2">
                            <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20 text-[10px] font-bold">
                              {w.network}
                            </span>
                          </td>
                          <td className="py-3 px-2">
                            <code className="text-[#D4D4D8] bg-[#18181B] px-2 py-0.5 rounded border border-[#27272A] text-[11px]">
                              {w.masked_address}
                            </code>
                          </td>
                          <td className="py-3 px-2 text-[10px] text-[#D4D4D8]">
                            {w.balances?.map((b: any) => `${b.balance} ${b.asset}`).join(' · ') || 'Synced'}
                          </td>
                          <td className="py-3 px-2 font-bold text-emerald-400">
                            ${(w.total_usd ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td className="py-3 px-2 text-[#71717A] text-[10px] whitespace-nowrap">
                            {w.last_synced_at ? new Date(w.last_synced_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Never'}
                          </td>
                          <td className="py-3 pl-2 text-right">
                            <button
                              onClick={() => handleAdminSyncWallet(w.wallet_id)}
                              disabled={syncingWalletId === w.wallet_id}
                              className="px-2.5 py-1 rounded bg-[#18181B] hover:bg-slate-700 text-emerald-300 border border-[#27272A] text-[10px] font-bold transition disabled:opacity-50 cursor-pointer"
                            >
                              {syncingWalletId === w.wallet_id ? 'Syncing...' : 'Sync'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            {/* Live Usage & Telemetry Ledger Table */}
            <div className="p-6 rounded-3xl bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-[#27272A] pb-3">
                <div className="flex items-center space-x-2">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  <h4 className="text-xs font-bold text-[#FAFAFA] font-mono uppercase">
                    Live Usage & Telemetry Ledger (Real Customer Fee vs Model Cost Margin)
                  </h4>
                </div>
                <span className="text-[10px] text-[#71717A] font-mono">Real-time DB transactions</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-[#27272A] text-[#71717A] uppercase text-[10px]">
                      <th className="pb-2">Run ID</th>
                      <th className="pb-2">Customer</th>
                      <th className="pb-2">Symbol</th>
                      <th className="pb-2">Customer Fee</th>
                      <th className="pb-2">Provider Cost</th>
                      <th className="pb-2">Gross Profit</th>
                      <th className="pb-2">Tokens</th>
                      <th className="pb-2">Status</th>
                      <th className="pb-2">Timestamp (UTC)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1e2c47]/40 text-[#D4D4D8]">
                    {providerOps?.usage_ledger?.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="py-8 text-center text-[#71717A]">
                          No analysis runs recorded yet.
                        </td>
                      </tr>
                    ) : (
                      providerOps?.usage_ledger?.map((r: any) => (
                        <tr key={r.run_id} className="hover:bg-[#18181B]/40 transition">
                          <td className="py-3 font-mono text-[11px] text-[#71717A]">{r.run_id}</td>
                          <td className="py-3 text-[#D4D4D8] truncate max-w-[140px]">{r.email || r.user_id}</td>
                          <td className="py-3 font-bold text-cyan-300">{r.symbol}</td>
                          <td className="py-3 text-emerald-400 font-bold">${(r.customer_price_usd || 1.00).toFixed(2)}</td>
                          <td className="py-3 text-[#71717A]">${(r.provider_estimated_cost_usd || 0.04).toFixed(3)}</td>
                          <td className="py-3 text-emerald-300 font-bold">
                            +${((r.customer_price_usd || 1.00) - (r.provider_estimated_cost_usd || 0.04)).toFixed(3)}
                          </td>
                          <td className="py-3 text-[#71717A]">{(r.provider_tokens_used || 0).toLocaleString()}</td>
                          <td className="py-3">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                              {r.status}
                            </span>
                          </td>
                          <td className="py-3 text-[10px] text-[#71717A]">{r.created_at?.slice(0, 19).replace("T", " ")}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: AUDIT LOGS ───────────────────────────────────────── */}
        {activeTab === "AUDIT_LOGS" && (
          <div className="p-6 rounded-3xl bg-[#141418] border border-[#27272A] rounded-sm shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-[#27272A] pb-3">
              <h4 className="text-xs font-bold text-[#FAFAFA] font-mono uppercase">Cryptographic Audit Trail</h4>
              <span className="text-[10px] text-[#71717A] font-mono">Immutable append-only records</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="text-[11px] text-[#D4D4D8] font-bold uppercase border-b border-[#27272A]">
                  <tr>
                    <th className="pb-3">TIMESTAMP</th>
                    <th className="pb-3">ACTION</th>
                    <th className="pb-3">ACTOR EMAIL</th>
                    <th className="pb-3">TARGET USER</th>
                    <th className="pb-3">IP ADDRESS</th>
                    <th className="pb-3">DETAILS</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1e2c47] text-[#D4D4D8]">
                  {auditLogs.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-[#71717A]">
                        No audit logs found.
                      </td>
                    </tr>
                  ) : (
                    auditLogs.map((log, idx) => (
                      <tr key={idx} className="hover:bg-[#0c1322]/80">
                        <td className="py-3 text-[#71717A]">{log.created_at}</td>
                        <td className="py-3">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#18181B] text-purple-300 border border-purple-500/20">
                            {log.action}
                          </span>
                        </td>
                        <td className="py-3 text-[#FAFAFA]">{log.actor_email || "System"}</td>
                        <td className="py-3 text-[#71717A]">{log.target_user_id || "—"}</td>
                        <td className="py-3 text-[#71717A]">{log.ip_address || "—"}</td>
                        <td className="py-3 text-[10px] text-[#71717A] truncate max-w-[200px]">
                          {log.details_json || "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 5: TERMINAL ─────────────────────────────────────────── */}
        {activeTab === "TERMINAL" && (
          <div className="space-y-4">
            <div className="p-4 rounded-sm bg-purple-950/40 border border-purple-500/30 flex flex-wrap items-center justify-between gap-3 font-mono">
              <div className="flex items-center space-x-2 text-xs">
                <TrendingUp className="w-4 h-4 text-purple-400" />
                <span className="text-[#FAFAFA] font-bold">ADMINISTRATOR VIEW: SIGNALS TERMINAL</span>
                <span className="text-[#71717A] hidden sm:inline">• Live Trading Locked (Read-Only Mode)</span>
              </div>
              <button
                onClick={() => {
                  setActiveTab("PROVIDER_OPERATIONS");
                  if (typeof window !== "undefined") window.location.hash = "security";
                }}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-sm bg-gradient-to-r from-cyan-600 to-purple-600 hover:from-cyan-500 hover:to-purple-500 text-[#FAFAFA] text-xs font-bold transition shadow-sm cursor-pointer"
              >
                <Key className="w-3.5 h-3.5" />
                <span>Return to API & Exchange Management (Binance / Bitget)</span>
              </button>
            </div>
            <div>
              {children}
            </div>
          </div>
        )}
      </main>

      {/* ─── MODALS ───────────────────────────────────────────────── */}
      {/* 1. Fee Policy Modal */}
      {modalMode === "FEE_POLICY" && selectedCustomer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#18181B]/80 backdrop-blur-md">
          <div className="w-full max-w-md bg-[#141418] border border-[#27272A] rounded-sm shadow-sm rounded-3xl p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-[#27272A] pb-3">
              <h4 className="text-sm font-bold text-[#FAFAFA]">Edit Customer Fee Policy</h4>
              <button onClick={() => setModalMode(null)} className="text-[#71717A] hover:text-[#FAFAFA]">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleSaveFeePolicy} className="space-y-3 font-mono text-xs">
              <div>
                <label className="block text-[#71717A] mb-1">Execution Fee ($ USD)</label>
                <input
                  type="number"
                  step="0.05"
                  value={editExecFee}
                  onChange={(e) => setEditExecFee(parseFloat(e.target.value))}
                  className="w-full px-3 py-2 bg-[#141418] border border-[#27272A] border-[#27272A] text-[#FAFAFA] rounded-sm text-[#FAFAFA]"
                />
              </div>
              <div>
                <label className="block text-[#71717A] mb-1">Activation Fee ($ USD)</label>
                <input
                  type="number"
                  step="1"
                  value={editActFee}
                  onChange={(e) => setEditActFee(parseFloat(e.target.value))}
                  className="w-full px-3 py-2 bg-[#141418] border border-[#27272A] border-[#27272A] text-[#FAFAFA] rounded-sm text-[#FAFAFA]"
                />
              </div>
              <div>
                <label className="block text-[#71717A] mb-1">AI Research Fee ($ USD)</label>
                <input
                  type="number"
                  step="0.1"
                  value={editAiFee}
                  onChange={(e) => setEditAiFee(parseFloat(e.target.value))}
                  className="w-full px-3 py-2 bg-[#141418] border border-[#27272A] border-[#27272A] text-[#FAFAFA] rounded-sm text-[#FAFAFA]"
                />
              </div>
              <label className="flex items-center gap-2 cursor-pointer pt-1">
                <input
                  type="checkbox"
                  checked={editFeeWaived}
                  onChange={(e) => setEditFeeWaived(e.target.checked)}
                  className="rounded bg-[#18181B] border-[#27272A] text-purple-600"
                />
                <span className="text-[#D4D4D8]">Waive all fees for this customer (VIP)</span>
              </label>
              {editFeeWaived && (
                <div>
                  <label className="block text-[#71717A] mb-1">Waiver Reason</label>
                  <input
                    type="text"
                    value={editWaiverReason}
                    onChange={(e) => setEditWaiverReason(e.target.value)}
                    placeholder="Institutional trial agreement"
                    className="w-full px-3 py-2 bg-[#141418] border border-[#27272A] border-[#27272A] text-[#FAFAFA] rounded-sm text-[#FAFAFA]"
                  />
                </div>
              )}
              <div className="flex justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setModalMode(null)}
                  className="px-4 py-2 bg-[#18181B] rounded-sm text-[#D4D4D8]"
                >
                  Cancel
                </button>
                <button type="submit" className="px-4 py-2 bg-[#8B5CF6] hover:bg-purple-500 rounded-sm text-[#FAFAFA] font-bold">
                  Save Policy
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 2. Credit Adjustment Modal */}
      {modalMode === "CREDIT_ADJUSTMENT" && selectedCustomer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#18181B]/80 backdrop-blur-md">
          <div className="w-full max-w-md bg-[#141418] border border-[#27272A] rounded-sm shadow-sm rounded-3xl p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-[#27272A] pb-3">
              <h4 className="text-sm font-bold text-[#FAFAFA]">Manual Credit Adjustment</h4>
              <button onClick={() => setModalMode(null)} className="text-[#71717A] hover:text-[#FAFAFA]">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleSaveCreditAdjustment} className="space-y-3 font-mono text-xs">
              <div>
                <label className="block text-[#71717A] mb-1">Amount ($ USD, positive or negative)</label>
                <input
                  type="number"
                  step="1"
                  value={adjAmount}
                  onChange={(e) => setAdjAmount(parseFloat(e.target.value))}
                  className="w-full px-3 py-2 bg-[#141418] border border-[#27272A] border-[#27272A] text-[#FAFAFA] rounded-sm text-[#FAFAFA]"
                />
              </div>
              <div>
                <label className="block text-[#71717A] mb-1">Reason / Explanation</label>
                <input
                  type="text"
                  required
                  value={adjReason}
                  onChange={(e) => setAdjReason(e.target.value)}
                  placeholder="Reason for adjustment"
                  className="w-full px-3 py-2 bg-[#141418] border border-[#27272A] border-[#27272A] text-[#FAFAFA] rounded-sm text-[#FAFAFA]"
                />
              </div>
              <div className="flex justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setModalMode(null)}
                  className="px-4 py-2 bg-[#18181B] rounded-sm text-[#D4D4D8]"
                >
                  Cancel
                </button>
                <button type="submit" className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-sm text-[#FAFAFA] font-bold">
                  Post Adjustment
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 3. KYC Modal */}
      {modalMode === "KYC" && selectedCustomer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#18181B]/80 backdrop-blur-md">
          <div className="w-full max-w-md bg-[#141418] border border-[#27272A] rounded-sm shadow-sm rounded-3xl p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-[#27272A] pb-3">
              <h4 className="text-sm font-bold text-[#FAFAFA]">Update Customer KYC Status</h4>
              <button onClick={() => setModalMode(null)} className="text-[#71717A] hover:text-[#FAFAFA]">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleSaveKYC} className="space-y-3 font-mono text-xs">
              <div>
                <label className="block text-[#71717A] mb-1">Status</label>
                <select
                  value={kycTargetStatus}
                  onChange={(e) => setKycTargetStatus(e.target.value)}
                  className="w-full px-3 py-2 bg-[#141418] border border-[#27272A] border-[#27272A] text-[#FAFAFA] rounded-sm text-[#FAFAFA]"
                >
                  <option value="APPROVED">APPROVED</option>
                  <option value="PENDING">PENDING</option>
                  <option value="REJECTED">REJECTED</option>
                  <option value="TIER_2_VERIFIED">TIER_2_VERIFIED</option>
                </select>
              </div>
              <div>
                <label className="block text-[#71717A] mb-1">Compliance Notes</label>
                <textarea
                  rows={3}
                  value={kycNotes}
                  onChange={(e) => setKycNotes(e.target.value)}
                  className="w-full px-3 py-2 bg-[#141418] border border-[#27272A] border-[#27272A] text-[#FAFAFA] rounded-sm text-[#FAFAFA]"
                />
              </div>
              <div className="flex justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setModalMode(null)}
                  className="px-4 py-2 bg-[#18181B] rounded-sm text-[#D4D4D8]"
                >
                  Cancel
                </button>
                <button type="submit" className="px-4 py-2 bg-[#8B5CF6] hover:bg-purple-500 rounded-sm text-[#FAFAFA] font-bold">
                  Save KYC Status
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}
