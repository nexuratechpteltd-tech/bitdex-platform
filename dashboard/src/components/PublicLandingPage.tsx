"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Shield,
  ShieldCheck,
  Zap,
  TrendingUp,
  Cpu,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  User,
  Key,
  Eye,
  EyeOff,
  Loader2,
  Scale,
  Mail,
  Timer,
  RotateCcw,
  Clock,
  Sparkles,
  Lock,
} from "lucide-react";

interface PublicLandingPageProps {
  onLoginSuccess: (token: string, user: any) => void;
}

async function safeJson(res: Response): Promise<any> {
  try {
    const text = await res.text();
    return JSON.parse(text);
  } catch {
    return { detail: `Server response error (${res.status}). Please try again.` };
  }
}

// ─── 6-SLOT MONOSPACE OTP INPUT COMPONENT (Gemini Approved Design) ───
interface SixDigitOtpInputProps {
  value: string;
  onChange: (val: string) => void;
  onComplete?: (val: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
}

function SixDigitOtpInput({ value, onChange, onComplete, disabled, autoFocus = true }: SixDigitOtpInputProps) {
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const digits = Array.from({ length: 6 }, (_, i) => value[i] || "");

  const handleDigitChange = (index: number, val: string) => {
    const clean = val.replace(/[^0-9]/g, "");
    if (!clean) {
      const nextArr = [...digits];
      nextArr[index] = "";
      const nextStr = nextArr.join("").trim();
      onChange(nextStr);
      return;
    }

    const lastChar = clean[clean.length - 1];
    const nextArr = [...digits];
    nextArr[index] = lastChar;
    const nextStr = nextArr.join("");
    onChange(nextStr);

    if (index < 5 && inputRefs.current[index + 1]) {
      inputRefs.current[index + 1]?.focus();
    }

    if (nextStr.length === 6 && onComplete) {
      onComplete(nextStr);
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace") {
      if (!digits[index] && index > 0) {
        inputRefs.current[index - 1]?.focus();
        const nextArr = [...digits];
        nextArr[index - 1] = "";
        onChange(nextArr.join(""));
      } else {
        const nextArr = [...digits];
        nextArr[index] = "";
        onChange(nextArr.join(""));
      }
    } else if (e.key === "ArrowLeft" && index > 0) {
      inputRefs.current[index - 1]?.focus();
    } else if (e.key === "ArrowRight" && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/[^0-9]/g, "").slice(0, 6);
    if (pasted) {
      onChange(pasted);
      const targetFocus = Math.min(pasted.length, 5);
      inputRefs.current[targetFocus]?.focus();
      if (pasted.length === 6 && onComplete) {
        onComplete(pasted);
      }
    }
  };

  return (
    <div className="flex items-center justify-between gap-2 sm:gap-2.5 py-2">
      {digits.map((digit, idx) => (
        <input
          key={idx}
          ref={(el) => { inputRefs.current[idx] = el; }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={1}
          autoFocus={autoFocus && idx === 0}
          disabled={disabled}
          value={digit}
          onChange={(e) => handleDigitChange(idx, e.target.value)}
          onKeyDown={(e) => handleKeyDown(idx, e)}
          onPaste={handlePaste}
          className={`w-11 sm:w-12 h-14 text-center font-mono text-2xl font-black rounded-xl border transition-all select-none outline-none ${
            digit
              ? "bg-[#1E2329] border-[#00E5FF] text-[#00E5FF] shadow-[0_0_12px_rgba(0,229,255,0.25)]"
              : "bg-[#11161F] border-[#2B3139] text-[#EAECEF] hover:border-[#848E9C]"
          } focus:border-[#00E5FF] focus:bg-[#1E2329] focus:ring-2 focus:ring-[#00E5FF]/20`}
        />
      ))}
    </div>
  );
}

export default function PublicLandingPage({ onLoginSuccess }: PublicLandingPageProps) {
  const [authModal, setAuthModal] = useState<"SIGN_IN" | "SIGN_UP" | "FORGOT_PASSWORD" | null>(null);
  
  // Credentials
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [username, setUsername] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [country, setCountry] = useState("SG");
  
  // Mandatory Two-Step Email OTP & 2FA State (Sign In)
  const [loginStage, setLoginStage] = useState<"CREDENTIALS" | "OTP_VERIFY">("CREDENTIALS");
  const [challengeId, setChallengeId] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [maskedEmail, setMaskedEmail] = useState("");
  const [twoFactorRequired, setTwoFactorRequired] = useState(false);
  const [countdown, setCountdown] = useState(300);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [rememberMe, setRememberMe] = useState(false);

  // Registration Multi-Step State (Phase 2 & 7)
  const [signupStage, setSignupStage] = useState<"CREDENTIALS" | "OTP_VERIFY" | "SUCCESS">("CREDENTIALS");
  const [signupChallengeId, setSignupChallengeId] = useState("");
  const [signupOtpCode, setSignupOtpCode] = useState("");
  const [signupMaskedEmail, setSignupMaskedEmail] = useState("");
  const [signupCountdown, setSignupCountdown] = useState(300);
  const [signupCooldown, setSignupCooldown] = useState(0);
  const [signupEmail, setSignupEmail] = useState("");
  const [provisionedUser, setProvisionedUser] = useState<any>(null);

  // Delivery status reporting
  const [deliveryStatus, setDeliveryStatus] = useState<"SENDING" | "ACCEPTED" | "PENDING" | "FAILED" | null>(null);

  // Forgot Password State
  const [forgotStage, setForgotStage] = useState<"EMAIL" | "OTP" | "NEW_PASSWORD">("EMAIL");
  const [resetChallengeId, setResetChallengeId] = useState("");
  const [resetOtpCode, setResetOtpCode] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [resetCountdown, setResetCountdown] = useState(300);
  const [resetCooldown, setResetCooldown] = useState(0);

  const [agreeTerms, setAgreeTerms] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  // Timer effect for OTP validity and resend cooldowns
  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (authModal === "SIGN_IN" && loginStage === "OTP_VERIFY") {
      timer = setInterval(() => {
        setCountdown((prev) => (prev > 0 ? prev - 1 : 0));
        setResendCooldown((prev) => (prev > 0 ? prev - 1 : 0));
      }, 1000);
    } else if (authModal === "SIGN_UP" && signupStage === "OTP_VERIFY") {
      timer = setInterval(() => {
        setSignupCountdown((prev) => (prev > 0 ? prev - 1 : 0));
        setSignupCooldown((prev) => (prev > 0 ? prev - 1 : 0));
      }, 1000);
    } else if (authModal === "FORGOT_PASSWORD" && forgotStage === "OTP") {
      timer = setInterval(() => {
        setResetCountdown((prev) => (prev > 0 ? prev - 1 : 0));
        setResetCooldown((prev) => (prev > 0 ? prev - 1 : 0));
      }, 1000);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [authModal, loginStage, signupStage, forgotStage]);

  const resetModalState = () => {
    setLoginStage("CREDENTIALS");
    setChallengeId("");
    setOtpCode("");
    setTotpCode("");
    setMaskedEmail("");
    setTwoFactorRequired(false);
    setCountdown(300);
    setResendCooldown(0);
    setRememberMe(false);
    setPassword("");
    setConfirmPassword("");

    setSignupStage("CREDENTIALS");
    setSignupChallengeId("");
    setSignupOtpCode("");
    setSignupMaskedEmail("");
    setSignupCountdown(300);
    setSignupCooldown(0);
    setSignupEmail("");
    setProvisionedUser(null);

    setForgotStage("EMAIL");
    setResetChallengeId("");
    setResetOtpCode("");
    setResetToken("");
    setNewPassword("");
    setResetCountdown(300);
    setResetCooldown(0);

    setDeliveryStatus(null);
    setErrorMsg(null);
    setSuccessMsg(null);
  };

  // ─── Sign In Handlers ──────────────────────────────────────────────
  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    setDeliveryStatus("SENDING");

    try {
      const res = await fetch("/api/backend/saas/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          password,
        }),
      });

      const data = await safeJson(res);
      if (!res.ok) {
        setDeliveryStatus(null);
        throw new Error(data.detail || data.error || "Invalid email or password.");
      }

      if (data.status === "EMAIL_OTP_REQUIRED") {
        setChallengeId(data.challenge_id);
        setMaskedEmail(data.email_masked || email);
        setTwoFactorRequired(Boolean(data.requires_2fa));
        setLoginStage("OTP_VERIFY");
        setCountdown(data.expires_in_seconds || 300);
        setResendCooldown(60);

        if (data.delivery_status === "ACCEPTED" || data.delivery_status === "SENT") {
          setDeliveryStatus("ACCEPTED");
          setSuccessMsg(data.message || "Email provider accepted the message");
        } else if (data.delivery_status === "FAILED" || data.delivery_blocked) {
          setDeliveryStatus("FAILED");
          setErrorMsg(data.message || "Could not send verification email. Please retry.");
        } else {
          setDeliveryStatus("PENDING");
          setSuccessMsg(data.message || "Delivery status pending");
        }
        return;
      }

