"use client";

import React, { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import PublicLandingPage from "@/components/PublicLandingPage";

// Dynamically import authenticated dashboards (code-splitting, zero impact on public landing LCP/TBT)
const CustomerPortal = dynamic(() => import("@/components/CustomerPortal"), {
  ssr: false,
});
const AdminPanel = dynamic(() => import("@/components/AdminPanel"), {
  ssr: false,
});
const InstitutionalConsole = dynamic(
  () => import("@/components/InstitutionalConsole"),
  { ssr: false }
);

export default function TauricPortal() {
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [portalMode, setPortalMode] = useState<"CUSTOMER" | "ADMIN">(() => {
    if (typeof window !== "undefined") {
      const h = window.location.hash.toLowerCase();
      if (
        h.startsWith("#admin") ||
        h === "#customers" ||
        h === "#support" ||
        h === "#pricing" ||
        h === "#exchanges" ||
        h === "#audit" ||
        h === "#provider_operations"
      ) {
        return "ADMIN";
      }
    }
    return "CUSTOMER";
  });

  useEffect(() => {
    const handleHash = () => {
      if (typeof window === "undefined") return;
      const h = window.location.hash.toLowerCase();
      if (
        h.startsWith("#admin") ||
        h === "#customers" ||
        h === "#support" ||
        h === "#pricing" ||
        h === "#exchanges" ||
        h === "#audit"
      ) {
        setPortalMode("ADMIN");
      } else if (
        h === "#trading" ||
        h === "#dashboard" ||
        h === "#account" ||
        h === "#signals" ||
        h === "#balances" ||
        h === "#connections" ||
        h === "#settings" || h === "#security" || h === "#notifications" || h === "#guardrails" || h === "#billing" || h === "#pnl" || h === "#positions" || h === "#profit_loss"
      ) {
        setPortalMode("CUSTOMER");
      }
    };
    handleHash();
    window.addEventListener("hashchange", handleHash);
    return () => window.removeEventListener("hashchange", handleHash);
  }, []);

  useEffect(() => {
    // Check localStorage for active session
    const savedToken =
      typeof window !== "undefined"
        ? localStorage.getItem("tauric_session_token")
        : null;
    const savedUser =
      typeof window !== "undefined"
        ? localStorage.getItem("tauric_session_user")
        : null;

    if (savedToken) {
      setAuthToken(savedToken);
      if (savedUser) {
        try {
          setCurrentUser(JSON.parse(savedUser));
        } catch {
          // ignore
        }
      }
      // Validate session with backend
      fetch("/trading/api/backend/saas/customer/me", {
        headers: { Authorization: `Bearer ${savedToken}` },
      })
        .then((res) => {
          if (res.ok) {
            return res.json();
          }
          throw new Error("Session expired");
        })
        .then((data) => {
          setCurrentUser(data.user);
          localStorage.setItem("tauric_session_user", JSON.stringify(data.user));
        })
        .catch(() => {
          // Token expired or invalid
          localStorage.removeItem("tauric_session_token");
          localStorage.removeItem("tauric_session_user");
          setAuthToken(null);
          setCurrentUser(null);
        });
    }
  }, []);

  const handleLoginSuccess = (token: string, user: any) => {
    localStorage.setItem("tauric_session_token", token);
    localStorage.setItem("tauric_session_user", JSON.stringify(user));
    setAuthToken(token);
    setCurrentUser(user);
  };

  const handleSignOut = async () => {
    const tokenToRevoke = authToken || (typeof window !== "undefined" ? localStorage.getItem("tauric_session_token") : null);
    if (typeof window !== "undefined") {
      const keysToPurge = [
        "tauric_session_token",
        "tauric_session_user",
        "bitdex_auth_token",
        "tauric_token",
        "bitdex_token",
        "sheltr_token",
        "bitdex_active_account",
        "bitdex_preferred_account",
        "bitdex_customer_trades",
      ];
      keysToPurge.forEach((k) => localStorage.removeItem(k));
      if (window.location.hash) {
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
      }
    }
    setAuthToken(null);
    setCurrentUser(null);
    if (tokenToRevoke) {
      try {
        await fetch("/api/backend/saas/auth/logout", {
          method: "POST",
          headers: { Authorization: `Bearer ${tokenToRevoke}` },
          keepalive: true,
        });
      } catch {
        // ignore network failure during signout
      }
    }
  };

  // 1. Unauthenticated / Initial SSR: Render Public SaaS Landing Page immediately
  if (!currentUser || !authToken) {
    return <PublicLandingPage onLoginSuccess={handleLoginSuccess} />;
  }

  // 2. Administrator Portal Mode (accessible by ADMIN or OWNER in ADMIN portalMode)
  if ((currentUser.role === "ADMIN" || currentUser.role === "OWNER") && portalMode === "ADMIN") {
    return (
      <AdminPanel
        token={authToken}
        adminUser={currentUser}
        onSignOut={handleSignOut}
        onSwitchPortal={() => {
          setPortalMode("CUSTOMER");
          if (typeof window !== "undefined") window.location.hash = "trading";
        }}
      >
        <InstitutionalConsole />
      </AdminPanel>
    );
  }

  // 3. Customer Portal (Trading Terminal, Technical Analysis, Execution, Account, Balances, Billing)
  return (
    <CustomerPortal
      token={authToken}
      user={currentUser}
      onSignOut={handleSignOut}
      onSwitchPortal={
        currentUser.role === "ADMIN" || currentUser.role === "OWNER"
          ? () => {
              setPortalMode("ADMIN");
              if (typeof window !== "undefined") window.location.hash = "admin";
            }
          : undefined
      }
    >
      <InstitutionalConsole />
    </CustomerPortal>
  );
}
