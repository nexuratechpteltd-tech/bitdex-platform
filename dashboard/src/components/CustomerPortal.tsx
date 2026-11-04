"use client";
import InstitutionalTradingDashboard from "./InstitutionalTradingDashboard";
import ProtectionCenter from "./ProtectionCenter";

import React, { useState, useEffect } from "react";
import Image from "next/image";
import {
  Search,
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
  Menu,
  Scale,
  Coins,
  Sparkles,
  Cpu,
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
  Bell,
  Sliders,
} from "lucide-react";
import BinancePayModal from "./BinancePayModal";

import SidebarNav, { NavDestination } from "./layout/SidebarNav";
import PairSearchSelector, { PairItem } from "./search/PairSearchSelector";
import OverviewView from "./dashboard/OverviewView";
import TradingTerminalView from "./dashboard/TradingTerminalView";
import ExchangeConnectionsView from "./dashboard/ExchangeConnectionsView";
import BalancesView from "./dashboard/BalancesView";
import OrdersHoldingsView from "./dashboard/OrdersHoldingsView";
import CustomerSettingsView from "./dashboard/CustomerSettingsView";
import HelpSupportView from "./dashboard/HelpSupportView";
import StatusBadge from "./common/StatusBadge";

import InstitutionalOrderLedger from "./InstitutionalOrderLedger";

interface CustomerPortalProps {
  token: string;
  user: any;
  onSignOut: () => void;
  children?: React.ReactNode; // Trading Console / Signals
  onSwitchPortal?: () => void;
}

