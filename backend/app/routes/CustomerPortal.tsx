"use client";

import React, { useState, useEffect } from "react";
import Image from "next/image";
import {
  ChevronDown,
  Edit3,
  Mail,
  ShieldCheck,
  ShieldAlert,
  Zap,
  TrendingUp,
  CreditCard,
  QrCode,
  Lock,
  Key,
  LogOut,
  User,
  Plus,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  RefreshCw,
  ExternalLink,
  Wallet,
  FileText,
  DollarSign,
  Activity,
  Layers,
  ChevronRight,
  LifeBuoy,
  MessageSquare,
  Send,
  HelpCircle,
  X,
  Clock,
  ArrowRight,
  Info,
} from "lucide-react";
import BinancePayModal from "./BinancePayModal";

interface CustomerPortalProps {
  token: string;
  user: any;
  onSignOut: () => void;
  children?: React.ReactNode; // Trading Console / Signals
}

export default function CustomerPortal({ token, user, onSignOut, children }: CustomerPortalProps) {
  const [activeTab, setActiveTab] = useState<"TRADING" | "CONNECTIONS" | "BILLING" | "SECURITY" | "SUPPORT" | "PROFIT_LOSS">("TRADING");
  const [profile, setProfile] = useState<any>(user);
  const [billingSummary, setBillingSummary] = useState<any>({
    prepaid_credits_usd: 0.0,
    total_deposited_usd: 0.0,
    total_fees_paid_usd: 0.0,
  });
  const [feePolicy, setFeePolicy] = useState<any>({
    activation_fee_usd: 20.0,
    activation_fee_charged: 0,
    execution_fee_usd: 0.30,
    ai_research_fee_usd: 1.00,
    fee_waived: 0,
  });
  const [ledger, setLedger] = useState<any[]>([]);
  const [connections, setConnections] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error" | "info"; message: string } | null>(null);

  // In-App Toast & Confirmation Modal State (replaces alert and confirm)
  const [confirmModal, setConfirmModal] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    confirmText?: string;
    onConfirm: () => void;
  } | null>(null);

  // Binance Pay Modal State
  const [isPayModalOpen, setIsPayModalOpen] = useState(false);
  const [payModalType, setPayModalType] = useState<"ACTIVATION_FEE" | "PREPAID_TOPUP">("PREPAID_TOPUP");
  const [payModalAmount, setPayModalAmount] = useState(50);

  // Provider-Neutral Connection Form
  const [newConnName, setNewConnName] = useState("Binance");
  const [newConnLabel, setNewConnLabel] = useState("Primary Account");
  const [newConnEnv, setNewConnEnv] = useState("DEMO");
  const [newConnApiKey, setNewConnApiKey] = useState("");
  const [newConnSecret, setNewConnSecret] = useState("");
  const [newConnPassphrase, setNewConnPassphrase] = useState("");
  const [isTestingConn, setIsTestingConn] = useState(false);
  const [isSavingConn, setIsSavingConn] = useState(false);
  const [connTestResult, setConnTestResult] = useState<any>(null);

  // 2FA Setup Form
  const [totpSetupData, setTotpSetupData] = useState<any>(null);
  const [totpVerifyCode, setTotpVerifyCode] = useState("");
  const [isSettingUp2FA, setIsSettingUp2FA] = useState(false);

  // Password Rotation Form
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [isRotatingPassword, setIsRotatingPassword] = useState(false);

  // Account Settings & Profile Dropdown State
  const [isProfileDropdownOpen, setIsProfileDropdownOpen] = useState(false);
  const [activeAccountModal, setActiveAccountModal] = useState<"PROFILE" | "CHANGE_USERNAME" | "CHANGE_EMAIL" | "CHANGE_PASSWORD" | null>(null);

  // Change Username State
  const [newUsernameInput, setNewUsernameInput] = useState("");
  const [isUpdatingUsername, setIsUpdatingUsername] = useState(false);
  const [usernameError, setUsernameError] = useState<string | null>(null);

  // Change Email State (2-step with duplicate check modal)
  const [newEmailInput, setNewEmailInput] = useState("");
  const [emailOtpInput, setEmailOtpInput] = useState("");
  const [emailChangeStep, setEmailChangeStep] = useState<"INPUT" | "OTP">("INPUT");
  const [isInitiatingEmailChange, setIsInitiatingEmailChange] = useState(false);
  const [isVerifyingEmailChange, setIsVerifyingEmailChange] = useState(false);
  const [emailChangeError, setEmailChangeError] = useState<string | null>(null);
  const [emailDuplicateModal, setEmailDuplicateModal] = useState(false);

  // Change Password State
  const [currentPassInput, setCurrentPassInput] = useState("");
  const [newPassInput, setNewPassInput] = useState("");
  const [confirmPassInput, setConfirmPassInput] = useState("");
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [passwordChangeError, setPasswordChangeError] = useState<string | null>(null);

  // Simulated / Demo Trades for P&L State
  const [simulatedTrades, setSimulatedTrades] = useState<any[]>([]);

  // Cross-component listeners
  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("bitdex_customer_trades");
      if (stored) {
        try { setSimulatedTrades(JSON.parse(stored)); } catch {}
      }
      const handleNav = (e: any) => {
        if (e.detail) setActiveTab(e.detail);
      };
      const handleOpenAct = () => {
        setPayModalType("ACTIVATION_FEE");
        setPayModalAmount(20.0);
        setIsPayModalOpen(true);
      };
      const handleTrade = (e: any) => {
        if (e.detail) {
          setSimulatedTrades((prev) => [e.detail, ...prev]);
        }
      };
      window.addEventListener("bitdex_navigate_tab", handleNav);
      window.addEventListener("bitdex_open_activation", handleOpenAct);
      window.addEventListener("bitdex_trade_executed", handleTrade);
      return () => {
        window.removeEventListener("bitdex_navigate_tab", handleNav);
        window.removeEventListener("bitdex_open_activation", handleOpenAct);
        window.removeEventListener("bitdex_trade_executed", handleTrade);
      };
    }
  }, []);

  // Account Settings Handlers
  const handleChangeUsername = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanUser = newUsernameInput.trim();
    if (cleanUser.length < 3 || cleanUser.length > 30) {
      setUsernameError("Username must be between 3 and 30 characters.");
      return;
    }
    if (!/^[a-zA-Z0-9_.-]+$/.test(cleanUser)) {
      setUsernameError("Username can only contain letters, numbers, underscores, periods, and hyphens.");
      return;
    }
    setIsUpdatingUsername(true);
    setUsernameError(null);
    try {
      const res = await fetch(getApiUrl("/saas/customer/account/change-username"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ new_username: cleanUser }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update username");
      const updatedName = data.username || data.user?.username || cleanUser;
      setProfile((prev: any) => ({ ...prev, username: updatedName }));
      setActiveAccountModal(null);
      setFeedback({ type: "success", message: `Username successfully updated to ${updatedName}` });
    } catch (err: any) {
      setUsernameError(err.message || "Failed to change username");
    } finally {
      setIsUpdatingUsername(false);
    }
  };

  const handleInitiateEmailChange = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = newEmailInput.trim().toLowerCase();
    if (!cleanEmail || !cleanEmail.includes("@")) {
      setEmailChangeError("Please enter a valid email address.");
      return;
    }
    setIsInitiatingEmailChange(true);
    setEmailChangeError(null);
    try {
      const res = await fetch(getApiUrl("/saas/customer/account/change-email/initiate"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ new_email: cleanEmail }),
      });
      if (res.status === 409) {
        setEmailDuplicateModal(true);
        return;
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to initiate email change");
      setEmailChangeStep("OTP");
    } catch (err: any) {
      setEmailChangeError(err.message || "Failed to initiate email change");
    } finally {
      setIsInitiatingEmailChange(false);
    }
  };

  const handleVerifyEmailChange = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = newEmailInput.trim().toLowerCase();
    const cleanOtp = emailOtpInput.trim();
    if (cleanOtp.length !== 6) {
      setEmailChangeError("Please enter the 6-digit OTP code.");
      return;
    }
    setIsVerifyingEmailChange(true);
    setEmailChangeError(null);
    try {
      const res = await fetch(getApiUrl("/saas/customer/account/change-email/verify"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ new_email: cleanEmail, otp_code: cleanOtp }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Invalid or expired verification code");
      const updatedEmail = data.email || data.user?.email || cleanEmail;
      setProfile((prev: any) => ({ ...prev, email: updatedEmail }));
      setActiveAccountModal(null);
      setFeedback({
        type: "success",
        message: "Email address successfully updated. Security notices have been sent to both email addresses.",
      });
    } catch (err: any) {
      setEmailChangeError(err.message || "Failed to verify email change");
    } finally {
      setIsVerifyingEmailChange(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassInput !== confirmPassInput) {
      setPasswordChangeError("New passwords do not match.");
      return;
    }
    if (newPassInput.length < 8) {
      setPasswordChangeError("New password must be at least 8 characters long.");
      return;
    }
    setIsChangingPassword(true);
    setPasswordChangeError(null);
    try {
      const res = await fetch(getApiUrl("/saas/customer/account/change-password"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          current_password: currentPassInput,
          new_password: newPassInput,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to change password");
      setCurrentPassInput("");
      setNewPassInput("");
      setConfirmPassInput("");
      setActiveAccountModal(null);
      setFeedback({
        type: "success",
        message: "Password changed successfully. Other active sessions have been safely revoked.",
      });
    } catch (err: any) {
      setPasswordChangeError(err.message || "Failed to change password");
    } finally {
      setIsChangingPassword(false);
    }
  };


  // Support Ticketing State
  const [supportTickets, setSupportTickets] = useState<any[]>([]);
  const [selectedTicket, setSelectedTicket] = useState<any>(null);
  const [isTicketLoading, setIsTicketLoading] = useState(false);
  const [isCreateTicketOpen, setIsCreateTicketOpen] = useState(false);
  const [newTicketSubject, setNewTicketSubject] = useState("");
  const [newTicketCategory, setNewTicketCategory] = useState("TECHNICAL");
  const [newTicketMessage, setNewTicketMessage] = useState("");
  const [isSubmittingTicket, setIsSubmittingTicket] = useState(false);
  const [customerTicketReply, setCustomerTicketReply] = useState("");
  const [isSubmittingReply, setIsSubmittingReply] = useState(false);

  // Helper for API base url that works both with root / and /trading
  const getApiUrl = (endpoint: string) => {
    // If running under /trading or root, /api/backend will route via rewrites/Nginx
    return `/api/backend${endpoint}`;
  };

  const fetchCustomerData = async () => {
    setIsLoading(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };

      // 1. Fetch Profile & Billing Summary
      const profRes = await fetch(getApiUrl("/saas/customer/me"), { headers });
      if (profRes.ok) {
        const pData = await profRes.json();
        setProfile(pData.user);
        setBillingSummary(pData.billing_summary);
        setFeePolicy(pData.fee_policy);
      }

      // 2. Fetch Connections
      const connRes = await fetch(getApiUrl("/saas/customer/connections"), { headers });
      if (connRes.ok) {
        const cData = await connRes.json();
        setConnections(cData.connections || []);
      }

      // 3. Fetch Ledger
      const ledRes = await fetch(getApiUrl("/saas/customer/billing/ledger?limit=30"), { headers });
      if (ledRes.ok) {
        const lData = await ledRes.json();
        setLedger(lData.ledger || []);
      }
    } catch (err: any) {
      console.error("Failed to load customer data", err);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchSupportTickets = async () => {
    setIsTicketLoading(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const res = await fetch(getApiUrl("/saas/customer/support/tickets"), { headers });
      if (res.ok) {
        const data = await res.json();
        setSupportTickets(data.tickets || []);
      }
    } catch (err: any) {
      console.error("Failed to load support tickets", err);
    } finally {
      setIsTicketLoading(false);
    }
  };

  const fetchTicketDetails = async (ticketId: string) => {
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const res = await fetch(getApiUrl(`/saas/customer/support/tickets/${ticketId}`), { headers });
      if (res.ok) {
        const data = await res.json();
        setSelectedTicket(data);
      }
    } catch (err: any) {
      console.error("Failed to load ticket details", err);
    }
  };

  useEffect(() => {
    fetchCustomerData();
  }, [token]);

  useEffect(() => {
    if (activeTab === "SUPPORT") {
      fetchSupportTickets();
    }
  }, [activeTab]);

  // Test Connection Handler
  const handleTestConnection = async () => {
    if (!newConnApiKey || !newConnSecret) {
      setFeedback({ type: "error", message: "API Key and Secret are required to test connection." });
      return;
    }
    setIsTestingConn(true);
    setConnTestResult(null);
    setFeedback(null);
    try {
      const res = await fetch(getApiUrl("/saas/customer/connections/test"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          exchange_name: newConnName.trim(),
          provider: newConnName.trim().toUpperCase(),
          environment: newConnEnv,
          api_key: newConnApiKey.trim(),
          api_secret: newConnSecret.trim(),
          passphrase: newConnPassphrase.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Connection test failed");
      setConnTestResult(data);
      setFeedback({ type: "success", message: data.message || "Connection validated successfully." });
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setIsTestingConn(false);
    }
  };

  // Save Connection Handler
  const handleSaveConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newConnApiKey || !newConnSecret) {
      setFeedback({ type: "error", message: "API Key and Secret are mandatory." });
      return;
    }
    setIsSavingConn(true);
    setFeedback(null);
    try {
      const res = await fetch(getApiUrl("/saas/customer/connections"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          exchange_name: newConnName.trim(),
          provider: newConnName.trim().toUpperCase(),
          label: newConnLabel.trim() || `${newConnName} Account`,
          environment: newConnEnv,
          api_key: newConnApiKey.trim(),
          api_secret: newConnSecret.trim(),
          passphrase: newConnPassphrase.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to save connection");

      setFeedback({
        type: "success",
        message: `${newConnName} connection saved. Status: ${data.connection?.verification_status || "SAVED"}`,
      });
      setNewConnApiKey("");
      setNewConnSecret("");
      setNewConnPassphrase("");
      setConnTestResult(null);
      await fetchCustomerData();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setIsSavingConn(false);
    }
  };

  // Delete Connection Handler
  const handleDeleteConnection = (accountId: string) => {
    setConfirmModal({
      isOpen: true,
      title: "Remove Exchange Connection",
      message: "Are you sure you want to permanently remove this exchange connection? Credentials will be securely purged from the vault.",
      confirmText: "Remove Connection",
      onConfirm: async () => {
        try {
          const res = await fetch(getApiUrl(`/saas/customer/connections/${accountId}`), {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` },
          });
          if (res.ok) {
            setFeedback({ type: "success", message: "Exchange connection removed successfully." });
            await fetchCustomerData();
          } else {
            const data = await res.json();
            throw new Error(data.detail || "Failed to delete connection");
          }
        } catch (err: any) {
          setFeedback({ type: "error", message: err.message });
        } finally {
          setConfirmModal(null);
        }
      },
    });
  };

  // 2FA Setup
  const handleStart2FASetup = async () => {
    setIsSettingUp2FA(true);
    setFeedback(null);
    try {
      const res = await fetch(getApiUrl("/saas/customer/2fa/setup"), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to initiate 2FA setup");
      setTotpSetupData(data);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setIsSettingUp2FA(false);
    }
  };

  const handleVerify2FASetup = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    try {
      const res = await fetch(getApiUrl("/saas/customer/2fa/verify"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          totp_secret: totpSetupData.totp_secret,
          code: totpVerifyCode.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Invalid TOTP verification code");
      setFeedback({ type: "success", message: "Two-Factor Authentication enabled successfully!" });
      setTotpSetupData(null);
      setTotpVerifyCode("");
      await fetchCustomerData();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    }
  };

  // Rotate Password
  const handleRotatePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmNewPassword) {
      setFeedback({ type: "error", message: "New passwords do not match." });
      return;
    }
    if (newPassword.length < 8) {
      setFeedback({ type: "error", message: "New password must be at least 8 characters long." });
      return;
    }
    setIsRotatingPassword(true);
    setFeedback(null);
    try {
      const res = await fetch(getApiUrl("/saas/customer/password/rotate"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to update password");

      setOldPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
      setFeedback({
        type: "success",
        message: "Password updated successfully! Existing sessions were revoked. Please sign in with your new password.",
      });
      setTimeout(() => {
        onSignOut();
      }, 2500);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setIsRotatingPassword(false);
    }
  };

  // Create Support Ticket
  const handleCreateTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTicketSubject.trim() || !newTicketMessage.trim()) {
      setFeedback({ type: "error", message: "Subject and message are required." });
      return;
    }
    setIsSubmittingTicket(true);
    try {
      const res = await fetch(getApiUrl("/saas/customer/support/tickets"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          subject: newTicketSubject.trim(),
          category: newTicketCategory,
          message: newTicketMessage.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to submit support ticket");

      setFeedback({
        type: "success",
        message: `Ticket #${data.ticket_id} opened successfully. Our team will respond shortly at ${profile?.email}.`,
      });
      setNewTicketSubject("");
      setNewTicketMessage("");
      setIsCreateTicketOpen(false);
      await fetchSupportTickets();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setIsSubmittingTicket(false);
    }
  };

  // Reply to Support Ticket
  const handleSendTicketReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customerTicketReply.trim() || !selectedTicket) return;
    setIsSubmittingReply(true);
    try {
      const res = await fetch(getApiUrl(`/saas/customer/support/tickets/${selectedTicket.ticket.ticket_id}/reply`), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          message: customerTicketReply.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to post reply");

      setCustomerTicketReply("");
      await fetchTicketDetails(selectedTicket.ticket.ticket_id);
      await fetchSupportTickets();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setIsSubmittingReply(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "VERIFIED_READ_ONLY":
      case "VERIFIED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono bg-emerald-500/10 text-emerald-400 rounded-full border border-emerald-500/20 font-bold">
            <CheckCircle2 className="w-3 h-3" />
            VERIFIED READ-ONLY
          </span>
        );
      case "SAVED_UNSUPPORTED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono bg-cyan-500/10 text-cyan-400 rounded-full border border-cyan-500/20 font-bold">
            <Info className="w-3 h-3" />
            SAVED (PENDING ADAPTER)
          </span>
        );
      case "VERIFICATION_FAILED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono bg-rose-500/10 text-rose-400 rounded-full border border-rose-500/20 font-bold">
            <AlertTriangle className="w-3 h-3" />
            VERIFICATION FAILED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono bg-slate-800 text-slate-300 rounded-full border border-slate-700">
            {status}
          </span>
        );
    }
  };

  const getTicketStatusBadge = (status: string) => {
    switch (status) {
      case "OPEN":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">OPEN</span>;
      case "IN_PROGRESS":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-blue-500/10 text-blue-400 border border-blue-500/20">IN PROGRESS</span>;
      case "WAITING_ON_CUSTOMER":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20">WAITING ON YOU</span>;
      case "RESOLVED":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-purple-500/10 text-purple-400 border border-purple-500/20">RESOLVED</span>;
      case "CLOSED":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-slate-800 text-slate-400 border border-slate-700">CLOSED</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-slate-800 text-slate-300">{status}</span>;
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* ─── CUSTOMER PORTAL HEADER (BITDEX BRANDING) ─────────────── */}
      <header className="sticky top-0 z-40 w-full border-b border-slate-800/80 bg-slate-950/95 backdrop-blur-md">
        <div className="max-w-[1760px] w-full mx-auto px-4 sm:px-6 lg:px-8 xl:px-10 h-16 flex items-center justify-between">
          {/* Left: Brand Identity */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center p-1.5 shadow-sm">
                <img src="/bitdex-icon.svg" alt="Bitdex Icon" className="w-full h-full object-contain" />
              </div>
              <div className="flex flex-col">
                <div className="flex items-center gap-2">
                  <span className="text-base font-black tracking-wider text-white">BITDEX</span>
                  <span className="px-2 py-0.5 text-[9px] font-mono bg-emerald-500/10 text-emerald-300 rounded border border-emerald-500/20 font-bold uppercase">
                    Customer Portal
                  </span>
                </div>
                <span className="text-[10px] text-slate-500 font-mono hidden sm:inline">
                  https://bitdex.ltd • Institutional Quantitative Analytics
                </span>
              </div>
            </div>
          </div>

          {/* Right: Actions, Prepaid Credits & Profile Dropdown */}
          <div className="flex items-center gap-3">
            {/* Compact Account Activation Control */}
            {!feePolicy.activation_fee_charged ? (
              <button
                id="header-activate-account-btn"
                onClick={() => {
                  setPayModalType("ACTIVATION_FEE");
                  setPayModalAmount(20.0);
                  setIsPayModalOpen(true);
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold font-mono transition-all cursor-pointer shadow-md shadow-amber-500/20"
              >
                <AlertTriangle className="w-3.5 h-3.5 text-slate-950" />
                <span>Activate Account</span>
              </button>
            ) : (
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono font-bold">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Activated</span>
              </div>
            )}

            {/* Prepaid Credits Pill */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs font-mono">
              <span className="text-slate-400">Prepaid:</span>
              <span className="text-emerald-400 font-bold">
                ${(billingSummary?.prepaid_credits_usd || 0).toFixed(2)}
              </span>
              <button
                onClick={() => {
                  setPayModalType("PREPAID_TOPUP");
                  setPayModalAmount(50.0);
                  setIsPayModalOpen(true);
                }}
                className="ml-1 px-2 py-0.5 rounded bg-emerald-600/80 hover:bg-emerald-500 text-white text-[10px] font-bold cursor-pointer transition-all"
              >
                + Top Up
              </button>
            </div>

            {/* User Profile Dropdown Pill */}
            <div className="relative">
              <button
                onClick={() => setIsProfileDropdownOpen(!isProfileDropdownOpen)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-800 text-xs font-mono transition-all cursor-pointer"
              >
                <div className="w-6 h-6 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-300 font-bold text-xs">
                  {(profile?.username || profile?.email || "U")[0].toUpperCase()}
                </div>
                <div className="hidden sm:flex flex-col text-left">
                  <span className="text-white font-bold text-xs leading-none">
                    {profile?.username || profile?.email?.split("@")[0]}
                  </span>
                  <span className="text-[10px] text-slate-400 leading-tight">
                    {profile?.email}
                  </span>
                </div>
                <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
              </button>

              {/* Profile Dropdown Menu */}
              {isProfileDropdownOpen && (
                <div
                  className="absolute right-0 mt-2 w-56 rounded-2xl bg-slate-900 border border-slate-800 shadow-2xl py-2 z-50 text-xs font-mono"
                  onMouseLeave={() => setIsProfileDropdownOpen(false)}
                >
                  <div className="px-4 py-2 border-b border-slate-800">
                    <div className="text-white font-bold truncate">{profile?.username || "Trader"}</div>
                    <div className="text-[10px] text-slate-400 truncate">{profile?.email}</div>
                  </div>
                  <button
                    onClick={() => {
                      setIsProfileDropdownOpen(false);
                      setActiveAccountModal("PROFILE");
                    }}
                    className="w-full px-4 py-2 text-left text-slate-300 hover:text-white hover:bg-slate-800/80 flex items-center gap-2 cursor-pointer"
                  >
                    <User className="w-3.5 h-3.5 text-slate-400" />
                    Profile
                  </button>
                  <button
                    onClick={() => {
                      setIsProfileDropdownOpen(false);
                      setNewUsernameInput(profile?.username || "");
                      setUsernameError(null);
                      setActiveAccountModal("CHANGE_USERNAME");
                    }}
                    className="w-full px-4 py-2 text-left text-slate-300 hover:text-white hover:bg-slate-800/80 flex items-center gap-2 cursor-pointer"
                  >
                    <Edit3 className="w-3.5 h-3.5 text-slate-400" />
                    Change Username
                  </button>
                  <button
                    onClick={() => {
                      setIsProfileDropdownOpen(false);
                      setNewEmailInput("");
                      setEmailOtpInput("");
                      setEmailChangeStep("INPUT");
                      setEmailChangeError(null);
                      setActiveAccountModal("CHANGE_EMAIL");
                    }}
                    className="w-full px-4 py-2 text-left text-slate-300 hover:text-white hover:bg-slate-800/80 flex items-center gap-2 cursor-pointer"
                  >
                    <Mail className="w-3.5 h-3.5 text-slate-400" />
                    Change Email
                  </button>
                  <button
                    onClick={() => {
                      setIsProfileDropdownOpen(false);
                      setCurrentPassInput("");
                      setNewPassInput("");
                      setConfirmPassInput("");
                      setPasswordChangeError(null);
                      setActiveAccountModal("CHANGE_PASSWORD");
                    }}
                    className="w-full px-4 py-2 text-left text-slate-300 hover:text-white hover:bg-slate-800/80 flex items-center gap-2 cursor-pointer"
                  >
                    <Lock className="w-3.5 h-3.5 text-slate-400" />
                    Change Password
                  </button>
                  <div className="my-1 border-t border-slate-800" />
                  <button
                    onClick={() => {
                      setIsProfileDropdownOpen(false);
                      onSignOut();
                    }}
                    className="w-full px-4 py-2 text-left text-rose-400 hover:text-rose-300 hover:bg-rose-950/30 flex items-center gap-2 cursor-pointer"
                  >
                    <LogOut className="w-3.5 h-3.5 text-rose-400" />
                    Sign Out
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Navigation Tabs (Exactly 6 Primary Items) */}
        <div className="max-w-[1760px] w-full mx-auto px-4 sm:px-6 lg:px-8 xl:px-10 flex items-center gap-2 border-t border-slate-900 pt-1 pb-1 overflow-x-auto">
          <button
            onClick={() => setActiveTab("TRADING")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all cursor-pointer whitespace-nowrap ${
              activeTab === "TRADING"
                ? "bg-emerald-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            Live Market Signals
          </button>
          <button
            onClick={() => setActiveTab("CONNECTIONS")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all cursor-pointer whitespace-nowrap ${
              activeTab === "CONNECTIONS"
                ? "bg-emerald-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            Exchange Connections
            {connections.length > 0 && (
              <span className="px-1.5 py-0.2 text-[9px] rounded-full bg-slate-800 text-slate-300 font-mono">
                {connections.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab("BILLING")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all cursor-pointer whitespace-nowrap ${
              activeTab === "BILLING"
                ? "bg-emerald-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <Wallet className="w-3.5 h-3.5" />
            Billing & Invoices
          </button>
          <button
            onClick={() => setActiveTab("SUPPORT")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all cursor-pointer whitespace-nowrap ${
              activeTab === "SUPPORT"
                ? "bg-emerald-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <LifeBuoy className="w-3.5 h-3.5" />
            Help & Support
          </button>
          <button
            onClick={() => setActiveTab("SECURITY")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all cursor-pointer whitespace-nowrap ${
              activeTab === "SECURITY"
                ? "bg-emerald-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <Key className="w-3.5 h-3.5" />
            Security & Two-Factor Authentication
          </button>
          <button
            onClick={() => setActiveTab("PROFIT_LOSS")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all cursor-pointer whitespace-nowrap ${
              activeTab === "PROFIT_LOSS"
                ? "bg-emerald-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            Profit & Loss
          </button>
        </div>
      </header>

      {/* ─── NOTIFICATION FEEDBACK BANNER ─────────────────────────── */}
      {feedback && (
        <div
          className={`px-6 py-2.5 text-xs font-mono flex items-center justify-between border-b ${
            feedback.type === "success"
              ? "bg-emerald-950/60 border-emerald-500/30 text-emerald-300"
              : feedback.type === "error"
              ? "bg-rose-950/60 border-rose-500/30 text-rose-300"
              : "bg-blue-950/60 border-blue-500/30 text-blue-300"
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
            <button onClick={() => setFeedback(null)} className="text-slate-400 hover:text-white cursor-pointer">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* ─── MAIN CONTENT CONTAINER (FLUID RESPONSIVE SHELL) ──────── */}
      <main className="flex-1 max-w-[1760px] w-full mx-auto px-4 sm:px-6 lg:px-8 xl:px-10 py-6">
        {/* TAB 1: TRADING / SIGNALS CONSOLE */}
        {activeTab === "TRADING" && (
          <div>
            {children}
          </div>
        )}

        {/* TAB 2: CONNECTIONS (PROVIDER-NEUTRAL EXCHANGE INTERFACE) ── */}
        {activeTab === "CONNECTIONS" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              {/* Connected Accounts Card */}
              <div className="p-6 rounded-3xl bg-slate-900 border border-slate-800 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <div>
                    <h3 className="text-sm font-bold text-white flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 text-emerald-400" />
                      Connected Exchange Accounts
                    </h3>
                    <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                      Vault-encrypted API keys with mandatory read-only validation.
                    </p>
                  </div>
                  <button onClick={fetchCustomerData} className="text-slate-400 hover:text-white text-xs p-1">
                    <RefreshCw className="w-3.5 h-3.5" />
                  </button>
                </div>

                {connections.length === 0 ? (
                  <div className="py-12 text-center text-slate-500 text-xs font-mono border border-dashed border-slate-800 rounded-2xl">
                    No exchange connections found. Add your read/trade API keys below to enable automated analysis and execution.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {connections.map((c) => (
                      <div
                        key={c.account_id}
                        className="p-4 rounded-2xl bg-slate-950 border border-slate-800/80 flex flex-wrap items-center justify-between gap-3"
                      >
                        <div className="space-y-1.5">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-white text-xs">{c.label || c.exchange_name}</span>
                            <span className="px-2 py-0.5 text-[9px] font-mono bg-purple-500/10 text-purple-300 rounded border border-purple-500/20 font-bold uppercase">
                              {c.exchange_name || c.provider}
                            </span>
                            <span
                              className={`px-2 py-0.5 text-[9px] font-mono rounded border font-bold ${
                                c.environment === "LIVE"
                                  ? "bg-amber-500/10 text-amber-300 border-amber-500/20"
                                  : "bg-cyan-500/10 text-cyan-300 border-cyan-500/20"
                              }`}
                            >
                              {c.environment}
                            </span>
                            {getStatusBadge(c.verification_status || "SAVED_UNSUPPORTED")}
                          </div>
                          <div className="text-[10px] font-mono text-slate-500 flex flex-wrap items-center gap-3">
                            <span>ID: {c.account_id}</span>
                            <span>•</span>
                            <span className="text-emerald-400">Withdrawal Permissions: Strictly Blocked</span>
                            {c.key_fingerprint && (
                              <>
                                <span>•</span>
                                <span>Key: {c.key_fingerprint}</span>
                              </>
                            )}
                          </div>
                        </div>

                        <button
                          onClick={() => handleDeleteConnection(c.account_id)}
                          className="p-2 rounded-xl text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-all cursor-pointer"
                          title="Delete Connection"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Add New Connection Form (Provider-Neutral) */}
              <div className="p-6 rounded-3xl bg-slate-900 border border-slate-800 space-y-4">
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <Plus className="w-4 h-4 text-emerald-400" />
                    Connect Exchange Account
                  </h3>
                  <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                    Enter any supported or custom exchange. Validated adapters receive active verification; custom exchanges are securely stored for upcoming connector rollout.
                  </p>
                </div>

                <form onSubmit={handleSaveConnection} className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">
                        Exchange / Account Name
                      </label>
                      <input
                        type="text"
                        required
                        list="popular-exchanges"
                        value={newConnName}
                        onChange={(e) => setNewConnName(e.target.value)}
                        placeholder="e.g. Binance, Bybit, Coinbase..."
                        className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500"
                      />
                      <datalist id="popular-exchanges">
                        <option value="Binance" />
                        <option value="Bybit" />
                        <option value="Bitget" />
                        <option value="Coinbase Advanced" />
                        <option value="Kraken" />
                        <option value="Deribit" />
                        <option value="OKX" />
                        <option value="MetaTrader 5 (MT5)" />
                      </datalist>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">Environment</label>
                      <select
                        value={newConnEnv}
                        onChange={(e) => setNewConnEnv(e.target.value)}
                        className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500"
                      >
                        <option value="DEMO">Demo / Testnet Sandbox</option>
                        <option value="LIVE">Live Exchange (Read/Trade Only)</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">Customer Label / Notes</label>
                      <input
                        type="text"
                        value={newConnLabel}
                        onChange={(e) => setNewConnLabel(e.target.value)}
                        placeholder="e.g. Main Spot Strategy"
                        className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">API Key</label>
                    <input
                      type="password"
                      required
                      value={newConnApiKey}
                      onChange={(e) => setNewConnApiKey(e.target.value)}
                      placeholder="Enter Exchange API Key"
                      className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white font-mono focus:outline-none focus:border-emerald-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">API Secret</label>
                    <input
                      type="password"
                      required
                      value={newConnSecret}
                      onChange={(e) => setNewConnSecret(e.target.value)}
                      placeholder="Enter Exchange API Secret"
                      className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white font-mono focus:outline-none focus:border-emerald-500"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-xs font-semibold text-slate-300">
                        Passphrase / Second Factor (Optional)
                      </label>
                      <span className="text-[10px] text-slate-500 font-mono">Required for Bitget, OKX, KuCoin, MT5</span>
                    </div>
                    <input
                      type="password"
                      value={newConnPassphrase}
                      onChange={(e) => setNewConnPassphrase(e.target.value)}
                      placeholder="Optional passphrase if required by exchange"
                      className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white font-mono focus:outline-none focus:border-emerald-500"
                    />
                  </div>

                  {connTestResult && (
                    <div
                      className={`p-4 rounded-xl text-xs font-mono border ${
                        connTestResult.verification_status === "VERIFIED_READ_ONLY" || connTestResult.status === "SUCCESS"
                          ? "bg-emerald-950/40 border-emerald-500/30 text-emerald-300"
                          : connTestResult.verification_status === "SAVED_UNSUPPORTED"
                          ? "bg-blue-950/40 border-blue-500/30 text-blue-300"
                          : "bg-rose-950/40 border-rose-500/30 text-rose-300"
                      }`}
                    >
                      <div className="flex items-center justify-between font-bold mb-1">
                        <span>Test Result: {connTestResult.verification_status || connTestResult.status}</span>
                        {getStatusBadge(connTestResult.verification_status || "UNKNOWN")}
                      </div>
                      <p>{connTestResult.message || connTestResult.detail}</p>
                    </div>
                  )}

                  <div className="flex items-center gap-3 pt-2">
                    <button
                      type="button"
                      onClick={handleTestConnection}
                      disabled={isTestingConn || !newConnApiKey || !newConnSecret}
                      className="px-4 py-2.5 rounded-xl border border-slate-700 hover:border-slate-600 bg-slate-800 text-white text-xs font-bold font-mono transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2"
                    >
                      {isTestingConn && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                      Test Credentials
                    </button>
                    <button
                      type="submit"
                      disabled={isSavingConn || !newConnApiKey || !newConnSecret}
                      className="flex-1 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold font-mono transition-all disabled:opacity-50 cursor-pointer flex items-center justify-center gap-2 shadow-lg shadow-emerald-950/30"
                    >
                      {isSavingConn && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                      Save & Encrypt Connection
                    </button>
                  </div>
                </form>
              </div>
            </div>

            {/* Sidebar Security & Instructions */}
            <div className="space-y-6">
              <div className="p-6 rounded-3xl bg-slate-900 border border-slate-800 space-y-4">
                <div className="flex items-center gap-2 text-xs font-mono font-bold text-emerald-400 uppercase">
                  <ShieldCheck className="w-4 h-4" />
                  Security Guarantee
                </div>
                <div className="space-y-3 text-xs text-slate-400 font-mono leading-relaxed">
                  <p>
                    • <strong>Zero Withdrawal Authority:</strong> Bitdex rejects any API keys with withdrawal privileges enabled.
                  </p>
                  <p>
                    • <strong>Provider-Neutral Architecture:</strong> Connect major exchanges or store enterprise custom endpoints.
                  </p>
                  <p>
                    • <strong>Hardware Vault:</strong> Keys are AES-256 encrypted using customer-isolated salting before persistent storage.
                  </p>
                  <p>
                    • <strong>Automated Verification:</strong> Live connectivity is re-validated periodically with latency telemetry.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: BILLING & INVOICES ───────────────────────────────── */}
        {activeTab === "BILLING" && (
          <div className="space-y-6">
            {/* Balance Overview Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
                <div className="flex items-center justify-between text-xs font-mono text-slate-400">
                  <span>PREPAID CREDIT BALANCE</span>
                  <Wallet className="w-4 h-4 text-emerald-400" />
                </div>
                <div className="text-2xl font-black text-white font-mono">
                  ${(billingSummary?.prepaid_credits_usd || 0).toFixed(2)}
                </div>
                <div className="text-[11px] text-slate-500 font-mono">
                  Funds AI Intelligence ($1.00/run) & executions ($0.30/exec)
                </div>
              </div>

              <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
                <div className="flex items-center justify-between text-xs font-mono text-slate-400">
                  <span>TOTAL TOPPED UP</span>
                  <DollarSign className="w-4 h-4 text-cyan-400" />
                </div>
                <div className="text-2xl font-black text-white font-mono">
                  ${(billingSummary?.total_deposited_usd || 0).toFixed(2)}
                </div>
                <div className="text-[11px] text-slate-500 font-mono">
                  Cumulative verified Binance Pay deposits
                </div>
              </div>

              <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
                <div className="flex items-center justify-between text-xs font-mono text-slate-400">
                  <span>TOTAL USAGE DEDUCTED</span>
                  <Activity className="w-4 h-4 text-purple-400" />
                </div>
                <div className="text-2xl font-black text-white font-mono">
                  ${(billingSummary?.total_fees_paid_usd || 0).toFixed(2)}
                </div>
                <div className="text-[11px] text-slate-500 font-mono">
                  Billed automatically with failure refunds
                </div>
              </div>
            </div>

            {/* Top Up Action Card */}
            <div className="p-6 rounded-3xl bg-slate-900 border border-slate-800 flex flex-wrap items-center justify-between gap-4">
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-white flex items-center gap-2">
                  <CreditCard className="w-4 h-4 text-emerald-400" />
                  Instant Account Top-Up via Binance Pay
                </h4>
                <p className="text-xs text-slate-400 font-mono">
                  Zero network fees. Instant credit confirmation via Binance Pay QR code or checkout url.
                </p>
              </div>
              <div className="flex items-center gap-3">
                {[25, 50, 100, 250].map((amt) => (
                  <button
                    key={amt}
                    onClick={() => {
                      setPayModalType("PREPAID_TOPUP");
                      setPayModalAmount(amt);
                      setIsPayModalOpen(true);
                    }}
                    className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-mono text-xs font-bold transition-all cursor-pointer border border-slate-700"
                  >
                    +${amt}
                  </button>
                ))}
              </div>
            </div>

            {/* Billing Ledger Table */}
            <div className="p-6 rounded-3xl bg-slate-900 border border-slate-800 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <h4 className="text-sm font-bold text-white flex items-center gap-2">
                  <FileText className="w-4 h-4 text-emerald-400" />
                  Detailed Transaction & Fee History
                </h4>
                <span className="text-xs text-slate-500 font-mono">Last 30 Records</span>
              </div>

              {ledger.length === 0 ? (
                <div className="py-10 text-center text-slate-500 text-xs font-mono">
                  No billing transactions recorded yet.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="text-[11px] text-slate-400 border-b border-slate-800">
                      <tr>
                        <th className="pb-3">DATE / TIME</th>
                        <th className="pb-3">TRANSACTION TYPE</th>
                        <th className="pb-3">DESCRIPTION</th>
                        <th className="pb-3">AMOUNT</th>
                        <th className="pb-3">POST BALANCE</th>
                        <th className="pb-3">REFERENCE</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 text-slate-300">
                      {ledger.map((item, idx) => (
                        <tr key={idx} className="hover:bg-slate-950/40">
                          <td className="py-3 text-slate-400">{item.created_at}</td>
                          <td className="py-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                item.entry_type === "CREDIT_TOPUP"
                                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                  : item.entry_type === "AI_RESEARCH_FEE" || item.entry_type === "EXECUTION_FEE"
                                  ? "bg-purple-500/10 text-purple-300 border border-purple-500/20"
                                  : "bg-slate-800 text-slate-300"
                              }`}
                            >
                              {item.entry_type}
                            </span>
                          </td>
                          <td className="py-3">{item.description || "—"}</td>
                          <td
                            className={`py-3 font-bold ${
                              item.amount_usd > 0 ? "text-emerald-400" : "text-rose-400"
                            }`}
                          >
                            {item.amount_usd > 0 ? `+$${item.amount_usd.toFixed(2)}` : `-$${Math.abs(item.amount_usd).toFixed(2)}`}
                          </td>
                          <td className="py-3 text-slate-400">
                            ${(item.balance_after_usd || 0).toFixed(2)}
                          </td>
                          <td className="py-3 text-[10px] text-slate-500 truncate max-w-[140px]">
                            {item.reference_id || item.transaction_id || "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 4: HELP & SUPPORT (TICKETING & FAQ) ─────────────────── */}
        {activeTab === "SUPPORT" && (
          <div className="space-y-6">
            {/* Support Header Banner */}
            <div className="p-6 rounded-3xl bg-slate-900 border border-slate-800 flex flex-wrap items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <LifeBuoy className="w-5 h-5 text-emerald-400" />
                  <h3 className="text-sm font-bold text-white">Bitdex Help & Official Support</h3>
                </div>
                <p className="text-xs text-slate-400 font-mono">
                  Official correspondence & ticket updates are handled securely via{" "}
                  <strong className="text-emerald-400">go@bitdex.ltd</strong>.
                </p>
              </div>
              <button
                onClick={() => setIsCreateTicketOpen(true)}
                className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-bold transition-all cursor-pointer flex items-center gap-2 shadow-lg shadow-emerald-950/30"
              >
                <Plus className="w-4 h-4" />
                Open Support Ticket
              </button>
            </div>

            {/* Tickets & Thread Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Tickets List */}
              <div className="p-6 rounded-3xl bg-slate-900 border border-slate-800 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <h4 className="text-xs font-bold text-white font-mono uppercase">Your Support Tickets</h4>
                  <button onClick={fetchSupportTickets} className="text-slate-400 hover:text-white p-1">
                    <RefreshCw className={`w-3.5 h-3.5 ${isTicketLoading ? "animate-spin" : ""}`} />
                  </button>
                </div>

                {supportTickets.length === 0 ? (
                  <div className="py-8 text-center text-slate-500 text-xs font-mono">
                    No active support tickets. Click "Open Support Ticket" if you need assistance.
                  </div>
                ) : (
                  <div className="space-y-2.5 max-h-[500px] overflow-y-auto">
                    {supportTickets.map((t) => (
                      <div
                        key={t.ticket_id}
                        onClick={() => fetchTicketDetails(t.ticket_id)}
                        className={`p-3.5 rounded-2xl border transition-all cursor-pointer ${
                          selectedTicket?.ticket?.ticket_id === t.ticket_id
                            ? "bg-slate-800 border-emerald-500/50 shadow-sm"
                            : "bg-slate-950/60 border-slate-800/80 hover:bg-slate-800/50"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="text-xs font-bold text-white truncate">{t.subject}</span>
                          {getTicketStatusBadge(t.status)}
                        </div>
                        <div className="text-[10px] font-mono text-slate-400 flex items-center justify-between">
                          <span>#{t.ticket_id.slice(0, 8)} • {t.category}</span>
                          <span>{t.created_at?.split("T")[0] || t.created_at?.slice(0, 10)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Ticket Details & Conversation Thread */}
              <div className="lg:col-span-2 p-6 rounded-3xl bg-slate-900 border border-slate-800 flex flex-col min-h-[400px]">
                {selectedTicket ? (
                  <div className="flex-1 flex flex-col space-y-4">
                    {/* Header */}
                    <div className="border-b border-slate-800 pb-3 flex items-center justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold text-white">{selectedTicket.ticket.subject}</h4>
                          {getTicketStatusBadge(selectedTicket.ticket.status)}
                        </div>
                        <span className="text-[10px] font-mono text-slate-400">
                          Ticket #{selectedTicket.ticket.ticket_id} • Category: {selectedTicket.ticket.category} • Created: {selectedTicket.ticket.created_at}
                        </span>
                      </div>
                      <button
                        onClick={() => setSelectedTicket(null)}
                        className="text-slate-400 hover:text-white p-1"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>

                    {/* Messages Thread */}
                    <div className="flex-1 space-y-3 overflow-y-auto max-h-[350px] pr-2">
                      {selectedTicket.messages?.map((msg: any) => (
                        <div
                          key={msg.message_id}
                          className={`p-4 rounded-2xl text-xs font-mono leading-relaxed ${
                            msg.sender_type === "CUSTOMER"
                              ? "bg-slate-950 border border-slate-800 text-slate-200 ml-6"
                              : "bg-emerald-950/30 border border-emerald-500/30 text-emerald-200 mr-6"
                          }`}
                        >
                          <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1.5 pb-1 border-b border-slate-800/50">
                            <span className="font-bold flex items-center gap-1.5">
                              {msg.sender_type === "CUSTOMER" ? (
                                <>
                                  <User className="w-3 h-3 text-slate-400" />
                                  You ({msg.sender_email})
                                </>
                              ) : (
                                <>
                                  <ShieldCheck className="w-3 h-3 text-emerald-400" />
                                  Bitdex Support ({msg.sender_email || "go@bitdex.ltd"})
                                </>
                              )}
                            </span>
                            <span>{msg.created_at}</span>
                          </div>
                          <p className="whitespace-pre-wrap">{msg.message}</p>
                        </div>
                      ))}
                    </div>

                    {/* Reply Form */}
                    {selectedTicket.ticket.status !== "CLOSED" ? (
                      <form onSubmit={handleSendTicketReply} className="pt-2 border-t border-slate-800 flex gap-2">
                        <input
                          type="text"
                          required
                          value={customerTicketReply}
                          onChange={(e) => setCustomerTicketReply(e.target.value)}
                          placeholder="Type your reply to Bitdex Support..."
                          className="flex-1 px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500 font-mono"
                        />
                        <button
                          type="submit"
                          disabled={isSubmittingReply || !customerTicketReply.trim()}
                          className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-bold transition-all disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
                        >
                          {isSubmittingReply ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                          Reply
                        </button>
                      </form>
                    ) : (
                      <div className="p-3 text-center text-xs text-slate-500 font-mono bg-slate-950 rounded-xl">
                        This ticket is marked as CLOSED. Open a new ticket if further assistance is required.
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center py-12 text-center text-slate-500 space-y-2">
                    <MessageSquare className="w-8 h-8 text-slate-600" />
                    <p className="text-xs font-mono">Select a ticket from the list to view conversation history</p>
                  </div>
                )}
              </div>
            </div>

            {/* Support Knowledgebase / FAQ */}
            <div className="p-6 rounded-3xl bg-slate-900 border border-slate-800 space-y-4">
              <h4 className="text-xs font-bold text-white font-mono uppercase flex items-center gap-2">
                <HelpCircle className="w-4 h-4 text-emerald-400" />
                Frequently Asked Questions
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono text-slate-300">
                <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800/80 space-y-1.5">
                  <span className="font-bold text-white">How do prepaid AI credits work?</span>
                  <p className="text-slate-400 leading-relaxed text-[11px]">
                    Each Dual-AI Deep Intelligence analysis costs a fixed $1.00 USD. If an analysis fails or times out, credits are immediately and automatically refunded to your balance.
                  </p>
                </div>
                <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800/80 space-y-1.5">
                  <span className="font-bold text-white">Can Bitdex withdraw funds from my exchange?</span>
                  <p className="text-slate-400 leading-relaxed text-[11px]">
                    Never. The Bitdex engine enforces strict read/trade restrictions and actively rejects any credentials created with withdrawal or transfer permissions.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 5: SECURITY & 2FA ───────────────────────────────────── */}
        {activeTab === "SECURITY" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Update Password Form */}
            <div className="p-6 rounded-3xl bg-slate-900 border border-slate-800 space-y-4">
              <div className="flex items-center gap-2 text-xs font-mono font-bold text-white uppercase border-b border-slate-800 pb-3">
                <Lock className="w-4 h-4 text-emerald-400" />
                Update Account Password
              </div>
              <p className="text-xs text-slate-400 font-mono">
                Rotating your password automatically invalidates all active sessions across all devices for security.
              </p>

              <form onSubmit={handleRotatePassword} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Current Password</label>
                  <input
                    type="password"
                    required
                    value={oldPassword}
                    onChange={(e) => setOldPassword(e.target.value)}
                    placeholder="Enter current password"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">New Password</label>
                  <input
                    type="password"
                    required
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="At least 8 characters"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Confirm New Password</label>
                  <input
                    type="password"
                    required
                    value={confirmNewPassword}
                    onChange={(e) => setConfirmNewPassword(e.target.value)}
                    placeholder="Repeat new password"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <button
                  type="submit"
                  disabled={isRotatingPassword || !oldPassword || !newPassword}
                  className="w-full py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-mono text-xs font-bold transition-all disabled:opacity-50 cursor-pointer flex items-center justify-center gap-2 border border-slate-700"
                >
                  {isRotatingPassword && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Update Password & Invalidate Sessions
                </button>
              </form>
            </div>

            {/* Two-Factor Authentication (TOTP) */}
            <div className="p-6 rounded-3xl bg-slate-900 border border-slate-800 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2 text-xs font-mono font-bold text-white uppercase">
                  <Key className="w-4 h-4 text-emerald-400" />
                  Two-Factor Authentication (2FA)
                </div>
                {profile?.two_factor_enabled ? (
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-bold">
                    ENABLED
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-amber-500/10 text-amber-300 border border-amber-500/20 font-bold">
                    DISABLED
                  </span>
                )}
              </div>

              {profile?.two_factor_enabled ? (
                <div className="space-y-3 text-xs font-mono text-slate-300">
                  <div className="p-4 rounded-2xl bg-emerald-950/30 border border-emerald-500/30 flex items-start gap-3">
                    <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold text-white block">TOTP Protection Active</span>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        Your account requires Google Authenticator / 1Password verification on login and sensitive credential modifications.
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <p className="text-xs text-slate-400 font-mono">
                    Protect your portfolio with standard Time-based One-Time Password (TOTP) authenticator apps.
                  </p>

                  {!totpSetupData ? (
                    <button
                      onClick={handleStart2FASetup}
                      disabled={isSettingUp2FA}
                      className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-bold transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2 shadow-lg shadow-emerald-950/30"
                    >
                      {isSettingUp2FA && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                      Begin 2FA Setup
                    </button>
                  ) : (
                    <form onSubmit={handleVerify2FASetup} className="space-y-4 p-4 rounded-2xl bg-slate-950 border border-slate-800">
                      <div className="space-y-2">
                        <span className="text-xs font-bold text-white font-mono block">1. Scan QR Code</span>
                        <div className="p-3 bg-white rounded-xl inline-block">
                          <img src={totpSetupData.qr_uri} alt="2FA QR Code" className="w-36 h-36" />
                        </div>
                        <div className="text-[10px] font-mono text-slate-400">
                          Secret: <strong className="text-emerald-300 select-all">{totpSetupData.totp_secret}</strong>
                        </div>
                      </div>

                      <div className="space-y-2">
                        <span className="text-xs font-bold text-white font-mono block">2. Enter 6-Digit Code</span>
                        <input
                          type="text"
                          required
                          maxLength={6}
                          value={totpVerifyCode}
                          onChange={(e) => setTotpVerifyCode(e.target.value)}
                          placeholder="000000"
                          className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs text-white font-mono tracking-widest text-center focus:outline-none focus:border-emerald-500"
                        />
                      </div>

                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => setTotpSetupData(null)}
                          className="px-3 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-mono cursor-pointer"
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="flex-1 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-bold cursor-pointer transition-all"
                        >
                          Verify & Activate 2FA
                        </button>
                      </div>
                    </form>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
        {/* TAB 6: PROFIT & LOSS (INSTITUTIONAL PERFORMANCE & TRADES) ─ */}
        {activeTab === "PROFIT_LOSS" && (
          <div className="space-y-6">
            {/* Performance Overview Banner */}
            <div className="p-6 rounded-3xl bg-slate-900 border border-slate-800 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-bold text-white flex items-center gap-2">
                      <Activity className="w-5 h-5 text-emerald-400" />
                      Profit & Loss Performance Overview
                    </h3>
                    <span className="px-2.5 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-500/30 text-[10px] font-mono font-bold flex items-center gap-1">
                      <ShieldAlert className="w-3 h-3 text-cyan-400" />
                      SIMULATED / DEMO ENVIRONMENT (STAGING)
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 font-mono mt-1">
                    Real-time quantitative performance tracking across connected accounts and simulated executions.
                  </p>
                </div>
                <button
                  onClick={() => {
                    const raw = localStorage.getItem("bitdex_customer_trades");
                    if (raw) {
                      try { setSimulatedTrades(JSON.parse(raw)); } catch {}
                    }
                    fetchCustomerData();
                  }}
                  className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-mono flex items-center gap-1.5 transition-all cursor-pointer"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  Refresh P&L
                </button>
              </div>

              {/* Metrics Row */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="p-4 rounded-2xl bg-slate-950/70 border border-slate-800/80">
                  <span className="text-[10px] font-mono uppercase text-slate-400 font-bold block">
                    Total Portfolio Equity
                  </span>
                  <div className="text-xl font-bold font-mono text-white mt-1">
                    ${(100000.0 + simulatedTrades.reduce((acc, t) => acc + (t.realized_pnl || 0), 0)).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <span className="text-[10px] font-mono text-emerald-400 mt-1 block">
                    $100,000.00 Staging Margin Base
                  </span>
                </div>

                <div className="p-4 rounded-2xl bg-slate-950/70 border border-slate-800/80">
                  <span className="text-[10px] font-mono uppercase text-slate-400 font-bold block">
                    Realized P&L
                  </span>
                  <div className={`text-xl font-bold font-mono mt-1 ${
                    simulatedTrades.reduce((acc, t) => acc + (t.realized_pnl || 0), 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                  }`}>
                    ${simulatedTrades.reduce((acc, t) => acc + (t.realized_pnl || 0), 0).toFixed(2)}
                  </div>
                  <span className="text-[10px] font-mono text-slate-500 mt-1 block">
                    Net of 0.10% simulated exchange fees
                  </span>
                </div>

                <div className="p-4 rounded-2xl bg-slate-950/70 border border-slate-800/80">
                  <span className="text-[10px] font-mono uppercase text-slate-400 font-bold block">
                    Unrealized P&L
                  </span>
                  <div className="text-xl font-bold font-mono text-slate-300 mt-1">
                    $0.00 <span className="text-xs font-normal text-slate-500">(0.00%)</span>
                  </div>
                  <span className="text-[10px] font-mono text-slate-500 mt-1 block">
                    Across 0 active floating positions
                  </span>
                </div>

                <div className="p-4 rounded-2xl bg-slate-950/70 border border-slate-800/80">
                  <span className="text-[10px] font-mono uppercase text-slate-400 font-bold block">
                    Executed Orders / Win Rate
                  </span>
                  <div className="text-xl font-bold font-mono text-cyan-400 mt-1">
                    {simulatedTrades.length} <span className="text-xs font-normal text-slate-400">fills (100% demo)</span>
                  </div>
                  <span className="text-[10px] font-mono text-slate-500 mt-1 block">
                    Zero capital risk in read-only mode
                  </span>
                </div>
              </div>
            </div>

            {/* Section 1: Open Positions */}
            <div className="p-6 rounded-3xl bg-slate-900 border border-slate-800 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <Layers className="w-4 h-4 text-cyan-400" />
                  Active Open Positions
                </h3>
                <span className="text-[11px] font-mono text-slate-500">0 Open Positions</span>
              </div>

              <div className="py-12 text-center text-slate-500 text-xs font-mono border border-dashed border-slate-800 rounded-2xl space-y-2">
                <Activity className="w-8 h-8 text-slate-600 mx-auto" />
                <p className="font-semibold text-slate-400">No active open positions</p>
                <p className="text-[11px] text-slate-500 max-w-md mx-auto">
                  Execute trades from Live Market Signals using the Trade Execution Wizard to stage and simulate algorithmic positions.
                </p>
              </div>
            </div>

            {/* Section 2: Fills and Execution History */}
            <div className="p-6 rounded-3xl bg-slate-900 border border-slate-800 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <FileText className="w-4 h-4 text-emerald-400" />
                    Execution Fills & Trade History
                  </h3>
                  <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                    Audit trail of all executed simulated orders, fill prices, and fee deductions.
                  </p>
                </div>
                {simulatedTrades.length > 0 && (
                  <button
                    onClick={() => {
                      localStorage.removeItem("bitdex_customer_trades");
                      setSimulatedTrades([]);
                    }}
                    className="text-[10px] font-mono text-slate-500 hover:text-rose-400 transition-colors"
                  >
                    Clear History
                  </button>
                )}
              </div>

              {simulatedTrades.length === 0 ? (
                <div className="py-12 text-center text-slate-500 text-xs font-mono border border-dashed border-slate-800 rounded-2xl space-y-2">
                  <Clock className="w-8 h-8 text-slate-600 mx-auto" />
                  <p className="font-semibold text-slate-400">No execution fills recorded yet</p>
                  <p className="text-[11px] text-slate-500 max-w-md mx-auto">
                    When you stage and confirm orders through the Trade Execution Wizard, verified execution receipts and fill logs will be preserved here.
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-950/50">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-800">
                      <tr>
                        <th className="p-3">Order ID</th>
                        <th className="p-3">Pair</th>
                        <th className="p-3">Side</th>
                        <th className="p-3">Fill Price</th>
                        <th className="p-3">Quantity</th>
                        <th className="p-3">Notional</th>
                        <th className="p-3">Fee (0.10%)</th>
                        <th className="p-3">Status</th>
                        <th className="p-3">Timestamp (UTC)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {simulatedTrades.map((t, idx) => (
                        <tr key={idx} className="hover:bg-slate-900/40">
                          <td className="p-3 text-cyan-300 font-bold">{t.order_id}</td>
                          <td className="p-3 text-white font-bold">{t.symbol}</td>
                          <td className="p-3">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              t.side === "BUY" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                            }`}>
                              {t.side}
                            </span>
                          </td>
                          <td className="p-3 text-white font-bold">${Number(t.price).toLocaleString()}</td>
                          <td className="p-3 text-slate-300">{t.quantity}</td>
                          <td className="p-3 text-slate-300">${Number(t.notional || 0).toFixed(2)}</td>
                          <td className="p-3 text-amber-400">${Number(t.fee || 0).toFixed(4)}</td>
                          <td className="p-3">
                            <span className="px-2 py-0.5 rounded text-[9px] bg-emerald-950 text-emerald-300 border border-emerald-500/30 font-bold">
                              {t.status || "FILLED"}
                            </span>
                          </td>
                          <td className="p-3 text-slate-400">{new Date(t.timestamp).toUTCString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {/* ─── CREATE SUPPORT TICKET MODAL ──────────────────────────── */}
      {isCreateTicketOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl overflow-hidden p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <LifeBuoy className="w-5 h-5 text-emerald-400" />
                <h3 className="text-sm font-bold text-white">Open Support Ticket</h3>
              </div>
              <button onClick={() => setIsCreateTicketOpen(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateTicket} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Subject</label>
                <input
                  type="text"
                  required
                  value={newTicketSubject}
                  onChange={(e) => setNewTicketSubject(e.target.value)}
                  placeholder="Brief summary of your inquiry"
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Category</label>
                <select
                  value={newTicketCategory}
                  onChange={(e) => setNewTicketCategory(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500"
                >
                  <option value="TECHNICAL">Technical & Signals</option>
                  <option value="EXCHANGE_CONNECTION">Exchange API Connections</option>
                  <option value="BILLING">Billing & Binance Pay Top-Ups</option>
                  <option value="SECURITY">Account Security & 2FA</option>
                  <option value="GENERAL">General Inquiry</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Detailed Message</label>
                <textarea
                  required
                  rows={4}
                  value={newTicketMessage}
                  onChange={(e) => setNewTicketMessage(e.target.value)}
                  placeholder="Provide details about your question, exchange name, or transaction ID..."
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500 font-mono"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateTicketOpen(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-mono cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingTicket}
                  className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold font-mono transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2"
                >
                  {isSubmittingTicket && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Submit Ticket
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ─── IN-APP CONFIRMATION MODAL (REPLACES BROWSER CONFIRM) ──── */}
      {confirmModal && confirmModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">{confirmModal.title}</h3>
                <p className="text-xs text-slate-400 mt-1">{confirmModal.message}</p>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setConfirmModal(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-mono cursor-pointer transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmModal.onConfirm}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold font-mono cursor-pointer transition-colors"
              >
                {confirmModal.confirmText || "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── ACCOUNT SETTINGS: PROFILE MODAL ───────────────────────── */}
      {activeAccountModal === "PROFILE" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl p-6 space-y-4 font-mono">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <User className="w-4 h-4 text-emerald-400" />
                Customer Account Profile
              </h3>
              <button onClick={() => setActiveAccountModal(null)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
                <span className="text-[10px] text-slate-500 block uppercase font-bold">Database User ID</span>
                <span className="text-cyan-300 font-bold break-all">{profile?.user_id || "USR-UNKNOWN"}</span>
              </div>
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
                <span className="text-[10px] text-slate-500 block uppercase font-bold">Username</span>
                <span className="text-white font-bold">{profile?.username || "Not Set"}</span>
              </div>
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
                <span className="text-[10px] text-slate-500 block uppercase font-bold">Email Address</span>
                <span className="text-white font-bold">{profile?.email}</span>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
                  <span className="text-[10px] text-slate-500 block uppercase font-bold">Account Role</span>
                  <span className="text-emerald-400 font-bold">{profile?.role || "CUSTOMER"}</span>
                </div>
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
                  <span className="text-[10px] text-slate-500 block uppercase font-bold">2FA Status</span>
                  <span className={profile?.two_factor_enabled ? "text-emerald-400 font-bold" : "text-amber-400 font-bold"}>
                    {profile?.two_factor_enabled ? "Enabled (TOTP)" : "Disabled"}
                  </span>
                </div>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setActiveAccountModal(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white text-xs font-mono transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── ACCOUNT SETTINGS: CHANGE USERNAME MODAL ────────────────── */}
      {activeAccountModal === "CHANGE_USERNAME" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl p-6 space-y-4 font-mono">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Edit3 className="w-4 h-4 text-emerald-400" />
                Change Username
              </h3>
              <button onClick={() => setActiveAccountModal(null)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleChangeUsername} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Proposed New Username</label>
                <input
                  type="text"
                  required
                  value={newUsernameInput}
                  onChange={(e) => setNewUsernameInput(e.target.value)}
                  placeholder="e.g. QuantitativeTrader"
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500 font-mono"
                />
                <span className="text-[10px] text-slate-500 mt-1 block">
                  3-30 characters. Letters, numbers, underscores, periods, and hyphens.
                </span>
              </div>

              {usernameError && (
                <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs">
                  {usernameError}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setActiveAccountModal(null)}
                  className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-mono cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isUpdatingUsername || !newUsernameInput.trim()}
                  className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold font-mono transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2"
                >
                  {isUpdatingUsername && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Update Username
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ─── ACCOUNT SETTINGS: CHANGE EMAIL MODAL ───────────────────── */}
      {activeAccountModal === "CHANGE_EMAIL" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl p-6 space-y-4 font-mono">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Mail className="w-4 h-4 text-emerald-400" />
                Change Email Address
              </h3>
              <button onClick={() => setActiveAccountModal(null)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            {emailChangeStep === "INPUT" ? (
              <form onSubmit={handleInitiateEmailChange} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Current Email</label>
                  <div className="px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-400">
                    {profile?.email}
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Proposed New Email Address</label>
                  <input
                    type="email"
                    required
                    value={newEmailInput}
                    onChange={(e) => setNewEmailInput(e.target.value)}
                    placeholder="e.g. new.email@domain.com"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500 font-mono"
                  />
                  <span className="text-[10px] text-slate-500 mt-1 block">
                    A 6-digit OTP code will be sent to the new address from go@bitdex.ltd to verify ownership.
                  </span>
                </div>

                {emailChangeError && (
                  <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs">
                    {emailChangeError}
                  </div>
                )}

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setActiveAccountModal(null)}
                    className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-mono cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isInitiatingEmailChange || !newEmailInput.trim()}
                    className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold font-mono transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2"
                  >
                    {isInitiatingEmailChange && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                    Send Verification OTP
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleVerifyEmailChange} className="space-y-4">
                <div className="p-3.5 rounded-xl bg-emerald-950/40 border border-emerald-500/30 text-emerald-300 text-xs">
                  <p className="font-bold">Verification code sent!</p>
                  <p className="text-[11px] mt-1 text-emerald-200">
                    We sent a 6-digit code to <strong>{newEmailInput}</strong>. Please enter it below.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Enter 6-Digit OTP Code</label>
                  <input
                    type="text"
                    maxLength={6}
                    required
                    value={emailOtpInput}
                    onChange={(e) => setEmailOtpInput(e.target.value.replace(/[^0-9]/g, ""))}
                    placeholder="123456"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-base text-center tracking-widest text-emerald-400 font-bold focus:outline-none focus:border-emerald-500 font-mono"
                  />
                </div>

                {emailChangeError && (
                  <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs">
                    {emailChangeError}
                  </div>
                )}

                <div className="flex justify-between items-center pt-2">
                  <button
                    type="button"
                    onClick={() => setEmailChangeStep("INPUT")}
                    className="text-xs text-slate-400 hover:text-white underline cursor-pointer"
                  >
                    Back
                  </button>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setActiveAccountModal(null)}
                      className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-mono cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isVerifyingEmailChange || emailOtpInput.length !== 6}
                      className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold font-mono transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2"
                    >
                      {isVerifyingEmailChange && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                      Confirm & Update Email
                    </button>
                  </div>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* ─── EMAIL DUPLICATE MODAL (EXACT SPEC REQUIREMENT) ─────────── */}
      {emailDuplicateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-slate-900 border border-rose-500/40 rounded-3xl shadow-2xl p-6 space-y-4 font-mono">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-rose-500/20 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">Email Already Registered</h3>
                <p className="text-xs text-rose-300 mt-1 font-sans">
                  This email address is already registered. Please use another email.
                </p>
              </div>
            </div>
            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setEmailDuplicateModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white text-xs font-mono transition-colors cursor-pointer"
              >
                OK
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── ACCOUNT SETTINGS: CHANGE PASSWORD MODAL ────────────────── */}
      {activeAccountModal === "CHANGE_PASSWORD" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl p-6 space-y-4 font-mono">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Lock className="w-4 h-4 text-emerald-400" />
                Change Password
              </h3>
              <button onClick={() => setActiveAccountModal(null)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleChangePassword} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Current Password</label>
                <input
                  type="password"
                  required
                  value={currentPassInput}
                  onChange={(e) => setCurrentPassInput(e.target.value)}
                  placeholder="Enter current password"
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">New Password</label>
                <input
                  type="password"
                  required
                  value={newPassInput}
                  onChange={(e) => setNewPassInput(e.target.value)}
                  placeholder="At least 8 characters"
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Confirm New Password</label>
                <input
                  type="password"
                  required
                  value={confirmPassInput}
                  onChange={(e) => setConfirmPassInput(e.target.value)}
                  placeholder="Re-type new password"
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-emerald-500 font-mono"
                />
              </div>

              {passwordChangeError && (
                <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs">
                  {passwordChangeError}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setActiveAccountModal(null)}
                  className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-mono cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isChangingPassword || !currentPassInput || !newPassInput}
                  className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold font-mono transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2"
                >
                  {isChangingPassword && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Change Password
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ─── BINANCE PAY MODAL ─────────────────────────────────────── */}
      <BinancePayModal
        isOpen={isPayModalOpen}
        onClose={() => setIsPayModalOpen(false)}
        token={token}
        type={payModalType}
        amount={payModalAmount}
        onSuccess={() => {
          fetchCustomerData();
          setIsPayModalOpen(false);
          setFeedback({ type: "success", message: "Binance Pay transaction initiated or completed successfully!" });
        }}
      />
    </div>
  );
}
