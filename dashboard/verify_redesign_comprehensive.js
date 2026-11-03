/**
 * Comprehensive Staging Verification & Visual Evidence Script
 * Real cryptographically valid JWT tokens for Administrator and Customer.
 */

const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");

const BASE_URL = "http://127.0.0.1:33900";
const OUTPUT_DIR = "/opt/tauric-platform-staging/dashboard/redesign_evidence_output";

// Real signed JWTs generated with tauric_super_secret_staging_jwt_key_2026_xyz
const ADMIN_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJVU1ItQURNLUIwMjJGNDkwIiwiZW1haWwiOiJoZWxsb0BuZXh1cmEubHRkIiwicm9sZSI6IkFETUlOIiwiZXhwIjoxNzkzOTAyMDgwfQ.hJkwS7s7xZ8Juv6sdPNkWJLMk8njFFtqv750Q9taz5Q";
const CUSTOMER_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJVU1ItNDAyRjdCRkU2RCIsImVtYWlsIjoiZGVzaWdua3Jhb0BnbWFpbC5jb20iLCJyb2xlIjoiQ1VTVE9NRVIiLCJleHAiOjE3OTM5MDIwODB9.lceu9H9lU2lnxkbeEO6PenYUN-C9MCoB9f6LO1iaxYQ";

const ADMIN_USER = {
  user_id: "USR-ADM-B022F490",
  email: "hello@nexura.ltd",
  username: "System Administrator",
  role: "ADMIN",
  status: "ACTIVE",
  kyc_status: "APPROVED",
  two_factor_enabled: 1
};

const CUSTOMER_USER = {
  user_id: "USR-402F7BFE6D",
  email: "designkrao@gmail.com",
  username: "Customer User",
  role: "CUSTOMER",
  status: "ACTIVE",
  kyc_status: "PENDING",
  two_factor_enabled: 0
};