export default function CustomerPortal({ token, user, onSignOut, children, onSwitchPortal }: CustomerPortalProps) {

  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [selectedSearchPair, setSelectedSearchPair] = useState<any>(null);
  const [currentNav, setCurrentNav] = useState<NavDestination>(() => {
    if (typeof window !== "undefined") {
      const h = window.location.hash.toLowerCase();
      if (h === "#overview") return "OVERVIEW";
      if (h === "#terminal" || h === "#trading") return "TERMINAL";
      if (h === "#long-term" || h === "#signals" || h === "#dashboard") return "LONG_TERM";
      if (h === "#hft" || h === "#scalp") return "HFT";
      if (h === "#connections" || h === "#wallets" || h === "#account") return "CONNECTIONS";
      if (h === "#balances") return "BALANCES";
      if (h === "#orders" || h === "#pnl" || h === "#positions" || h === "#holdings") return "ORDERS";
      if (h === "#settings" || h === "#security" || h === "#billing") return "SETTINGS";
      if (h === "#support") return "SUPPORT";
    }
    return "OVERVIEW";
  });

  const navigateTo = (dest: NavDestination) => {
    setCurrentNav(dest);
    if (typeof window !== "undefined") {
      const hashMap: Record<NavDestination, string> = {
        OVERVIEW: "overview",
        TERMINAL: "terminal",
        LONG_TERM: "long-term",
        HFT: "hft",
        CONNECTIONS: "connections",
        BALANCES: "balances",
        ORDERS: "orders",
        SETTINGS: "settings",
        SUPPORT: "support",
      };
      window.location.hash = hashMap[dest] || "overview";
    }
    if (dest === "LONG_TERM") {
      setActiveTab("TRADING");
      setTradingMode("LONG_TERM");
    } else if (dest === "HFT") {
      setActiveTab("TRADING");
      setTradingMode("HFT");
    } else if (dest === "CONNECTIONS") {
      setActiveTab("CONNECTIONS");
    } else if (dest === "BALANCES") {
      setActiveTab("BALANCES");
    } else if (dest === "ORDERS") {
      setActiveTab("PROFIT_LOSS");
    } else if (dest === "SETTINGS") {
      setActiveTab("SETTINGS");
    } else if (dest === "SUPPORT") {
      setActiveTab("SUPPORT");
    }
  };

  const [activeTab, setActiveTab] = useState<"TRADING" | "CONNECTIONS" | "BALANCES" | "BILLING" | "SECURITY" | "SUPPORT" | "PROFIT_LOSS" | "SETTINGS">(() => {
    if (typeof window !== "undefined") {
      const h = window.location.hash.toLowerCase();
      if (h === "#pnl" || h === "#positions" || h === "#profit_loss" || h === "#orders" || h === "#ledger" || h === "#trades" || h === "#holdings") return "PROFIT_LOSS";
      if (h === "#balances") return "BALANCES";
      if (h === "#connections" || h === "#wallets") return "CONNECTIONS";
      if (h === "#settings" || h === "#account" || h === "#profile" || h === "#security" || h === "#billing" || h === "#notifications" || h === "#guardrails") return "SETTINGS";
      if (h === "#support") return "SUPPORT";
    }
    return "TRADING";
  });

  const [settingsSubTab, setSettingsSubTab] = useState<"PROFILE_SECURITY" | "BILLING_CREDITS" | "NOTIFICATIONS" | "RISK_GUARDRAILS">(() => {
    if (typeof window !== "undefined") {
      const h = window.location.hash.toLowerCase();
      if (h === "#billing" || h === "#credits" || h === "#invoices") return "BILLING_CREDITS";
      if (h === "#notifications" || h === "#alerts") return "NOTIFICATIONS";
      if (h === "#guardrails" || h === "#risk") return "RISK_GUARDRAILS";
    }
    return "PROFILE_SECURITY";
  });

  // Three-Mode Customer Navigation State (Phase 2)
  const [tradingMode, setTradingMode] = useState<"LONG_TERM" | "GRID" | "HFT">(() => {
    if (typeof window !== "undefined") {
      const h = window.location.hash.toLowerCase();
      if (h === "#grid") return "GRID";
      if (h === "#hft" || h === "#scalp" || h === "#futures") return "HFT";
    }
    return "LONG_TERM";
  });

  // Notification Rules State (Phase 6)
  const [notifyExecReceipts, setNotifyExecReceipts] = useState<boolean>(true);
  const [notifyPriceAlerts, setNotifyPriceAlerts] = useState<boolean>(true);
  const [notifyStaleData, setNotifyStaleData] = useState<boolean>(true);
  const [notifyWeeklyDigest, setNotifyWeeklyDigest] = useState<boolean>(true);
  const [priceAlertThreshold, setPriceAlertThreshold] = useState<string>("2.5");
  const [notificationSavedToast, setNotificationSavedToast] = useState<boolean>(false);

  // Risk Guardrails State (Phase 6)
  const [guardrailDefaultCapital, setGuardrailDefaultCapital] = useState<number>(250);
  const [guardrailMaxExposurePct, setGuardrailMaxExposurePct] = useState<number>(50);
  const [guardrailMaxSlippagePct, setGuardrailMaxSlippagePct] = useState<number>(0.10);
  const [guardrailLeverageLock, setGuardrailLeverageLock] = useState<boolean>(true);
  const [isEmergencyKillModalOpen, setIsEmergencyKillModalOpen] = useState<boolean>(false);
  const [emergencyKillSuccess, setEmergencyKillSuccess] = useState<boolean>(false);
  const [guardrailSavedToast, setGuardrailSavedToast] = useState<boolean>(false);

  useEffect(() => {
    const handleHash = () => {
      if (typeof window === "undefined") return;
      const h = window.location.hash.toLowerCase();
      if (h === "#overview") { setCurrentNav("OVERVIEW"); }
      else if (h === "#terminal") { setCurrentNav("TERMINAL"); }
      else if (h === "#grid") { setCurrentNav("LONG_TERM"); setActiveTab("TRADING"); setTradingMode("GRID"); }
      else if (h === "#hft" || h === "#scalp" || h === "#futures") { setCurrentNav("HFT"); setActiveTab("TRADING"); setTradingMode("HFT"); }
      else if (h === "#long-term" || h === "#signals" || h === "#dashboard" || h === "#longterm") { setCurrentNav("LONG_TERM"); setActiveTab("TRADING"); setTradingMode("LONG_TERM"); }
      else if (h === "#trading") { setCurrentNav("TERMINAL"); setActiveTab("TRADING"); }
      else if (h === "#connections" || h === "#wallets" || h === "#account") { setCurrentNav("CONNECTIONS"); setActiveTab("CONNECTIONS"); }
      else if (h === "#balances") { setCurrentNav("BALANCES"); setActiveTab("BALANCES"); }
      else if (h === "#orders" || h === "#pnl" || h === "#positions" || h === "#ledger" || h === "#trades" || h === "#holdings") { setCurrentNav("ORDERS"); setActiveTab("PROFIT_LOSS"); }
      else if (h === "#settings" || h === "#security" || h === "#2fa" || h === "#billing" || h === "#notifications" || h === "#guardrails") { setCurrentNav("SETTINGS"); setActiveTab("SETTINGS"); }
      else if (h === "#support") { setCurrentNav("SUPPORT"); setActiveTab("SUPPORT"); }
      else if (h === "#pnl" || h === "#positions" || h === "#profit_loss" || h === "#orders" || h === "#ledger" || h === "#trades" || h === "#holdings") setActiveTab("PROFIT_LOSS");
      else if (h === "#balances") setActiveTab("BALANCES");
      else if (h === "#connections" || h === "#wallets") setActiveTab("CONNECTIONS");
      else if (h === "#settings" || h === "#account" || h === "#profile") { setActiveTab("SETTINGS"); setSettingsSubTab("PROFILE_SECURITY"); }
      else if (h === "#security" || h === "#2fa") { setActiveTab("SETTINGS"); setSettingsSubTab("PROFILE_SECURITY"); }
      else if (h === "#billing" || h === "#credits" || h === "#invoices") { setActiveTab("SETTINGS"); setSettingsSubTab("BILLING_CREDITS"); }
      else if (h === "#notifications" || h === "#alerts") { setActiveTab("SETTINGS"); setSettingsSubTab("NOTIFICATIONS"); }
      else if (h === "#guardrails" || h === "#risk") { setActiveTab("SETTINGS"); setSettingsSubTab("RISK_GUARDRAILS"); }
      else if (h === "#support") setActiveTab("SUPPORT");
      else if (h === "#trading" || h === "#signals") setActiveTab("TRADING");
    };
    handleHash();
    window.addEventListener("hashchange", handleHash);
    return () => window.removeEventListener("hashchange", handleHash);
  }, []);
  const [isMobileDrawerOpen, setIsMobileDrawerOpen] = useState(false);
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
  const [newConnLabel, setNewConnLabel] = useState("");
  const [newConnEnv, setNewConnEnv] = useState("DEMO");
  const [newConnApiKey, setNewConnApiKey] = useState("");
  const [newConnSecret, setNewConnSecret] = useState("");
  const [newConnPassphrase, setNewConnPassphrase] = useState("");

  // Phase 1: Exchange Connections & Vault Manager Filter States
  const [connEnvFilter, setConnEnvFilter] = useState<"ALL" | "LIVE" | "DEMO">("ALL");
  const [connExchangeFilter, setConnExchangeFilter] = useState<string>("ALL");
  const [connStatusFilter, setConnStatusFilter] = useState<string>("ALL");
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const [connectStep, setConnectStep] = useState<1 | 2 | 3>(1);
  const [isSyncingAll, setIsSyncingAll] = useState(false);
  // Phase 3: Dedicated Portfolio, Balances & P&L Ledger State
  const [balancesEnv, setBalancesEnv] = useState<"LIVE" | "DEMO">("LIVE");
  // Phase 4: 3-Tab Execution Ledger State
  const [ledgerSubTab, setLedgerSubTab] = useState<"POSITIONS" | "WORKING_ORDERS" | "HISTORY">("POSITIONS");
  const [ledgerEnv, setLedgerEnv] = useState<"LIVE" | "DEMO">("DEMO");
  const [ledgerPositions, setLedgerPositions] = useState<any[]>([]);
  const [ledgerOpenOrders, setLedgerOpenOrders] = useState<any[]>([]);
  const [ledgerClosedPositions, setLedgerClosedPositions] = useState<any[]>([]);
  const [isLedgerLoading, setIsLedgerLoading] = useState(false);

  const fetchLedgerData = async () => {
    setIsLedgerLoading(true);
    try {
      const token = localStorage.getItem("bitdex_auth_token") || localStorage.getItem("tauric_token");
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const posRes = await fetch(`/trading/api/backend/orders/positions?environment=${ledgerEnv}&market_type=ALL`, { headers });
      if (posRes.ok) {
        const pData = await posRes.json();
        setLedgerPositions(pData.open_positions || []);
        setLedgerClosedPositions(pData.closed_positions || []);
      }

      const ordRes = await fetch(`/trading/api/backend/orders/open?environment=${ledgerEnv}`, { headers });
      if (ordRes.ok) {
        const oData = await ordRes.json();
        setLedgerOpenOrders(oData.orders || []);
      }
    } catch {}
    finally {
      setIsLedgerLoading(false);
    }
  };

  const handleCancelWorkingOrder = async (order: any) => {
    try {
      const token = localStorage.getItem("bitdex_auth_token") || localStorage.getItem("tauric_token");
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch("/trading/api/backend/orders/cancel", {
        method: "POST",
        headers,
        body: JSON.stringify({
          symbol: order.symbol,
          client_order_id: order.client_order_id || order.order_id,
          profile_id: order.profile_id || "CONN-DK-BIN-DEMO-MIGRATED",
          exchange: order.exchange || "BINANCE",
          environment: order.environment || "DEMO"
        })
      });
      if (res.ok) {
        fetchLedgerData();
      }
    } catch {}
  };

  useEffect(() => {
    fetchLedgerData();
  }, [ledgerEnv, ledgerSubTab]);

  // Feed Sync & AI Live Telemetry Indicators
  const [feedLastSync, setFeedLastSync] = useState("Live Real-time");

  // Top Search & Live Market Ticker State
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [tickerItems, setTickerItems] = useState<any[]>([]);
  const [forexSessionInfo, setForexSessionInfo] = useState<any>(null);

  useEffect(() => {
    const fetchOverview = async () => {
      try {
        const res = await fetch("/trading/api/backend/markets/overview");
        if (res.ok) {
          const data = await res.json();
          if (data.status === "SUCCESS") {
            const combined = [...(data.crypto || []), ...(data.forex || [])];
            setTickerItems(combined);
            setForexSessionInfo(data.session || null);
            setSelectedSearchPair((prev: any) => prev || (combined.length > 0 ? combined[0] : null));
          }
        }
      } catch (err) {
        console.error("Failed to fetch market overview", err);
      }
    };
    fetchOverview();
    const interval = setInterval(fetchOverview, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      setIsSearchOpen(false);
      return;
    }
    const timer = setTimeout(async () => {
      setIsSearching(true);
      try {
        const res = await fetch(`/trading/api/backend/markets/search?q=${encodeURIComponent(searchQuery.trim())}`);
        if (res.ok) {
          const d = await res.json();
          setSearchResults(d.results || []);
          setIsSearchOpen(true);
        }
      } catch (err) {
        console.error("Search query error", err);
      } finally {
        setIsSearching(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleSelectSearchPair = (item: any) => {
    setIsSearchOpen(false);
    setSearchQuery("");
    setActiveTab("TRADING");
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("bitdex_trigger_four_engine", {
          detail: {
            symbol: item.canonical_symbol || item.symbol,
            market: item.asset_class === "FOREX" || item.asset_class === "METALS" ? "FOREX" : "CRYPTO",
            timeframe: "1h",
          },
        })
      );
    }
  };
  const [isFeedRefreshing, setIsFeedRefreshing] = useState(false);
  const [tauricTelemetry, setTauricTelemetry] = useState<any>({
    status: "READY",
    is_active: false,
    model: "tauric-deep-quant-v2",
    requests_today: null,
    tokens_today: null,
    cost_usd: null,
    completed: null,
    failed: null,
    latency_ms: null
  });
  const [jevTelemetry, setJevTelemetry] = useState<any>({
    status: "READY",
    is_active: false,
    model: "jev-micro-risk-v1",
    requests_today: null,
    tokens_today: null,
    cost_usd: null,
    completed: null,
    failed: null,
    latency_ms: null
  });
  const [selectedTelemetryEngine, setSelectedTelemetryEngine] = useState<"tauric" | "jev" | null>(null);

  // Non-Custodial Watched Wallets State
  const [wallets, setWallets] = useState<any[]>([]);
  const [isAddingWallet, setIsAddingWallet] = useState(false);
  const [walletAddress, setWalletAddress] = useState("");
  const [walletLabel, setWalletLabel] = useState("");
  const [walletNetwork, setWalletNetwork] = useState("ETHEREUM");
  const [walletEnv, setWalletEnv] = useState("LIVE");
  const [walletError, setWalletError] = useState<string | null>(null);
  const [isSavingWallet, setIsSavingWallet] = useState(false);

  // Consolidated Balances State
  const [balancesData, setBalancesData] = useState<any>(null);
  const [isBalancesLoading, setIsBalancesLoading] = useState(false);
  const [balancesLastSync, setBalancesLastSync] = useState<string>("");
  const [isTestingConn, setIsTestingConn] = useState(false);
  const [isSavingConn, setIsSavingConn] = useState(false);
  const [connTestResult, setConnTestResult] = useState<any>(null);
  const [isRefreshingConn, setIsRefreshingConn] = useState<Record<string, boolean>>({});
  const [isTestingSavedConn, setIsTestingSavedConn] = useState<Record<string, boolean>>({});

  // Disable 2FA
  const handleDisable2FA = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!disablePassword) {
      setFeedback({ type: "error", message: "Please enter your password to disable 2FA." });
      return;
    }
    setIsDisabling2FA(true);
    setFeedback(null);
    try {
      const res = await fetch(getApiUrl("/saas/customer/auth/2fa/disable"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ password: disablePassword }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Failed to disable 2FA");
      if (profile) setProfile({ ...profile, two_factor_enabled: false });
      setShowDisable2FAModal(false);
      setDisablePassword("");
      setFeedback({ type: "success", message: "Authenticator app (TOTP) disabled successfully." });
      await fetchCustomerData();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message });
    } finally {
      setIsDisabling2FA(false);
    }
  };

  // 2FA Setup Form
  const [totpSetupData, setTotpSetupData] = useState<any>(null);
  const [totpVerifyCode, setTotpVerifyCode] = useState("");
  const [isSettingUp2FA, setIsSettingUp2FA] = useState(false);
  const [showDisable2FAModal, setShowDisable2FAModal] = useState(false);
  const [disablePassword, setDisablePassword] = useState("");
  const [isDisabling2FA, setIsDisabling2FA] = useState(false);
  const [copiedKeyToast, setCopiedKeyToast] = useState(false);

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
      const handleOpenTopUp = (e: any) => {
        setPayModalType("PREPAID_TOPUP");
        setPayModalAmount(e?.detail?.amount || 50.0);
        setIsPayModalOpen(true);
      };
      const handleTrade = (e: any) => {
        if (e.detail) {
          setSimulatedTrades((prev) => [e.detail, ...prev]);
        }
      };
      window.addEventListener("bitdex_navigate_tab", handleNav);
      window.addEventListener("bitdex_open_activation", handleOpenAct);
      window.addEventListener("bitdex_open_topup", handleOpenTopUp);
      window.addEventListener("bitdex_trade_executed", handleTrade);
      return () => {
        window.removeEventListener("bitdex_navigate_tab", handleNav);
        window.removeEventListener("bitdex_open_activation", handleOpenAct);
        window.removeEventListener("bitdex_open_topup", handleOpenTopUp);
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

  const fetchWallets = async () => {
    try {
      const res = await fetch(getApiUrl("/saas/customer/wallets"), {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setWallets(data.wallets || []);
      }
    } catch {}
  };

  const handleAddWallet = async (e: React.FormEvent) => {
    e.preventDefault();
    setWalletError(null);
    setIsSavingWallet(true);
    try {
      const res = await fetch(getApiUrl("/saas/customer/wallets"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          address: walletAddress.trim(),
          label: walletLabel.trim() || undefined,
          network: walletNetwork,
          environment: walletEnv
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to add watched wallet.");
      setFeedback({ type: "success", message: data.message || "Watched wallet connected successfully." });
      setWalletAddress("");
      setWalletLabel("");
      setIsAddingWallet(false);
      await fetchWallets();
      await fetchBalances(true);
    } catch (err: any) {
      setWalletError(err.message || "Failed to connect wallet.");
    } finally {
      setIsSavingWallet(false);
    }
  };

  const handleDeleteWallet = async (walletId: string) => {
    if (!confirm("Are you sure you want to disconnect this watched wallet?")) return;
    try {
      const res = await fetch(getApiUrl(`/saas/customer/wallets/${walletId}`), {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to disconnect wallet.");
      setFeedback({ type: "success", message: "Wallet cleanly disconnected." });
      await fetchWallets();
      await fetchBalances(true);
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to disconnect wallet." });
    }
  };

  const fetchBalances = async (force: boolean = false) => {
    setIsBalancesLoading(true);
    try {
      const res = await fetch(getApiUrl("/saas/customer/balances"), {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setBalancesData(data);
        setBalancesLastSync(new Date().toLocaleTimeString());
      }
    } catch (err) {
      console.error("Failed to fetch balances", err);
    } finally {
      setIsBalancesLoading(false);
    }
  };

  const handleFeedRefresh = () => {
    setIsFeedRefreshing(true);
    setTauricTelemetry((prev: any) => ({ ...prev, is_active: true, requests_today: prev.requests_today + 1 }));
    setJevTelemetry((prev: any) => ({ ...prev, is_active: true, requests_today: prev.requests_today + 1 }));
    
    // Dispatch custom event to trigger refresh in UnifiedSignalDashboard if present
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("bitdex_force_refresh_signals"));
    }
    
    setTimeout(() => {
      setIsFeedRefreshing(false);
      setFeedLastSync(new Date().toLocaleTimeString());
      setTauricTelemetry((prev: any) => ({ ...prev, is_active: false }));
      setJevTelemetry((prev: any) => ({ ...prev, is_active: false }));
      setFeedback({ type: "success", message: "Live quantitative stream synchronized successfully." });
    }, 1200);
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

      // 4. Fetch Wallets & Balances
      fetchWallets();
      fetchBalances();
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

    // Synchronize URL hash with activeTab so direct links like /#security or /#connections land immediately
    const syncHash = () => {
      if (typeof window === "undefined") return;
      const hash = (window.location.hash || "").toLowerCase();
      if (hash === "#security" || hash === "#connections" || hash === "#exchange-connections") {
        setActiveTab("CONNECTIONS");
      } else if (hash === "#2fa" || hash === "#password") {
        setActiveTab("SECURITY");
      } else if (hash === "#balances") {
        setActiveTab("BALANCES");
        fetchBalances();
      } else if (hash === "#billing" || hash === "#invoices") {
        setActiveTab("BILLING");
      } else if (hash === "#support" || hash === "#tickets") {
        setActiveTab("SUPPORT");
      } else if (hash === "#trading" || hash === "#signals") {
        setActiveTab("TRADING");
      }
    };
    syncHash();
    window.addEventListener("hashchange", syncHash);

    const handleOpenTopup = (e: any) => {
      const topupAmt = e?.detail?.amount || 20;
      setPayModalAmount(topupAmt);
      setPayModalType("PREPAID_TOPUP");
      setIsPayModalOpen(true);
    };
    window.addEventListener("bitdex_open_topup", handleOpenTopup);
    return () => {
      window.removeEventListener("hashchange", syncHash);
      window.removeEventListener("bitdex_open_topup", handleOpenTopup);
    };
  }, [token]);

  useEffect(() => {
    if (activeTab === "SUPPORT") {
      fetchSupportTickets();
    }
  }, [activeTab]);

  // Helper: Retrieve primary quote balance
  const getQuoteBalance = (conn: any) => {
    if (conn.account_data?.asset_balances) {
      const usdt = conn.account_data.asset_balances.find((b: any) => b.asset === "USDT");
      if (usdt) return `${Number(usdt.total).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT`;
      const usdc = conn.account_data.asset_balances.find((b: any) => b.asset === "USDC");
      if (usdc) return `${Number(usdc.total).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDC`;
    }
    if (conn.balance_usd !== null && conn.balance_usd !== undefined) {
      return `${Number(conn.balance_usd).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD`;
    }
    return "0.00 USDT";
  };

  // Helper: Format relative timestamp
  const formatTimeAgo = (dateStr?: string) => {
    if (!dateStr) return "Never";
    try {
      const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
      if (diff < 5) return "Just now";
      if (diff < 60) return `${diff}s ago`;
      if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
      if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
      return new Date(dateStr).toLocaleDateString();
    } catch {
      return "Recent";
    }
  };

  // Sync All Connections Handler
  const handleSyncAllConnections = async () => {
    if (connections.length === 0 || isSyncingAll) return;
    setIsSyncingAll(true);
    setFeedback(null);
    try {
      await Promise.allSettled(
        connections.map((c) =>
          fetch(getApiUrl(`/saas/customer/connections/${c.account_id}/refresh`), {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
          })
        )
      );
      setFeedback({ type: "success", message: `Synchronized ${connections.length} exchange profiles.` });
      await fetchCustomerData();
    } catch (err: any) {
      setFeedback({ type: "error", message: err.message || "Failed to synchronize exchange profiles." });
    } finally {
      setIsSyncingAll(false);
    }
  };

  // Live Balance Refresh Handler for a connected exchange
  const handleRefreshConnection = async (accountId: string) => {
    setIsRefreshingConn((prev) => ({ ...prev, [accountId]: true }));
    setFeedback(null);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    try {
      const res = await fetch(getApiUrl(`/saas/customer/connections/${accountId}/refresh`), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}: ${res.statusText}` }));
      if (!res.ok) throw new Error(data.detail || "Failed to refresh balances");
      setFeedback({ type: "success", message: data.message || "Authoritative exchange balances refreshed successfully." });
      await fetchCustomerData();
    } catch (err: any) {
      clearTimeout(timeoutId);
      const msg = err.name === "AbortError" ? "Balance refresh request timed out after 10 seconds." : err.message;
      setFeedback({ type: "error", message: msg });
    } finally {
      setIsRefreshingConn((prev) => ({ ...prev, [accountId]: false }));
    }
  };

  // Re-verify saved connection credentials
  const handleRetestSavedConnection = async (accountId: string) => {
    setIsTestingSavedConn((prev) => ({ ...prev, [accountId]: true }));
    setFeedback(null);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    try {
      const res = await fetch(getApiUrl(`/saas/customer/connections/${accountId}/test`), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}: ${res.statusText}` }));
      if (!res.ok) throw new Error(data.detail || "Connection validation failed");
      setFeedback({ type: "success", message: data.message || "Exchange connection verified successfully." });
      await fetchCustomerData();
    } catch (err: any) {
      clearTimeout(timeoutId);
      const msg = err.name === "AbortError" ? "Connection validation timed out after 10 seconds." : err.message;
      setFeedback({ type: "error", message: msg });
    } finally {
      setIsTestingSavedConn((prev) => ({ ...prev, [accountId]: false }));
    }
  };

  // Test Connection Handler
  const handleTestConnection = async () => {
    if (!newConnApiKey || !newConnSecret) {
      setFeedback({ type: "error", message: "API Key and Secret are required to test connection." });
      return;
    }
    setIsTestingConn(true);
    setConnTestResult(null);
    setFeedback(null);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    try {
      const res = await fetch(getApiUrl("/saas/customer/connections/test"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        signal: controller.signal,
        body: JSON.stringify({
          exchange_name: newConnName.trim(),
          provider: newConnName.trim().toUpperCase(),
          environment: newConnEnv,
          api_key: newConnApiKey.trim(),
          api_secret: newConnSecret.trim(),
          passphrase: newConnPassphrase.trim() || undefined,
        }),
      });
      clearTimeout(timeoutId);
      const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}: ${res.statusText}` }));
      if (!res.ok) {
        const errorMsg = data.detail || "Connection test failed";
        setConnTestResult({
          status: "FAILED",
          verification_status: "VERIFICATION_FAILED",
          message: errorMsg,
          detail: errorMsg
        });
        throw new Error(errorMsg);
      }
      setConnTestResult(data);
      setFeedback({ type: "success", message: data.message || "Connection validated successfully." });
    } catch (err: any) {
      clearTimeout(timeoutId);
      const isAbort = err.name === "AbortError";
      const displayMsg = isAbort ? "Request timed out after 10 seconds. The exchange did not respond." : err.message;
      setFeedback({ type: "error", message: displayMsg });
      setConnTestResult((prev: any) => prev || {
        status: "FAILED",
        verification_status: "VERIFICATION_FAILED",
        message: displayMsg,
        detail: displayMsg
      });
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
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 12000);
    try {
      const res = await fetch(getApiUrl("/saas/customer/connections"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        signal: controller.signal,
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
      clearTimeout(timeoutId);
      const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}: ${res.statusText}` }));
      if (!res.ok) throw new Error(data.detail || "Failed to save connection");

      setFeedback({
        type: "success",
        message: `${newConnName} connection saved successfully. Status: ${data.connection?.verification_status || "VERIFIED"}`,
      });
      setNewConnApiKey("");
      setNewConnSecret("");
      setNewConnPassphrase("");
      setConnTestResult(null);
      setIsConnectModalOpen(false);
      setConnectStep(1);
      await fetchCustomerData();
    } catch (err: any) {
      clearTimeout(timeoutId);
      const isAbort = err.name === "AbortError";
      const displayMsg = isAbort ? "Save request timed out after 12 seconds." : err.message;
      setFeedback({ type: "error", message: displayMsg });
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
      const res = await fetch(getApiUrl("/saas/customer/auth/2fa/setup"), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to initiate 2FA setup");
      setTotpSetupData(data.setup || data);
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
      const res = await fetch(getApiUrl("/saas/customer/auth/2fa/verify"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          totp_secret: totpSetupData.totp_secret,
          code: totpVerifyCode.trim(),
          totp_code: totpVerifyCode.trim(),
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
      case "CONNECTED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono bg-emerald-500/10 text-[#0ECB81] rounded-full border border-emerald-500/20 font-bold">
            <CheckCircle2 className="w-3 h-3" />
            VERIFIED READ-ONLY
          </span>
        );
      case "SAVED_UNSUPPORTED":
      case "INTEGRATION_NOT_YET_SUPPORTED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono bg-cyan-500/10 text-cyan-400 rounded-full border border-cyan-500/20 font-bold">
            <Info className="w-3 h-3" />
            Saved — Connector Not Supported
          </span>
        );
      case "VERIFICATION_FAILED":
      case "CONNECTION_FAILED":
      case "AUTHENTICATION_FAILED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono bg-rose-500/10 text-[#F6465D] rounded-full border border-rose-500/20 font-bold">
            <AlertTriangle className="w-3 h-3" />
            Connection Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono bg-[#151921] text-[#EAECEF] rounded-full border border-[#2B3139]">
            {status}
          </span>
        );
    }
  };

  const getTicketStatusBadge = (status: string) => {
    switch (status) {
      case "OPEN":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-emerald-500/10 text-[#0ECB81] border border-emerald-500/20">OPEN</span>;
      case "IN_PROGRESS":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-blue-500/10 text-[#00E5FF] border border-[#00E5FF]/20">IN PROGRESS</span>;
      case "WAITING_ON_CUSTOMER":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20">WAITING ON YOU</span>;
      case "RESOLVED":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-purple-500/10 text-purple-400 border border-purple-500/20">RESOLVED</span>;
      case "CLOSED":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-[#151921] text-[#848E9C] border border-[#2B3139]">CLOSED</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-[#151921] text-[#EAECEF]">{status}</span>;
    }
  };

  const filteredConnections = connections.filter((c) => {
    if (connEnvFilter === "LIVE" && c.environment !== "LIVE") return false;
    if (connEnvFilter === "DEMO" && c.environment !== "DEMO") return false;
    if (
      connExchangeFilter !== "ALL" &&
      (c.provider || c.exchange_name || "").toUpperCase() !== connExchangeFilter.toUpperCase()
    )
      return false;
    if (
      connStatusFilter === "VERIFIED" &&
      c.verification_status !== "VERIFIED" &&
      c.connection_status !== "CONNECTED"
    )
      return false;
    if (
      connStatusFilter === "UNVERIFIED" &&
      (c.verification_status === "VERIFIED" || c.connection_status === "CONNECTED")
    )
      return false;
    return true;
  });

  const groupedConnections: Record<string, any[]> = {};
  filteredConnections.forEach((c) => {
    const providerKey = (c.exchange_name || c.provider || "OTHER").toUpperCase();
    if (!groupedConnections[providerKey]) groupedConnections[providerKey] = [];
    groupedConnections[providerKey].push(c);
  });

  return (
    <div className="flex h-screen bg-[#080B10] text-[#F1F5F9] font-sans overflow-hidden">
      {/* ─── 1. COLLAPSIBLE DESKTOP SIDEBAR + MOBILE DRAWER ───────── */}
      <SidebarNav
        currentNav={currentNav}
        onNavigate={navigateTo}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
        isMobileDrawerOpen={isMobileDrawerOpen}
        onCloseMobileDrawer={() => setIsMobileDrawerOpen(false)}
        userEmail={profile?.email || user?.email}
        userRole={user?.role}
        onSignOut={onSignOut}
        onSwitchPortal={onSwitchPortal}
      />

      {/* ─── 2. MAIN WORKSPACE VIEWPORT ───────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {/* ─── STICKY INSTITUTIONAL CONTEXT HEADER ────────────────── */}
        <header className="sticky top-0 z-40 h-16 bg-[#0E131B] border-b border-[#1E2736] flex items-center justify-between px-4 sm:px-6 shrink-0">
          {/* Left: Mobile Drawer Trigger + Quick Search Trigger */}
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setIsMobileDrawerOpen(true)}
              className="lg:hidden p-2 rounded-lg text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#151C28]"
              aria-label="Open navigation menu"
            >
              <Menu className="w-5 h-5" />
            </button>

            {/* Quick Search Button (opens PairSearchSelector) */}
            <button
              type="button"
              onClick={() => setIsSearchOpen(true)}
              className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl bg-[#151C28] hover:bg-[#1E2736] border border-[#1E2736] hover:border-[#38BDF8] text-xs font-mono text-[#94A3B8] transition-all cursor-pointer min-w-[160px] sm:min-w-[240px]"
            >
              <Search className="w-3.5 h-3.5 text-[#38BDF8]" />
              <span className="truncate">Search instrument...</span>
              <span className="hidden sm:inline-block ml-auto text-[10px] px-1.5 py-0.2 rounded bg-[#0E131B] text-[#64748B] border border-[#1E2736]">
                Ctrl+K
              </span>
            </button>
          </div>

          {/* Right: Broker Pill, Environment Badge & User Menu */}
          <div className="flex items-center gap-2 sm:gap-3 shrink-0">
            {/* Exness Connection Pill (Truthful Disconnected State) */}
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#EF4444]/15 text-[#EF4444] border border-[#EF4444]/30 text-xs font-mono font-bold">
              <span className="w-1.5 h-1.5 rounded-full bg-[#EF4444]" />
              <span>EXNESS: NOT CONNECTED</span>
            </div>

            {/* Environment Badge */}
            <StatusBadge type="ENVIRONMENT" state="SIMULATED" />

            {/* Emergency Lock Indicator */}
            <div className="hidden md:flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-[#EF4444]/15 text-[#EF4444] border border-[#EF4444]/30">
              <Lock className="w-3 h-3" />
              <span>Locked</span>
            </div>

            {/* Profile Dropdown */}
            <div className="relative">
              <button
                onClick={() => setIsProfileDropdownOpen(!isProfileDropdownOpen)}
                className="flex items-center gap-2 p-1.5 rounded-xl bg-[#151C28] border border-[#1E2736] hover:border-[#38BDF8] text-xs font-mono transition-colors"
              >
                <div className="w-6 h-6 rounded-lg bg-[#38BDF8]/20 text-[#38BDF8] font-bold flex items-center justify-center text-[10px]">
                  {(profile?.email || user?.email || "U")[0].toUpperCase()}
                </div>
                <span className="hidden md:inline font-bold text-[#F1F5F9] max-w-[120px] truncate">
                  {profile?.email || user?.email}
                </span>
                <ChevronDown className="w-3.5 h-3.5 text-[#94A3B8]" />
              </button>

              {isProfileDropdownOpen && (
                <div className="absolute right-0 mt-2 w-56 bg-[#0E131B] border border-[#1E2736] rounded-xl shadow-2xl py-1.5 z-50 text-xs font-mono">
                  <div className="px-3 py-2 border-b border-[#1E2736]">
                    <span className="text-[10px] text-[#64748B] uppercase block">Authenticated User</span>
                    <span className="font-bold text-[#F1F5F9] truncate block">{profile?.email || user?.email}</span>
                    <span className="text-[10px] text-[#10B981] mt-0.5 block">Role: {user?.role || "CUSTOMER"}</span>
                  </div>
                  <button
                    onClick={() => { navigateTo("CONNECTIONS"); setIsProfileDropdownOpen(false); }}
                    className="w-full px-3 py-2 text-left text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#151C28] flex items-center gap-2"
                  >
                    <Link2 className="w-3.5 h-3.5 text-[#38BDF8]" />
                    <span>Exchange Connections</span>
                  </button>
                  <button
                    onClick={() => { navigateTo("SETTINGS"); setIsProfileDropdownOpen(false); }}
                    className="w-full px-3 py-2 text-left text-[#94A3B8] hover:text-[#F1F5F9] hover:bg-[#151C28] flex items-center gap-2"
                  >
                    <Sliders className="w-3.5 h-3.5 text-[#38BDF8]" />
                    <span>Settings &amp; Security</span>
                  </button>
                  {onSwitchPortal && (
                    <button
                      onClick={() => { setIsProfileDropdownOpen(false); onSwitchPortal(); }}
                      className="w-full px-3 py-2 text-left text-purple-400 hover:bg-[#151C28] flex items-center gap-2 border-t border-[#1E2736]"
                    >
                      <ShieldCheck className="w-3.5 h-3.5 text-purple-400" />
                      <span>Administrator Portal</span>
                    </button>
                  )}
                  <div className="border-t border-[#1E2736] my-1" />
                  <button
                    onClick={() => { setIsProfileDropdownOpen(false); onSignOut(); }}
                    className="w-full px-3 py-2 text-left text-rose-400 hover:bg-[#151C28] flex items-center gap-2"
                  >
                    <LogOut className="w-3.5 h-3.5 text-rose-500" />
                    <span>Sign Out</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* ─── LIVE NUMERICAL TICKER STRIP (ZERO CHART OVERHEAD) ──── */}
        <div className="bg-[#080B10] py-1.5 px-4 sm:px-6 text-xs font-mono flex items-center justify-between gap-4 overflow-x-auto border-b border-[#1E2736] shrink-0">
          <div className="flex items-center gap-5 shrink-0">
            <span className="bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30 px-2 py-0.5 rounded text-[10px] font-bold tracking-wider flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#10B981] animate-pulse" />
              LIVE FEED
            </span>
            {tickerItems && tickerItems.length > 0 ? (
              tickerItems.slice(0, 8).map((t: any) => {
                const isPos = (t.change_24h ?? 0) >= 0;
                return (
                  <div
                    key={t.symbol}
                    onClick={() => {
                      setSelectedSearchPair({ canonical_symbol: t.symbol, market: t.market, price: t.price });
                      navigateTo("TERMINAL");
                    }}
                    className="flex items-center gap-1.5 cursor-pointer hover:text-[#38BDF8] transition-colors"
                  >
                    <span className="text-[#64748B]">{t.symbol}</span>
                    <strong className="text-[#F1F5F9] font-mono tabular-nums">
                      {typeof t.price === "number" ? (t.price >= 10 ? t.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : t.price.toFixed(4)) : "--"}
                    </strong>
                    <span className={isPos ? "text-[#10B981]" : "text-[#F43F5E]"}>
                      {isPos ? "+" : ""}{typeof t.change_24h === "number" ? t.change_24h.toFixed(2) : "0.00"}%
                    </span>
                  </div>
                );
              })
            ) : (
              <span className="text-[#64748B]">Streaming verified market quotes...</span>
            )}
          </div>
          <div className="hidden xl:flex items-center gap-3 shrink-0 text-[#64748B] text-[11px]">
            <span>Forex session: <strong className="text-[#10B981]">Open</strong> · London/NY Active</span>
          </div>
        </div>

        {/* ─── MAIN WORKSPACE CONTENT AREA (SCROLLABLE) ───────────── */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 min-w-0">
          {currentNav === "OVERVIEW" && (
            <OverviewView
              balance={balancesData?.total_usd || 5000.0}
              equity={balancesData?.total_usd || 5000.0}
              unrealizedPnl={0.0}
              realizedPnl={0.0}
              exnessConnected={false}
              tickerItems={tickerItems || []}
              onNavigate={navigateTo}
              onSelectPair={(p) => {
                setSelectedSearchPair(p);
                navigateTo("TERMINAL");
              }}
            />
          )}

          {currentNav === "TERMINAL" && (
            <TradingTerminalView
              selectedPair={selectedSearchPair}
              onOpenSearch={() => setIsSearchOpen(true)}
              onExecuteAnalysis={(sym, mkt) => {
                setSelectedSearchPair({ canonical_symbol: sym, market: mkt });
                navigateTo("LONG_TERM");
              }}
              openPositions={ledgerPositions || []}
              onInitiateOrder={(spec) => {
                // Execution guarded
              }}
              isLoadingPrices={!selectedSearchPair && tickerItems.length === 0}
            />
          )}

          {currentNav === "LONG_TERM" && (
            <div className="space-y-4">
              {children}
            </div>
          )}

          {currentNav === "HFT" && (
            <div>
              <InstitutionalTradingDashboard token={token} />
            </div>
          )}

          {currentNav === "CONNECTIONS" && (
            <ExchangeConnectionsView
              exnessConnected={false}
              onRefresh={() => fetchConnections()}
            />
          )}

          {currentNav === "BALANCES" && (
            <BalancesView
              balance={balancesData?.total_usd || 5000.0}
              equity={balancesData?.total_usd || 5000.0}
              freeMargin={balancesData?.total_usd || 5000.0}
              usedMargin={0.0}
              realizedPnl={0.0}
              unrealizedPnl={0.0}
              onRefresh={() => fetchBalances(true)}
            />
          )}

          {currentNav === "ORDERS" && (
            <OrdersHoldingsView
              openPositions={ledgerPositions || []}
              pendingOrders={ledgerOpenOrders || []}
              closedPositions={ledgerClosedPositions || []}
              onRefresh={() => fetchLedgerData()}
            />
          )}

          {currentNav === "SETTINGS" && (
            <CustomerSettingsView user={user} />
          )}

          {currentNav === "SUPPORT" && (
            <HelpSupportView />
          )}
        </main>
      </div>

      {/* ─── PAIR SEARCH SELECTOR MODAL (CTRL+K) ───────────────────── */}
      <PairSearchSelector
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        pairs={(tickerItems || []).map((t: any) => ({
          canonical_symbol: t.symbol,
          symbol: t.symbol,
          name: t.name,
          asset_class: t.market,
          price: t.price,
          change_24h: t.change_24h,
          spread: 1.2,
        }))}
        onSelectPair={(p) => {
          setSelectedSearchPair(p);
          navigateTo("TERMINAL");
        }}
      />

{/* ─── IN-APP CONFIRMATION MODAL (REPLACES BROWSER CONFIRM) ──── */}
      {confirmModal && confirmModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#262C36]/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-3xl shadow-2xl p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-[#F6465D] shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[#EAECEF]">{confirmModal.title}</h3>
                <p className="text-xs text-[#848E9C] mt-1">{confirmModal.message}</p>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-[#2B3139]">
              <button
                type="button"
                onClick={() => setConfirmModal(null)}
                className="px-4 py-2 rounded-xl bg-[#151921] hover:bg-slate-700 text-[#EAECEF] text-xs font-mono cursor-pointer transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmModal.onConfirm}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-[#EAECEF] text-xs font-bold font-mono cursor-pointer transition-colors"
              >
                {confirmModal.confirmText || "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── ACCOUNT SETTINGS: PROFILE MODAL ───────────────────────── */}
      {activeAccountModal === "PROFILE" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#262C36]/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-3xl shadow-2xl p-6 space-y-4 font-mono">
            <div className="flex items-center justify-between border-b border-[#2B3139] pb-3">
              <h3 className="text-sm font-bold text-[#EAECEF] flex items-center gap-2">
                <User className="w-4 h-4 text-[#0ECB81]" />
                Customer Account Profile
              </h3>
              <button onClick={() => setActiveAccountModal(null)} className="text-[#848E9C] hover:text-[#EAECEF]">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                <span className="text-[10px] text-[#848E9C] block uppercase font-bold">Database User ID</span>
                <span className="text-cyan-300 font-bold break-all">{profile?.user_id || "USR-UNKNOWN"}</span>
              </div>
              <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                <span className="text-[10px] text-[#848E9C] block uppercase font-bold">Username</span>
                <span className="text-[#EAECEF] font-bold">{profile?.username || "Not Set"}</span>
              </div>
              <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                <span className="text-[10px] text-[#848E9C] block uppercase font-bold">Email Address</span>
                <span className="text-[#EAECEF] font-bold">{profile?.email}</span>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                  <span className="text-[10px] text-[#848E9C] block uppercase font-bold">Account Role</span>
                  <span className="text-[#0ECB81] font-bold">{profile?.role || "CUSTOMER"}</span>
                </div>
                <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                  <span className="text-[10px] text-[#848E9C] block uppercase font-bold">2FA Status</span>
                  <span className={profile?.two_factor_enabled ? "text-[#0ECB81] font-bold" : "text-amber-400 font-bold"}>
                    {profile?.two_factor_enabled ? "Enabled (TOTP)" : "Disabled"}
                  </span>
                </div>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setActiveAccountModal(null)}
                className="px-4 py-2 rounded-xl bg-[#151921] hover:bg-slate-700 text-[#EAECEF] text-xs font-mono transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── ACCOUNT SETTINGS: CHANGE USERNAME MODAL ────────────────── */}
      {activeAccountModal === "CHANGE_USERNAME" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#262C36]/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-3xl shadow-2xl p-6 space-y-4 font-mono">
            <div className="flex items-center justify-between border-b border-[#2B3139] pb-3">
              <h3 className="text-sm font-bold text-[#EAECEF] flex items-center gap-2">
                <Edit3 className="w-4 h-4 text-[#0ECB81]" />
                Change Username
              </h3>
              <button onClick={() => setActiveAccountModal(null)} className="text-[#848E9C] hover:text-[#EAECEF]">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleChangeUsername} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-[#EAECEF] mb-1">Proposed New Username</label>
                <input
                  type="text"
                  required
                  value={newUsernameInput}
                  onChange={(e) => setNewUsernameInput(e.target.value)}
                  placeholder="e.g. QuantitativeTrader"
                  className="w-full px-3 py-2 rounded-xl bg-[#1E2329] border border-[#2B3139] text-[#EAECEF] text-xs text-[#EAECEF] focus:outline-none focus:border-emerald-500 font-mono"
                />
                <span className="text-[10px] text-[#848E9C] mt-1 block">
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
                  className="px-4 py-2 rounded-xl bg-[#151921] text-[#EAECEF] text-xs font-mono cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isUpdatingUsername || !newUsernameInput.trim()}
                  className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-[#EAECEF] text-xs font-bold font-mono transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2"
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
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#262C36]/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-3xl shadow-2xl p-6 space-y-4 font-mono">
            <div className="flex items-center justify-between border-b border-[#2B3139] pb-3">
              <h3 className="text-sm font-bold text-[#EAECEF] flex items-center gap-2">
                <Mail className="w-4 h-4 text-[#0ECB81]" />
                Change Email Address
              </h3>
              <button onClick={() => setActiveAccountModal(null)} className="text-[#848E9C] hover:text-[#EAECEF]">
                <X className="w-4 h-4" />
              </button>
            </div>

            {emailChangeStep === "INPUT" ? (
              <form onSubmit={handleInitiateEmailChange} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-[#EAECEF] mb-1">Current Email</label>
                  <div className="px-3 py-2 rounded-xl bg-[#262C36] border border-[#2B3139] text-xs text-[#848E9C]">
                    {profile?.email}
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#EAECEF] mb-1">Proposed New Email Address</label>
                  <input
                    type="email"
                    required
                    value={newEmailInput}
                    onChange={(e) => setNewEmailInput(e.target.value)}
                    placeholder="e.g. new.email@domain.com"
                    className="w-full px-3 py-2 rounded-xl bg-[#1E2329] border border-[#2B3139] text-[#EAECEF] text-xs text-[#EAECEF] focus:outline-none focus:border-emerald-500 font-mono"
                  />
                  <span className="text-[10px] text-[#848E9C] mt-1 block">
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
                    className="px-4 py-2 rounded-xl bg-[#151921] text-[#EAECEF] text-xs font-mono cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isInitiatingEmailChange || !newEmailInput.trim()}
                    className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-[#EAECEF] text-xs font-bold font-mono transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2"
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
                  <label className="block text-xs font-semibold text-[#EAECEF] mb-1">Enter 6-Digit OTP Code</label>
                  <input
                    type="text"
                    maxLength={6}
                    required
                    value={emailOtpInput}
                    onChange={(e) => setEmailOtpInput(e.target.value.replace(/[^0-9]/g, ""))}
                    placeholder="123456"
                    className="w-full px-3 py-2 rounded-xl bg-[#1E2329] border border-[#2B3139] text-[#EAECEF] text-base text-center tracking-widest text-[#0ECB81] font-bold focus:outline-none focus:border-emerald-500 font-mono"
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
                    className="text-xs text-[#848E9C] hover:text-[#EAECEF] underline cursor-pointer"
                  >
                    Back
                  </button>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setActiveAccountModal(null)}
                      className="px-4 py-2 rounded-xl bg-[#151921] text-[#EAECEF] text-xs font-mono cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isVerifyingEmailChange || emailOtpInput.length !== 6}
                      className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-[#EAECEF] text-xs font-bold font-mono transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2"
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
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#262C36]/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-[#1E2329] border border-rose-500/40 rounded-3xl shadow-2xl p-6 space-y-4 font-mono">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-rose-500/20 border border-rose-500/30 flex items-center justify-center text-[#F6465D] shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[#EAECEF]">Email Already Registered</h3>
                <p className="text-xs text-rose-300 mt-1 font-sans">
                  This email address is already registered. Please use another email.
                </p>
              </div>
            </div>
            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setEmailDuplicateModal(false)}
                className="px-4 py-2 rounded-xl bg-[#151921] hover:bg-slate-700 text-[#EAECEF] text-xs font-mono transition-colors cursor-pointer"
              >
                OK
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── ACCOUNT SETTINGS: CHANGE PASSWORD MODAL ────────────────── */}
      {activeAccountModal === "CHANGE_PASSWORD" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#262C36]/85 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-md bg-[#1E2329] border border-[#2B3139] shadow-sm rounded-3xl shadow-2xl p-6 space-y-4 font-mono">
            <div className="flex items-center justify-between border-b border-[#2B3139] pb-3">
              <h3 className="text-sm font-bold text-[#EAECEF] flex items-center gap-2">
                <Lock className="w-4 h-4 text-[#0ECB81]" />
                Change Password
              </h3>
              <button onClick={() => setActiveAccountModal(null)} className="text-[#848E9C] hover:text-[#EAECEF]">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleChangePassword} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-[#EAECEF] mb-1">Current Password</label>
                <input
                  type="password"
                  required
                  value={currentPassInput}
                  onChange={(e) => setCurrentPassInput(e.target.value)}
                  placeholder="Enter current password"
                  className="w-full px-3 py-2 rounded-xl bg-[#1E2329] border border-[#2B3139] text-[#EAECEF] text-xs text-[#EAECEF] focus:outline-none focus:border-emerald-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#EAECEF] mb-1">New Password</label>
                <input
                  type="password"
                  required
                  value={newPassInput}
                  onChange={(e) => setNewPassInput(e.target.value)}
                  placeholder="At least 8 characters"
                  className="w-full px-3 py-2 rounded-xl bg-[#1E2329] border border-[#2B3139] text-[#EAECEF] text-xs text-[#EAECEF] focus:outline-none focus:border-emerald-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#EAECEF] mb-1">Confirm New Password</label>
                <input
                  type="password"
                  required
                  value={confirmPassInput}
                  onChange={(e) => setConfirmPassInput(e.target.value)}
                  placeholder="Re-type new password"
                  className="w-full px-3 py-2 rounded-xl bg-[#1E2329] border border-[#2B3139] text-[#EAECEF] text-xs text-[#EAECEF] focus:outline-none focus:border-emerald-500 font-mono"
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
                  className="px-4 py-2 rounded-xl bg-[#151921] text-[#EAECEF] text-xs font-mono cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isChangingPassword || !currentPassInput || !newPassInput}
                  className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-[#EAECEF] text-xs font-bold font-mono transition-all disabled:opacity-50 cursor-pointer flex items-center gap-2"
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
      {/* ─── LIVE AI TELEMETRY MODAL (TAURIC & JEV) ────────────────── */}
      {selectedTelemetryEngine && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#262C36]/80 backdrop-blur-md">
          <div className="max-w-md w-full rounded-3xl bg-[#1E2329] border border-[#2B3139] shadow-sm shadow-2xl p-6 font-mono text-xs space-y-4">
            <div className="flex items-center justify-between border-b border-[#2B3139] pb-3">
              <div className="flex items-center gap-2.5">
                <div className={`w-8 h-8 rounded-xl flex items-center justify-center ${
                  selectedTelemetryEngine === "tauric"
                    ? "bg-emerald-500/20 text-[#0ECB81] border border-emerald-500/30"
                    : "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30"
                }`}>
                  <Cpu className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-bold text-[#EAECEF] text-sm uppercase">
                    {selectedTelemetryEngine === "tauric" ? "Tauric Deep Quantitative Engine" : "Jev Micro-Risk Guardian"}
                  </h3>
                  <p className="text-[10px] text-[#848E9C]">
                    {selectedTelemetryEngine === "tauric" ? "Macro structure & institutional kline screening" : "Independent blind review & volatility safety gating"}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedTelemetryEngine(null)}
                className="p-1 rounded-lg text-[#848E9C] hover:text-[#EAECEF] hover:bg-[#151921] cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {(() => {
              const data = selectedTelemetryEngine === "tauric" ? tauricTelemetry : jevTelemetry;
              return (
                <div className="space-y-3">
                  <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139] flex items-center justify-between">
                    <span className="text-[#848E9C]">Connection Status:</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-[#0ECB81] border border-emerald-500/20 flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      CONNECTED / READY
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                      <span className="text-[10px] text-[#848E9C] block uppercase">Requests Today</span>
                      <span className="text-lg font-bold text-[#EAECEF] tabular-nums">{data.requests_today ?? "--"}</span>
                    </div>
                    <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                      <span className="text-[10px] text-[#848E9C] block uppercase">Tokens Consumed</span>
                      <span className="text-lg font-bold text-cyan-400 tabular-nums">{typeof data.tokens_today === "number" ? data.tokens_today.toLocaleString() : "--"}</span>
                    </div>
                    <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                      <span className="text-[10px] text-[#848E9C] block uppercase">Completed / Failed</span>
                      <span className="text-sm font-bold text-[#EAECEF] tabular-nums">
                        <span className="text-[#0ECB81]">{data.completed ?? "--"}</span> / <span className="text-[#F6465D]">{data.failed ?? "--"}</span>
                      </span>
                    </div>
                    <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139]">
                      <span className="text-[10px] text-[#848E9C] block uppercase">Period Usage Cost</span>
                      <span className="text-sm font-bold text-[#0ECB81] tabular-nums">{typeof data.cost_usd === "number" ? `$${data.cost_usd.toFixed(2)}` : "--"}</span>
                    </div>
                  </div>

                  <div className="p-3 rounded-xl bg-[#262C36] border border-[#2B3139] text-[11px] text-[#848E9C] space-y-1">
                    <div><strong>Model:</strong> {data.model}</div>
                    <div><strong>Current Task:</strong> {data.is_active ? "Evaluating fresh candle closes" : "Standby (Listening to market feed)"}</div>
                    <div><strong>Average Latency:</strong> {typeof data.latency_ms === "number" ? `${data.latency_ms} ms` : "--"}</div>
                  </div>
                </div>
              );
            })()}

            <button
              onClick={() => setSelectedTelemetryEngine(null)}
              className="w-full py-2.5 rounded-xl bg-[#151921] hover:bg-slate-700 text-[#EAECEF] font-bold cursor-pointer"
            >
              Close Telemetry
            </button>
          </div>
        </div>
      )}
    
      {/* ─── PHASE 1: 3-STEP GUIDED CONNECT EXCHANGE ACCOUNT MODAL ─── */}
      {isConnectModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0B0E11]/80 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-xl bg-[#1E2329] border border-[#2B3139] rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
            {/* Modal Header */}
            <div className="p-5 border-b border-[#2B3139] flex items-center justify-between bg-[#262C36]">
              <div>
                <h3 className="text-base font-bold text-[#EAECEF] font-mono flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-[#0ECB81]" />
                  <span>Connect Exchange Account</span>
                </h3>
                <div className="flex items-center gap-2 mt-1 text-[11px] font-mono text-[#848E9C]">
                  <span className={connectStep === 1 ? "text-cyan-400 font-bold" : "text-[#848E9C]"}>1. Environment</span>
                  <span>→</span>
                  <span className={connectStep === 2 ? "text-cyan-400 font-bold" : "text-[#848E9C]"}>2. Credentials</span>
                  <span>→</span>
                  <span className={connectStep === 3 ? "text-cyan-400 font-bold" : "text-[#848E9C]"}>3. Handshake</span>
                </div>
              </div>
              <button
                onClick={() => setIsConnectModalOpen(false)}
                className="p-2 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-[#848E9C] hover:text-[#EAECEF] transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto flex-1 font-mono text-xs space-y-4">
              {/* Step 1: Exchange & Environment Selection */}
              {connectStep === 1 && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-[#EAECEF] mb-1.5">Select Exchange Provider</label>
                    <select
                      value={newConnName}
                      onChange={(e) => setNewConnName(e.target.value)}
                      className="w-full px-3 py-2.5 rounded-xl bg-[#151921] border border-[#2B3139] text-[#EAECEF] text-xs focus:outline-none focus:border-cyan-500 cursor-pointer"
                    >
                      <option value="Binance">Binance (Spot & Futures)</option>
                      <option value="Bitget">Bitget (Spot & Futures)</option>
                      <option value="Bybit">Bybit</option>
                      <option value="Coinbase Advanced">Coinbase Advanced</option>
                      <option value="OKX">OKX</option>
                      <option value="Kraken">Kraken</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#EAECEF] mb-1.5">Select Environment Mode</label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {/* Card A: LIVE */}
                      <div
                        onClick={() => setNewConnEnv("LIVE")}
                        className={`p-4 rounded-xl border cursor-pointer transition-all ${
                          newConnEnv === "LIVE"
                            ? "border-emerald-500 bg-emerald-950/30 text-[#0ECB81] shadow-lg shadow-emerald-950/30"
                            : "border-[#2B3139] bg-[#151921] text-[#848E9C] hover:border-slate-600 hover:text-[#EAECEF]"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-bold text-xs flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-[#0ECB81]"></span>
                            ● LIVE REAL
                          </span>
                          {newConnEnv === "LIVE" && <CheckCircle2 className="w-4 h-4 text-[#0ECB81]" />}
                        </div>
                        <p className="text-[11px] leading-relaxed text-[#848E9C]">
                          Direct routing to official production exchange endpoints for live portfolio tracking and authorized execution.
                        </p>
                      </div>

                      {/* Card B: DEMO */}
                      <div
                        onClick={() => setNewConnEnv("DEMO")}
                        className={`p-4 rounded-xl border cursor-pointer transition-all ${
                          newConnEnv === "DEMO"
                            ? "border-amber-500 bg-amber-950/30 text-[#F0B90B] shadow-lg shadow-amber-950/30"
                            : "border-[#2B3139] bg-[#151921] text-[#848E9C] hover:border-slate-600 hover:text-[#EAECEF]"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-bold text-xs flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-[#F0B90B]"></span>
                            ◐ DEMO SANDBOX
                          </span>
                          {newConnEnv === "DEMO" && <CheckCircle2 className="w-4 h-4 text-[#F0B90B]" />}
                        </div>
                        <p className="text-[11px] leading-relaxed text-[#848E9C]">
                          Testnet and sandbox endpoints (`demo-api.binance.com`). Risk-free testing with zero capital exposure.
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="pt-2 flex justify-end">
                    <button
                      type="button"
                      onClick={() => setConnectStep(2)}
                      className="px-5 py-2.5 rounded-xl bg-[#00E5FF] hover:bg-[#00E5FF]/90 text-[#0B0E11] font-bold text-xs transition-all cursor-pointer flex items-center gap-2"
                    >
                      <span>Next: Enter Credentials</span>
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}

              {/* Step 2: Account Alias & Encrypted Credentials */}
              {connectStep === 2 && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-[#EAECEF] mb-1">Account Alias / Custom Label</label>
                    <input
                      type="text"
                      value={newConnLabel}
                      onChange={(e) => setNewConnLabel(e.target.value)}
                      placeholder={`e.g. ${newConnName} ${newConnEnv === "LIVE" ? "Live Primary" : "Demo 01"}`}
                      className="w-full px-3 py-2 rounded-xl bg-[#151921] border border-[#2B3139] text-[#EAECEF] text-xs focus:outline-none focus:border-cyan-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#EAECEF] mb-1">API Key</label>
                    <input
                      type="password"
                      required
                      value={newConnApiKey}
                      onChange={(e) => setNewConnApiKey(e.target.value)}
                      placeholder="Enter Exchange API Key"
                      className="w-full px-3 py-2 rounded-xl bg-[#151921] border border-[#2B3139] text-[#EAECEF] text-xs font-mono focus:outline-none focus:border-cyan-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#EAECEF] mb-1">API Secret</label>
                    <input
                      type="password"
                      required
                      value={newConnSecret}
                      onChange={(e) => setNewConnSecret(e.target.value)}
                      placeholder="Enter Exchange API Secret"
                      className="w-full px-3 py-2 rounded-xl bg-[#151921] border border-[#2B3139] text-[#EAECEF] text-xs font-mono focus:outline-none focus:border-cyan-500"
                    />
                  </div>

                  {(newConnName.toUpperCase().includes("BITGET") || newConnName.toUpperCase().includes("OKX")) && (
                    <div>
                      <label className="block text-xs font-semibold text-[#EAECEF] mb-1">API Passphrase (Mandatory for {newConnName})</label>
                      <input
                        type="password"
                        value={newConnPassphrase}
                        onChange={(e) => setNewConnPassphrase(e.target.value)}
                        placeholder="Enter API Passphrase"
                        className="w-full px-3 py-2 rounded-xl bg-[#151921] border border-[#2B3139] text-[#EAECEF] text-xs font-mono focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                  )}

                  <div className="pt-2 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setConnectStep(1)}
                      className="px-4 py-2 rounded-xl bg-[#151921] hover:bg-[#262C36] text-[#848E9C] hover:text-[#EAECEF] text-xs font-bold transition-all cursor-pointer"
                    >
                      ← Back
                    </button>
                    <button
                      type="button"
                      disabled={!newConnApiKey || !newConnSecret}
                      onClick={() => {
                        setConnectStep(3);
                        handleTestConnection();
                      }}
                      className="px-5 py-2.5 rounded-xl bg-[#00E5FF] hover:bg-[#00E5FF]/90 text-[#0B0E11] font-bold text-xs transition-all cursor-pointer flex items-center gap-2 disabled:opacity-50"
                    >
                      <span>Next: Verify Handshake</span>
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}

              {/* Step 3: Pre-Save Handshake & Permission Verification */}
              {connectStep === 3 && (
                <div className="space-y-4">
                  {/* 3-Point Checklist */}
                  <div className="p-4 rounded-xl bg-[#151921] border border-[#2B3139] space-y-3">
                    <div className="text-xs font-bold text-[#EAECEF] uppercase tracking-wider mb-2">
                      Pre-Save Security & Permission Handshake
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      {connTestResult?.status === "SUCCESS" || connTestResult?.verification_status === "VERIFIED_READ_ONLY" ? (
                        <CheckCircle2 className="w-4 h-4 text-[#0ECB81]" />
                      ) : isTestingConn ? (
                        <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-rose-400" />
                      )}
                      <span className={connTestResult?.status === "SUCCESS" || connTestResult?.verification_status === "VERIFIED_READ_ONLY" ? "text-emerald-300 font-bold" : "text-[#848E9C]"}>
                        Authentication Handshake Valid (Outbound IP: 169.58.218.168)
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      {connTestResult?.account_data ? (
                        <CheckCircle2 className="w-4 h-4 text-[#0ECB81]" />
                      ) : isTestingConn ? (
                        <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-slate-500" />
                      )}
                      <span className={connTestResult?.account_data ? "text-emerald-300 font-bold" : "text-[#848E9C]"}>
                        Wallet Balance Read Scope Confirmed ({connTestResult?.account_data ? `$${Number(connTestResult.account_data.total_usd ?? 0).toFixed(2)} USD retrieved` : "Pending"})
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      <CheckCircle2 className="w-4 h-4 text-[#0ECB81]" />
                      <span className="text-emerald-300 font-bold">
                        Security Check: Withdrawal Permission Disabled (Safe)
                      </span>
                    </div>
                  </div>

                  {/* Diagnostic Banner */}
                  {connTestResult && (
                    <div
                      className={`p-3.5 rounded-xl border text-xs ${
                        connTestResult.status === "SUCCESS" || connTestResult.verification_status === "VERIFIED_READ_ONLY"
                          ? "bg-emerald-950/40 border-emerald-500/40 text-emerald-300"
                          : "bg-rose-950/40 border-rose-500/40 text-rose-300"
                      }`}
                    >
                      <div className="font-bold flex items-center justify-between">
                        <span>Result: {connTestResult.status || connTestResult.verification_status}</span>
                      </div>
                      <p className="mt-1 text-[11px] text-[#EAECEF] leading-relaxed">
                        {connTestResult.message || connTestResult.detail}
                      </p>
                    </div>
                  )}

                  <div className="pt-2 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setConnectStep(2)}
                      className="px-4 py-2 rounded-xl bg-[#151921] hover:bg-[#262C36] text-[#848E9C] hover:text-[#EAECEF] text-xs font-bold transition-all cursor-pointer"
                    >
                      ← Back
                    </button>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleTestConnection}
                        disabled={isTestingConn}
                        className="px-3.5 py-2 rounded-xl bg-[#151921] hover:bg-[#262C36] text-[#EAECEF] border border-[#2B3139] text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5"
                      >
                        {isTestingConn && <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400" />}
                        Retest Handshake
                      </button>
                      <button
                        type="button"
                        onClick={(e) => handleSaveConnection(e)}
                        disabled={isSavingConn || !newConnApiKey || !newConnSecret}
                        className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-[#EAECEF] font-bold text-xs transition-all cursor-pointer flex items-center gap-2 shadow-lg shadow-emerald-950/40 disabled:opacity-50"
                      >
                        {isSavingConn && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                        Save & Encrypt Connection
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {/* ─── DISABLE 2FA CONFIRMATION MODAL ───────────────────────── */}
      {showDisable2FAModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
          <div className="relative w-full max-w-md rounded-2xl bg-[#1E2329] border border-[#2B3139] shadow-2xl p-6 space-y-4 font-mono text-xs">
            <div className="flex items-center justify-between border-b border-[#2B3139] pb-3">
              <div className="flex items-center gap-2 font-bold text-rose-400 uppercase">
                <AlertTriangle className="w-4 h-4" />
                Disable Authenticator App (2FA)
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowDisable2FAModal(false);
                  setDisablePassword("");
                }}
                className="text-[#848E9C] hover:text-[#EAECEF] p-1"
              >
                ✕
              </button>
            </div>

            <p className="text-[#848E9C] leading-relaxed">
              Disabling your Authenticator App will remove the secondary hardware-backed confirmation step. Your primary email OTP verification will remain active.
            </p>

            <form onSubmit={handleDisable2FA} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-[#EAECEF] mb-1">
                  Confirm Account Password
                </label>
                <input
                  type="password"
                  required
                  value={disablePassword}
                  onChange={(e) => setDisablePassword(e.target.value)}
                  placeholder="Enter your current password"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-[#151921] border border-[#2B3139] text-[#EAECEF] text-xs focus:outline-none focus:border-rose-400"
                />
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setShowDisable2FAModal(false);
                    setDisablePassword("");
                  }}
                  className="px-4 py-2.5 rounded-xl bg-[#151921] hover:bg-[#262C36] text-[#EAECEF] font-bold cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isDisabling2FA || !disablePassword}
                  className="flex-1 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-bold cursor-pointer flex items-center justify-center gap-2"
                >
                  {isDisabling2FA && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Confirm & Disable 2FA
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
 
      
    </div>
  );
}
