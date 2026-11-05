"use client";
import ProtectionCenter from "./ProtectionCenter";

import React, { useState, useEffect, useMemo, useRef } from "react";
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
  Clock,
  User,
  ChevronRight,
  ExternalLink,
  Shield,
  Trash2,
  PauseCircle,
  PlayCircle,
  Mail,
  Copy,
  Check,
  AlertCircle,
  ArrowUpDown,
  Download,
  Server,
  Settings,
  Layers,
  ChevronDown,
  ArrowRight
} from "lucide-react";

interface AdminPanelProps {
  token: string;
  adminUser: any;
  onSignOut: () => void;
  children?: React.ReactNode;
  onSwitchPortal?: () => void;
}

// API Error normalization helper to prevent React runtime error #31 (objects as React children)
function formatApiError(err: any, fallback: string): string {
  if (!err) return fallback;
  if (typeof err === "string") return err;
  if (typeof err.detail === "string") return err.detail;
  if (Array.isArray(err.detail)) {
    return err.detail
      .map((e: any) => {
        if (typeof e === "string") return e;
        if (e && typeof e === "object") {
          const locStr = Array.isArray(e.loc) ? e.loc.filter((p: any) => p !== "body").join(".") : "";
          const msg = e.msg || e.message || JSON.stringify(e);
          return locStr ? `${locStr}: ${msg}` : msg;
        }
        return String(e);
      })
      .join("; ");
  }
  if (err.detail && typeof err.detail === "object") {
    return err.detail.message || err.detail.error || err.detail.msg || JSON.stringify(err.detail);
  }
  if (typeof err.message === "string") return err.message;
  return fallback;
}