async function runVerification() {
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
  });

  const page = await browser.newPage();
  const results = [];

  console.log("======================================================================");
  console.log("BITDEX STAGING LIGHT REDESIGN COMPREHENSIVE VERIFICATION");
  console.log("======================================================================");

  async function assertNoCharts(pageName) {
    const chartElements = await page.evaluate(() => {
      const canvases = document.querySelectorAll("canvas").length;
      const recharts = document.querySelectorAll(".recharts-wrapper, .recharts-surface").length;
      const tvCharts = document.querySelectorAll(".tv-lightweight-charts, [id*='tradingview']").length;
      const svgCharts = document.querySelectorAll("svg.sparkline, svg[class*='chart']").length;
      return { canvases, recharts, tvCharts, svgCharts, total: canvases + recharts + tvCharts + svgCharts };
    });

    if (chartElements.total === 0) {
      console.log(`[PASS] Chart Prohibition Verified on ${pageName}: 0 chart elements detected.`);
      results.push({ area: `No Charts - ${pageName}`, pass: true });
    } else {
      console.error(`[FAIL] Charts detected on ${pageName}:`, chartElements);
      results.push({ area: `No Charts - ${pageName}`, pass: false, detail: chartElements });
    }
  }

  // 1. PUBLIC LANDING PAGE
  console.log("\n--- [Phase 1] Testing Public Landing Page (Light Theme) ---");
  await page.setViewport({ width: 1440, height: 900 });
  await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle2" });
  await page.evaluate(() => {
    localStorage.clear();
  });
  await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1500));

  await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_public_landing_1440.png"), fullPage: false });
  console.log("✓ Captured redesign_public_landing_1440.png");
  await assertNoCharts("Public Landing Page (Desktop)");

  // Public Landing Mobile (390px)
  await page.setViewport({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_public_landing_mobile_390.png"), fullPage: false });
  console.log("✓ Captured redesign_public_landing_mobile_390.png");

  // 2. CUSTOMER PORTAL
  console.log("\n--- [Phase 2] Testing Customer Portal (Light Theme) ---");
  await page.setViewport({ width: 1440, height: 900 });

  await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle2" });
  await page.evaluate((jwt, usr) => {
    localStorage.setItem("tauric_session_token", jwt);
    localStorage.setItem("tauric_session_user", JSON.stringify(usr));
  }, CUSTOMER_JWT, CUSTOMER_USER);

  await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 2500));

  await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_customer_signals_1440.png"), fullPage: false });
  console.log("✓ Captured redesign_customer_signals_1440.png");
  await assertNoCharts("Customer Signals Tab");

  // Click CONNECTIONS tab
  try {
    await page.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll("button"));
      const connTab = tabs.find(b => b.textContent && b.textContent.includes("Exchange Connections"));
      if (connTab) connTab.click();
    });
    await new Promise((r) => setTimeout(r, 1500));
    await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_customer_connections_1440.png"), fullPage: false });
    console.log("✓ Captured redesign_customer_connections_1440.png");
  } catch (e) {
    console.error("Connections tab error:", e.message);
  }

  // Click BALANCES tab
  try {
    await page.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll("button"));
      const balTab = tabs.find(b => b.textContent && b.textContent.includes("Balances"));
      if (balTab) balTab.click();
    });
    await new Promise((r) => setTimeout(r, 1500));
    await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_customer_balances_1440.png"), fullPage: false });
    console.log("✓ Captured redesign_customer_balances_1440.png");
  } catch (e) {
    console.error("Balances tab error:", e.message);
  }

  // Click BILLING tab
  try {
    await page.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll("button"));
      const billTab = tabs.find(b => b.textContent && b.textContent.includes("Billing"));
      if (billTab) billTab.click();
    });
    await new Promise((r) => setTimeout(r, 1500));
    await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_customer_billing_1440.png"), fullPage: false });
    console.log("✓ Captured redesign_customer_billing_1440.png");
  } catch (e) {
    console.error("Billing tab error:", e.message);
  }

  // Click SECURITY tab
  try {
    await page.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll("button"));
      const secTab = tabs.find(b => b.textContent && b.textContent.includes("Security"));
      if (secTab) secTab.click();
    });
    await new Promise((r) => setTimeout(r, 1500));
    await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_customer_security_1440.png"), fullPage: false });
    console.log("✓ Captured redesign_customer_security_1440.png");
  } catch (e) {
    console.error("Security tab error:", e.message);
  }

  // Click PROFIT & LOSS tab
  try {
    await page.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll("button"));
      const pnlTab = tabs.find(b => b.textContent && b.textContent.includes("Profit & Loss"));
      if (pnlTab) pnlTab.click();
    });
    await new Promise((r) => setTimeout(r, 1500));
    await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_customer_pnl_1440.png"), fullPage: false });
    console.log("✓ Captured redesign_customer_pnl_1440.png");
  } catch (e) {
    console.error("P&L tab error:", e.message);
  }

  // Switch back to SIGNALS tab and trigger Technical Analysis
  await page.evaluate(() => {
    const tabs = Array.from(document.querySelectorAll("button"));
    const sigTab = tabs.find(b => b.textContent && b.textContent.includes("Signals"));
    if (sigTab) sigTab.click();
  });
  await new Promise((r) => setTimeout(r, 1500));

  const taTriggered = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    const taBtn = btns.find(b => b.textContent && b.textContent.includes("Technical Analysis"));
    if (taBtn) {
      taBtn.click();
      return true;
    }
    return false;
  });

  if (taTriggered) {
    await new Promise((r) => setTimeout(r, 3500));
    await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_four_engine_board_1440.png"), fullPage: false });
    console.log("✓ Captured redesign_four_engine_board_1440.png");
    await assertNoCharts("Four-Engine Decision Board");
  }

  // 3. ADMINISTRATOR PANEL
  console.log("\n--- [Phase 3] Testing Administrator Panel (Light Theme) ---");
  await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle2" });
  await page.evaluate((jwt, usr) => {
    localStorage.setItem("tauric_session_token", jwt);
    localStorage.setItem("tauric_session_user", JSON.stringify(usr));
  }, ADMIN_JWT, ADMIN_USER);

  await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 2500));

  await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_admin_provider_operations_1440.png"), fullPage: false });
  console.log("✓ Captured redesign_admin_provider_operations_1440.png");
  await assertNoCharts("Admin Provider Operations");

  // Click CUSTOMERS tab
  try {
    await page.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll("button"));
      const tab = tabs.find(b => b.getAttribute("data-testid") === "tab-customers" || (b.textContent && b.textContent.includes("Customers")));
      if (tab) tab.click();
    });
    await new Promise((r) => setTimeout(r, 1500));
    await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_admin_customers_1440.png"), fullPage: false });
    console.log("✓ Captured redesign_admin_customers_1440.png");
  } catch (e) {
    console.error("Admin customers tab error:", e.message);
  }

  // Click SUPPORT INBOX tab
  try {
    await page.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll("button"));
      const tab = tabs.find(b => b.getAttribute("data-testid") === "tab-support-inbox" || (b.textContent && b.textContent.includes("Support")));
      if (tab) tab.click();
    });
    await new Promise((r) => setTimeout(r, 1500));
    await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_admin_support_1440.png"), fullPage: false });
    console.log("✓ Captured redesign_admin_support_1440.png");
  } catch (e) {
    console.error("Admin support tab error:", e.message);
  }

  // Click AI PRICING tab
  try {
    await page.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll("button"));
      const tab = tabs.find(b => b.getAttribute("data-testid") === "tab-ai-pricing" || (b.textContent && (b.textContent.includes("AI Telemetry") || b.textContent.includes("AI Pricing"))));
      if (tab) tab.click();
    });
    await new Promise((r) => setTimeout(r, 1500));
    await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_admin_ai_pricing_1440.png"), fullPage: false });
    console.log("✓ Captured redesign_admin_ai_pricing_1440.png");
  } catch (e) {
    console.error("Admin AI pricing tab error:", e.message);
  }

  // Click AUDIT LOGS tab
  try {
    await page.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll("button"));
      const tab = tabs.find(b => b.getAttribute("data-testid") === "tab-audit-logs" || (b.textContent && (b.textContent.includes("Audit Trail") || b.textContent.includes("Audit Logs"))));
      if (tab) tab.click();
    });
    await new Promise((r) => setTimeout(r, 1500));
    await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_admin_audit_logs_1440.png"), fullPage: false });
    console.log("✓ Captured redesign_admin_audit_logs_1440.png");
  } catch (e) {
    console.error("Admin audit logs tab error:", e.message);
  }

  // Click TERMINAL tab & trigger TA for Admin Fee Exemption verification
  try {
    await page.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll("button"));
      const tab = tabs.find(b => b.getAttribute("data-testid") === "tab-terminal" || (b.textContent && (b.textContent.includes("Signals Terminal") || b.textContent.includes("Terminal"))));
      if (tab) tab.click();
    });
    await new Promise((r) => setTimeout(r, 2000));

    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("button"));
      const taBtn = btns.find(b => b.textContent && b.textContent.includes("Technical Analysis"));
      if (taBtn) taBtn.click();
    });
    await new Promise((r) => setTimeout(r, 3500));

    await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_admin_terminal_fee_exempt_1440.png"), fullPage: false });
    console.log("✓ Captured redesign_admin_terminal_fee_exempt_1440.png");
    await assertNoCharts("Admin Terminal & Four-Engine Board");
  } catch (e) {
    console.error("Admin terminal tab error:", e.message);
  }

  // 4. RESPONSIVE VIEWPORTS
  console.log("\n--- [Phase 4] Testing Responsive Viewports (Light Theme) ---");
  await page.setViewport({ width: 1024, height: 768 });
  await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_responsive_tablet_1024.png"), fullPage: false });
  console.log("✓ Captured redesign_responsive_tablet_1024.png");

  await page.setViewport({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_responsive_mobile_390.png"), fullPage: false });
  console.log("✓ Captured redesign_responsive_mobile_390.png");

  await page.setViewport({ width: 320, height: 568 });
  await page.screenshot({ path: path.join(OUTPUT_DIR, "redesign_responsive_compact_mobile_320.png"), fullPage: false });
  console.log("✓ Captured redesign_responsive_compact_mobile_320.png");

  await browser.close();

  console.log("\n======================================================================");
  console.log(`VERIFICATION COMPLETED: All screenshots saved to ${OUTPUT_DIR}`);
  console.log("======================================================================");
}

runVerification().catch((e) => {
  console.error("Fatal test error:", e);
  process.exit(1);
});