      if (data.token) {
        setDeliveryStatus(null);
        onLoginSuccess(data.token, data.user);
      }
    } catch (err: any) {
      setDeliveryStatus(null);
      setErrorMsg(err.message || "Failed to sign in. Please verify your credentials.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerifyOtp = async (codeToVerify?: string) => {
    const code = (codeToVerify || otpCode).trim();
    if (code.length !== 6) {
      setErrorMsg("Please enter the complete 6-digit email verification code.");
      return;
    }
    if (twoFactorRequired && (!totpCode || totpCode.trim().length !== 6)) {
      setErrorMsg("Please enter the 6-digit authenticator 2FA code.");
      return;
    }

    setIsLoading(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      const res = await fetch("/api/backend/saas/auth/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          challenge_id: challengeId,
          otp_code: code,
          totp_code: totpCode.trim() || undefined,
          remember_me: rememberMe,
        }),
      });

      const data = await safeJson(res);
      if (!res.ok) {
        throw new Error(data.detail || data.error || "Verification failed. Check the code.");
      }

      if (data.status === "TOTP_2FA_REQUIRED") {
        setTwoFactorRequired(true);
        setErrorMsg("Two-factor authenticator code required for privileged access.");
        return;
      }

      if (data.token) {
        onLoginSuccess(data.token, data.user);
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Invalid or expired verification code.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleResendOtp = async () => {
    if (resendCooldown > 0 || !challengeId) return;
    setIsLoading(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    setDeliveryStatus("SENDING");
    try {
      const res = await fetch("/api/backend/saas/auth/resend-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ challenge_id: challengeId }),
      });
      const data = await safeJson(res);
      if (!res.ok) {
        setDeliveryStatus("FAILED");
        throw new Error(data.detail || "Could not send verification email. Please retry.");
      }
      setResendCooldown(data.resend_cooldown_seconds || 60);
      setCountdown(data.expires_in_seconds || 300);

      if (data.delivery_status === "ACCEPTED" || data.delivery_status === "SENT") {
        setDeliveryStatus("ACCEPTED");
        setSuccessMsg(data.message || "Email provider accepted the message");
      } else if (data.delivery_status === "FAILED" || data.delivery_blocked) {
        setDeliveryStatus("FAILED");
        setErrorMsg(data.message || "Could not send verification email. Please retry.");
      } else {
        setDeliveryStatus("PENDING");
        setSuccessMsg(data.message || "Delivery status pending");
      }
    } catch (err: any) {
      setDeliveryStatus("FAILED");
      setErrorMsg(err.message || "Could not send verification email. Please retry.");
    } finally {
      setIsLoading(false);
    }
  };

  // ─── Sign Up Handlers (Phase 2 & 7) ────────────────────────────────
  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!firstName.trim() || !lastName.trim()) {
      setErrorMsg("Please enter both your first and last name.");
      return;
    }
    if (password.length < 8) {
      setErrorMsg("Password must be at least 8 characters long.");
      return;
    }
    if (password !== confirmPassword) {
      setErrorMsg("Passwords do not match. Please re-enter.");
      return;
    }
    if (!agreeTerms) {
      setErrorMsg("You must accept the Terms of Service and Risk Disclosures.");
      return;
    }

    setIsLoading(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    setDeliveryStatus("SENDING");

    try {
      const res = await fetch("/api/backend/saas/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          password,
          username: username.trim() || `${firstName.trim().toLowerCase()}_trader`,
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          country,
        }),
      });

      const data = await safeJson(res);
      if (!res.ok) {
        setDeliveryStatus(null);
        throw new Error(data.detail || data.error || "Registration failed.");
      }

      setSignupChallengeId(data.challenge_id);
      setSignupEmail(email.trim().toLowerCase());
      setSignupMaskedEmail(data.email_masked || email);
      setSignupCountdown(data.expires_in_seconds || 300);
      setSignupCooldown(data.resend_cooldown_seconds || 60);
      setSignupStage("OTP_VERIFY");

      if (data.delivery_status === "ACCEPTED" || data.delivery_status === "SENT") {
        setDeliveryStatus("ACCEPTED");
        setSuccessMsg(data.message || "Email provider accepted the message");
      } else if (data.delivery_status === "FAILED" || data.delivery_blocked) {
        setDeliveryStatus("FAILED");
        setErrorMsg(data.message || "Could not send verification email. Please retry.");
      } else {
        setDeliveryStatus("PENDING");
        setSuccessMsg(data.message || "Delivery status pending");
      }
    } catch (err: any) {
      setDeliveryStatus(null);
      setErrorMsg(err.message || "Failed to create account.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerifySignUpOtp = async (codeToVerify?: string) => {
    const code = (codeToVerify || signupOtpCode).trim();
    if (code.length !== 6) {
      setErrorMsg("Please enter the complete 6-digit verification code.");
      return;
    }

    setIsLoading(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    const emailToSend = (signupEmail || email).trim().toLowerCase();

    try {
      const res = await fetch("/api/backend/saas/auth/register/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: emailToSend,
          challenge_id: signupChallengeId,
          otp_code: code,
        }),
      });

      const data = await safeJson(res);
      if (!res.ok) {
        const errorText = typeof data.detail === "string"
          ? data.detail
          : (Array.isArray(data.detail) ? data.detail.map((d: any) => d.msg).join(", ") : (data.error || "Verification failed. Check the code."));
        throw new Error(errorText);
      }

      setProvisionedUser(data.user || data);
      setSignupStage("SUCCESS");
      setSuccessMsg("Account successfully verified and activated!");
    } catch (err: any) {
      setErrorMsg(err.message || "Invalid or expired verification code.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleResendSignUpOtp = async () => {
    if (signupCooldown > 0 || !signupChallengeId) return;
    setIsLoading(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    setDeliveryStatus("SENDING");
    try {
      const res = await fetch("/api/backend/saas/auth/register/resend-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: (signupEmail || email).trim().toLowerCase(),
          challenge_id: signupChallengeId,
        }),
      });
      const data = await safeJson(res);
      if (!res.ok) {
        setDeliveryStatus("FAILED");
        throw new Error(data.detail || "Could not send verification email. Please retry.");
      }
      setSignupCooldown(data.resend_cooldown_seconds || 60);
      setSignupCountdown(data.expires_in_seconds || 300);

      if (data.delivery_status === "ACCEPTED" || data.delivery_status === "SENT") {
        setDeliveryStatus("ACCEPTED");
        setSuccessMsg(data.message || "Email provider accepted the message");
      } else if (data.delivery_status === "FAILED" || data.delivery_blocked) {
        setDeliveryStatus("FAILED");
        setErrorMsg(data.message || "Could not send verification email. Please retry.");
      } else {
        setDeliveryStatus("PENDING");
        setSuccessMsg(data.message || "Delivery status pending");
      }
    } catch (err: any) {
      setDeliveryStatus("FAILED");
      setErrorMsg(err.message || "Could not send verification email. Please retry.");
    } finally {
      setIsLoading(false);
    }
  };

  // ─── Forgot Password Handlers ──────────────────────────────────────
  const handleForgotStep1Email = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    setDeliveryStatus("SENDING");
    try {
      const res = await fetch("/api/backend/saas/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
      const data = await safeJson(res);
      if (!res.ok) {
        setDeliveryStatus(null);
        throw new Error(data.detail || "Password reset request failed");
      }
      
      setResetChallengeId(data.challenge_id);
      setMaskedEmail(data.email_masked || email);
      setResetCountdown(data.expires_in_seconds || 300);
      setResetCooldown(data.resend_cooldown_seconds || 60);
      setForgotStage("OTP");

      if (data.delivery_status === "ACCEPTED" || data.delivery_status === "SENT") {
        setDeliveryStatus("ACCEPTED");
        setSuccessMsg(data.message || "Email provider accepted the message");
      } else if (data.delivery_status === "FAILED" || data.delivery_blocked) {
        setDeliveryStatus("FAILED");
        setErrorMsg(data.message || "Could not send verification email. Please retry.");
      } else {
        setDeliveryStatus("PENDING");
        setSuccessMsg(data.message || "Delivery status pending");
      }
    } catch (err: any) {
      setDeliveryStatus(null);
      setErrorMsg(err.message || "Password reset request failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotStep2VerifyOtp = async (codeToVerify?: string) => {
    const code = (codeToVerify || resetOtpCode).trim();
    if (code.length !== 6) {
      setErrorMsg("Please enter the complete 6-digit verification code.");
      return;
    }
    setIsLoading(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await fetch("/api/backend/saas/auth/forgot-password/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          challenge_id: resetChallengeId,
          otp_code: code,
        }),
      });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.detail || "Invalid or expired reset code");
      setResetToken(data.reset_token);
      setForgotStage("NEW_PASSWORD");
      setSuccessMsg(data.message || "Code verified. Please set your new password.");
    } catch (err: any) {
      setErrorMsg(err.message || "Invalid or expired code.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotResendOtp = async () => {
    if (resetCooldown > 0 || !resetChallengeId) return;
    setIsLoading(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    setDeliveryStatus("SENDING");
    try {
      const res = await fetch("/api/backend/saas/auth/forgot-password/resend-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ challenge_id: resetChallengeId }),
      });
      const data = await safeJson(res);
      if (!res.ok) {
        setDeliveryStatus("FAILED");
        throw new Error(data.detail || "Could not send verification email. Please retry.");
      }
      setResetCooldown(data.resend_cooldown_seconds || 60);
      setResetCountdown(data.expires_in_seconds || 300);

      if (data.delivery_status === "ACCEPTED" || data.delivery_status === "SENT") {
        setDeliveryStatus("ACCEPTED");
        setSuccessMsg(data.message || "Email provider accepted the message");
      } else if (data.delivery_status === "FAILED" || data.delivery_blocked) {
        setDeliveryStatus("FAILED");
        setErrorMsg(data.message || "Could not send verification email. Please retry.");
      } else {
        setDeliveryStatus("PENDING");
        setSuccessMsg(data.message || "Delivery status pending");
      }
    } catch (err: any) {
      setDeliveryStatus("FAILED");
      setErrorMsg(err.message || "Could not send verification email. Please retry.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotStep3Complete = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 8) {
      setErrorMsg("New password must be at least 8 characters long.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setErrorMsg("New password and confirm password do not match.");
      return;
    }
    setIsLoading(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await fetch("/api/backend/saas/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          challenge_id: resetChallengeId,
          reset_token: resetToken,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.detail || "Failed to update password");
      setSuccessMsg("Password successfully reset! Please sign in with your new password.");
      setTimeout(() => {
        resetModalState();
        setAuthModal("SIGN_IN");
      }, 1500);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to reset password.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0B0E11] text-[#EAECEF] flex flex-col font-sans selection:bg-sky-500 selection:text-[#EAECEF]">
      {/* ─── PUBLIC NAVBAR ────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 w-full border-b border-[#2B3139] bg-[#1E2329]/90 backdrop-blur-md">
        <div className="max-w-[1760px] mx-auto px-4 sm:px-6 lg:px-8 xl:px-10 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/bitdex-logo.svg" alt="BITDEX" width={160} height={32} className="h-8 w-auto" />
            <span className="px-2 py-0.5 text-[10px] font-mono bg-purple-500/10 text-purple-300 rounded-md border border-purple-500/20 font-bold hidden sm:inline-block">
              QUANTITATIVE INTELLIGENCE
            </span>
          </div>

          <nav className="hidden md:flex items-center gap-8 text-xs font-semibold text-slate-300">
            <a href="#features" className="hover:text-purple-400 transition-colors">Features</a>
            <a href="#signals" className="hover:text-purple-400 transition-colors">AI Intelligence</a>
            <a href="#exchanges" className="hover:text-purple-400 transition-colors">Exchange Adapters</a>
            <a href="#pricing" className="hover:text-purple-400 transition-colors">Transparent Pricing</a>
            <a href="#security" className="hover:text-purple-400 transition-colors">Security & Non-Custodial</a>
          </nav>

          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                resetModalState();
                setAuthModal("SIGN_IN");
              }}
              className="px-4 py-2 rounded-xl text-xs font-bold text-[#EAECEF] hover:text-[#EAECEF] hover:bg-[#151921] border border-[#263554] transition-all cursor-pointer"
            >
              Sign In
            </button>
            <button
              onClick={() => {
                resetModalState();
                setAuthModal("SIGN_UP");
              }}
              className="px-4 py-2 rounded-xl text-xs font-bold text-[#EAECEF] bg-purple-600 hover:bg-purple-500 transition-all cursor-pointer shadow-lg shadow-purple-600/20"
            >
              Get Started
            </button>
          </div>
        </div>
      </header>

      {/* ─── HERO SECTION ─────────────────────────────────────────── */}
      <section className="relative overflow-hidden pt-20 pb-24 md:pt-28 md:pb-32 border-b border-slate-800/60">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_-20%,rgba(120,40,200,0.25),rgba(255,255,255,0))]" />
        
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center space-y-6">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-300 text-xs font-mono">
            <ShieldCheck className="w-4 h-4 text-purple-400" />
            Non-Custodial Architecture • Withdrawal Permissions Strictly Prohibited
          </div>

          <h1 className="text-4xl sm:text-5xl md:text-6xl font-black text-[#EAECEF] tracking-tight leading-tight">
            Institutional Quantitative AI & Execution for{" "}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-purple-400 via-indigo-300 to-pink-400">
              Modern Digital Asset Traders
            </span>
          </h1>

          <p className="max-w-3xl mx-auto text-sm sm:text-base text-[#848E9C] leading-relaxed">
            Bitdex delivers autonomous quantitative market scanning, AI signal streams, and independent on-demand AI research. 
            Connect your exchange accounts with read-only credentials; our platform enforces absolute non-custodial protection.
          </p>

          <div className="pt-4 flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={() => {
                resetModalState();
                setAuthModal("SIGN_UP");
              }}
              className="w-full sm:w-auto px-8 py-3.5 rounded-2xl bg-purple-600 hover:bg-purple-500 text-[#EAECEF] font-bold text-sm flex items-center justify-center gap-2 transition-all cursor-pointer shadow-xl shadow-purple-600/30"
            >
              Create Bitdex Account
              <ArrowRight className="w-4 h-4" />
            </button>

            <button
              onClick={() => {
                resetModalState();
                setAuthModal("SIGN_IN");
              }}
              className="w-full sm:w-auto px-8 py-3.5 rounded-2xl bg-[#151e32] hover:bg-[#1a2642] border border-[#263554] text-[#EAECEF] font-bold text-sm transition-all cursor-pointer"
            >
              Sign In to Customer Portal
            </button>
          </div>

          {/* Key Trust Metrics */}
          <div className="pt-12 grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl mx-auto text-left">
            <div className="p-4 rounded-2xl bg-[#1E2329] border border-[#2B3139] shadow-sm">
              <div className="text-xs text-[#848E9C] font-mono">EXECUTION SAFETY</div>
              <div className="text-lg font-bold text-emerald-400 mt-1">Read & Trade Only</div>
              <div className="text-[11px] text-[#848E9C] mt-0.5">Withdrawals rejected in vault</div>
            </div>
            <div className="p-4 rounded-2xl bg-[#1E2329] border border-[#2B3139] shadow-sm">
              <div className="text-xs text-[#848E9C] font-mono">SUPPORTED ASSETS</div>
              <div className="text-lg font-bold text-purple-300 mt-1">Crypto & Forex</div>
              <div className="text-[11px] text-[#848E9C] mt-0.5">Binance, Bybit, Bitget, MT5</div>
            </div>
            <div className="p-4 rounded-2xl bg-[#1E2329] border border-[#2B3139] shadow-sm">
              <div className="text-xs text-[#848E9C] font-mono">AI QUANT ENGINE</div>
              <div className="text-lg font-bold text-indigo-300 mt-1">Bitdex Neural Quant</div>
              <div className="text-[11px] text-[#848E9C] mt-0.5">On-demand deep synthesis</div>
            </div>
            <div className="p-4 rounded-2xl bg-[#1E2329] border border-[#2B3139] shadow-sm">
              <div className="text-xs text-[#848E9C] font-mono">OFFICIAL SUPPORT</div>
              <div className="text-lg font-bold text-amber-300 mt-1">go@bitdex.ltd</div>
              <div className="text-[11px] text-[#848E9C] mt-0.5">Verified ticketing & live SMTP</div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── FEATURES GRID ────────────────────────────────────────── */}
      <section id="features" className="py-20 border-b border-slate-800/60 bg-slate-950/40">
        <div className="max-w-[1760px] mx-auto px-4 sm:px-6 lg:px-8 xl:px-10 space-y-12">
          <div className="text-center space-y-3">
            <h2 className="text-2xl sm:text-3xl font-black text-[#EAECEF]">Engineered for Trading Rigor</h2>
            <p className="text-xs sm:text-sm text-[#848E9C] max-w-2xl mx-auto">
              Built on mathematical order-flow models, dynamic ATR bounds, and strict capital preservation rules.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-6 rounded-3xl bg-[#1E2329] border border-[#2B3139] shadow-sm space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                <Cpu className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-[#EAECEF]">Independent AI Intelligence</h3>
              <p className="text-xs text-[#848E9C] leading-relaxed">
                Run deep multi-timeframe quantitative market syntheses on any asset on demand. Deducts pay-per-use credits with full automatic refund protection on failure.
              </p>
            </div>

            <div className="p-6 rounded-3xl bg-[#1E2329] border border-[#2B3139] shadow-sm space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                <TrendingUp className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-[#EAECEF]">Real-Time AI Signals Stream</h3>
              <p className="text-xs text-[#848E9C] leading-relaxed">
                Continuous high-probability algorithmic signals across Crypto, Forex, and Metals with strict risk-to-reward ratios and transparent technical checklists.
              </p>
            </div>

            <div className="p-6 rounded-3xl bg-[#1E2329] border border-[#2B3139] shadow-sm space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-[#EAECEF]">Generic Exchange Connectivity</h3>
              <p className="text-xs text-[#848E9C] leading-relaxed">
                Provider-neutral connection interface supporting any brokerage or exchange. Verified adapters provide read-only balance sync while unverified connections remain securely encrypted.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ─── TRANSPARENT PRICING ──────────────────────────────────── */}
      <section id="pricing" className="py-20 border-b border-slate-800/60 bg-[#0b0f19]">
        <div className="max-w-[1760px] mx-auto px-4 sm:px-6 lg:px-8 xl:px-10 space-y-12">
          <div className="text-center space-y-3">
            <h2 className="text-2xl sm:text-3xl font-black text-[#EAECEF]">Simple, Predictable Platform Pricing</h2>
            <p className="text-xs sm:text-sm text-[#848E9C] max-w-xl mx-auto">
              No profit-sharing and no hidden custody fees. You keep 100% of your gains and pay only for platform execution and AI intelligence.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto">
            {/* Activation Fee Card */}
            <div className="p-6 rounded-3xl bg-[#1E2329] border border-[#2B3139] shadow-sm space-y-4 flex flex-col justify-between">
              <div className="space-y-2">
                <span className="text-[11px] font-mono text-purple-400 font-bold uppercase">Account Onboarding</span>
                <h4 className="text-xl font-black text-[#EAECEF]">Activation Fee</h4>
                <div className="text-3xl font-black text-[#EAECEF] pt-2">$20.00 <span className="text-xs font-normal text-[#848E9C]">one-time</span></div>
                <p className="text-xs text-[#848E9C] pt-2">
                  One-time onboarding and account verification fee. Assessed only upon qualifying live account activation.
                </p>
              </div>
              <ul className="text-xs text-slate-300 space-y-2 pt-4 border-t border-slate-800">
                <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" /> Verified exchange connectivity</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" /> Non-custodial security setup</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" /> Staging & sandbox testing</li>
              </ul>
            </div>

            {/* Per-Order Execution Fee Card */}
            <div className="p-6 rounded-3xl bg-purple-950/30 border-2 border-purple-500/50 space-y-4 flex flex-col justify-between shadow-2xl shadow-purple-600/10">
              <div className="space-y-2">
                <span className="text-[11px] font-mono text-purple-300 font-bold uppercase">Execution Meter</span>
                <h4 className="text-xl font-black text-[#EAECEF]">Platform Execution Fee</h4>
                <div className="text-3xl font-black text-purple-300 pt-2">$0.30 <span className="text-xs font-normal text-[#848E9C]">/ qualifying order</span></div>
                <p className="text-xs text-slate-300 pt-2">
                  Deducted automatically from your prepaid balance only when a qualifying real order is confirmed. Unsubmitted and paper orders remain free.
                </p>
              </div>
              <ul className="text-xs text-slate-300 space-y-2 pt-4 border-t border-purple-500/30">
                <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" /> Atomic ledger debits</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" /> Idempotent charge deduplication</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" /> Multi-fill counted as single order</li>
              </ul>
            </div>

            {/* AI Research Fee Card */}
            <div className="p-6 rounded-3xl bg-[#1E2329] border border-[#2B3139] shadow-sm space-y-4 flex flex-col justify-between">
              <div className="space-y-2">
                <span className="text-[11px] font-mono text-indigo-400 font-bold uppercase">Intelligence Meter</span>
                <h4 className="text-xl font-black text-[#EAECEF]">AI Market Analysis</h4>
                <div className="text-3xl font-black text-[#EAECEF] pt-2">$1.00 <span className="text-xs font-normal text-[#848E9C]">/ on-demand run (100¢)</span></div>
                <p className="text-xs text-[#848E9C] pt-2">
                  On-demand quantitative intelligence run with pre-confirmation display. Automatically refunded if an analysis fails.
                </p>
              </div>
              <ul className="text-xs text-slate-300 space-y-2 pt-4 border-t border-slate-800">
                <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" /> Multi-timeframe synthesis</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" /> Automatic refund on failure</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" /> Idempotent execution token</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ─── LEGAL & RISK DISCLOSURE ──────────────────────────────── */}
      <section id="security" className="py-12 border-b border-slate-800/60 bg-slate-950 text-[11px] text-[#848E9C]">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 space-y-4">
          <div className="flex items-center gap-2 font-bold text-[#848E9C] uppercase tracking-wider text-xs">
            <Scale className="w-4 h-4 text-purple-400" />
            Regulatory & Trading Risk Disclosures
          </div>
          <p className="leading-relaxed">
            <strong>Risk Warning:</strong> Trading spot cryptocurrencies, foreign exchange, and commodities carries substantial risk and is not suitable for all investors. Algorithmic software execution involves technical, market, and latency risks. Past backtest or live performance does not guarantee future results.
          </p>
          <p className="leading-relaxed">
            <strong>Non-Custodial Service:</strong> Bitdex does not accept custody of digital assets or fiat currency for trading purposes. Customers maintain exclusive ownership of their exchange accounts. Platform software operates strictly via restricted API permissions with withdrawal and transfer rights disabled.
          </p>
          <p className="leading-relaxed">
            <strong>Official Support:</strong> For assistance, contact our official support team at <a href="mailto:go@bitdex.ltd" className="text-purple-400 underline font-semibold">go@bitdex.ltd</a>.
          </p>
        </div>
      </section>

      {/* ─── FOOTER ──────────────────────────────────────────────── */}
      <footer className="py-8 bg-slate-950 text-center text-xs text-[#848E9C] border-t border-slate-900">
        <div className="flex items-center justify-center gap-2 mb-2">
          <img src="/bitdex-icon.svg" alt="Bitdex" width={16} height={16} className="w-4 h-4" />
          <span className="font-bold text-[#848E9C]">BITDEX</span>
        </div>
        <p>© 2026 Bitdex. All rights reserved. Primary domain: https://bitdex.ltd • Support: go@bitdex.ltd</p>
      </footer>

      {/* ─── AUTHENTICATION MODAL ─────────────────────────────────── */}

      {/* ─── ASYMMETRIC SPLIT-TERMINAL AUTHENTICATION MODAL (Gemini Approved Architecture) ─── */}
      {authModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 md:p-8 bg-black/85 backdrop-blur-md overflow-y-auto">
          <div className="relative w-full max-w-5xl rounded-3xl bg-[#151921] border border-[#2B3139] shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9)] overflow-hidden my-auto flex flex-col md:flex-row min-h-[580px]">
            
            {/* ─── LEFT SHOWCASE TERMINAL (45% Width on Desktop, Compact on Mobile) ─── */}
            <div className="hidden md:flex md:w-[45%] bg-[#11161F] border-r border-[#2B3139] p-7 flex-col justify-between relative overflow-hidden">
              {/* Ambient background glow */}
              <div className="absolute -top-24 -left-24 w-64 h-64 bg-[#00E5FF]/10 rounded-full blur-3xl pointer-events-none" />
              <div className="absolute -bottom-24 -right-24 w-64 h-64 bg-purple-600/10 rounded-full blur-3xl pointer-events-none" />

              {/* Terminal Top Info */}
              <div className="relative space-y-6">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#00E5FF] to-purple-600 flex items-center justify-center text-[#0B0E11] font-black text-base shadow-lg shadow-[#00E5FF]/20">
                    B
                  </div>
                  <div>
                    <div className="text-sm font-black text-[#EAECEF] tracking-wide flex items-center gap-1.5 font-mono">
                      BITDEX <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#00E5FF]/15 text-[#00E5FF] border border-[#00E5FF]/30 font-bold">QUANT 2.0</span>
                    </div>
                    <div className="text-[11px] font-mono text-[#848E9C]">Autonomous Execution & Synthesizer</div>
                  </div>
                </div>

                {/* 4-Engine Decision Synthesizer Interactive Strip */}
                <div className="space-y-2.5">
                  <div className="text-[10px] font-mono font-bold text-[#848E9C] uppercase tracking-wider flex items-center justify-between">
                    <span>4-Engine Synthesizer</span>
                    <span className="text-[#0ECB81] flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#0ECB81] animate-pulse" />
                      ONLINE
                    </span>
                  </div>

                  <div className="space-y-2 font-mono text-xs">
                    {/* TAURIC Engine */}
                    <div className="p-3 rounded-xl bg-[#151921] border border-[#2B3139] hover:border-[#00E5FF]/40 transition-colors">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-[#00E5FF] flex items-center gap-1.5">
                          <Zap className="w-3.5 h-3.5" /> TAURIC ENGINE
                        </span>
                        <span className="text-[10px] text-[#00E5FF] bg-[#00E5FF]/10 px-1.5 py-0.5 rounded">99.8% Sync</span>
                      </div>
                      <p className="text-[11px] text-[#848E9C] mt-1 font-sans">
                        Macro Structural & Orderflow Trend Analysis
                      </p>
                    </div>

                    {/* JEV Engine */}
                    <div className="p-3 rounded-xl bg-[#151921] border border-[#2B3139] hover:border-purple-500/40 transition-colors">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-purple-400 flex items-center gap-1.5">
                          <Cpu className="w-3.5 h-3.5" /> JEV ENGINE
                        </span>
                        <span className="text-[10px] text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">Sub-1ms</span>
                      </div>
                      <p className="text-[11px] text-[#848E9C] mt-1 font-sans">
                        Orderbook Depth & Microstructure Arbitrage Guard
                      </p>
                    </div>

                    {/* CIPHER Engine */}
                    <div className="p-3 rounded-xl bg-[#151921] border border-[#2B3139] hover:border-[#0ECB81]/40 transition-colors">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-[#0ECB81] flex items-center gap-1.5">
                          <TrendingUp className="w-3.5 h-3.5" /> CIPHER ENGINE
                        </span>
                        <span className="text-[10px] text-[#0ECB81] bg-[#0ECB81]/10 px-1.5 py-0.5 rounded">12 TF Active</span>
                      </div>
                      <p className="text-[11px] text-[#848E9C] mt-1 font-sans">
                        Multi-Timeframe Statistical Regime Classifier
                      </p>
                    </div>

                    {/* OCTOBOT Engine */}
                    <div className="p-3 rounded-xl bg-[#151921] border border-[#2B3139] hover:border-[#F0B90B]/40 transition-colors">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-[#F0B90B] flex items-center gap-1.5">
                          <ShieldCheck className="w-3.5 h-3.5" /> OCTOBOT ENGINE
                        </span>
                        <span className="text-[10px] text-[#F0B90B] bg-[#F0B90B]/10 px-1.5 py-0.5 rounded">Non-Custodial</span>
                      </div>
                      <p className="text-[11px] text-[#848E9C] mt-1 font-sans">
                        Autonomous Grid & Algorithmic Execution Controller
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Platform Trust & Telemetry Strip */}
              <div className="relative pt-6 border-t border-[#2B3139] space-y-3 font-mono text-xs">
                <div className="flex items-center gap-2 text-[#848E9C] text-[11px]">
                  <ShieldCheck className="w-4 h-4 text-[#0ECB81] shrink-0" />
                  <span>Zero-Custody Architecture: Withdrawal permissions strictly prohibited in vault.</span>
                </div>
                <div className="flex items-center justify-between text-[10px] text-[#848E9C] pt-1">
                  <span>Feeds: Binance • Bitget • Metals</span>
                  <span className="text-[#0ECB81] font-bold">● PASS</span>
                </div>
              </div>
            </div>

            {/* ─── MOBILE STICKY COMPACT HEADER (<md Screens) ─── */}
            <div className="flex md:hidden items-center justify-between px-4 py-3 bg-[#11161F] border-b border-[#2B3139] text-xs font-mono">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-lg bg-gradient-to-tr from-[#00E5FF] to-purple-600 flex items-center justify-center text-[#0B0E11] font-black text-xs">
                  B
                </div>
                <span className="font-bold text-[#EAECEF]">BITDEX QUANT</span>
              </div>
              <div className="flex items-center gap-2 text-[10px]">
                <span className="text-[#0ECB81] flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#0ECB81]" /> 4 Engines
                </span>
                <span className="text-[#848E9C]">|</span>
                <span className="text-[#00E5FF]">Non-Custodial</span>
              </div>
            </div>

            {/* ─── RIGHT VAULT INTERACTION CARD (55% Width on Desktop) ─── */}
            <div className="flex-1 bg-[#151921] flex flex-col justify-between relative">
              {/* Dynamic Top Accent Bar */}
              <div className={`h-1 w-full ${signupStage === "SUCCESS" ? "bg-[#0ECB81]" : "bg-gradient-to-r from-[#00E5FF] via-purple-500 to-[#0ECB81]"}`} />

              <div className="p-6 sm:p-8 md:p-10 space-y-5">
                {/* Header Row */}
                <div className="flex items-start justify-between border-b border-[#2B3139] pb-4">
                  <div>
                    <h3 className="text-base sm:text-lg font-black text-[#EAECEF] flex items-center gap-2">
                      <User className="w-4 h-4 text-[#00E5FF]" />
                      {authModal === "SIGN_IN" && (loginStage === "CREDENTIALS" ? "Sign In to Bitdex" : "Two-Step Verification")}
                      {authModal === "SIGN_UP" && (
                        signupStage === "CREDENTIALS" ? "Create Bitdex Account" :
                        signupStage === "OTP_VERIFY" ? "Verify Email Address" :
                        "Account Verified"
                      )}
                      {authModal === "FORGOT_PASSWORD" && (
                        forgotStage === "EMAIL" ? "Forgot Password" :
                        forgotStage === "OTP" ? "Verify Reset Code" : "Set New Password"
                      )}
                    </h3>
                    <p className="text-[11px] text-[#848E9C] mt-0.5 font-mono">
                      {authModal === "SIGN_IN" && (loginStage === "CREDENTIALS" ? "Enter your credentials to enter the terminal" : "Confirm email one-time passcode")}
                      {authModal === "SIGN_UP" && (
                        signupStage === "CREDENTIALS" ? "Institutional Non-Custodial Algorithmic Access" :
                        signupStage === "OTP_VERIFY" ? "Enter the 6-digit code dispatched to your email" :
                        "Your non-custodial trading account is active"
                      )}
                      {authModal === "FORGOT_PASSWORD" && "Recover your Bitdex account credentials"}
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      setAuthModal(null);
                      resetModalState();
                    }}
                    className="p-1 rounded-lg text-[#848E9C] hover:text-[#EAECEF] hover:bg-[#1E2329] transition-all cursor-pointer"
                  >
                    ✕
                  </button>
                </div>

                {/* Feedback Alerts */}
                {errorMsg && (
                  <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
                    <span>{errorMsg}</span>
                  </div>
                )}
                {successMsg && signupStage !== "SUCCESS" && (
                  <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
                    <span>{successMsg}</span>
                  </div>
                )}

                {/* ─── VIEW 1: SIGN IN FLOW ─── */}
                {authModal === "SIGN_IN" && (
                  <>
                    {loginStage === "CREDENTIALS" ? (
                      <form onSubmit={handleSignIn} className="space-y-4">
                        <div>
                          <label className="block text-xs font-semibold text-slate-300 mb-1">Email Address</label>
                          <input
                            type="email"
                            required
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="trader@bitdex.ltd"
                            className="w-full px-3.5 py-2.5 rounded-xl bg-[#11161F] border border-[#2B3139] text-[#EAECEF] text-xs placeholder-[#848E9C] focus:outline-none focus:border-[#00E5FF] font-medium"
                          />
                        </div>

                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <label className="text-xs font-semibold text-slate-300">Password</label>
                            <button
                              type="button"
                              onClick={() => {
                                resetModalState();
                                setAuthModal("FORGOT_PASSWORD");
                              }}
                              className="text-[11px] text-[#00E5FF] hover:underline cursor-pointer"
                            >
                              Forgot password?
                            </button>
                          </div>
                          <div className="relative">
                            <input
                              type={showPassword ? "text" : "password"}
                              required
                              value={password}
                              onChange={(e) => setPassword(e.target.value)}
                              placeholder="••••••••"
                              className="w-full px-3.5 py-2.5 rounded-xl bg-[#11161F] border border-[#2B3139] text-[#EAECEF] text-xs placeholder-[#848E9C] focus:outline-none focus:border-[#00E5FF]"
                            />
                            <button
                              type="button"
                              onClick={() => setShowPassword(!showPassword)}
                              className="absolute right-3 top-2.5 text-[#848E9C] hover:text-[#EAECEF] cursor-pointer"
                            >
                              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </button>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 pt-0.5 pb-1">
                          <input
                            type="checkbox"
                            id="rememberMeCheckbox"
                            checked={rememberMe}
                            onChange={(e) => setRememberMe(e.target.checked)}
                            className="w-4 h-4 rounded bg-[#11161F] border-[#2B3139] text-[#00E5FF] focus:ring-0 cursor-pointer"
                          />
                          <label htmlFor="rememberMeCheckbox" className="text-xs text-slate-300 cursor-pointer select-none">
                            Remember browser for 24 hours
                          </label>
                        </div>

                        <button
                          type="submit"
                          disabled={isLoading}
                          className="w-full py-3 rounded-xl bg-[#00E5FF] hover:bg-[#00E5FF]/90 text-[#0B0E11] font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-lg shadow-[#00E5FF]/20 disabled:opacity-50"
                        >
                          {isLoading ? (
                            <>
                              <Loader2 className="w-4 h-4 animate-spin" />
                              <span>Sending verification code…</span>
                            </>
                          ) : (
                            "Sign In to Trading Terminal"
                          )}
                        </button>

                        <div className="text-center text-xs text-[#848E9C] pt-2 border-t border-[#2B3139]">
                          Don't have an account?{" "}
                          <button
                            type="button"
                            onClick={() => {
                              resetModalState();
                              setAuthModal("SIGN_UP");
                            }}
                            className="text-[#00E5FF] hover:underline font-bold cursor-pointer"
                          >
                            Create Bitdex Account
                          </button>
                        </div>
                      </form>
                    ) : (
                      <div className="space-y-4">
                        {/* Dispatch Metadata Card */}
                        <div className="p-3.5 rounded-2xl bg-[#11161F] border border-[#2B3139] space-y-2">
                          <div className="flex items-center justify-between text-xs font-semibold text-[#00E5FF]">
                            <span className="flex items-center gap-1.5">
                              <Mail className="w-3.5 h-3.5 text-[#00E5FF]" />
                              Code dispatched to:
                            </span>
                            <span className="font-mono text-[#EAECEF]">{maskedEmail}</span>
                          </div>
                          <div className="flex items-center justify-between text-[11px] text-[#848E9C] font-mono">
                            <span className="flex items-center gap-1">
                              <Timer className="w-3.5 h-3.5 text-[#848E9C]" />
                              Expires in:
                            </span>
                            <span className={countdown < 60 ? "text-rose-400 font-bold" : "text-[#EAECEF] font-bold"}>
                              {Math.floor(countdown / 60)}:{(countdown % 60).toString().padStart(2, "0")}
                            </span>
                          </div>
                        </div>

                        {/* Truthful Delivery Status Reporting */}
                        {deliveryStatus === "SENDING" && (
                          <div className="p-3 rounded-xl bg-purple-500/10 border border-purple-500/30 text-purple-300 text-xs flex items-center gap-2">
                            <Loader2 className="w-4 h-4 shrink-0 animate-spin text-purple-400" />
                            <span className="font-semibold">Dispatching OTP via GoDaddy SMTP…</span>
                          </div>
                        )}
                        {deliveryStatus === "ACCEPTED" && (
                          <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2.5">
                            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
                            <div className="space-y-0.5">
                              <div className="font-bold text-emerald-200">Email provider accepted the message</div>
                              <div className="text-[11px] text-emerald-300/80">
                                Verification dispatch accepted by GoDaddy SMTP for delivery.
                              </div>
                            </div>
                          </div>
                        )}
                        {deliveryStatus === "PENDING" && (
                          <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs flex items-center gap-2.5">
                            <Clock className="w-4 h-4 shrink-0 text-cyan-400" />
                            <div className="space-y-0.5">
                              <div className="font-bold text-cyan-200">Delivery status pending</div>
                              <div className="text-[11px] text-cyan-300/80">
                                Awaiting SMTP provider delivery confirmation.
                              </div>
                            </div>
                          </div>
                        )}
                        {deliveryStatus === "FAILED" && (
                          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2.5">
                            <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
                            <div className="space-y-0.5">
                              <div className="font-bold text-rose-200">Could not send verification email. Please retry.</div>
                              <div className="text-[11px] text-rose-300/80">
                                Provider dispatch failed. Use the Resend code button below to try again.
                              </div>
                            </div>
                          </div>
                        )}

                        {/* 6-Slot Monospace OTP Input */}
                        <div>
                          <label className="block text-xs font-semibold text-slate-300 mb-1">
                            6-Digit Email Verification Code
                          </label>
                          <SixDigitOtpInput
                            value={otpCode}
                            onChange={setOtpCode}
                            onComplete={(val) => {
                              if (!twoFactorRequired) {
                                handleVerifyOtp(val);
                              }
                            }}
                            disabled={isLoading || countdown === 0}
                          />
                        </div>

                        {/* Conditional Privileged Authenticator TOTP Prompt (ONLY IF REQUIRED) */}
                        {twoFactorRequired && (
                          <div className="p-3.5 rounded-xl bg-indigo-950/40 border border-indigo-500/40 space-y-2">
                            <label className="block text-xs font-bold text-indigo-300 flex items-center gap-1.5">
                              <Key className="w-3.5 h-3.5 text-indigo-400" />
                              Mandatory Authenticator 2FA (TOTP)
                            </label>
                            <input
                              type="text"
                              maxLength={6}
                              value={totpCode}
                              onChange={(e) => setTotpCode(e.target.value.replace(/[^0-9]/g, ""))}
                              placeholder="000000"
                              className="w-full px-3 py-2 rounded-lg bg-[#11161F] border border-indigo-500 text-sm font-mono text-center tracking-widest text-indigo-200 focus:outline-none"
                            />
                            <div className="text-[10px] text-[#848E9C]">
                              Administrative and enrolled accounts require secondary TOTP authenticator validation.
                            </div>
                          </div>
                        )}

                        {/* Primary Button: Swaps to Resend if Expired */}
                        {countdown > 0 ? (
                          <button
                            type="button"
                            onClick={() => handleVerifyOtp()}
                            disabled={isLoading || otpCode.length !== 6}
                            className="w-full py-3 rounded-xl bg-[#00E5FF] hover:bg-[#00E5FF]/90 disabled:opacity-50 text-[#0B0E11] font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-lg shadow-[#00E5FF]/20"
                          >
                            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Verify Code & Sign In"}
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={handleResendOtp}
                            disabled={isLoading}
                            className="w-full py-3 rounded-xl bg-amber-500 hover:bg-amber-400 text-[#0B0E11] font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-lg shadow-amber-500/20"
                          >
                            <RotateCcw className="w-4 h-4" />
                            Send Fresh 6-Digit Code
                          </button>
                        )}

                        {/* Resend & Back controls */}
                        <div className="flex items-center justify-between text-xs pt-1 border-t border-[#2B3139]">
                          <button
                            type="button"
                            onClick={handleResendOtp}
                            disabled={resendCooldown > 0 || isLoading}
                            className="text-[#00E5FF] hover:underline disabled:text-[#848E9C] font-semibold flex items-center gap-1 cursor-pointer disabled:cursor-not-allowed"
                          >
                            <RotateCcw className="w-3 h-3" />
                            {resendCooldown > 0 ? `Resend code (${resendCooldown}s)` : "Resend code"}
                          </button>

                          <button
                            type="button"
                            onClick={() => {
                              setLoginStage("CREDENTIALS");
                              setOtpCode("");
                              setTotpCode("");
                              setErrorMsg(null);
                            }}
                            className="text-[#848E9C] hover:text-[#EAECEF] cursor-pointer"
                          >
                            Use different account
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}

                {/* ─── VIEW 2: SIGN UP FLOW (Phase 2 & 7) ─── */}
                {authModal === "SIGN_UP" && (
                  <>
                    {/* Stage 1: Signup Form */}
                    {signupStage === "CREDENTIALS" && (
                      <form onSubmit={handleSignUp} className="space-y-3.5">
                        <div className="grid grid-cols-2 gap-2.5">
                          <div>
                            <label className="block text-xs font-semibold text-slate-300 mb-1">First Name</label>
                            <input
                              type="text"
                              required
                              value={firstName}
                              onChange={(e) => setFirstName(e.target.value)}
                              placeholder="Alex"
                              className="w-full px-3.5 py-2.5 rounded-xl bg-[#11161F] border border-[#2B3139] text-[#EAECEF] text-xs placeholder-[#848E9C] focus:outline-none focus:border-[#00E5FF]"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-semibold text-slate-300 mb-1">Last Name</label>
                            <input
                              type="text"
                              required
                              value={lastName}
                              onChange={(e) => setLastName(e.target.value)}
                              placeholder="Morgan"
                              className="w-full px-3.5 py-2.5 rounded-xl bg-[#11161F] border border-[#2B3139] text-[#EAECEF] text-xs placeholder-[#848E9C] focus:outline-none focus:border-[#00E5FF]"
                            />
                          </div>
                        </div>

                        <div>
                          <label className="block text-xs font-semibold text-slate-300 mb-1">Email Address</label>
                          <input
                            type="email"
                            required
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="alex.morgan@domain.com"
                            className="w-full px-3.5 py-2.5 rounded-xl bg-[#11161F] border border-[#2B3139] text-[#EAECEF] text-xs placeholder-[#848E9C] focus:outline-none focus:border-[#00E5FF]"
                          />
                        </div>

                        <div className="grid grid-cols-2 gap-2.5">
                          <div>
                            <label className="block text-xs font-semibold text-slate-300 mb-1">Password</label>
                            <div className="relative">
                              <input
                                type={showPassword ? "text" : "password"}
                                required
                                minLength={8}
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="••••••••"
                                className="w-full px-3.5 py-2.5 rounded-xl bg-[#11161F] border border-[#2B3139] text-[#EAECEF] text-xs placeholder-[#848E9C] focus:outline-none focus:border-[#00E5FF]"
                              />
                              <button
                                type="button"
                                onClick={() => setShowPassword(!showPassword)}
                                className="absolute right-2.5 top-2.5 text-[#848E9C] hover:text-[#EAECEF] cursor-pointer"
                              >
                                {showPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                              </button>
                            </div>
                          </div>

                          <div>
                            <label className="block text-xs font-semibold text-slate-300 mb-1">Confirm Password</label>
                            <div className="relative">
                              <input
                                type={showConfirmPassword ? "text" : "password"}
                                required
                                minLength={8}
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                placeholder="••••••••"
                                className="w-full px-3.5 py-2.5 rounded-xl bg-[#11161F] border border-[#2B3139] text-[#EAECEF] text-xs placeholder-[#848E9C] focus:outline-none focus:border-[#00E5FF]"
                              />
                              <button
                                type="button"
                                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                                className="absolute right-2.5 top-2.5 text-[#848E9C] hover:text-[#EAECEF] cursor-pointer"
                              >
                                {showConfirmPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                              </button>
                            </div>
                          </div>
                        </div>

                        <div>
                          <label className="block text-xs font-semibold text-slate-300 mb-1">Country of Residence</label>
                          <select
                            value={country}
                            onChange={(e) => setCountry(e.target.value)}
                            className="w-full px-3.5 py-2.5 rounded-xl bg-[#11161F] border border-[#2B3139] text-[#EAECEF] text-xs focus:outline-none focus:border-[#00E5FF]"
                          >
                            <option value="SG">Singapore (SG)</option>
                            <option value="US">United States (US)</option>
                            <option value="GB">United Kingdom (GB)</option>
                            <option value="AE">United Arab Emirates (AE)</option>
                            <option value="DE">Germany (DE)</option>
                            <option value="CH">Switzerland (CH)</option>
                            <option value="HK">Hong Kong (HK)</option>
                            <option value="AU">Australia (AU)</option>
                          </select>
                        </div>

                        <div className="flex items-start gap-2 pt-1">
                          <input
                            type="checkbox"
                            id="terms"
                            checked={agreeTerms}
                            onChange={(e) => setAgreeTerms(e.target.checked)}
                            className="mt-1 rounded bg-[#11161F] border-[#2B3139] text-[#00E5FF] focus:ring-0 cursor-pointer"
                          />
                          <label htmlFor="terms" className="text-[11px] text-[#848E9C] leading-tight cursor-pointer">
                            I acknowledge that Bitdex is a non-custodial software service. I have reviewed the trading risks and agree to the Terms of Service.
                          </label>
                        </div>

                        <button
                          type="submit"
                          disabled={isLoading}
                          className="w-full py-3 rounded-xl bg-[#00E5FF] hover:bg-[#00E5FF]/90 text-[#0B0E11] font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-lg shadow-[#00E5FF]/20 disabled:opacity-50"
                        >
                          {isLoading ? (
                            <>
                              <Loader2 className="w-4 h-4 animate-spin" />
                              <span>Dispatching Verification Code…</span>
                            </>
                          ) : (
                            "Create Account & Dispatch OTP"
                          )}
                        </button>

                        <div className="text-center text-xs text-[#848E9C] pt-2 border-t border-[#2B3139]">
                          Already have an account?{" "}
                          <button
                            type="button"
                            onClick={() => {
                              resetModalState();
                              setAuthModal("SIGN_IN");
                            }}
                            className="text-[#00E5FF] hover:underline font-bold cursor-pointer"
                          >
                            Sign In
                          </button>
                        </div>
                      </form>
                    )}

                    {/* Stage 2: Registration OTP Verification */}
                    {signupStage === "OTP_VERIFY" && (
                      <div className="space-y-4">
                        <div className="p-3.5 rounded-2xl bg-[#11161F] border border-[#2B3139] space-y-2">
                          <div className="flex items-center justify-between text-xs font-semibold text-[#00E5FF]">
                            <span className="flex items-center gap-1.5">
                              <Mail className="w-3.5 h-3.5 text-[#00E5FF]" />
                              Verification code sent to:
                            </span>
                            <span className="font-mono text-[#EAECEF]">{signupMaskedEmail}</span>
                          </div>
                          <div className="flex items-center justify-between text-[11px] text-[#848E9C] font-mono">
                            <span className="flex items-center gap-1">
                              <Timer className="w-3.5 h-3.5 text-[#848E9C]" />
                              Code validity:
                            </span>
                            <span className={signupCountdown < 60 ? "text-rose-400 font-bold" : "text-[#EAECEF] font-bold"}>
                              {Math.floor(signupCountdown / 60)}:{(signupCountdown % 60).toString().padStart(2, "0")}
                            </span>
                          </div>
                        </div>

                        {/* Delivery Status */}
                        {deliveryStatus === "SENDING" && (
                          <div className="p-3 rounded-xl bg-purple-500/10 border border-purple-500/30 text-purple-300 text-xs flex items-center gap-2">
                            <Loader2 className="w-4 h-4 shrink-0 animate-spin text-purple-400" />
                            <span className="font-semibold">Dispatching registration code via GoDaddy SMTP…</span>
                          </div>
                        )}
                        {deliveryStatus === "ACCEPTED" && (
                          <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2.5">
                            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
                            <div className="space-y-0.5">
                              <div className="font-bold text-emerald-200">Email provider accepted the message</div>
                              <div className="text-[11px] text-emerald-300/80">
                                Registration dispatch accepted by GoDaddy SMTP for delivery.
                              </div>
                            </div>
                          </div>
                        )}
                        {deliveryStatus === "PENDING" && (
                          <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs flex items-center gap-2.5">
                            <Clock className="w-4 h-4 shrink-0 text-cyan-400" />
                            <div className="space-y-0.5">
                              <div className="font-bold text-cyan-200">Delivery status pending</div>
                              <div className="text-[11px] text-cyan-300/80">
                                Awaiting SMTP provider delivery confirmation.
                              </div>
                            </div>
                          </div>
                        )}
                        {deliveryStatus === "FAILED" && (
                          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2.5">
                            <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
                            <div className="space-y-0.5">
                              <div className="font-bold text-rose-200">Could not send verification email. Please retry.</div>
                              <div className="text-[11px] text-rose-300/80">
                                Provider dispatch failed. Use the Resend code button below to try again.
                              </div>
                            </div>
                          </div>
                        )}

                        <div>
                          <label className="block text-xs font-semibold text-slate-300 mb-1">
                            Enter 6-Digit Email Verification Code
                          </label>
                          <SixDigitOtpInput
                            value={signupOtpCode}
                            onChange={setSignupOtpCode}
                            onComplete={(val) => handleVerifySignUpOtp(val)}
                            disabled={isLoading || signupCountdown === 0}
                          />
                        </div>

                        {/* Primary Action Button */}
                        {signupCountdown > 0 ? (
                          <button
                            type="button"
                            onClick={() => handleVerifySignUpOtp()}
                            disabled={isLoading || signupOtpCode.length !== 6}
                            className="w-full py-3 rounded-xl bg-[#0ECB81] hover:bg-[#0ECB81]/90 disabled:opacity-50 text-[#0B0E11] font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-lg shadow-[#0ECB81]/20"
                          >
                            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Verify Email & Complete Registration"}
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={handleResendSignUpOtp}
                            disabled={isLoading}
                            className="w-full py-3 rounded-xl bg-amber-500 hover:bg-amber-400 text-[#0B0E11] font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-lg shadow-amber-500/20"
                          >
                            <RotateCcw className="w-4 h-4" />
                            Send Fresh 6-Digit Code
                          </button>
                        )}

                        <div className="flex items-center justify-between text-xs pt-1 border-t border-[#2B3139]">
                          <button
                            type="button"
                            onClick={handleResendSignUpOtp}
                            disabled={signupCooldown > 0 || isLoading}
                            className="text-[#00E5FF] hover:underline disabled:text-[#848E9C] font-semibold flex items-center gap-1 cursor-pointer disabled:cursor-not-allowed"
                          >
                            <RotateCcw className="w-3 h-3" />
                            {signupCooldown > 0 ? `Resend code (${signupCooldown}s)` : "Resend code"}
                          </button>

                          <button
                            type="button"
                            onClick={() => {
                              setSignupStage("CREDENTIALS");
                              setSignupOtpCode("");
                              setErrorMsg(null);
                            }}
                            className="text-[#848E9C] hover:text-[#EAECEF] cursor-pointer"
                          >
                            Change email
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Stage 3: Registration Success Screen */}
                    {signupStage === "SUCCESS" && (
                      <div className="space-y-6 text-center py-4">
                        <div className="w-16 h-16 rounded-3xl bg-[#0ECB81]/15 border border-[#0ECB81]/30 flex items-center justify-center text-[#0ECB81] mx-auto shadow-lg shadow-[#0ECB81]/10">
                          <CheckCircle2 className="w-9 h-9" />
                        </div>

                        <div className="space-y-1.5">
                          <h3 className="text-xl font-black text-[#EAECEF]">
                            Account Successfully Verified & Provisioned
                          </h3>
                          <p className="text-xs text-[#848E9C] max-w-sm mx-auto font-sans">
                            Welcome to Bitdex! Your non-custodial trading profile has been initialized with verified email authentication.
                          </p>
                        </div>

                        {/* Provisioning Dossier Card */}
                        <div className="p-4 rounded-2xl bg-[#11161F] border border-[#2B3139] text-left font-mono text-xs space-y-2.5">
                          <div className="text-[10px] uppercase font-bold text-[#848E9C] tracking-wider border-b border-[#2B3139] pb-1.5 flex items-center justify-between">
                            <span>Account Provisioning Dossier</span>
                            <span className="text-[#0ECB81] font-bold">● ACTIVE TENANT</span>
                          </div>
                          <div className="grid grid-cols-2 gap-2 text-[11px]">
                            <div>
                              <span className="text-[#848E9C] block text-[10px]">ACCOUNT ID</span>
                              <span className="text-[#EAECEF] font-bold truncate block">{provisionedUser?.user_id || "USR-VERIFIED"}</span>
                            </div>
                            <div>
                              <span className="text-[#848E9C] block text-[10px]">EMAIL STATUS</span>
                              <span className="text-[#0ECB81] font-bold flex items-center gap-1">
                                <CheckCircle2 className="w-3 h-3" /> VERIFIED & BOUND
                              </span>
                            </div>
                            <div>
                              <span className="text-[#848E9C] block text-[10px]">VAULT POLICY</span>
                              <span className="text-[#00E5FF] font-bold">NON-CUSTODIAL (ZERO-WITHDRAWAL)</span>
                            </div>
                            <div>
                              <span className="text-[#848E9C] block text-[10px]">QUANT ENGINES</span>
                              <span className="text-[#EAECEF] font-bold">TAURIC • JEV • CIPHER • OCTOBOT</span>
                            </div>
                          </div>
                        </div>

                        <button
                          type="button"
                          onClick={() => {
                            resetModalState();
                            setAuthModal("SIGN_IN");
                            setEmail(provisionedUser?.email || email);
                          }}
                          className="w-full py-3.5 rounded-xl bg-[#0ECB81] hover:bg-[#0ECB81]/90 text-[#0B0E11] font-bold font-mono text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-lg shadow-[#0ECB81]/20"
                        >
                          <span>Launch BITDEX Trading Terminal</span>
                          <ArrowRight className="w-4 h-4" />
                        </button>
                      </div>
                    )}
                  </>
                )}

                {/* ─── VIEW 3: FORGOT PASSWORD 3-STEP FLOW ─── */}
                {authModal === "FORGOT_PASSWORD" && (
                  <div className="space-y-4">
                    {forgotStage === "EMAIL" && (
                      <form onSubmit={handleForgotStep1Email} className="space-y-4">
                        <p className="text-xs text-[#848E9C]">
                          Enter your registered email address. We will dispatch a 6-digit verification code to reset your password.
                        </p>

                        <div>
                          <label className="block text-xs font-semibold text-slate-300 mb-1">Email Address</label>
                          <input
                            type="email"
                            required
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="user@bitdex.ltd"
                            className="w-full px-3.5 py-2.5 rounded-xl bg-[#11161F] border border-[#2B3139] text-[#EAECEF] text-xs placeholder-[#848E9C] focus:outline-none focus:border-[#00E5FF]"
                          />
                        </div>

                        <button
                          type="submit"
                          disabled={isLoading}
                          className="w-full py-3 rounded-xl bg-[#00E5FF] hover:bg-[#00E5FF]/90 text-[#0B0E11] font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-lg shadow-[#00E5FF]/20 disabled:opacity-50"
                        >
                          {isLoading ? (
                            <>
                              <Loader2 className="w-4 h-4 animate-spin" />
                              <span>Sending verification code…</span>
                            </>
                          ) : (
                            "Send 6-Digit Reset Code"
                          )}
                        </button>

                        <div className="text-center text-xs text-[#848E9C] pt-2 border-t border-[#2B3139]">
                          Remembered your password?{" "}
                          <button
                            type="button"
                            onClick={() => {
                              resetModalState();
                              setAuthModal("SIGN_IN");
                            }}
                            className="text-[#00E5FF] hover:underline font-bold cursor-pointer"
                          >
                            Sign In
                          </button>
                        </div>
                      </form>
                    )}

                    {forgotStage === "OTP" && (
                      <div className="space-y-4">
                        <div className="p-3.5 rounded-2xl bg-[#11161F] border border-[#2B3139] space-y-2">
                          <div className="flex items-center justify-between text-xs font-semibold text-[#00E5FF]">
                            <span className="flex items-center gap-1.5">
                              <Mail className="w-3.5 h-3.5 text-[#00E5FF]" />
                              Reset code sent to:
                            </span>
                            <span className="font-mono text-[#EAECEF]">{maskedEmail}</span>
                          </div>
                          <div className="flex items-center justify-between text-[11px] text-[#848E9C] font-mono">
                            <span className="flex items-center gap-1">
                              <Timer className="w-3.5 h-3.5 text-[#848E9C]" />
                              Expires in:
                            </span>
                            <span className={resetCountdown < 60 ? "text-rose-400 font-bold" : "text-[#EAECEF] font-bold"}>
                              {Math.floor(resetCountdown / 60)}:{(resetCountdown % 60).toString().padStart(2, "0")}
                            </span>
                          </div>
                        </div>

                        {deliveryStatus === "ACCEPTED" && (
                          <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2.5">
                            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
                            <div className="space-y-0.5">
                              <div className="font-bold text-emerald-200">Email provider accepted the message</div>
                              <div className="text-[11px] text-emerald-300/80">
                                Reset code dispatch accepted by GoDaddy SMTP for delivery.
                              </div>
                            </div>
                          </div>
                        )}
                        {deliveryStatus === "FAILED" && (
                          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2.5">
                            <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
                            <div className="space-y-0.5">
                              <div className="font-bold text-rose-200">Could not send verification email. Please retry.</div>
                              <div className="text-[11px] text-rose-300/80">
                                Provider dispatch failed. Use the Resend code button below to try again.
                              </div>
                            </div>
                          </div>
                        )}

                        <div>
                          <label className="block text-xs font-semibold text-slate-300 mb-1">
                            Enter 6-Digit Reset Code
                          </label>
                          <SixDigitOtpInput
                            value={resetOtpCode}
                            onChange={setResetOtpCode}
                            onComplete={(val) => handleForgotStep2VerifyOtp(val)}
                            disabled={isLoading || resetCountdown === 0}
                          />
                        </div>

                        {resetCountdown > 0 ? (
                          <button
                            type="button"
                            onClick={() => handleForgotStep2VerifyOtp()}
                            disabled={isLoading || resetOtpCode.length !== 6}
                            className="w-full py-3 rounded-xl bg-[#00E5FF] hover:bg-[#00E5FF]/90 text-[#0B0E11] font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-lg shadow-[#00E5FF]/20 disabled:opacity-50"
                          >
                            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Verify Code"}
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={handleForgotResendOtp}
                            disabled={isLoading}
                            className="w-full py-3 rounded-xl bg-amber-500 hover:bg-amber-400 text-[#0B0E11] font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-lg shadow-amber-500/20"
                          >
                            <RotateCcw className="w-4 h-4" />
                            Send Fresh 6-Digit Code
                          </button>
                        )}

                        <div className="flex items-center justify-between text-xs pt-1 border-t border-[#2B3139]">
                          <button
                            type="button"
                            onClick={handleForgotResendOtp}
                            disabled={resetCooldown > 0 || isLoading}
                            className="text-[#00E5FF] hover:underline disabled:text-[#848E9C] font-semibold flex items-center gap-1 cursor-pointer disabled:cursor-not-allowed"
                          >
                            <RotateCcw className="w-3 h-3" />
                            {resetCooldown > 0 ? `Resend code (${resetCooldown}s)` : "Resend code"}
                          </button>

                          <button
                            type="button"
                            onClick={() => setForgotStage("EMAIL")}
                            className="text-[#848E9C] hover:text-[#EAECEF] cursor-pointer"
                          >
                            Change email
                          </button>
                        </div>
                      </div>
                    )}

                    {forgotStage === "NEW_PASSWORD" && (
                      <form onSubmit={handleForgotStep3Complete} className="space-y-4">
                        <p className="text-xs text-[#848E9C]">
                          Verification successful. Please enter your new password below.
                        </p>

                        <div>
                          <label className="block text-xs font-semibold text-slate-300 mb-1">New Password (min 8 chars)</label>
                          <input
                            type="password"
                            required
                            minLength={8}
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                            placeholder="••••••••"
                            className="w-full px-3.5 py-2.5 rounded-xl bg-[#11161F] border border-[#2B3139] text-[#EAECEF] text-xs placeholder-[#848E9C] focus:outline-none focus:border-[#00E5FF]"
                          />
                        </div>

                        <div>
                          <label className="block text-xs font-semibold text-slate-300 mb-1">Confirm New Password</label>
                          <input
                            type="password"
                            required
                            minLength={8}
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            placeholder="••••••••"
                            className="w-full px-3.5 py-2.5 rounded-xl bg-[#11161F] border border-[#2B3139] text-[#EAECEF] text-xs placeholder-[#848E9C] focus:outline-none focus:border-[#00E5FF]"
                          />
                        </div>

                        <button
                          type="submit"
                          disabled={isLoading}
                          className="w-full py-3 rounded-xl bg-[#00E5FF] hover:bg-[#00E5FF]/90 text-[#0B0E11] font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-lg shadow-[#00E5FF]/20 disabled:opacity-50"
                        >
                          {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Save New Password"}
                        </button>
                      </form>
                    )}
                  </div>
                )}

              </div>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