export default function AdminPanel({
  token,
  adminUser,
  onSignOut,
  children,
  onSwitchPortal,
}: AdminPanelProps) {
  // Navigation
  // Admin Profile Dropdown State
  const [isAdminDropdownOpen, setIsAdminDropdownOpen] = useState(false);
  const adminDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (adminDropdownRef.current && !adminDropdownRef.current.contains(event.target as Node)) {
        setIsAdminDropdownOpen(false);
      }
    }
    if (isAdminDropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isAdminDropdownOpen]);

  const [activeModule, setActiveModule] = useState<
    "CUSTOMERS" | "SUPPORT" | "AI_PRICING" | "EXCHANGES" | "AUDIT" | "TERMINAL"
  >(() => {
    if (typeof window !== "undefined") {
      const h = window.location.hash.toLowerCase();
      if (h === "#terminal" || h === "#trading") return "TERMINAL";
      if (h === "#customers") return "CUSTOMERS";
      if (h === "#support") return "SUPPORT";
      if (h === "#pricing" || h === "#ai") return "AI_PRICING";
      if (h === "#exchanges") return "EXCHANGES";
      if (h === "#audit") return "AUDIT";
    }
    return "CUSTOMERS";
  });

  // Global State
  const [customers, setCustomers] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [tickets, setTickets] = useState<any[]>([]);
  const [selectedTicket, setSelectedTicket] = useState<any | null>(null);
  const [ticketReply, setTicketReply] = useState("");
  const [isInternalNote, setIsInternalNote] = useState(false);
  const [isTicketSubmitting, setIsTicketSubmitting] = useState(false);
  const [providerOps, setProviderOps] = useState<any | null>(null);
  const [globalPricing, setGlobalPricing] = useState<{
    AI_ANALYSIS: number;
    STRATEGY_EXECUTION: number;
    PLATFORM_ACTIVATION: number;
  }>({
    AI_ANALYSIS: 1.0,
    STRATEGY_EXECUTION: 0.3,
    PLATFORM_ACTIVATION: 20.0,
  });

  const [isLoading, setIsLoading] = useState(false);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error" | "info";
    message: string;
  } | null>(null);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [kycFilter, setKycFilter] = useState("ALL");
  const [pricingFilter, setPricingFilter] = useState("ALL");
  const [ticketStatusFilter, setTicketStatusFilter] = useState("ALL");
  const [auditActionFilter, setAuditActionFilter] = useState("ALL");

  // Customer 360 Drawer State
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [customer360Data, setCustomer360Data] = useState<any | null>(null);
  const [is360Loading, setIs360Loading] = useState(false);
  const [active360Tab, setActive360Tab] = useState<
    "OVERVIEW" | "PRICING" | "AI_TELEMETRY" | "CONNECTIONS" | "AUDIT"
  >("OVERVIEW");

  // Action Modals State
  const [activeModal, setActiveModal] = useState<
    "HOLD" | "BLOCK" | "REACTIVATE" | "DELETE" | "KYC" | "EMAIL" | "PRICING_OVERRIDE" | "GLOBAL_PRICING" | "CREDIT_OVERRIDE" | null
  >(null);
  const [overrideCreditsAmount, setOverrideCreditsAmount] = useState<string>("0.00");
  const [creditReferenceId, setCreditReferenceId] = useState<string>("");
  const [modalReason, setModalReason] = useState("");
  const [modalConfirm, setModalConfirm] = useState(false);
  const [isActionLoading, setIsActionLoading] = useState(false);

  // KYC Modal Specific
  const [selectedKycDocs, setSelectedKycDocs] = useState<string[]>([
    "GOVERNMENT_ID",
    "PROOF_OF_ADDRESS",
  ]);

  // Email Modal Specific
  const [emailSubject, setEmailSubject] = useState("");
  const [emailBody, setEmailBody] = useState("");

  // Pricing Override Specific
  const [overrideService, setOverrideService] = useState("AI_ANALYSIS");
  const [overridePrice, setOverridePrice] = useState<string>("1.00");
  const [overrideExpiry, setOverrideExpiry] = useState("");

  // Global Pricing Form
  const [newGlobalPricing, setNewGlobalPricing] = useState({
    AI_ANALYSIS: 1.0,
    STRATEGY_EXECUTION: 0.3,
    PLATFORM_ACTIVATION: 20.0,
  });

  // Audit Diff Viewer
  const [expandedLogId, setExpandedLogId] = useState<string | null>(null);
  const [copiedText, setCopiedText] = useState<string | null>(null);

  const getApiUrl = (endpoint: string) => `/api/backend${endpoint}`;

  const showFeedback = (type: "success" | "error" | "info", message: any) => {
    const safeMessage = typeof message === "string" ? message : formatApiError(message, "An unexpected error occurred.");
    setFeedback({ type, message: safeMessage });
    setTimeout(() => setFeedback(null), 4000);
  };

  const copyToClipboard = (text: string, id: string) => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(text);
      setCopiedText(id);
      setTimeout(() => setCopiedText(null), 2000);
    }
  };

  // ─── Fetch Initial Data ───
  const fetchCustomers = async () => {
    try {
      const res = await fetch(getApiUrl("/saas/admin/customers"), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const d = await res.json();
        setCustomers(d.customers || []);
      }
    } catch {
      // non-fatal
    }
  };

  const fetchAuditLogs = async () => {
    try {
      const res = await fetch(getApiUrl("/saas/admin/audit-logs?limit=100"), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const d = await res.json();
        setAuditLogs(d.logs || d.audit_logs || []);
      }
    } catch {
      // non-fatal
    }
  };

  const fetchTickets = async () => {
    try {
      const url =
        ticketStatusFilter === "ALL"
          ? getApiUrl("/saas/admin/support/tickets")
          : getApiUrl(`/saas/admin/support/tickets?status=${ticketStatusFilter}`);
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const d = await res.json();
        setTickets(d.tickets || []);
      }
    } catch {
      // non-fatal
    }
  };

  const fetchProviderOperations = async () => {
    try {
      const res = await fetch(getApiUrl("/saas/admin/provider-operations"), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const d = await res.json();
        setProviderOps(d);
      }
    } catch {
      // non-fatal
    }
  };

  const fetchGlobalPricing = async () => {
    try {
      const res = await fetch(getApiUrl("/saas/admin/pricing/global"), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const d = await res.json();
        if (d.global) {
          setGlobalPricing(d.global);
          setNewGlobalPricing(d.global);
        }
      }
    } catch {
      // non-fatal
    }
  };

  const reloadAll = async () => {
    setIsLoading(true);
    await Promise.all([
      fetchCustomers(),
      fetchAuditLogs(),
      fetchTickets(),
      fetchProviderOperations(),
      fetchGlobalPricing(),
    ]);
    setIsLoading(false);
  };

  useEffect(() => {
    reloadAll();
  }, [token]);

  useEffect(() => {
    if (activeModule === "SUPPORT") {
      fetchTickets();
    }
  }, [ticketStatusFilter]);

  // ─── Fetch Customer 360 ───
  const openCustomer360 = async (userId: string) => {
    setSelectedCustomerId(userId);
    setIs360Loading(true);
    setActive360Tab("OVERVIEW");
    try {
      const res = await fetch(getApiUrl(`/saas/admin/customers/${userId}/360`), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const d = await res.json();
        setCustomer360Data(d);
      } else {
        showFeedback("error", "Failed to load Customer 360 dossier.");
      }
    } catch {
      showFeedback("error", "Network error retrieving Customer 360 dossier.");
    } finally {
      setIs360Loading(false);
    }
  };

  const refreshCustomer360 = async () => {
    if (!selectedCustomerId) return;
    try {
      const res = await fetch(
        getApiUrl(`/saas/admin/customers/${selectedCustomerId}/360`),
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (res.ok) {
        const d = await res.json();
        setCustomer360Data(d);
      }
    } catch {
      // non-fatal
    }
  };

  // ─── Lifecycle Actions ───
  const handleHold = async () => {
    if (!selectedCustomerId) return;
    if (!modalReason || modalReason.trim().length < 3) {
      showFeedback("error", "Reason must be at least 3 characters.");
      return;
    }
    setIsActionLoading(true);
    try {
      const res = await fetch(
        getApiUrl(`/saas/admin/customers/${selectedCustomerId}/hold`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ reason: modalReason.trim() }),
        }
      );
      if (res.ok) {
        showFeedback("success", "Temporary hold successfully placed.");
        setActiveModal(null);
        setModalReason("");
        await refreshCustomer360();
        await fetchCustomers();
        await fetchAuditLogs();
      } else {
        const err = await res.json().catch(() => ({ detail: "Failed to place hold." }));
        showFeedback("error", formatApiError(err, "Failed to place hold."));
      }
    } catch (e: any) {
      showFeedback("error", formatApiError(e, "Network error placing hold."));
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleBlock = async () => {
    if (!selectedCustomerId) return;
    if (!modalReason || modalReason.trim().length < 3) {
      showFeedback("error", "Reason must be at least 3 characters.");
      return;
    }
    setIsActionLoading(true);
    try {
      const res = await fetch(
        getApiUrl(`/saas/admin/customers/${selectedCustomerId}/block`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ reason: modalReason.trim() }),
        }
      );
      if (res.ok) {
        showFeedback("success", "Customer blocked and all sessions revoked.");
        setActiveModal(null);
        setModalReason("");
        await refreshCustomer360();
        await fetchCustomers();
        await fetchAuditLogs();
      } else {
        const err = await res.json().catch(() => ({ detail: "Failed to block customer." }));
        showFeedback("error", formatApiError(err, "Failed to block customer."));
      }
    } catch (e: any) {
      showFeedback("error", formatApiError(e, "Network error blocking customer."));
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleReactivate = async () => {
    if (!selectedCustomerId) return;
    if (!modalReason || modalReason.trim().length < 3) {
      showFeedback("error", "Reason must be at least 3 characters.");
      return;
    }
    setIsActionLoading(true);
    try {
      const res = await fetch(
        getApiUrl(`/saas/admin/customers/${selectedCustomerId}/reactivate`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ reason: modalReason.trim() }),
        }
      );
      if (res.ok) {
        showFeedback("success", "Customer account reactivated successfully.");
        setActiveModal(null);
        setModalReason("");
        await refreshCustomer360();
        await fetchCustomers();
        await fetchAuditLogs();
      } else {
        const err = await res.json().catch(() => ({ detail: "Failed to reactivate customer." }));
        showFeedback("error", formatApiError(err, "Failed to reactivate customer."));
      }
    } catch (e: any) {
      showFeedback("error", formatApiError(e, "Network error reactivating customer."));
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedCustomerId) return;
    if (!modalReason || modalReason.trim().length < 3) {
      showFeedback("error", "Reason must be at least 3 characters.");
      return;
    }
    setIsActionLoading(true);
    try {
      const res = await fetch(
        getApiUrl(`/saas/admin/customers/${selectedCustomerId}`),
        {
          method: "DELETE",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ reason: modalReason.trim(), confirm: modalConfirm }),
        }
      );
      if (res.ok) {
        showFeedback("success", "Customer permanently deleted and email freed.");
        setActiveModal(null);
        setModalReason("");
        setModalConfirm(false);
        setSelectedCustomerId(null);
        setCustomer360Data(null);
        await fetchCustomers();
        await fetchAuditLogs();
      } else {
        const err = await res.json().catch(() => ({ detail: "Failed to delete customer." }));
        if (err.detail?.code === "CONFIRMATION_REQUIRED") {
          setModalConfirm(true);
          showFeedback("info", err.detail.message);
        } else {
          showFeedback("error", formatApiError(err, "Failed to delete customer."));
        }
      }
    } catch (e: any) {
      showFeedback("error", formatApiError(e, "Network error deleting customer."));
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleRequestKyc = async () => {
    if (!selectedCustomerId || selectedKycDocs.length === 0) return;
    if (!modalReason || modalReason.trim().length < 10) {
      showFeedback("error", "Compliance note must be at least 10 characters long.");
      return;
    }
    setIsActionLoading(true);
    try {
      const res = await fetch(
        getApiUrl(`/saas/admin/customers/${selectedCustomerId}/kyc/request`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            document_types: selectedKycDocs,
            message: modalReason.trim(),
          }),
        }
      );
      if (res.ok) {
        showFeedback("success", "KYC documents requested and institutional notice emailed.");
        setActiveModal(null);
        setModalReason("");
        await refreshCustomer360();
        await fetchCustomers();
        await fetchAuditLogs();
      } else {
        const err = await res.json().catch(() => ({ detail: "Failed to request KYC." }));
        showFeedback("error", formatApiError(err, "Failed to request KYC."));
      }
    } catch (e: any) {
      showFeedback("error", formatApiError(e, "Network error requesting KYC."));
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleSendEmail = async () => {
    if (!selectedCustomerId) return;
    if (!emailSubject || emailSubject.trim().length < 3) {
      showFeedback("error", "Email subject must be at least 3 characters.");
      return;
    }
    if (!emailBody || emailBody.trim().length < 10) {
      showFeedback("error", "Email body must be at least 10 characters.");
      return;
    }
    setIsActionLoading(true);
    try {
      const res = await fetch(
        getApiUrl(`/saas/admin/customers/${selectedCustomerId}/email`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            subject: emailSubject.trim(),
            body_html: emailBody.trim(),
            email_type: "ADMIN_COMMUNICATION",
          }),
        }
      );
      if (res.ok) {
        showFeedback("success", "Institutional email dispatched to customer.");
        setActiveModal(null);
        setEmailSubject("");
        setEmailBody("");
        await refreshCustomer360();
        await fetchAuditLogs();
      } else {
        const err = await res.json().catch(() => ({ detail: "Failed to dispatch email." }));
        showFeedback("error", formatApiError(err, "Failed to dispatch email."));
      }
    } catch (e: any) {
      showFeedback("error", formatApiError(e, "Network error dispatching email."));
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleSetPricingOverride = async () => {
    if (!selectedCustomerId) return;
    if (!modalReason || modalReason.trim().length < 3) {
      showFeedback("error", "Reason for override is required (minimum 3 characters).");
      return;
    }
    const parsedPrice = parseFloat(String(overridePrice));
    if (isNaN(parsedPrice) || parsedPrice < 0) {
      showFeedback("error", "Please enter a valid price ($0.00 or greater).");
      return;
    }
    setIsActionLoading(true);
    try {
      const res = await fetch(
        getApiUrl(`/saas/admin/customers/${selectedCustomerId}/pricing/override`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            service_id: overrideService,
            price_usd: parsedPrice,
            reason: modalReason.trim(),
            confirm: modalConfirm,
            expires_at: overrideExpiry ? overrideExpiry : null,
          }),
        }
      );
      if (res.ok) {
        showFeedback(
          "success",
          `Pricing override for ${overrideService} set successfully to $${parsedPrice.toFixed(2)}.`
        );
        setActiveModal(null);
        setModalReason("");
        setModalConfirm(false);
        await refreshCustomer360();
        await fetchCustomers();
        await fetchAuditLogs();
      } else {
        const err = await res.json().catch(() => ({ detail: "Failed to set override." }));
        if (err.detail?.code === "CONFIRMATION_REQUIRED") {
          setModalConfirm(true);
          showFeedback(
            "info",
            err.detail?.message || "Material change detected (>25%). Click Confirm & Apply to proceed."
          );
        } else {
          showFeedback("error", formatApiError(err, "Failed to set override."));
        }
      }
    } catch (e: any) {
      showFeedback("error", formatApiError(e, "Network error setting override."));
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleRevokeOverride = async (serviceId: string) => {
    if (!selectedCustomerId) return;
    const reason = prompt("Enter reason for revoking override:");
    if (!reason || reason.trim().length < 3) return;
    try {
      const res = await fetch(
        getApiUrl(
          `/saas/admin/customers/${selectedCustomerId}/pricing/override/${serviceId}`
        ),
        {
          method: "DELETE",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ reason: reason.trim() }),
        }
      );
      if (res.ok) {
        showFeedback("success", "Override revoked. Global default restored.");
        await refreshCustomer360();
        await fetchCustomers();
        await fetchAuditLogs();
      } else {
        const err = await res.json().catch(() => ({ detail: "Failed to revoke override." }));
        showFeedback("error", formatApiError(err, "Failed to revoke override."));
      }
    } catch (e: any) {
      showFeedback("error", formatApiError(e, "Network error revoking override."));
    }
  };

  const handleUpdateGlobalPricing = async () => {
    if (!modalReason || modalReason.trim().length < 3) {
      showFeedback("error", "A valid reason (minimum 3 characters) is required for global pricing adjustments.");
      return;
    }
    setIsActionLoading(true);
    try {
      const res = await fetch(getApiUrl("/saas/admin/pricing/global"), {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          changes: newGlobalPricing,
          reason: modalReason.trim(),
          confirm: modalConfirm,
        }),
      });
      if (res.ok) {
        showFeedback("success", "Global platform pricing defaults updated.");
        setActiveModal(null);
        setModalReason("");
        setModalConfirm(false);
        await fetchGlobalPricing();
        await fetchAuditLogs();
      } else {
        const err = await res.json().catch(() => ({ detail: "Failed to update global pricing." }));
        if (err.detail?.code === "CONFIRMATION_REQUIRED") {
          setModalConfirm(true);
          showFeedback("info", err.detail.message);
        } else {
          showFeedback("error", formatApiError(err, "Failed to update global pricing."));
        }
      }
    } catch (e: any) {
      showFeedback("error", formatApiError(e, "Network error updating global pricing."));
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleCreditOverride = async () => {
    if (!selectedCustomerId) return;
    const parsedAmount = parseFloat(overrideCreditsAmount);
    if (isNaN(parsedAmount) || parsedAmount < 0) {
      showFeedback("error", "Target balance must be a non-negative number.");
      return;
    }
    if (!modalReason || modalReason.trim().length < 3) {
      showFeedback("error", "A valid audit reason (minimum 3 characters) is required.");
      return;
    }
    setIsActionLoading(true);
    try {
      const res = await fetch(
        getApiUrl(`/saas/admin/customers/${selectedCustomerId}/credits/override`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            new_credits_usd: parsedAmount,
            reason: modalReason.trim(),
            reference_id: creditReferenceId.trim() || undefined,
          }),
        }
      );
      if (res.ok) {
        showFeedback("success", `Prepaid credits successfully updated to $${parsedAmount.toFixed(2)} USDT.`);
        setActiveModal(null);
        setModalReason("");
        setCreditReferenceId("");
        setOverrideCreditsAmount("0.00");
        await refreshCustomer360();
        await fetchCustomers();
        await fetchAuditLogs();
      } else {
        const err = await res.json().catch(() => ({ detail: "Failed to override credits." }));
        showFeedback("error", formatApiError(err, "Failed to override credits."));
      }
    } catch (e: any) {
      showFeedback("error", formatApiError(e, "Network error overriding credits."));
    } finally {
      setIsActionLoading(false);
    }
  };

  // ─── Filtered Customers List ───
  const filteredCustomers = useMemo(() => {
    return customers.filter((c) => {
      const q = searchQuery.toLowerCase().trim();
      const matchSearch =
        !q ||
        c.user_id?.toLowerCase().includes(q) ||
        c.email?.toLowerCase().includes(q) ||
        c.username?.toLowerCase().includes(q) ||
        c.first_name?.toLowerCase().includes(q) ||
        c.last_name?.toLowerCase().includes(q);

      const matchStatus =
        statusFilter === "ALL" ||
        c.status === statusFilter;

      const matchKyc =
        kycFilter === "ALL" ||
        (c.kyc_status || "NOT_REQUIRED") === kycFilter;

      const matchPricing =
        pricingFilter === "ALL" ||
        (pricingFilter === "OVERRIDE" && c.has_pricing_override) ||
        (pricingFilter === "GLOBAL" && !c.has_pricing_override);

      return matchSearch && matchStatus && matchKyc && matchPricing;
    });
  }, [customers, searchQuery, statusFilter, kycFilter, pricingFilter]);

  // ─── Filtered Audit Logs ───
  const filteredAuditLogs = useMemo(() => {
    return auditLogs.filter((l) => {
      if (auditActionFilter === "ALL") return true;
      return l.action === auditActionFilter;
    });
  }, [auditLogs, auditActionFilter]);

  const uniqueAuditActions = useMemo(() => {
    const s = new Set<string>();
    auditLogs.forEach((l) => {
      if (l.action) s.add(l.action);
    });
    return Array.from(s).sort();
  }, [auditLogs]);

  // Status Pill Styles
  const getStatusBadge = (status: string) => {
    const s = status?.toUpperCase() || "UNKNOWN";
    if (s === "ACTIVE") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
          <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
          ACTIVE
        </span>
      );
    }
    if (s === "TEMPORARY_HOLD") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30">
          <span className="w-1.5 h-1.5 rounded-full bg-[#F59E0B]" />
          TEMP HOLD
        </span>
      );
    }
    if (s === "BLOCKED") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#F43F5E]/15 text-[#F43F5E] border border-[#F43F5E]/30">
          <span className="w-1.5 h-1.5 rounded-full bg-[#F43F5E]" />
          BLOCKED
        </span>
      );
    }
    if (s === "DELETED") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gray-500/15 text-gray-400 border border-gray-500/30">
          DELETED
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-300">
        {s}
      </span>
    );
  };

  const getKycBadge = (status: string) => {
    const k = status?.toUpperCase() || "NOT_REQUIRED";
    if (k === "APPROVED") {
      return (
        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#10B981]">
          <CheckCircle2 className="w-3.5 h-3.5" /> Approved
        </span>
      );
    }
    if (k === "PENDING" || k === "PENDING_DOCUMENTS") {
      return (
        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#F59E0B]">
          <Clock className="w-3.5 h-3.5" /> Pending Doc
        </span>
      );
    }
    if (k === "REJECTED") {
      return (
        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#F43F5E]">
          <AlertCircle className="w-3.5 h-3.5" /> Rejected
        </span>
      );
    }
    return (
      <span className="text-[11px] text-slate-400">Not Required</span>
    );
  };

  return (
    <div className="min-h-screen bg-[#0A0A0E] text-[#EAECEF] font-sans flex flex-col antialiased selection:bg-[#00E5FF]/20 selection:text-[#00E5FF]">
      {/* ─── TOP GOVERNANCE HEADER ─── */}
      <header className="h-14 bg-[#121218] border-b border-[#272735] flex items-center justify-between px-6 z-30 sticky top-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[#181822] border border-[#272735] flex items-center justify-center font-black text-sm tracking-wider">
              <span className="text-white">B</span>
              <span className="text-[#00E5FF]">X</span>
            </div>
            <div className="flex items-baseline">
              <span className="font-extrabold text-base tracking-wider text-white">BIT</span>
              <span className="font-extrabold text-base tracking-wider text-[#00E5FF]">DEX</span>
              <span className="ml-2 text-[10px] font-semibold uppercase tracking-widest text-[#8B5CF6] px-1.5 py-0.5 rounded bg-[#8B5CF6]/10 border border-[#8B5CF6]/30">
                ADMIN
              </span>
            </div>
          </div>

          <div className="h-4 w-px bg-[#272735]" />

          <div className="flex items-center gap-2 text-xs">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#10B981]/10 text-[#10B981] border border-[#10B981]/25 font-mono text-[11px]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#10B981] animate-pulse" />
              TENANT ISOLATION ACTIVE
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#181822] text-slate-300 border border-[#272735] font-mono text-[11px]">
              TAURIC: ONLINE (8ms)
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {onSwitchPortal && (
            <button
              id="btn-switch-to-trading-terminal"
              onClick={onSwitchPortal}
              className="text-xs px-3.5 py-1.5 rounded-lg bg-[#00E5FF]/15 hover:bg-[#00E5FF]/25 text-[#00E5FF] hover:text-white border border-[#00E5FF]/40 font-semibold transition flex items-center gap-2 cursor-pointer shadow-sm"
              title="Switch to Customer Trading Terminal"
            >
              <Activity className="w-4 h-4 text-[#00E5FF]" />
              <span>Trading Terminal</span>
              <ArrowRight className="w-3.5 h-3.5 text-[#00E5FF]/80" />
            </button>
          )}

          <div className="relative" ref={adminDropdownRef}>
            <button
              id="btn-admin-profile-dropdown"
              onClick={() => setIsAdminDropdownOpen(!isAdminDropdownOpen)}
              className="flex items-center gap-2.5 p-1.5 pl-2 rounded-lg bg-[#181822] border border-[#272735] hover:border-[#8B5CF6]/60 transition cursor-pointer select-none"
            >
              <div className="w-7 h-7 rounded-full bg-[#8B5CF6]/20 border border-[#8B5CF6]/40 flex items-center justify-center text-xs font-bold text-[#8B5CF6]">
                {adminUser?.first_name?.[0] || adminUser?.email?.[0]?.toUpperCase() || "A"}
              </div>
              <div className="text-left hidden sm:block">
                <div className="text-xs font-semibold leading-tight text-white max-w-[140px] truncate">
                  {adminUser?.email || "sysadmin@bitdex.ltd"}
                </div>
                <div className="text-[10px] font-mono text-[#8B5CF6] uppercase">
                  {adminUser?.role || "ADMINISTRATOR"}
                </div>
              </div>
              <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${isAdminDropdownOpen ? "rotate-180" : ""}`} />
            </button>

            {isAdminDropdownOpen && (
              <div className="absolute right-0 mt-2 w-64 bg-[#121218] border border-[#272735] rounded-xl shadow-2xl py-2 z-50 text-xs font-sans animate-in fade-in duration-150">
                <div className="px-3 py-2 border-b border-[#272735]">
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider block font-bold">
                    Authenticated Administrator
                  </span>
                  <span className="font-semibold text-white truncate block mt-0.5">
                    {adminUser?.email || "sysadmin@bitdex.ltd"}
                  </span>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-[#8B5CF6]/20 text-[#8B5CF6] border border-[#8B5CF6]/30">
                      {adminUser?.role || "ADMINISTRATOR"}
                    </span>
                    <span className="text-[10px] font-mono text-[#10B981]">
                      ISOLATION ACTIVE
                    </span>
                  </div>
                </div>

                <div className="py-1">
                  {onSwitchPortal && (
                    <button
                      id="dropdown-switch-to-terminal"
                      onClick={() => {
                        setIsAdminDropdownOpen(false);
                        onSwitchPortal();
                      }}
                      className="w-full px-3 py-2 text-left text-slate-300 hover:text-white hover:bg-[#181822] flex items-center justify-between group cursor-pointer"
                    >
                      <div className="flex items-center gap-2">
                        <Activity className="w-3.5 h-3.5 text-[#00E5FF]" />
                        <span className="font-medium text-[#00E5FF]">Trading Terminal</span>
                      </div>
                      <ArrowRight className="w-3 h-3 text-slate-500 group-hover:text-white" />
                    </button>
                  )}
                  <button
                    onClick={() => {
                      setActiveModule("CUSTOMERS");
                      setIsAdminDropdownOpen(false);
                    }}
                    className="w-full px-3 py-2 text-left text-slate-300 hover:text-white hover:bg-[#181822] flex items-center gap-2 cursor-pointer"
                  >
                    <Users className="w-3.5 h-3.5 text-slate-400" />
                    <span>Customer Directory</span>
                  </button>
                  <button
                    onClick={() => {
                      setActiveModule("AI_PRICING");
                      setIsAdminDropdownOpen(false);
                    }}
                    className="w-full px-3 py-2 text-left text-slate-300 hover:text-white hover:bg-[#181822] flex items-center gap-2 cursor-pointer"
                  >
                    <Cpu className="w-3.5 h-3.5 text-slate-400" />
                    <span>Global Pricing &amp; Overrides</span>
                  </button>
                  <button
                    onClick={() => {
                      setActiveModule("EXCHANGES");
                      setIsAdminDropdownOpen(false);
                    }}
                    className="w-full px-3 py-2 text-left text-slate-300 hover:text-white hover:bg-[#181822] flex items-center gap-2 cursor-pointer"
                  >
                    <Zap className="w-3.5 h-3.5 text-slate-400" />
                    <span>Exchange Infrastructure</span>
                  </button>
                  <button
                    onClick={() => {
                      setActiveModule("AUDIT");
                      setIsAdminDropdownOpen(false);
                    }}
                    className="w-full px-3 py-2 text-left text-slate-300 hover:text-white hover:bg-[#181822] flex items-center gap-2 cursor-pointer"
                  >
                    <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
                    <span>System Audit Trail</span>
                  </button>
                  <button
                    onClick={() => {
                      setActiveModule("SUPPORT");
                      setIsAdminDropdownOpen(false);
                    }}
                    className="w-full px-3 py-2 text-left text-slate-300 hover:text-white hover:bg-[#181822] flex items-center gap-2 cursor-pointer"
                  >
                    <MessageSquare className="w-3.5 h-3.5 text-slate-400" />
                    <span>Support Inbox</span>
                  </button>
                </div>

                <div className="pt-1 border-t border-[#272735]">
                  <button
                    id="btn-admin-sign-out"
                    onClick={() => {
                      setIsAdminDropdownOpen(false);
                      onSignOut();
                    }}
                    className="w-full px-3 py-2 text-left text-rose-400 hover:bg-rose-500/10 flex items-center gap-2 cursor-pointer font-medium"
                  >
                    <LogOut className="w-3.5 h-3.5 text-rose-400" />
                    <span>Sign Out</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ─── WORKSPACE LAYOUT (PERSISTENT LEFT NAV RAIL + MAIN VIEWPORT) ─── */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Nav Rail (240px wide) */}
        <aside className="w-60 bg-[#121218] border-r border-[#272735] flex flex-col justify-between select-none shrink-0">
          <div className="p-3 space-y-1">
            <div className="px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Operational Modules
            </div>

            <button
              onClick={() => setActiveModule("CUSTOMERS")}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium transition ${
                activeModule === "CUSTOMERS"
                  ? "bg-[#00E5FF]/10 text-[#00E5FF] border border-[#00E5FF]/30 shadow-sm"
                  : "text-slate-300 hover:bg-[#181822] hover:text-white"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Users className={`w-4 h-4 ${activeModule === "CUSTOMERS" ? "text-[#00E5FF]" : "text-slate-400"}`} />
                <span>Customers</span>
              </div>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#181822] text-slate-400 border border-[#272735]">
                {customers.length}
              </span>
            </button>

            <button
              onClick={() => setActiveModule("SUPPORT")}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium transition ${
                activeModule === "SUPPORT"
                  ? "bg-[#00E5FF]/10 text-[#00E5FF] border border-[#00E5FF]/30 shadow-sm"
                  : "text-slate-300 hover:bg-[#181822] hover:text-white"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <MessageSquare className={`w-4 h-4 ${activeModule === "SUPPORT" ? "text-[#00E5FF]" : "text-slate-400"}`} />
                <span>Support Inbox</span>
              </div>
              {tickets.filter((t) => t.status === "Open").length > 0 && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#F59E0B]/20 text-[#F59E0B] border border-[#F59E0B]/40">
                  {tickets.filter((t) => t.status === "Open").length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveModule("AI_PRICING")}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium transition ${
                activeModule === "AI_PRICING"
                  ? "bg-[#00E5FF]/10 text-[#00E5FF] border border-[#00E5FF]/30 shadow-sm"
                  : "text-slate-300 hover:bg-[#181822] hover:text-white"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Cpu className={`w-4 h-4 ${activeModule === "AI_PRICING" ? "text-[#00E5FF]" : "text-slate-400"}`} />
                <span>AI Telemetry & Pricing</span>
              </div>
            </button>

            <button
              onClick={() => setActiveModule("EXCHANGES")}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium transition ${
                activeModule === "EXCHANGES"
                  ? "bg-[#00E5FF]/10 text-[#00E5FF] border border-[#00E5FF]/30 shadow-sm"
                  : "text-slate-300 hover:bg-[#181822] hover:text-white"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Zap className={`w-4 h-4 ${activeModule === "EXCHANGES" ? "text-[#00E5FF]" : "text-slate-400"}`} />
                <span>Exchanges</span>
              </div>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
                ISOLATED
              </span>
            </button>

            <button
              onClick={() => setActiveModule("AUDIT")}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium transition ${
                activeModule === "AUDIT"
                  ? "bg-[#00E5FF]/10 text-[#00E5FF] border border-[#00E5FF]/30 shadow-sm"
                  : "text-slate-300 hover:bg-[#181822] hover:text-white"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <ShieldCheck className={`w-4 h-4 ${activeModule === "AUDIT" ? "text-[#00E5FF]" : "text-slate-400"}`} />
                <span>Audit Trail</span>
              </div>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#181822] text-slate-400 border border-[#272735]">
                {auditLogs.length}
              </span>
            </button>
          </div>

          {/* Rail Footer */}
          <div className="p-3 border-t border-[#272735] space-y-2">
            {onSwitchPortal && (
              <button
                id="btn-rail-switch-terminal"
                onClick={onSwitchPortal}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-[#00E5FF]/10 hover:bg-[#00E5FF]/20 text-[#00E5FF] hover:text-white text-xs font-semibold border border-[#00E5FF]/30 transition cursor-pointer shadow-sm"
              >
                <Activity className="w-3.5 h-3.5 text-[#00E5FF]" />
                <span>Trading Terminal</span>
              </button>
            )}
            <div className="p-2.5 rounded-lg bg-[#181822] border border-[#272735] text-[11px]">
              <div className="flex items-center justify-between text-slate-400 mb-1">
                <span>Global AI Run Rate</span>
                <span className="text-[#00E5FF] font-mono font-bold">
                  ${globalPricing.AI_ANALYSIS.toFixed(2)}
                </span>
              </div>
              <div className="flex items-center justify-between text-slate-400">
                <span>Strategy Execution</span>
                <span className="text-white font-mono font-bold">
                  ${globalPricing.STRATEGY_EXECUTION.toFixed(2)}
                </span>
              </div>
            </div>

            <button
              onClick={reloadAll}
              disabled={isLoading}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-[#181822] hover:bg-[#272735] text-slate-300 hover:text-white text-xs border border-[#272735] transition"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-[#00E5FF]" : ""}`} />
              Refresh Telemetry
            </button>
          </div>
        </aside>

        {/* ─── MAIN CONTENT VIEWPORT ─── */}
        <main className="flex-1 bg-[#0A0A0E] overflow-y-auto p-6 relative">
          {/* Feedback banner */}
          {feedback && (
            <div
              className={`mb-4 p-3.5 rounded-lg text-xs font-medium border flex items-center justify-between animate-fadeIn ${
                feedback.type === "success"
                  ? "bg-[#10B981]/15 text-[#10B981] border-[#10B981]/30"
                  : feedback.type === "error"
                  ? "bg-[#F43F5E]/15 text-[#F43F5E] border-[#F43F5E]/30"
                  : "bg-[#00E5FF]/15 text-[#00E5FF] border-[#00E5FF]/30"
              }`}
            >
              <div className="flex items-center gap-2">
                {feedback.type === "success" && <CheckCircle2 className="w-4 h-4" />}
                {feedback.type === "error" && <AlertTriangle className="w-4 h-4" />}
                {feedback.type === "info" && <AlertCircle className="w-4 h-4" />}
                <span>{feedback.message}</span>
              </div>
              <button
                onClick={() => setFeedback(null)}
                className="hover:opacity-75"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          <ProtectionCenter token={token} className="mb-6" />

          {/* Dual-Engine Platform Oversight & Risk Controls */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div className="rounded-xl bg-[#121218] border border-[#272735] p-4 font-mono text-xs">
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-[#272735]">
                <span className="text-white font-bold flex items-center gap-2">
                  <Layers className="w-4 h-4 text-purple-400" />
                  ENGINE A (SPOT &amp; SWING)
                </span>
                <span className="text-[10px] text-[#F59E0B] px-2 py-0.5 rounded bg-[#F59E0B]/10 border border-[#F59E0B]/30 font-bold">
                  STANDBY • LIVE LOCKED
                </span>
              </div>
              <div className="text-[11px] text-[#94A3B8] space-y-1">
                <div className="flex justify-between"><span>Strategy:</span><span className="text-white">SPOT_GRID_SWING</span></div>
                <div className="flex justify-between"><span>Mutual Exclusivity:</span><span className="text-[#10B981]">ARMED (0 Collisions)</span></div>
                <div className="flex justify-between"><span>Safety Locks:</span><span className="text-[#10B981]">Zero Real-Money Risk</span></div>
              </div>
            </div>

            <div className="rounded-xl bg-[#121218] border border-[#272735] p-4 font-mono text-xs">
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-[#272735]">
                <span className="text-white font-bold flex items-center gap-2">
                  <Zap className="w-4 h-4 text-[#00E5FF]" />
                  ENGINE B (AUTONOMOUS SCALPER)
                </span>
                <span className="text-[10px] text-[#00E5FF] px-2 py-0.5 rounded bg-[#00E5FF]/10 border border-[#00E5FF]/30 font-bold">
                  POST-ONLY MOMENTUM
                </span>
              </div>
              <div className="text-[11px] text-[#94A3B8] space-y-1">
                <div className="flex justify-between"><span>Filters:</span><span className="text-white">Donchian(20) • ADX&gt;22 • RVOL&gt;1.5</span></div>
                <div className="flex justify-between"><span>Leverage Ceiling:</span><span className="text-[#10B981]">5x Hard Clamped</span></div>
                <div className="flex justify-between"><span>Exposure Cap:</span><span className="text-white">50.0% Aggregate Portfolio</span></div>
              </div>
            </div>
          </div>


          {/* ════════════ MODULE 1: CUSTOMERS WORKSPACE ════════════ */}
          {activeModule === "CUSTOMERS" && (
            <div className="space-y-5">
              {/* Top Action Bar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                    Customer Management Workspace
                    <span className="text-xs font-mono font-normal text-slate-400 px-2 py-0.5 rounded bg-[#181822] border border-[#272735]">
                      {filteredCustomers.length} Total
                    </span>
                  </h1>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Tenant-isolated quantitative client accounts, compliance status, and custom fee policies.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      setNewGlobalPricing(globalPricing);
                      setActiveModal("GLOBAL_PRICING");
                    }}
                    className="px-3 py-1.5 rounded-lg bg-[#181822] hover:bg-[#272735] text-slate-300 hover:text-white text-xs border border-[#272735] transition flex items-center gap-1.5"
                  >
                    <Settings className="w-3.5 h-3.5 text-[#00E5FF]" />
                    Global Default Pricing
                  </button>
                </div>
              </div>

              {/* Filters Bar */}
              <div className="p-3 rounded-xl bg-[#121218] border border-[#272735] flex flex-wrap items-center justify-between gap-3">
                <div className="relative flex-1 min-w-[240px]">
                  <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search name, email, or Customer ID (USR-...)..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full bg-[#181822] border border-[#272735] focus:border-[#00E5FF] rounded-lg pl-9 pr-3 py-1.5 text-xs text-white placeholder-slate-500 outline-none transition"
                  />
                </div>

                <div className="flex items-center gap-2 text-xs">
                  <span className="text-slate-400 text-[11px]">Status:</span>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="bg-[#181822] border border-[#272735] rounded-lg px-2.5 py-1.5 text-xs text-slate-200 outline-none"
                  >
                    <option value="ALL">All Statuses</option>
                    <option value="ACTIVE">Active</option>
                    <option value="TEMPORARY_HOLD">Temporary Hold</option>
                    <option value="BLOCKED">Blocked</option>
                  </select>

                  <span className="text-slate-400 text-[11px] ml-1">KYC:</span>
                  <select
                    value={kycFilter}
                    onChange={(e) => setKycFilter(e.target.value)}
                    className="bg-[#181822] border border-[#272735] rounded-lg px-2.5 py-1.5 text-xs text-slate-200 outline-none"
                  >
                    <option value="ALL">All KYC</option>
                    <option value="APPROVED">Approved</option>
                    <option value="PENDING_DOCUMENTS">Pending Documents</option>
                    <option value="REJECTED">Rejected</option>
                    <option value="NOT_REQUIRED">Not Required</option>
                  </select>

                  <span className="text-slate-400 text-[11px] ml-1">Pricing:</span>
                  <select
                    value={pricingFilter}
                    onChange={(e) => setPricingFilter(e.target.value)}
                    className="bg-[#181822] border border-[#272735] rounded-lg px-2.5 py-1.5 text-xs text-slate-200 outline-none"
                  >
                    <option value="ALL">All Pricing</option>
                    <option value="OVERRIDE">Custom Override</option>
                    <option value="GLOBAL">Global Default</option>
                  </select>
                </div>
              </div>

              {/* Main Customers Table */}
              <div className="rounded-xl bg-[#121218] border border-[#272735] overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="bg-[#181822]/80 border-b border-[#272735] text-[11px] uppercase tracking-wider text-slate-400">
                        <th className="py-3 px-4 font-semibold">Customer & ID</th>
                        <th className="py-3 px-3 font-semibold">Role</th>
                        <th className="py-3 px-4 font-semibold">Status & Compliance</th>
                        <th className="py-3 px-4 font-semibold">Credits / Bal</th>
                        <th className="py-3 px-4 font-semibold">AI Usage (30D)</th>
                        <th className="py-3 px-4 font-semibold">Effective Pricing</th>
                        <th className="py-3 px-4 font-semibold text-right">Quick Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#272735]">
                      {filteredCustomers.length === 0 ? (
                        <tr>
                          <td colSpan={7} className="text-center py-12 text-slate-500">
                            No customers found matching the search and filter criteria.
                          </td>
                        </tr>
                      ) : (
                        filteredCustomers.map((cust) => {
                          const fullName =
                            cust.first_name || cust.last_name
                              ? `${cust.first_name || ""} ${cust.last_name || ""}`.trim()
                              : cust.username || cust.email?.split("@")[0] || "Trader";

                          return (
                            <tr
                              key={cust.user_id}
                              onClick={() => openCustomer360(cust.user_id)}
                              className="hover:bg-[#181822]/60 cursor-pointer transition group"
                            >
                              {/* 1. Customer & ID */}
                              <td className="py-3.5 px-4">
                                <div className="flex items-center gap-3">
                                  <div className="w-8 h-8 rounded-full bg-[#181822] border border-[#272735] flex items-center justify-center font-bold text-xs text-[#00E5FF]">
                                    {fullName[0]?.toUpperCase() || "C"}
                                  </div>
                                  <div>
                                    <div className="font-semibold text-white group-hover:text-[#00E5FF] transition">
                                      {fullName}
                                    </div>
                                    <div className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5 mt-0.5">
                                      <span>{cust.email}</span>
                                      <span className="text-slate-600">&bull;</span>
                                      <span className="text-slate-500">{cust.user_id}</span>
                                    </div>
                                  </div>
                                </div>
                              </td>

                              {/* 2. Role */}
                              <td className="py-3.5 px-3">
                                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium uppercase bg-[#181822] text-slate-300 border border-[#272735]">
                                  {cust.role || "CUSTOMER"}
                                </span>
                              </td>

                              {/* 3. Status & Compliance */}
                              <td className="py-3.5 px-4">
                                <div className="flex flex-col gap-1 items-start">
                                  {getStatusBadge(cust.status)}
                                  <div className="mt-0.5">
                                    {getKycBadge(cust.kyc_status)}
                                  </div>
                                </div>
                              </td>

                              {/* 4. Credits / Bal */}
                              <td className="py-3.5 px-4">
                                <div className="font-mono font-bold text-white">
                                  ${Number(cust.prepaid_credits_usd ?? cust.balance_usd ?? 0).toFixed(2)} USDT
                                </div>
                                <div className="text-[10px] text-slate-400 flex items-center gap-1 mt-0.5">
                                  {cust.two_factor_enabled ? (
                                    <span className="text-[#10B981] flex items-center gap-0.5">
                                      <Lock className="w-3 h-3" /> 2FA: Enabled
                                    </span>
                                  ) : (
                                    <span className="text-slate-500">2FA: Disabled</span>
                                  )}
                                </div>
                              </td>

                              {/* 5. AI Usage (30D) */}
                              <td className="py-3.5 px-4">
                                <div className="font-mono text-slate-200">
                                  {cust.ai_runs_count || 0} Runs
                                </div>
                                <div className="text-[11px] font-mono text-[#00E5FF]">
                                  ${Number(cust.ai_runs_usd || 0).toFixed(2)} Rev
                                </div>
                              </td>

                              {/* 6. Effective Pricing */}
                              <td className="py-3.5 px-4">
                                {cust.has_pricing_override ? (
                                  <div>
                                    <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-[#8B5CF6] uppercase">
                                      Custom Override
                                    </span>
                                    <div className="font-mono text-xs text-white">
                                      ${Number(cust.effective_ai_price || 0.75).toFixed(2)} / Run
                                    </div>
                                  </div>
                                ) : (
                                  <div>
                                    <span className="text-[10px] text-slate-400 uppercase">
                                      Global Default
                                    </span>
                                    <div className="font-mono text-xs text-slate-300">
                                      ${globalPricing.AI_ANALYSIS.toFixed(2)} / Run
                                    </div>
                                  </div>
                                )}
                              </td>

                              {/* 7. Actions */}
                              <td className="py-3.5 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                                <div className="flex items-center justify-end gap-1.5">
                                  <button
                                    id={`open-360-btn-${cust.user_id}`}
                                    onClick={() => openCustomer360(cust.user_id)}
                                    title="Open Customer 360° Inspection Drawer"
                                    className="px-2.5 py-1 rounded bg-[#181822] hover:bg-[#272735] text-slate-300 hover:text-white border border-[#272735] text-xs transition flex items-center gap-1"
                                  >
                                    <Eye className="w-3.5 h-3.5 text-[#00E5FF]" />
                                    <span>360°</span>
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ════════════ MODULE 2: SUPPORT INBOX ════════════ */}
          {activeModule === "SUPPORT" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                    Customer Support & Communication Centre
                  </h1>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Manage incoming tickets, direct KYC requests, and branded institutional notices.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={ticketStatusFilter}
                    onChange={(e) => setTicketStatusFilter(e.target.value)}
                    className="bg-[#121218] border border-[#272735] rounded-lg px-3 py-1.5 text-xs text-slate-200 outline-none"
                  >
                    <option value="ALL">All Tickets</option>
                    <option value="Open">Open</option>
                    <option value="In Progress">In Progress</option>
                    <option value="Resolved">Resolved</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 h-[calc(100vh-180px)]">
                {/* Tickets list */}
                <div className="rounded-xl bg-[#121218] border border-[#272735] flex flex-col overflow-hidden">
                  <div className="p-3 border-b border-[#272735] text-xs font-semibold text-slate-300">
                    Incoming Tickets ({tickets.length})
                  </div>
                  <div className="flex-1 overflow-y-auto divide-y divide-[#272735]">
                    {tickets.length === 0 ? (
                      <div className="p-8 text-center text-xs text-slate-500">
                        No support tickets in queue.
                      </div>
                    ) : (
                      tickets.map((t) => (
                        <div
                          key={t.ticket_id}
                          onClick={() => setSelectedTicket(t)}
                          className={`p-3.5 cursor-pointer text-xs transition ${
                            selectedTicket?.ticket_id === t.ticket_id
                              ? "bg-[#181822] border-l-2 border-[#00E5FF]"
                              : "hover:bg-[#181822]/60"
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-mono text-[10px] text-slate-400">
                              {t.ticket_id}
                            </span>
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                                t.status === "Open"
                                  ? "bg-[#F59E0B]/15 text-[#F59E0B]"
                                  : t.status === "In Progress"
                                  ? "bg-[#00E5FF]/15 text-[#00E5FF]"
                                  : "bg-[#10B981]/15 text-[#10B981]"
                              }`}
                            >
                              {t.status}
                            </span>
                          </div>
                          <div className="font-semibold text-white truncate">
                            {t.subject || "Support Inquiry"}
                          </div>
                          <div className="text-slate-400 text-[11px] truncate mt-0.5">
                            {t.user_email || t.user_id}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* Ticket Details & Thread */}
                <div className="lg:col-span-2 rounded-xl bg-[#121218] border border-[#272735] flex flex-col overflow-hidden">
                  {selectedTicket ? (
                    <>
                      <div className="p-4 border-b border-[#272735] flex items-center justify-between bg-[#181822]">
                        <div>
                          <div className="flex items-center gap-2">
                            <h2 className="font-bold text-sm text-white">
                              {selectedTicket.subject}
                            </h2>
                            <span className="font-mono text-xs text-slate-400">
                              #{selectedTicket.ticket_id}
                            </span>
                          </div>
                          <div className="text-xs text-slate-400 mt-0.5">
                            From: {selectedTicket.user_email} &bull; Created:{" "}
                            {selectedTicket.created_at}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => openCustomer360(selectedTicket.user_id)}
                            className="px-2.5 py-1 rounded bg-[#272735] hover:bg-[#323244] text-xs text-slate-200 transition"
                          >
                            View Customer 360°
                          </button>
                        </div>
                      </div>

                      {/* Conversation thread */}
                      <div className="flex-1 overflow-y-auto p-4 space-y-3">
                        <div className="p-3.5 rounded-lg bg-[#181822] border border-[#272735] text-xs">
                          <div className="flex items-center justify-between text-slate-400 mb-1.5">
                            <span className="font-semibold text-white">
                              {selectedTicket.user_email}
                            </span>
                            <span className="font-mono text-[10px]">
                              {selectedTicket.created_at}
                            </span>
                          </div>
                          <div className="text-slate-200 leading-relaxed whitespace-pre-wrap">
                            {selectedTicket.initial_message || selectedTicket.message}
                          </div>
                        </div>

                        {selectedTicket.messages?.map((m: any, idx: number) => (
                          <div
                            key={idx}
                            className={`p-3.5 rounded-lg text-xs ${
                              m.is_admin
                                ? "bg-[#00E5FF]/10 border border-[#00E5FF]/30 ml-8"
                                : "bg-[#181822] border border-[#272735] mr-8"
                            }`}
                          >
                            <div className="flex items-center justify-between text-slate-400 mb-1">
                              <span className="font-semibold text-white">
                                {m.sender_name || (m.is_admin ? "Support Team" : "Customer")}
                              </span>
                              <span className="font-mono text-[10px]">{m.created_at}</span>
                            </div>
                            <div className="text-slate-200 leading-relaxed whitespace-pre-wrap">
                              {m.message}
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Reply Box */}
                      <div className="p-3 border-t border-[#272735] bg-[#181822]">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2 text-xs">
                            <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
                              <input
                                type="checkbox"
                                checked={isInternalNote}
                                onChange={(e) => setIsInternalNote(e.target.checked)}
                                className="rounded bg-[#121218] border-[#272735] text-[#8B5CF6]"
                              />
                              <span>Internal note (not visible to customer)</span>
                            </label>
                          </div>
                        </div>

                        <div className="flex gap-2">
                          <textarea
                            value={ticketReply}
                            onChange={(e) => setTicketReply(e.target.value)}
                            placeholder="Type institutional reply or internal resolution note..."
                            rows={3}
                            className="flex-1 bg-[#121218] border border-[#272735] rounded-lg p-2.5 text-xs text-white placeholder-slate-500 outline-none focus:border-[#00E5FF]"
                          />
                          <button
                            onClick={async () => {
                              if (!ticketReply.trim() || !selectedTicket) return;
                              setIsTicketSubmitting(true);
                              try {
                                const res = await fetch(
                                  getApiUrl(`/saas/admin/support/tickets/${selectedTicket.ticket_id}/reply`),
                                  {
                                    method: "POST",
                                    headers: {
                                      "Content-Type": "application/json",
                                      Authorization: `Bearer ${token}`,
                                    },
                                    body: JSON.stringify({
                                      message: ticketReply,
                                      is_internal_note: isInternalNote,
                                    }),
                                  }
                                );
                                if (res.ok) {
                                  showFeedback("success", "Reply dispatched successfully.");
                                  setTicketReply("");
                                  await fetchTickets();
                                }
                              } finally {
                                setIsTicketSubmitting(false);
                              }
                            }}
                            disabled={isTicketSubmitting || !ticketReply.trim()}
                            className="px-4 rounded-lg bg-[#00E5FF] hover:bg-[#00c8e0] text-[#0A0A0E] font-bold text-xs transition flex flex-col items-center justify-center gap-1"
                          >
                            <Send className="w-4 h-4" />
                            <span>Send</span>
                          </button>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="flex-1 flex flex-col items-center justify-center text-slate-500 p-8">
                      <LifeBuoy className="w-8 h-8 mb-2 opacity-50" />
                      <div className="text-sm font-medium">Select a ticket to review conversation thread</div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ════════════ MODULE 3: AI TELEMETRY & GLOBAL PRICING ════════════ */}
          {activeModule === "AI_PRICING" && (
            <div className="space-y-6">
              <div>
                <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                  AI Telemetry & Global Pricing Engine
                </h1>
                <p className="text-xs text-slate-400 mt-0.5">
                  Platform-wide pricing benchmarks, multi-agent AI execution margins, and quota controls.
                </p>
              </div>

              {/* Telemetry Metric Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="p-4 rounded-xl bg-[#121218] border border-[#272735]">
                  <div className="text-xs text-slate-400 font-medium">Total AI Intelligence Runs</div>
                  <div className="text-2xl font-bold font-mono text-white mt-1">
                    {providerOps?.telemetry_summary?.total_runs || 181}
                  </div>
                  <div className="text-[11px] text-[#10B981] mt-1 flex items-center gap-1">
                    <span>{providerOps?.telemetry_summary?.completed_runs || 181} Completed</span>
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-[#121218] border border-[#272735]">
                  <div className="text-xs text-slate-400 font-medium">Gross AI Customer Revenue</div>
                  <div className="text-2xl font-bold font-mono text-[#00E5FF] mt-1">
                    ${Number(providerOps?.telemetry_summary?.total_customer_revenue_usd || 181.0).toFixed(2)}
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1">Pay-per-use billing deduction</div>
                </div>

                <div className="p-4 rounded-xl bg-[#121218] border border-[#272735]">
                  <div className="text-xs text-slate-400 font-medium">Provider Inference Costs</div>
                  <div className="text-2xl font-bold font-mono text-slate-300 mt-1">
                    ${Number(providerOps?.telemetry_summary?.total_provider_cost_usd || 7.24).toFixed(2)}
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1">LLM token consumption</div>
                </div>

                <div className="p-4 rounded-xl bg-[#121218] border border-[#272735]">
                  <div className="text-xs text-slate-400 font-medium">Net Gross Margin</div>
                  <div className="text-2xl font-bold font-mono text-[#10B981] mt-1">
                    {providerOps?.telemetry_summary?.gross_margin_pct || 96.0}%
                  </div>
                  <div className="text-[11px] text-[#10B981] mt-1">Institutional yield positive</div>
                </div>
              </div>

              {/* Global Default Pricing Card */}
              <div className="p-5 rounded-xl bg-[#121218] border border-[#272735]">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="text-sm font-bold text-white flex items-center gap-2">
                      <Settings className="w-4 h-4 text-[#00E5FF]" />
                      Global Default Pricing Architecture
                    </h2>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Base rates applied dynamically to all accounts unless superseded by an individual Customer Pricing Override.
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      setNewGlobalPricing(globalPricing);
                      setActiveModal("GLOBAL_PRICING");
                    }}
                    className="px-3.5 py-1.5 rounded-lg bg-[#00E5FF] hover:bg-[#00c8e0] text-[#0A0A0E] text-xs font-bold transition flex items-center gap-1.5"
                  >
                    Edit Global Defaults
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-3.5 rounded-lg bg-[#181822] border border-[#272735]">
                    <div className="text-[11px] text-slate-400 uppercase font-semibold">
                      AI Market Intelligence Run
                    </div>
                    <div className="text-xl font-bold font-mono text-white mt-1">
                      ${globalPricing.AI_ANALYSIS.toFixed(2)}{" "}
                      <span className="text-xs font-normal text-slate-400">/ run</span>
                    </div>
                    <div className="text-[11px] text-slate-500 mt-1">
                      Deducted per qualifying deep-dive research scan.
                    </div>
                  </div>

                  <div className="p-3.5 rounded-lg bg-[#181822] border border-[#272735]">
                    <div className="text-[11px] text-slate-400 uppercase font-semibold">
                      Strategy Execution Fee
                    </div>
                    <div className="text-xl font-bold font-mono text-white mt-1">
                      ${globalPricing.STRATEGY_EXECUTION.toFixed(2)}{" "}
                      <span className="text-xs font-normal text-slate-400">/ order</span>
                    </div>
                    <div className="text-[11px] text-slate-500 mt-1">
                      Charged per algorithmic spot or grid dispatch.
                    </div>
                  </div>

                  <div className="p-3.5 rounded-lg bg-[#181822] border border-[#272735]">
                    <div className="text-[11px] text-slate-400 uppercase font-semibold">
                      Platform Activation Fee
                    </div>
                    <div className="text-xl font-bold font-mono text-white mt-1">
                      ${globalPricing.PLATFORM_ACTIVATION.toFixed(2)}{" "}
                      <span className="text-xs font-normal text-slate-400">one-time</span>
                    </div>
                    <div className="text-[11px] text-slate-500 mt-1">
                      Initial account provisioning and keys onboarding.
                    </div>
                  </div>
                </div>
              </div>

              {/* Provider Registry (9 Providers) */}
              <div className="rounded-xl bg-[#121218] border border-[#272735] overflow-hidden">
                <div className="p-4 border-b border-[#272735] flex items-center justify-between">
                  <h2 className="text-sm font-bold text-white flex items-center gap-2">
                    <Server className="w-4 h-4 text-[#8B5CF6]" />
                    Integrated AI & Data Provider Registry
                  </h2>
                  <span className="text-xs font-mono text-slate-400">
                    9 Integrated Nodes Active
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="bg-[#181822]/80 border-b border-[#272735] text-[11px] uppercase tracking-wider text-slate-400">
                        <th className="py-2.5 px-4 font-semibold">Provider / Engine</th>
                        <th className="py-2.5 px-3 font-semibold">Category</th>
                        <th className="py-2.5 px-3 font-semibold">Latency</th>
                        <th className="py-2.5 px-3 font-semibold">Circuit Breaker</th>
                        <th className="py-2.5 px-3 font-semibold">Quota / Limits</th>
                        <th className="py-2.5 px-4 font-semibold text-right">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#272735]">
                      {providerOps?.providers?.map((p: any) => (
                        <tr key={p.provider_id} className="hover:bg-[#181822]/40">
                          <td className="py-3 px-4">
                            <div className="font-semibold text-white">{p.name}</div>
                            <div className="text-[10px] font-mono text-slate-500">
                              {p.model_identifier}
                            </div>
                          </td>
                          <td className="py-3 px-3">
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#181822] text-slate-300 border border-[#272735]">
                              {p.category}
                            </span>
                          </td>
                          <td className="py-3 px-3 font-mono text-slate-300">
                            {p.latency_ms}ms
                          </td>
                          <td className="py-3 px-3 font-mono">
                            <span className="text-[#10B981] font-semibold">
                              {p.circuit_breaker_state}
                            </span>
                          </td>
                          <td className="py-3 px-3 text-slate-400 text-[11px]">
                            {p.requests_remaining?.toLocaleString()} reqs left
                          </td>
                          <td className="py-3 px-4 text-right">
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30">
                              ONLINE
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ════════════ MODULE 4: EXCHANGES (TENANT ISOLATED) ════════════ */}
          {activeModule === "EXCHANGES" && (
            <div className="space-y-6">
              <div>
                <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                  Exchange Connections & Cryptographic Gateways
                </h1>
                <p className="text-xs text-slate-400 mt-0.5">
                  Tenant-isolated architecture separating administrator master infrastructure from customer test accounts.
                </p>
              </div>

              {/* Section A: Platform Master Infrastructure */}
              <div className="rounded-xl bg-[#121218] border border-[#8B5CF6]/40 overflow-hidden">
                <div className="p-4 bg-[#8B5CF6]/10 border-b border-[#8B5CF6]/30 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <ShieldAlert className="w-4 h-4 text-[#8B5CF6]" />
                    <span className="text-xs font-bold uppercase tracking-wider text-white">
                      Section A: Platform Master Production Exchange Connections
                    </span>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#8B5CF6]/20 text-[#8B5CF6] border border-[#8B5CF6]/40">
                    RESTRICTED TO PLATFORM INFRASTRUCTURE
                  </span>
                </div>

                <div className="p-3 bg-[#181822]/50 text-xs text-slate-400 border-b border-[#272735]">
                  These master connections provide institutional liquidity routing and price feed verification. They are strictly isolated and never shared with customer tenants.
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="bg-[#181822]/80 border-b border-[#272735] text-[11px] uppercase tracking-wider text-slate-400">
                        <th className="py-2.5 px-4 font-semibold">Account ID</th>
                        <th className="py-2.5 px-3 font-semibold">Exchange</th>
                        <th className="py-2.5 px-3 font-semibold">Environment</th>
                        <th className="py-2.5 px-4 font-semibold">Key Fingerprint</th>
                        <th className="py-2.5 px-4 font-semibold">Verification</th>
                        <th className="py-2.5 px-4 font-semibold text-right">Isolation</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#272735]">
                      {providerOps?.admin_connections?.map((ac: any) => (
                        <tr key={ac.account_id} className="hover:bg-[#181822]/40">
                          <td className="py-3 px-4 font-mono font-semibold text-white">
                            {ac.account_id}
                          </td>
                          <td className="py-3 px-3 font-medium text-slate-200">
                            {ac.exchange_name || ac.provider}
                          </td>
                          <td className="py-3 px-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${
                                ac.environment === "LIVE"
                                  ? "bg-[#F43F5E]/15 text-[#F43F5E] border border-[#F43F5E]/30"
                                  : "bg-[#00E5FF]/15 text-[#00E5FF] border border-[#00E5FF]/30"
                              }`}
                            >
                              {ac.environment}
                            </span>
                          </td>
                          <td className="py-3 px-4 font-mono text-slate-400 text-[11px]">
                            {ac.key_fingerprint || "0x99b...88a"}
                          </td>
                          <td className="py-3 px-4">
                            <span className="inline-flex items-center gap-1 text-[11px] text-[#10B981] font-medium">
                              <CheckCircle2 className="w-3.5 h-3.5" /> VERIFIED
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#8B5CF6]/15 text-[#8B5CF6] border border-[#8B5CF6]/30">
                              SYSTEM ISOLATED
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Section B: Customer Exchange Connections */}
              <div className="rounded-xl bg-[#121218] border border-[#272735] overflow-hidden">
                <div className="p-4 border-b border-[#272735] flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Zap className="w-4 h-4 text-[#00E5FF]" />
                    <span className="text-xs font-bold uppercase tracking-wider text-white">
                      Section B: Customer Exchange Connections
                    </span>
                  </div>
                  <span className="text-xs font-mono text-slate-400">
                    {providerOps?.customer_connections?.length || 0} Registered Customer Keys
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="bg-[#181822]/80 border-b border-[#272735] text-[11px] uppercase tracking-wider text-slate-400">
                        <th className="py-2.5 px-4 font-semibold">Customer</th>
                        <th className="py-2.5 px-3 font-semibold">Account ID</th>
                        <th className="py-2.5 px-3 font-semibold">Exchange</th>
                        <th className="py-2.5 px-3 font-semibold">Mode</th>
                        <th className="py-2.5 px-4 font-semibold">Balance (USDT)</th>
                        <th className="py-2.5 px-4 font-semibold text-right">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#272735]">
                      {providerOps?.customer_connections?.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="text-center py-8 text-slate-500">
                            No customer exchange connections found.
                          </td>
                        </tr>
                      ) : (
                        providerOps?.customer_connections?.map((cc: any) => (
                          <tr key={cc.account_id} className="hover:bg-[#181822]/40">
                            <td className="py-3 px-4">
                              <div className="font-semibold text-white">
                                {cc.customer_mask}
                              </div>
                              <div className="text-[10px] font-mono text-slate-500">
                                {cc.user_id}
                              </div>
                            </td>
                            <td className="py-3 px-3 font-mono text-slate-400">
                              {cc.account_id}
                            </td>
                            <td className="py-3 px-3 font-medium text-slate-300">
                              {cc.exchange_name || cc.provider}
                            </td>
                            <td className="py-3 px-3">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                                  cc.environment === "LIVE"
                                    ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                                    : "bg-blue-500/15 text-blue-400 border border-blue-500/30"
                                }`}
                              >
                                {cc.environment}
                              </span>
                            </td>
                            <td className="py-3 px-4 font-mono font-bold text-white">
                              ${Number(cc.usdt_balance || 0).toFixed(2)}
                            </td>
                            <td className="py-3 px-4 text-right">
                              <span className="inline-flex items-center gap-1 text-[11px] text-[#10B981] font-semibold">
                                <CheckCircle2 className="w-3.5 h-3.5" /> CONNECTED
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

          {/* ════════════ MODULE 5: AUDIT TRAIL ════════════ */}
          {activeModule === "AUDIT" && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                    Cryptographic Audit Trail
                  </h1>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Immutable event log of administrative interventions, price changes, and security events.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <select
                    value={auditActionFilter}
                    onChange={(e) => setAuditActionFilter(e.target.value)}
                    className="bg-[#121218] border border-[#272735] rounded-lg px-3 py-1.5 text-xs text-slate-200 outline-none"
                  >
                    <option value="ALL">All Actions</option>
                    {uniqueAuditActions.map((a) => (
                      <option key={a} value={a}>
                        {a}
                      </option>
                    ))}
                  </select>

                  <button
                    onClick={() => {
                      const csvContent =
                        "data:text/csv;charset=utf-8," +
                        ["log_id,created_at,actor_id,action,target_user_id,details_json"]
                          .concat(
                            filteredAuditLogs.map(
                              (l) =>
                                `"${l.log_id}","${l.created_at}","${l.actor_id}","${l.action}","${l.target_user_id}","${(
                                  l.details_json || ""
                                ).replace(/"/g, '""')}"`
                            )
                          )
                          .join("\n");
                      const encodedUri = encodeURI(csvContent);
                      const link = document.createElement("a");
                      link.setAttribute("href", encodedUri);
                      link.setAttribute("download", `bitdex_audit_${new Date().toISOString()}.csv`);
                      document.body.appendChild(link);
                      link.click();
                      document.body.removeChild(link);
                    }}
                    className="px-3 py-1.5 rounded-lg bg-[#181822] hover:bg-[#272735] text-slate-300 hover:text-white text-xs border border-[#272735] transition flex items-center gap-1.5"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Export CSV
                  </button>
                </div>
              </div>

              <div className="rounded-xl bg-[#121218] border border-[#272735] overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="bg-[#181822]/80 border-b border-[#272735] text-[11px] uppercase tracking-wider text-slate-400">
                        <th className="py-2.5 px-4 font-semibold">Timestamp (UTC)</th>
                        <th className="py-2.5 px-3 font-semibold">Action</th>
                        <th className="py-2.5 px-3 font-semibold">Actor</th>
                        <th className="py-2.5 px-4 font-semibold">Target Customer</th>
                        <th className="py-2.5 px-4 font-semibold">Payload & Details</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#272735]">
                      {filteredAuditLogs.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="text-center py-10 text-slate-500">
                            No audit logs found.
                          </td>
                        </tr>
                      ) : (
                        filteredAuditLogs.map((log) => {
                          const isExpanded = expandedLogId === log.log_id;
                          let parsedDetails: any = null;
                          try {
                            parsedDetails = log.details_json
                              ? JSON.parse(log.details_json)
                              : null;
                          } catch {
                            parsedDetails = log.details_json;
                          }

                          return (
                            <React.Fragment key={log.log_id}>
                              <tr className="hover:bg-[#181822]/40 transition">
                                <td className="py-3 px-4 font-mono text-[11px] text-slate-400 whitespace-nowrap">
                                  {log.created_at}
                                </td>
                                <td className="py-3 px-3">
                                  <span className="font-mono text-[11px] font-semibold text-[#00E5FF]">
                                    {log.action}
                                  </span>
                                </td>
                                <td className="py-3 px-3 font-mono text-[11px] text-slate-400">
                                  {log.actor_id}
                                </td>
                                <td className="py-3 px-4 font-mono text-[11px] text-slate-300">
                                  {log.target_user_id || "-"}
                                </td>
                                <td className="py-3 px-4">
                                  <div className="flex items-center justify-between">
                                    <div className="text-slate-300 truncate max-w-xs font-mono text-[11px]">
                                      {typeof parsedDetails === "object"
                                        ? JSON.stringify(parsedDetails)
                                        : parsedDetails || "-"}
                                    </div>
                                    <button
                                      onClick={() =>
                                        setExpandedLogId(isExpanded ? null : log.log_id)
                                      }
                                      className="ml-2 text-[10px] text-[#00E5FF] hover:underline whitespace-nowrap"
                                    >
                                      {isExpanded ? "Collapse" : "View JSON"}
                                    </button>
                                  </div>
                                </td>
                              </tr>
                              {isExpanded && (
                                <tr className="bg-[#181822]/70">
                                  <td colSpan={5} className="p-4 border-b border-[#272735]">
                                    <pre className="p-3 rounded bg-[#0A0A0E] text-[11px] font-mono text-[#00E5FF] overflow-x-auto border border-[#272735]">
                                      {JSON.stringify(parsedDetails, null, 2)}
                                    </pre>
                                  </td>
                                </tr>
                              )}
                            </React.Fragment>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* ════════════ CUSTOMER 360° SLIDE-OVER INSPECTION DRAWER (760PX) ════════════ */}
      {selectedCustomerId && (
        <div className="fixed inset-0 z-50 overflow-hidden flex justify-end animate-fadeIn">
          {/* Backdrop */}
          <div
            onClick={() => setSelectedCustomerId(null)}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
          />

          {/* Drawer Body (760px) */}
          <div className="relative w-full max-w-[760px] bg-[#121218] border-l border-[#272735] flex flex-col shadow-2xl z-10">
            {/* Drawer Header */}
            <div className="p-5 border-b border-[#272735] bg-[#181822] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-[#0A0A0E] border border-[#272735] flex items-center justify-center font-bold text-base text-[#00E5FF]">
                  {customer360Data?.profile?.email?.[0]?.toUpperCase() || "C"}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-bold text-white">
                      {customer360Data?.profile?.first_name || customer360Data?.profile?.username
                        ? `${customer360Data.profile.first_name || ""} ${customer360Data.profile.last_name || ""}`.trim()
                        : customer360Data?.profile?.email}
                    </h2>
                    {customer360Data?.profile && getStatusBadge(customer360Data.profile.status)}
                  </div>
                  <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mt-0.5">
                    <span>{customer360Data?.profile?.email}</span>
                    <button
                      onClick={() => copyToClipboard(customer360Data?.profile?.user_id, "uid")}
                      className="text-slate-500 hover:text-white flex items-center gap-0.5"
                    >
                      <span>({customer360Data?.profile?.user_id})</span>
                      {copiedText === "uid" ? <Check className="w-3 h-3 text-[#10B981]" /> : <Copy className="w-3 h-3" />}
                    </button>
                  </div>
                </div>
              </div>

              <button
                onClick={() => setSelectedCustomerId(null)}
                className="p-2 rounded-lg hover:bg-[#272735] text-slate-400 hover:text-white transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Tabs */}
            <div className="flex items-center px-5 border-b border-[#272735] bg-[#121218] text-xs">
              <button
                onClick={() => setActive360Tab("OVERVIEW")}
                className={`py-3 px-3 font-medium border-b-2 transition ${
                  active360Tab === "OVERVIEW"
                    ? "border-[#00E5FF] text-[#00E5FF]"
                    : "border-transparent text-slate-400 hover:text-white"
                }`}
              >
                Overview & Controls
              </button>
              <button
                id="tab-pricing-overrides"
                onClick={() => setActive360Tab("PRICING")}
                className={`py-3 px-3 font-medium border-b-2 transition ${
                  active360Tab === "PRICING"
                    ? "border-[#00E5FF] text-[#00E5FF]"
                    : "border-transparent text-slate-400 hover:text-white"
                }`}
              >
                Pricing Overrides
              </button>
              <button
                onClick={() => setActive360Tab("AI_TELEMETRY")}
                className={`py-3 px-3 font-medium border-b-2 transition ${
                  active360Tab === "AI_TELEMETRY"
                    ? "border-[#00E5FF] text-[#00E5FF]"
                    : "border-transparent text-slate-400 hover:text-white"
                }`}
              >
                AI Telemetry & Ledger
              </button>
              <button
                onClick={() => setActive360Tab("CONNECTIONS")}
                className={`py-3 px-3 font-medium border-b-2 transition ${
                  active360Tab === "CONNECTIONS"
                    ? "border-[#00E5FF] text-[#00E5FF]"
                    : "border-transparent text-slate-400 hover:text-white"
                }`}
              >
                Exchange Connections
              </button>
              <button
                onClick={() => setActive360Tab("AUDIT")}
                className={`py-3 px-3 font-medium border-b-2 transition ${
                  active360Tab === "AUDIT"
                    ? "border-[#00E5FF] text-[#00E5FF]"
                    : "border-transparent text-slate-400 hover:text-white"
                }`}
              >
                Audit Trail
              </button>
            </div>

            {/* Drawer Body Content */}
            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {is360Loading ? (
                <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                  <Loader2 className="w-8 h-8 animate-spin text-[#00E5FF] mb-2" />
                  <span className="text-xs">Loading Customer 360° Dossier...</span>
                </div>
              ) : (
                <>
                  {/* TAB 1: OVERVIEW & STATUS CONTROLS */}
                  {active360Tab === "OVERVIEW" && (
                    <div className="space-y-5">
                      {/* Metric cards */}
                      <div className="grid grid-cols-3 gap-3">
                        <div className="p-3.5 rounded-xl bg-[#181822] border border-[#272735]">
                          <div className="text-[11px] text-slate-400">Prepaid Credits</div>
                          <div className="text-lg font-bold font-mono text-[#00E5FF] mt-1">
                            ${Number(customer360Data?.prepaid_credits_usd ?? customer360Data?.balance_usd ?? 0).toFixed(2)} USDT
                          </div>
                        </div>

                        <div className="p-3.5 rounded-xl bg-[#181822] border border-[#272735]">
                          <div className="text-[11px] text-slate-400">AI Intelligence Runs</div>
                          <div className="text-lg font-bold font-mono text-white mt-1">
                            {customer360Data?.ai_usage?.total_runs || 0} Runs
                          </div>
                        </div>

                        <div className="p-3.5 rounded-xl bg-[#181822] border border-[#272735]">
                          <div className="text-[11px] text-slate-400">KYC Verification</div>
                          <div className="mt-1">
                            {getKycBadge(customer360Data?.profile?.kyc_status)}
                          </div>
                        </div>
                      </div>

                      {/* Action Command Matrix */}
                      <div className="p-4 rounded-xl bg-[#181822] border border-[#272735] space-y-3">
                        <div className="text-xs font-bold text-white uppercase tracking-wider">
                          Lifecycle Governance Controls
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                          {customer360Data?.profile?.status === "TEMPORARY_HOLD" ? (
                            <button
                              onClick={() => {
                                setModalReason("");
                                setActiveModal("REACTIVATE");
                              }}
                              className="px-3 py-2 rounded-lg bg-[#10B981]/15 hover:bg-[#10B981]/25 text-[#10B981] border border-[#10B981]/30 text-xs font-semibold flex items-center justify-center gap-1.5 transition"
                            >
                              <PlayCircle className="w-4 h-4" />
                              Reactivate Account
                            </button>
                          ) : (
                            <button
                              onClick={() => {
                                setModalReason("");
                                setActiveModal("HOLD");
                              }}
                              className="px-3 py-2 rounded-lg bg-[#F59E0B]/15 hover:bg-[#F59E0B]/25 text-[#F59E0B] border border-[#F59E0B]/30 text-xs font-semibold flex items-center justify-center gap-1.5 transition"
                            >
                              <PauseCircle className="w-4 h-4" />
                              Temporary Hold
                            </button>
                          )}

                          {customer360Data?.profile?.status === "BLOCKED" ? (
                            <button
                              onClick={() => {
                                setModalReason("");
                                setActiveModal("REACTIVATE");
                              }}
                              className="px-3 py-2 rounded-lg bg-[#10B981]/15 hover:bg-[#10B981]/25 text-[#10B981] border border-[#10B981]/30 text-xs font-semibold flex items-center justify-center gap-1.5 transition"
                            >
                              <PlayCircle className="w-4 h-4" />
                              Unblock Account
                            </button>
                          ) : (
                            <button
                              onClick={() => {
                                setModalReason("");
                                setActiveModal("BLOCK");
                              }}
                              className="px-3 py-2 rounded-lg bg-[#F43F5E]/15 hover:bg-[#F43F5E]/25 text-[#F43F5E] border border-[#F43F5E]/30 text-xs font-semibold flex items-center justify-center gap-1.5 transition"
                            >
                              <ShieldAlert className="w-4 h-4" />
                              Block Account
                            </button>
                          )}

                          <button
                            onClick={() => {
                              setModalReason("");
                              setActiveModal("KYC");
                            }}
                            className="px-3 py-2 rounded-lg bg-[#121218] hover:bg-[#272735] text-slate-200 border border-[#272735] text-xs font-medium flex items-center justify-center gap-1.5 transition"
                          >
                            <FileText className="w-4 h-4 text-[#00E5FF]" />
                            Request KYC Docs
                          </button>

                          <button
                            onClick={() => {
                              setEmailSubject("BITDEX Institutional Account Security Notice");
                              setEmailBody("");
                              setActiveModal("EMAIL");
                            }}
                            className="px-3 py-2 rounded-lg bg-[#121218] hover:bg-[#272735] text-slate-200 border border-[#272735] text-xs font-medium flex items-center justify-center gap-1.5 transition"
                          >
                            <Mail className="w-4 h-4 text-[#8B5CF6]" />
                            Send Branded Email
                          </button>

                          <button
                            onClick={() => {
                              setModalReason("");
                              setCreditReferenceId("");
                              const cur = customer360Data?.prepaid_credits_usd ?? customer360Data?.balance_usd ?? 0;
                              setOverrideCreditsAmount(Number(cur).toFixed(2));
                              setActiveModal("CREDIT_OVERRIDE");
                            }}
                            className="px-3 py-2 rounded-lg bg-[#121218] hover:bg-[#272735] text-slate-200 border border-[#272735] text-xs font-medium flex items-center justify-center gap-1.5 transition"
                          >
                            <DollarSign className="w-4 h-4 text-[#10B981]" />
                            Override Credits
                          </button>

                          <button
                            onClick={() => {
                              setModalReason("");
                              setModalConfirm(false);
                              setActiveModal("DELETE");
                            }}
                            className="px-3 py-2 rounded-lg bg-[#F43F5E]/10 hover:bg-[#F43F5E]/20 text-[#F43F5E] border border-[#F43F5E]/20 text-xs font-medium flex items-center justify-center gap-1.5 transition sm:col-span-2"
                          >
                            <Trash2 className="w-4 h-4" />
                            Permanently Delete Customer
                          </button>
                        </div>
                      </div>

                      {/* Outgoing Emails History */}
                      <div className="rounded-xl bg-[#181822] border border-[#272735] overflow-hidden">
                        <div className="p-3 border-b border-[#272735] text-xs font-bold text-white flex items-center justify-between">
                          <span>Communication & Email Dispatch History</span>
                          <span className="font-mono text-slate-400 text-[10px]">
                            {customer360Data?.emails_sent?.length || 0} Sent
                          </span>
                        </div>
                        <div className="divide-y divide-[#272735] max-h-48 overflow-y-auto">
                          {customer360Data?.emails_sent?.length === 0 ? (
                            <div className="p-4 text-center text-xs text-slate-500">
                              No previous administrative emails dispatched.
                            </div>
                          ) : (
                            customer360Data?.emails_sent?.map((em: any) => (
                              <div key={em.dispatch_id} className="p-3 text-xs flex items-center justify-between">
                                <div>
                                  <div className="font-semibold text-white">{em.email_type}</div>
                                  <div className="text-[10px] font-mono text-slate-400">{em.created_at}</div>
                                </div>
                                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-[#10B981]/15 text-[#10B981]">
                                  {em.status}
                                </span>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* TAB 2: PRICING OVERRIDES */}
                  {active360Tab === "PRICING" && (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                            Customer-Specific Pricing Overrides
                          </h3>
                          <p className="text-[11px] text-slate-400 mt-0.5">
                            Overrides supersede global defaults specifically for this tenant.
                          </p>
                        </div>
                        <button
                          id="set-new-override-btn"
                          onClick={() => {
                            setOverrideService("AI_ANALYSIS");
                            const currentRate = customer360Data?.pricing?.AI_ANALYSIS?.price_usd;
                            setOverridePrice(
                              currentRate !== undefined && currentRate !== null ? String(currentRate) : "1.00"
                            );
                            setModalReason("");
                            setModalConfirm(false);
                            setActiveModal("PRICING_OVERRIDE");
                          }}
                          className="px-3 py-1.5 rounded-lg bg-[#00E5FF] hover:bg-[#00c8e0] text-[#0A0A0E] text-xs font-bold transition flex items-center gap-1"
                        >
                          <Plus className="w-3.5 h-3.5" />
                          Set New Override
                        </button>
                      </div>

                      {/* Current Effective Rates */}
                      <div className="grid grid-cols-3 gap-3">
                        {customer360Data?.pricing &&
                          Object.entries(customer360Data.pricing).map(([sid, p]: [string, any]) => (
                            <div
                              key={sid}
                              className="p-3.5 rounded-xl bg-[#181822] border border-[#272735]"
                            >
                              <div className="text-[10px] font-semibold text-slate-400 uppercase">
                                {p.name}
                              </div>
                              <div className="text-lg font-bold font-mono text-white mt-1">
                                ${p.price_usd.toFixed(2)}
                              </div>
                              <div className="mt-1 flex items-center justify-between">
                                <span
                                  className={`text-[10px] font-semibold ${
                                    p.source === "OVERRIDE" ? "text-[#8B5CF6]" : "text-slate-500"
                                  }`}
                                >
                                  {p.source === "OVERRIDE" ? "● Custom Override" : "○ Global Default"}
                                </span>
                                <div className="flex items-center gap-2">
                                  <button
                                    id={`override-rate-btn-${sid}`}
                                    onClick={() => {
                                      setOverrideService(sid);
                                      setOverridePrice(String(p.price_usd));
                                      setModalReason("");
                                      setModalConfirm(false);
                                      setActiveModal("PRICING_OVERRIDE");
                                    }}
                                    className="text-[10px] text-[#00E5FF] hover:underline font-semibold"
                                  >
                                    {p.source === "OVERRIDE" ? "Edit Rate" : "Override"}
                                  </button>
                                  {p.source === "OVERRIDE" && (
                                    <button
                                      id={`revoke-rate-btn-${sid}`}
                                      onClick={() => handleRevokeOverride(sid)}
                                      className="text-[10px] text-[#F43F5E] hover:underline"
                                    >
                                      Revoke
                                    </button>
                                  )}
                                </div>
                              </div>
                            </div>
                          ))}
                      </div>

                      {/* Overrides Log for this customer */}
                      <div className="rounded-xl bg-[#181822] border border-[#272735] overflow-hidden">
                        <div className="p-3 border-b border-[#272735] text-xs font-bold text-white">
                          Override Change Audit History
                        </div>
                        <div className="divide-y divide-[#272735] max-h-48 overflow-y-auto">
                          {customer360Data?.overrides?.length === 0 ? (
                            <div className="p-4 text-center text-xs text-slate-500">
                              No custom override history recorded.
                            </div>
                          ) : (
                            customer360Data?.overrides?.map((ov: any) => (
                              <div key={ov.override_id} className="p-3 text-xs flex items-center justify-between">
                                <div>
                                  <div className="font-semibold text-white">
                                    {ov.service_id}: ${Number(ov.price_usd).toFixed(2)} ({ov.status})
                                  </div>
                                  <div className="text-[10px] text-slate-400 mt-0.5">
                                    Reason: {ov.reason} &bull; Set by: {ov.created_by}
                                  </div>
                                </div>
                                <div className="text-[10px] font-mono text-slate-500">
                                  {ov.created_at}
                                </div>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* TAB 3: AI TELEMETRY & RUNS */}
                  {active360Tab === "AI_TELEMETRY" && (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div className="p-3 rounded-lg bg-[#181822] border border-[#272735]">
                          <div className="text-[10px] text-slate-400">Total Runs</div>
                          <div className="text-base font-bold font-mono text-white mt-1">
                            {customer360Data?.ai_usage?.total_runs || 0}
                          </div>
                        </div>
                        <div className="p-3 rounded-lg bg-[#181822] border border-[#272735]">
                          <div className="text-[10px] text-slate-400">Completed</div>
                          <div className="text-base font-bold font-mono text-[#10B981] mt-1">
                            {customer360Data?.ai_usage?.completed_runs || 0}
                          </div>
                        </div>
                        <div className="p-3 rounded-lg bg-[#181822] border border-[#272735]">
                          <div className="text-[10px] text-slate-400">Failed / Refunded</div>
                          <div className="text-base font-bold font-mono text-[#F43F5E] mt-1">
                            {customer360Data?.ai_usage?.failed_runs || 0}
                          </div>
                        </div>
                        <div className="p-3 rounded-lg bg-[#181822] border border-[#272735]">
                          <div className="text-[10px] text-slate-400">Gross Spent</div>
                          <div className="text-base font-bold font-mono text-[#00E5FF] mt-1">
                            ${Number(customer360Data?.ai_usage?.total_revenue_usd || 0).toFixed(2)}
                          </div>
                        </div>
                      </div>

                      <div className="rounded-xl bg-[#181822] border border-[#272735] overflow-hidden">
                        <div className="p-3 border-b border-[#272735] text-xs font-bold text-white">
                          Recent Analysis Executions
                        </div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs">
                            <thead>
                              <tr className="bg-[#121218] border-b border-[#272735] text-[10px] uppercase text-slate-400">
                                <th className="py-2 px-3">Run ID</th>
                                <th className="py-2 px-3">Symbol</th>
                                <th className="py-2 px-3">Timeframe</th>
                                <th className="py-2 px-3">Status</th>
                                <th className="py-2 px-3 text-right">Charged</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-[#272735]">
                              {customer360Data?.ai_usage?.recent_runs?.length === 0 ? (
                                <tr>
                                  <td colSpan={5} className="p-4 text-center text-slate-500">
                                    No AI runs executed yet.
                                  </td>
                                </tr>
                              ) : (
                                customer360Data?.ai_usage?.recent_runs?.map((r: any) => (
                                  <tr key={r.run_id} className="hover:bg-[#121218]/40">
                                    <td className="py-2 px-3 font-mono text-[11px] text-slate-400">
                                      {r.run_id}
                                    </td>
                                    <td className="py-2 px-3 font-semibold text-white">
                                      {r.symbol}
                                    </td>
                                    <td className="py-2 px-3 text-slate-400">{r.timeframe}</td>
                                    <td className="py-2 px-3">
                                      <span
                                        className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                                          r.status === "COMPLETED"
                                            ? "bg-[#10B981]/15 text-[#10B981]"
                                            : "bg-[#F43F5E]/15 text-[#F43F5E]"
                                        }`}
                                      >
                                        {r.status}
                                      </span>
                                    </td>
                                    <td className="py-2 px-3 text-right font-mono text-white">
                                      ${Number(r.customer_price_usd || 0).toFixed(2)}
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

                  {/* TAB 4: EXCHANGE CONNECTIONS */}
                  {active360Tab === "CONNECTIONS" && (
                    <div className="space-y-4">
                      <div className="text-xs font-bold text-white uppercase tracking-wider">
                        Customer-Bound Exchange API Keys
                      </div>

                      {customer360Data?.connections?.length === 0 ? (
                        <div className="p-8 text-center text-xs text-slate-500 bg-[#181822] rounded-xl border border-[#272735]">
                          Customer has not linked any exchange API credentials yet.
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {customer360Data?.connections?.map((c: any) => (
                            <div
                              key={c.connection_id}
                              className="p-4 rounded-xl bg-[#181822] border border-[#272735] flex items-center justify-between text-xs"
                            >
                              <div>
                                <div className="font-bold text-white flex items-center gap-2">
                                  <span>{c.exchange_id?.toUpperCase()}</span>
                                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#121218] text-slate-300 border border-[#272735]">
                                    {c.environment}
                                  </span>
                                </div>
                                <div className="font-mono text-slate-400 text-[11px] mt-1">
                                  Fingerprint: {c.api_key_masked || "0x9***"}
                                </div>
                              </div>
                              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#10B981]/15 text-[#10B981]">
                                {c.status}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* TAB 5: AUDIT TRAIL */}
                  {active360Tab === "AUDIT" && (
                    <div className="space-y-3">
                      <div className="text-xs font-bold text-white uppercase tracking-wider">
                        Customer Audit Event Log
                      </div>
                      <div className="divide-y divide-[#272735] rounded-xl bg-[#181822] border border-[#272735] overflow-hidden">
                        {customer360Data?.recent_audit?.length === 0 ? (
                          <div className="p-4 text-center text-xs text-slate-500">
                            No audit events logged for this customer.
                          </div>
                        ) : (
                          customer360Data?.recent_audit?.map((a: any) => (
                            <div key={a.log_id} className="p-3 text-xs">
                              <div className="flex items-center justify-between mb-1">
                                <span className="font-mono font-semibold text-[#00E5FF]">
                                  {a.action}
                                </span>
                                <span className="font-mono text-[10px] text-slate-400">
                                  {a.created_at}
                                </span>
                              </div>
                              <div className="text-[11px] text-slate-300 font-mono bg-[#121218] p-2 rounded border border-[#272735] overflow-x-auto">
                                {a.details_json}
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ════════════ ACTION MODALS ════════════ */}

      {/* 1. HOLD MODAL */}
      {activeModal === "HOLD" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md rounded-xl bg-[#121218] border border-[#272735] p-5 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-[#F59E0B]">
              <PauseCircle className="w-6 h-6" />
              <h3 className="font-bold text-base text-white">Place Temporary Hold</h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Placing a temporary hold pauses trading execution and AI analysis while preserving account data. The customer is automatically notified.
            </p>
            <div>
              <label className="text-[11px] font-semibold text-slate-400 uppercase">
                Reason for Temporary Hold (Required)
              </label>
              <textarea
                value={modalReason}
                onChange={(e) => setModalReason(e.target.value)}
                placeholder="e.g. Compliance review of unusual IP geolocation shift..."
                rows={3}
                className="w-full mt-1.5 bg-[#181822] border border-[#272735] rounded-lg p-2.5 text-xs text-white placeholder-slate-500 outline-none focus:border-[#F59E0B]"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setActiveModal(null)}
                className="px-3 py-1.5 rounded-lg bg-[#181822] hover:bg-[#272735] text-xs text-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={handleHold}
                disabled={isActionLoading || modalReason.trim().length < 3}
                className="px-4 py-1.5 rounded-lg bg-[#F59E0B] hover:bg-[#e08e08] text-[#0A0A0E] font-bold text-xs transition"
              >
                {isActionLoading ? "Processing..." : "Confirm Temporary Hold"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 2. BLOCK MODAL */}
      {activeModal === "BLOCK" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md rounded-xl bg-[#121218] border border-[#F43F5E]/30 p-5 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-[#F43F5E]">
              <ShieldAlert className="w-6 h-6" />
              <h3 className="font-bold text-base text-white">Permanent Block</h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Blocking immediately revokes all active session tokens, locks API credentials, and denies all future login attempts.
            </p>
            <div>
              <label className="text-[11px] font-semibold text-slate-400 uppercase">
                Reason for Administrative Block (Required)
              </label>
              <textarea
                value={modalReason}
                onChange={(e) => setModalReason(e.target.value)}
                placeholder="e.g. Terms of Service violation / fraudulent activity..."
                rows={3}
                className="w-full mt-1.5 bg-[#181822] border border-[#272735] rounded-lg p-2.5 text-xs text-white placeholder-slate-500 outline-none focus:border-[#F43F5E]"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setActiveModal(null)}
                className="px-3 py-1.5 rounded-lg bg-[#181822] hover:bg-[#272735] text-xs text-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={handleBlock}
                disabled={isActionLoading || modalReason.trim().length < 3}
                className="px-4 py-1.5 rounded-lg bg-[#F43F5E] hover:bg-[#d9324e] text-white font-bold text-xs transition"
              >
                {isActionLoading ? "Processing..." : "Confirm Block & Revoke"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 3. REACTIVATE MODAL */}
      {activeModal === "REACTIVATE" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md rounded-xl bg-[#121218] border border-[#10B981]/30 p-5 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-[#10B981]">
              <PlayCircle className="w-6 h-6" />
              <h3 className="font-bold text-base text-white">Reactivate Customer Account</h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Reactivation restores all normal institutional trading and AI analysis capabilities.
            </p>
            <div>
              <label className="text-[11px] font-semibold text-slate-400 uppercase">
                Reason for Reactivation (Required)
              </label>
              <textarea
                value={modalReason}
                onChange={(e) => setModalReason(e.target.value)}
                placeholder="e.g. Compliance review passed successfully..."
                rows={3}
                className="w-full mt-1.5 bg-[#181822] border border-[#272735] rounded-lg p-2.5 text-xs text-white placeholder-slate-500 outline-none focus:border-[#10B981]"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setActiveModal(null)}
                className="px-3 py-1.5 rounded-lg bg-[#181822] hover:bg-[#272735] text-xs text-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={handleReactivate}
                disabled={isActionLoading || modalReason.trim().length < 3}
                className="px-4 py-1.5 rounded-lg bg-[#10B981] hover:bg-[#0da070] text-[#0A0A0E] font-bold text-xs transition"
              >
                {isActionLoading ? "Processing..." : "Reactivate Account"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 4. PERMANENT DELETE MODAL */}
      {activeModal === "DELETE" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md rounded-xl bg-[#121218] border border-[#F43F5E] p-5 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-[#F43F5E]">
              <Trash2 className="w-6 h-6" />
              <h3 className="font-bold text-base text-white">Permanently Delete Customer</h3>
            </div>
            <div className="p-3 rounded-lg bg-[#F43F5E]/10 border border-[#F43F5E]/30 text-xs text-[#F43F5E]">
              <strong>Warning:</strong> This permanently zeroes balances, wipes exchange API keys, revokes all sessions, and frees the email address for new registration.
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-400 uppercase">
                Reason for Permanent Deletion (Required)
              </label>
              <textarea
                value={modalReason}
                onChange={(e) => setModalReason(e.target.value)}
                placeholder="e.g. Customer requested GDPR right to be forgotten..."
                rows={3}
                className="w-full mt-1.5 bg-[#181822] border border-[#272735] rounded-lg p-2.5 text-xs text-white placeholder-slate-500 outline-none focus:border-[#F43F5E]"
              />
            </div>
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={modalConfirm}
                onChange={(e) => setModalConfirm(e.target.checked)}
                className="rounded bg-[#181822] border-[#272735] text-[#F43F5E]"
              />
              <span>I understand this action is completely irreversible.</span>
            </label>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setActiveModal(null)}
                className="px-3 py-1.5 rounded-lg bg-[#181822] hover:bg-[#272735] text-xs text-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={isActionLoading || modalReason.trim().length < 3 || !modalConfirm}
                className="px-4 py-1.5 rounded-lg bg-[#F43F5E] hover:bg-[#d9324e] text-white font-bold text-xs transition disabled:opacity-50"
              >
                {isActionLoading ? "Deleting..." : "Permanently Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. REQUEST KYC MODAL */}
      {activeModal === "KYC" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md rounded-xl bg-[#121218] border border-[#272735] p-5 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-[#00E5FF]">
              <FileText className="w-6 h-6" />
              <h3 className="font-bold text-base text-white">Request KYC Documentation</h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Select the compliance documents required from this client. An institutional request notice will be dispatched via email.
            </p>
            <div className="space-y-2">
              <label className="text-[11px] font-semibold text-slate-400 uppercase">
                Required Documents
              </label>
              {[
                { id: "GOVERNMENT_ID", label: "Government-Issued Passport / National ID" },
                { id: "PROOF_OF_ADDRESS", label: "Proof of Address (Utility Bill / Bank Statement)" },
                { id: "SOURCE_OF_FUNDS", label: "Source of Wealth / Proof of Funds Declaration" },
                { id: "CORPORATE_REGISTRATION", label: "Corporate Articles & Certificate of Incumbency" },
              ].map((doc) => (
                <label
                  key={doc.id}
                  className="flex items-center gap-2 p-2 rounded bg-[#181822] text-xs text-slate-200 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selectedKycDocs.includes(doc.id)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedKycDocs([...selectedKycDocs, doc.id]);
                      } else {
                        setSelectedKycDocs(selectedKycDocs.filter((x) => x !== doc.id));
                      }
                    }}
                    className="rounded bg-[#121218] border-[#272735] text-[#00E5FF]"
                  />
                  <span>{doc.label}</span>
                </label>
              ))}
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-400 uppercase">
                Custom Instructions Note
              </label>
              <textarea
                value={modalReason}
                onChange={(e) => setModalReason(e.target.value)}
                placeholder="Specific instructions or submission deadline..."
                rows={2}
                className="w-full mt-1 bg-[#181822] border border-[#272735] rounded-lg p-2 text-xs text-white placeholder-slate-500 outline-none focus:border-[#00E5FF]"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setActiveModal(null)}
                className="px-3 py-1.5 rounded-lg bg-[#181822] hover:bg-[#272735] text-xs text-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={handleRequestKyc}
                disabled={isActionLoading || selectedKycDocs.length === 0}
                className="px-4 py-1.5 rounded-lg bg-[#00E5FF] hover:bg-[#00c8e0] text-[#0A0A0E] font-bold text-xs transition"
              >
                {isActionLoading ? "Dispatching..." : "Dispatch KYC Request"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 6. SEND BRANDED EMAIL MODAL */}
      {activeModal === "EMAIL" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-lg rounded-xl bg-[#121218] border border-[#272735] p-5 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-[#8B5CF6]">
              <Mail className="w-6 h-6" />
              <h3 className="font-bold text-base text-white">Send Branded Institutional Email</h3>
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-400 uppercase">
                Subject Line
              </label>
              <input
                type="text"
                value={emailSubject}
                onChange={(e) => setEmailSubject(e.target.value)}
                className="w-full mt-1 bg-[#181822] border border-[#272735] rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-[#8B5CF6]"
              />
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-400 uppercase">
                Message Body (HTML supported)
              </label>
              <textarea
                value={emailBody}
                onChange={(e) => setEmailBody(e.target.value)}
                rows={6}
                placeholder="<p>Dear Customer,</p><p>Please note that your institutional API credentials require rotation...</p>"
                className="w-full mt-1 bg-[#181822] border border-[#272735] rounded-lg p-3 text-xs text-white placeholder-slate-500 font-mono outline-none focus:border-[#8B5CF6]"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setActiveModal(null)}
                className="px-3 py-1.5 rounded-lg bg-[#181822] hover:bg-[#272735] text-xs text-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={handleSendEmail}
                disabled={isActionLoading || !emailSubject.trim() || !emailBody.trim()}
                className="px-4 py-1.5 rounded-lg bg-[#8B5CF6] hover:bg-[#7c4ee0] text-white font-bold text-xs transition"
              >
                {isActionLoading ? "Sending..." : "Send Institutional Email"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 7. SET PRICING OVERRIDE MODAL */}
      {activeModal === "PRICING_OVERRIDE" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md rounded-xl bg-[#121218] border border-[#272735] p-5 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-[#00E5FF]">
              <DollarSign className="w-6 h-6" />
              <h3 className="font-bold text-base text-white">Set Customer Pricing Override</h3>
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-400 uppercase">Service</label>
              <select
                id="pricing-override-service-select"
                value={overrideService}
                onChange={(e) => {
                  const nextService = e.target.value;
                  setOverrideService(nextService);
                  setModalConfirm(false);
                  const currentRate = customer360Data?.pricing?.[nextService]?.price_usd;
                  if (currentRate !== undefined && currentRate !== null) {
                    setOverridePrice(String(currentRate));
                  }
                }}
                className="w-full mt-1 bg-[#181822] border border-[#272735] rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-[#00E5FF]"
              >
                <option value="AI_ANALYSIS">AI Market Intelligence Analysis</option>
                <option value="STRATEGY_EXECUTION">Strategy Execution Fee</option>
                <option value="PLATFORM_ACTIVATION">Platform Activation Fee</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-400 uppercase">
                New Price ($ USD)
              </label>
              <input
                id="pricing-override-price-input"
                type="text"
                inputMode="decimal"
                value={overridePrice}
                onChange={(e) => {
                  setOverridePrice(e.target.value);
                  setModalConfirm(false);
                }}
                placeholder="0.00"
                className="w-full mt-1 bg-[#181822] border border-[#272735] rounded-lg px-3 py-2 text-xs font-mono text-white outline-none focus:border-[#00E5FF]"
              />
              <p className="text-[10px] text-slate-500 mt-1">Enter 0 for free service, or any positive decimal rate.</p>
            </div>
            <div>
              <div className="flex items-center justify-between">
                <label className="text-[11px] font-semibold text-slate-400 uppercase">
                  Reason for Override (Required)
                </label>
                <span className={`text-[10px] font-mono ${modalReason.trim().length >= 3 ? "text-emerald-400" : "text-amber-400"}`}>
                  {modalReason.trim().length}/3 min chars
                </span>
              </div>
              <textarea
                id="pricing-override-reason-input"
                value={modalReason}
                onChange={(e) => setModalReason(e.target.value)}
                placeholder="e.g. Approved promotional zero-fee rate..."
                rows={2}
                className="w-full mt-1 bg-[#181822] border border-[#272735] rounded-lg p-2 text-xs text-white placeholder-slate-500 outline-none focus:border-[#00E5FF]"
              />
              {modalReason.trim().length === 0 ? (
                <p className="text-[10px] text-amber-400 mt-1 flex items-center gap-1 font-medium">
                  ⚠️ Audit reason required to enable the Apply Override button.
                </p>
              ) : modalReason.trim().length < 3 ? (
                <p className="text-[10px] text-[#F43F5E] mt-1">
                  Reason must be at least 3 characters.
                </p>
              ) : (
                <p className="text-[10px] text-emerald-400 mt-1">
                  ✓ Valid audit reason entered. Button enabled.
                </p>
              )}
            </div>
            {modalConfirm && (
              <div className="p-2.5 rounded bg-[#F59E0B]/10 border border-[#F59E0B]/30 text-xs text-[#F59E0B] flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span>This is a material price change (&gt;25%). Click &quot;Confirm &amp; Apply&quot; to apply this rate.</span>
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                id="pricing-override-cancel-btn"
                onClick={() => {
                  setActiveModal(null);
                  setModalConfirm(false);
                }}
                className="px-3 py-1.5 rounded-lg bg-[#181822] hover:bg-[#272735] text-xs text-slate-300 transition"
              >
                Cancel
              </button>
              <button
                type="button"
                id="pricing-override-apply-btn"
                onClick={handleSetPricingOverride}
                disabled={isActionLoading || modalReason.trim().length < 3}
                className={`px-4 py-1.5 rounded-lg font-bold text-xs transition disabled:opacity-40 disabled:cursor-not-allowed ${
                  modalConfirm
                    ? "bg-[#F59E0B] hover:bg-[#d97706] text-black shadow-lg shadow-[#F59E0B]/20"
                    : "bg-[#00E5FF] hover:bg-[#00c8e0] text-[#0A0A0E] shadow-lg shadow-[#00E5FF]/20"
                }`}
              >
                {isActionLoading
                  ? "Saving..."
                  : modalConfirm
                  ? "Confirm & Apply"
                  : modalReason.trim().length < 3
                  ? "Apply Override (Reason Required)"
                  : "Apply Override"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 9. CREDIT OVERRIDE MODAL */}
      {activeModal === "CREDIT_OVERRIDE" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md rounded-xl bg-[#121218] border border-[#272735] p-5 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-[#10B981]">
              <DollarSign className="w-6 h-6" />
              <h3 className="font-bold text-base text-white">Override Customer Prepaid Credits</h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Set an absolute balance for customer <span className="font-mono text-[#00E5FF]">{selectedCustomerId}</span>. All changes are recorded in the immutable audit trail and billing ledger.
            </p>

            <div className="space-y-3">
              <div>
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-semibold text-slate-400 uppercase">
                    Target Balance (USDT)
                  </label>
                  <button
                    type="button"
                    onClick={() => setOverrideCreditsAmount("0.00")}
                    className="text-[10px] text-[#F43F5E] hover:underline font-semibold"
                  >
                    Reset to $0.00
                  </button>
                </div>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={overrideCreditsAmount}
                  onChange={(e) => setOverrideCreditsAmount(e.target.value)}
                  className="w-full mt-1 bg-[#181822] border border-[#272735] rounded-lg px-3 py-2 text-xs font-mono text-white outline-none focus:border-[#10B981]"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold text-slate-400 uppercase">
                  Audit Reason (Minimum 3 characters)
                </label>
                <textarea
                  value={modalReason}
                  onChange={(e) => setModalReason(e.target.value)}
                  placeholder="e.g. Account balance reconciliation / administrative adjustment..."
                  rows={2}
                  className="w-full mt-1 bg-[#181822] border border-[#272735] rounded-lg p-2 text-xs text-white placeholder-slate-500 outline-none focus:border-[#10B981]"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold text-slate-400 uppercase">
                  Reference Ticket / ID (Optional)
                </label>
                <input
                  type="text"
                  value={creditReferenceId}
                  onChange={(e) => setCreditReferenceId(e.target.value)}
                  placeholder="e.g. TICKET-9821 or REF-001"
                  className="w-full mt-1 bg-[#181822] border border-[#272735] rounded-lg px-3 py-2 text-xs font-mono text-white outline-none focus:border-[#10B981]"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => {
                  setActiveModal(null);
                  setModalReason("");
                  setCreditReferenceId("");
                }}
                className="px-3 py-1.5 rounded-lg bg-[#181822] hover:bg-[#272735] text-xs text-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={handleCreditOverride}
                disabled={isActionLoading || modalReason.trim().length < 3}
                className="px-4 py-1.5 rounded-lg bg-[#10B981] hover:bg-[#0ea572] text-[#0A0A0E] font-bold text-xs transition"
              >
                {isActionLoading ? "Updating..." : "Confirm Override"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 8. GLOBAL PRICING MODAL */}
      {activeModal === "GLOBAL_PRICING" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md rounded-xl bg-[#121218] border border-[#272735] p-5 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-[#00E5FF]">
              <Settings className="w-6 h-6" />
              <h3 className="font-bold text-base text-white">Adjust Global Default Pricing</h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Modifying global defaults affects every customer account that does not have an active individual override.
            </p>
            <div className="space-y-3">
              <div>
                <label className="text-[11px] font-semibold text-slate-400 uppercase">
                  AI Analysis Fee ($ USD)
                </label>
                <input
                  type="number"
                  step="0.05"
                  value={newGlobalPricing.AI_ANALYSIS}
                  onChange={(e) =>
                    setNewGlobalPricing({
                      ...newGlobalPricing,
                      AI_ANALYSIS: parseFloat(e.target.value) || 0,
                    })
                  }
                  className="w-full mt-1 bg-[#181822] border border-[#272735] rounded-lg px-3 py-2 text-xs font-mono text-white outline-none focus:border-[#00E5FF]"
                />
              </div>
              <div>
                <label className="text-[11px] font-semibold text-slate-400 uppercase">
                  Strategy Execution Fee ($ USD)
                </label>
                <input
                  type="number"
                  step="0.05"
                  value={newGlobalPricing.STRATEGY_EXECUTION}
                  onChange={(e) =>
                    setNewGlobalPricing({
                      ...newGlobalPricing,
                      STRATEGY_EXECUTION: parseFloat(e.target.value) || 0,
                    })
                  }
                  className="w-full mt-1 bg-[#181822] border border-[#272735] rounded-lg px-3 py-2 text-xs font-mono text-white outline-none focus:border-[#00E5FF]"
                />
              </div>
              <div>
                <label className="text-[11px] font-semibold text-slate-400 uppercase">
                  Platform Activation Fee ($ USD)
                </label>
                <input
                  type="number"
                  step="1.0"
                  value={newGlobalPricing.PLATFORM_ACTIVATION}
                  onChange={(e) =>
                    setNewGlobalPricing({
                      ...newGlobalPricing,
                      PLATFORM_ACTIVATION: parseFloat(e.target.value) || 0,
                    })
                  }
                  className="w-full mt-1 bg-[#181822] border border-[#272735] rounded-lg px-3 py-2 text-xs font-mono text-white outline-none focus:border-[#00E5FF]"
                />
              </div>
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-400 uppercase">
                Reason for Adjustment (Required)
              </label>
              <textarea
                value={modalReason}
                onChange={(e) => setModalReason(e.target.value)}
                placeholder="e.g. Quarterly price schedule update..."
                rows={2}
                className="w-full mt-1 bg-[#181822] border border-[#272735] rounded-lg p-2 text-xs text-white placeholder-slate-500 outline-none focus:border-[#00E5FF]"
              />
            </div>
            {modalConfirm && (
              <div className="p-2.5 rounded bg-[#F59E0B]/10 border border-[#F59E0B]/30 text-xs text-[#F59E0B]">
                This updates global defaults across the entire platform. Confirm to proceed.
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setActiveModal(null)}
                className="px-3 py-1.5 rounded-lg bg-[#181822] hover:bg-[#272735] text-xs text-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={handleUpdateGlobalPricing}
                disabled={isActionLoading || modalReason.trim().length < 3}
                className="px-4 py-1.5 rounded-lg bg-[#00E5FF] hover:bg-[#00c8e0] text-[#0A0A0E] font-bold text-xs transition"
              >
                {isActionLoading ? "Updating..." : modalConfirm ? "Confirm & Update" : "Update Global Pricing"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
