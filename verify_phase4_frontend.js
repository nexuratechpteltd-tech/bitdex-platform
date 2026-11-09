const puppeteer = require("/opt/tauric-platform-staging/dashboard/node_modules/puppeteer");
const fs = require("fs");

const SCREENSHOT_DIR = "/opt/tauric-platform-staging/phase4_screenshots";
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function verify() {
  console.log("Launching headless browser for Phase 4 verification...");
  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  const token = process.env.BITDEX_TEST_TOKEN || "";
  const user = JSON.stringify({ user_id: "USR-328E147ACA", email: process.env.BITDEX_TEST_EMAIL || "test_customer@bitdex.io", role: "CUSTOMER", status: "ACTIVE" });

  await page.evaluateOnNewDocument((t, u) => {
    localStorage.setItem("tauric_session_token", t);
    localStorage.setItem("tauric_session_user", u);
    localStorage.setItem("bitdex_auth_token", t);
    localStorage.setItem("tauric_token", t);
  }, token, user);

  // Helper to click sidebar nav items
  async function clickNav(labelSubstring) {
    return await page.evaluate((label) => {
      const aside = document.querySelector("aside");
      if (!aside) return false;
      const btns = Array.from(aside.querySelectorAll("button"));
      const target = btns.find((b) => b.innerText.toLowerCase().includes(label.toLowerCase()));
      if (target) {
        target.click();
        return true;
      }
      return false;
    }, labelSubstring);
  }

  // 1. Load application at #funding
  console.log("Navigating to https://bitdex.ltd/#funding ...");
  await page.goto("https://bitdex.ltd/#funding", { waitUntil: "networkidle2", timeout: 30000 });
  await new Promise((r) => setTimeout(r, 2000));

  await page.screenshot({ path: `${SCREENSHOT_DIR}/phase4_funding_1440.png`, fullPage: false });
  console.log("Captured phase4_funding_1440.png");

  // Check Funding elements in DOM
  const fundingText = await page.evaluate(() => document.body.innerText);
  const hasFundingHeader = fundingText.includes("Funding & Transfers");
  const hasPaymentsApiBadge = fundingText.includes("EXNESS PAYMENTS API");
  const hasPrimaryWallet = fundingText.includes("Primary USD Wallet");
  const hasPartnerWallet = fundingText.includes("Partner Reward Wallet");
  const hasHistoryLedger = fundingText.includes("Transfer History Ledger");

  console.log("Funding Page Checks:", {
    hasFundingHeader,
    hasPaymentsApiBadge,
    hasPrimaryWallet,
    hasPartnerWallet,
    hasHistoryLedger,
  });

  // 2. Navigate to Trading Dashboard (#terminal) via sidebar click
  console.log("Clicking sidebar: Trading Dashboard ...");
  const clickedTerminal = await clickNav("Trading Dashboard");
  console.log("Clicked Trading Dashboard:", clickedTerminal);
  await new Promise((r) => setTimeout(r, 2000));

  // Click EXECUTE TRADE (DEMO / REAL) button
  const executeBtn = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    const target = btns.find((b) => b.innerText.includes("EXECUTE TRADE"));
    if (target) {
      target.click();
      return true;
    }
    return false;
  });
  console.log("Execute trade button clicked:", executeBtn);
  await new Promise((r) => setTimeout(r, 1000));

  // Take screenshot of Trade Execution Modal (Demo Tab)
  await page.screenshot({ path: `${SCREENSHOT_DIR}/phase4_trade_modal_demo_1440.png` });
  console.log("Captured phase4_trade_modal_demo_1440.png");

  // Click REAL ACCOUNT Tab inside modal
  const realTabClicked = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    const realTab = btns.find((b) => b.innerText.includes("REAL ACCOUNT"));
    if (realTab) {
      realTab.click();
      return true;
    }
    return false;
  });
  console.log("Real Account tab clicked:", realTabClicked);
  await new Promise((r) => setTimeout(r, 1000));

  // Take screenshot of Trade Execution Modal (Real Tab with warning & consent)
  await page.screenshot({ path: `${SCREENSHOT_DIR}/phase4_trade_modal_real_1440.png` });
  console.log("Captured phase4_trade_modal_real_1440.png");

  // Close modal with Cancel
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    const cancel = btns.find((b) => b.innerText.includes("Cancel"));
    if (cancel) cancel.click();
  });
  await new Promise((r) => setTimeout(r, 500));

  // 3. Navigate to Exchange Connections (#connections) via sidebar click
  console.log("Clicking sidebar: Exchange Connections ...");
  const clickedConn = await clickNav("Exchange Connections");
  console.log("Clicked Exchange Connections:", clickedConn);
  await new Promise((r) => setTimeout(r, 2000));

  await page.screenshot({ path: `${SCREENSHOT_DIR}/phase4_connections_1440.png` });
  console.log("Captured phase4_connections_1440.png");

  const connText = await page.evaluate(() => document.body.innerText);
  const hasDemoCard = connText.includes("EXNESS DEMO ACCOUNT");
  const hasRealCard = connText.includes("EXNESS REAL ACCOUNT");
  const hasNotConnected = connText.includes("EXNESS GATEWAY NOT CONNECTED") || connText.includes("GATEWAY NOT CONNECTED");

  console.log("Connections Page Checks:", {
    hasDemoCard,
    hasRealCard,
    hasNotConnected,
  });

  // 4. Verify Zero Charts anywhere
  const chartInspection = await page.evaluate(() => {
    const canvases = document.querySelectorAll("canvas").length;
    const tvWidgets = document.querySelectorAll("[class*='tradingview'], [id*='tradingview']").length;
    const recharts = document.querySelectorAll(".recharts-wrapper, .recharts-surface").length;
    const candlestickElements = document.querySelectorAll("[class*='candlestick']").length;
    return {
      canvases,
      tvWidgets,
      recharts,
      candlestickElements,
      totalCharts: canvases + tvWidgets + recharts + candlestickElements,
    };
  });
  console.log("Chartless Compliance Inspection:", chartInspection);

  // 5. Test 6 Viewports across responsive scale for #funding
  const viewports = [360, 390, 430, 768, 1024, 1440];
  for (const w of viewports) {
    await page.setViewport({ width: w, height: 800 });
    await clickNav("Funding & Transfers");
    await new Promise((r) => setTimeout(r, 500));
    await page.screenshot({ path: `${SCREENSHOT_DIR}/phase4_funding_vp_${w}px.png` });
    console.log(`Captured responsive screenshot: phase4_funding_vp_${w}px.png`);
  }

  await browser.close();
  console.log("Phase 4 frontend verification completed successfully!");
}

verify().catch((err) => {
  console.error("Verification error:", err);
  process.exit(1);
});
