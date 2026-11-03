const puppeteer = require('/opt/tauric-platform/dashboard/node_modules/puppeteer');
const fs = require('fs');
const path = require('path');

const OUTPUT_DIR = '/opt/tauric-platform-staging/dashboard/evidence_cleanup_output';
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const CUST_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJVU1ItNDAyRjdCRkU2RCIsInVzZXJfaWQiOiJVU1ItNDAyRjdCRkU2RCIsImVtYWlsIjoiZGVzaWdua3Jhb0BnbWFpbC5jb20iLCJyb2xlIjoiQ1VTVE9NRVIiLCJleHAiOjE3OTM3OTc1MTZ9.RLuKv9nNnSQjeP0N0jgp18boSLHvWcDhi1dHKLsQuIg";
const CUST_USER = {
  user_id: "USR-402F7BFE6D",
  email: "designkrao@gmail.com",
  username: "billal95",
  role: "CUSTOMER",
  status: "ACTIVE",
  first_name: "Billal",
  last_name: "",
  country: "GB",
  email_verified: true,
  two_factor_enabled: true,
  must_change_password: false,
  kyc_status: "NOT_REQUIRED"
};

const ADMIN_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJVU1ItQURNLUIwMjJGNDkwIiwidXNlcl9pZCI6IlVTUi1BRE0tQjAyMkY0OTAiLCJlbWFpbCI6ImhlbGxvQG5leHVyYS5sdGQiLCJyb2xlIjoiQURNSU4iLCJleHAiOjE3OTM3OTc1MTZ9.yvmQWMW4hZFudBBGnTyZWQV2fPZDw-IoIFgFgTuOvLo";
const ADMIN_USER = {
  user_id: "USR-ADM-B022F490",
  email: "hello@nexura.ltd",
  username: "System Administrator",
  role: "ADMIN",
  status: "ACTIVE",
  first_name: "System",
  last_name: "Administrator",
  country: "DE",
  email_verified: true,
  two_factor_enabled: true,
  must_change_password: false,
  kyc_status: "VERIFIED"
};

const BASE_URL = "http://127.0.0.1:33900";

async function run() {
  console.log("🚀 Starting Comprehensive Evidence Capture (Puppeteer)...");
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/chromium-browser',
    headless: 'new',
    protocolTimeout: 60000,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--window-size=1440,900'
    ]
  });

  try {
    const page = await browser.newPage();
    page.on('dialog', async dialog => {
      console.log('Dialog dismissed:', dialog.message());
      await dialog.dismiss();
    });

    // ─────────────────────────────────────────────────────────────────────────
    // 1. CUSTOMER PORTAL - DESKTOP 1440x900 (HEADER & SIGNAL CARDS WITH DIRECTIONAL METER)
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [1/9] Capturing Customer Portal Signals & Meters (1440x900)...");
    await page.setViewport({ width: 1440, height: 900 });
    await page.goto(`${BASE_URL}/`, { waitUntil: 'domcontentloaded' });
    
    // Inject Customer Session
    await page.evaluate((tok, usr) => {
      localStorage.clear();
      localStorage.setItem("tauric_session_token", tok);
      localStorage.setItem("tauric_session_user", JSON.stringify(usr));
    }, CUST_TOKEN, CUST_USER);

    await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle2' });

    // Wait for signals and technical analysis button to render
    await page.waitForFunction(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      return btns.some(b => b.textContent && b.textContent.includes('Technical Analysis'));
    }, { timeout: 20000 });

    await new Promise(r => setTimeout(r, 1500));

    // Scroll to Signal Cards to highlight Directional Meter and single Technical Analysis button
    await page.evaluate(() => {
      const el = document.querySelector('[data-testid="market-tab-crypto"]') || document.querySelector('input[placeholder*="Search"]');
      if (el) el.scrollIntoView({ behavior: 'instant' });
    });
    await new Promise(r => setTimeout(r, 1000));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_customer_header_and_signals_1440.png'),
      fullPage: false
    });

    // ─────────────────────────────────────────────────────────────────────────
    // 2. FOUR-ENGINE DECISION BOARD WITH GATED ACTIONS
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [2/9] Clicking Technical Analysis to open FourEngineDecisionBoard...");
    const clicked = await page.evaluate(() => {
      const allButtons = Array.from(document.querySelectorAll('button'));
      const techBtn = allButtons.find(b => b.textContent && b.textContent.includes('Technical Analysis'));
      if (techBtn) {
        techBtn.click();
        return true;
      }
      return false;
    });
    console.log(`Technical Analysis button clicked: ${clicked}`);

    // Wait for the four-engine API call and countdown timer
    await new Promise(r => setTimeout(r, 6000));

    // Scroll down inside modal if needed to show trade setup and action button
    await page.evaluate(() => {
      const modals = document.querySelectorAll('.overflow-y-auto');
      if (modals.length > 0) {
        modals[modals.length - 1].scrollTop = modals[modals.length - 1].scrollHeight;
      }
    });
    await new Promise(r => setTimeout(r, 1000));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_four_engine_decision_board_1440.png'),
      fullPage: false
    });

    // Close Four-Engine modal using specific title
    await page.evaluate(() => {
      const closeBtn = document.querySelector('button[title="Close Board"]') || Array.from(document.querySelectorAll('button')).find(b => b.textContent && (b.textContent.includes('Close') || b.textContent.includes('Dismiss')));
      if (closeBtn) closeBtn.click();
    });
    await new Promise(r => setTimeout(r, 1500));

    // ─────────────────────────────────────────────────────────────────────────
    // 3. SCALPING GRID EXECUTION MODAL (ALL 10 RISK FIELDS)
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [3/9] Opening Scalping Grid Execution Modal...");
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent("bitdex_open_scalp_grid"));
    });
    await new Promise(r => setTimeout(r, 2000));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_scalping_grid_modal_1440.png'),
      fullPage: false
    });

    // Close Scalping Grid modal
    await page.evaluate(() => {
      const closeButtons = Array.from(document.querySelectorAll('button'));
      const closeBtn = closeButtons.find(b => b.textContent && (b.textContent.includes('Close') || b.textContent.includes('Dismiss') || b.textContent.includes('Done')));
      if (closeBtn) closeBtn.click();
    });
    await new Promise(r => setTimeout(r, 1000));

    // ─────────────────────────────────────────────────────────────────────────
    // 4. BALANCES DASHBOARD (ISOLATED - 0 EXCHANGES, $0.00 EQUITY, NO $100K PAPER)
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [4/9] Switching to Balances Tab...");
    await page.evaluate(() => {
      const tab = document.querySelector('[data-testid="tab-balances"]') || Array.from(document.querySelectorAll('button')).find(b => b.textContent && b.textContent.includes('Balances'));
      if (tab) tab.click();
    });
    await new Promise(r => setTimeout(r, 2500));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_customer_balances_cleaned_1440.png'),
      fullPage: false
    });

    // ─────────────────────────────────────────────────────────────────────────
    // 5. ADMIN PANEL - HEADER WITH TAURIC/JEV PILLS
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [5/9] Switching to Admin Panel...");
    const adminPage = await browser.newPage();
    adminPage.on('dialog', async d => await d.dismiss());
    await adminPage.setViewport({ width: 1440, height: 900 });
    await adminPage.goto(`${BASE_URL}/`, { waitUntil: 'domcontentloaded' });
    
    await adminPage.evaluate((tok, usr) => {
      localStorage.clear();
      localStorage.setItem("tauric_session_token", tok);
      localStorage.setItem("tauric_session_user", JSON.stringify(usr));
    }, ADMIN_TOKEN, ADMIN_USER);

    await adminPage.goto(`${BASE_URL}/`, { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 2500));

    await adminPage.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_admin_header_cleaned_1440.png'),
      fullPage: false
    });

    // ─────────────────────────────────────────────────────────────────────────
    // 6. ADMIN PANEL - SECTION B CUSTOMER EXCHANGE CONNECTIONS
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [6/9] Switching Admin to Provider Operations (Section B)...");
    await adminPage.evaluate(() => {
      const tabBtn = document.querySelector('[data-testid="tab-provider-operations"]');
      if (tabBtn) tabBtn.click();
    });
    await new Promise(r => setTimeout(r, 2000));

    await adminPage.evaluate(() => {
      const secB = document.getElementById('section-b-exchanges');
      if (secB) secB.scrollIntoView({ behavior: 'instant' });
    });
    await new Promise(r => setTimeout(r, 1500));

    await adminPage.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_admin_section_b_exchanges_1440.png'),
      fullPage: false
    });

    // ─────────────────────────────────────────────────────────────────────────
    // 7. TABLET RESPONSIVE (1024x768)
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [7/9] Capturing Tablet Customer Portal (1024x768)...");
    await page.setViewport({ width: 1024, height: 768 });
    await page.evaluate(() => {
      const tab = Array.from(document.querySelectorAll('button')).find(b => b.textContent && (b.textContent.includes('Signal Intelligence') || b.textContent.includes('Signals')));
      if (tab) tab.click();
    });
    await new Promise(r => setTimeout(r, 1500));
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_responsive_tablet_1024.png'),
      fullPage: false
    });

    // ─────────────────────────────────────────────────────────────────────────
    // 8. MOBILE RESPONSIVE (390x844) + FOUR-ENGINE BOARD
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [8/9] Capturing Mobile Customer Portal (390x844)...");
    const mobilePage = await browser.newPage();
    mobilePage.on('dialog', async d => await d.dismiss());
    await mobilePage.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
    await mobilePage.goto(`${BASE_URL}/`, { waitUntil: 'domcontentloaded' });
    
    await mobilePage.evaluate((tok, usr) => {
      localStorage.clear();
      localStorage.setItem("tauric_session_token", tok);
      localStorage.setItem("tauric_session_user", JSON.stringify(usr));
    }, CUST_TOKEN, CUST_USER);

    await mobilePage.goto(`${BASE_URL}/`, { waitUntil: 'networkidle2' });
    await page.waitForFunction(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      return btns.some(b => b.textContent && b.textContent.includes('Technical Analysis'));
    }, { timeout: 20000 });
    await new Promise(r => setTimeout(r, 1500));

    await mobilePage.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_responsive_mobile_390.png'),
      fullPage: false
    });

    // Trigger Technical Analysis on mobile to show responsive board
    console.log("📸 [8b/9] Opening FourEngine on Mobile (390x844)...");
    await mobilePage.evaluate(() => {
      const allButtons = Array.from(document.querySelectorAll('button'));
      const techBtn = allButtons.find(b => b.textContent && b.textContent.includes('Technical Analysis'));
      if (techBtn) techBtn.click();
    });
    await new Promise(r => setTimeout(r, 6000));
    await mobilePage.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_mobile_four_engine_board_390.png'),
      fullPage: false
    });

    // ─────────────────────────────────────────────────────────────────────────
    // 9. COMPACT MOBILE RESPONSIVE (320x568)
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [9/9] Capturing Compact Mobile Customer Portal (320x568)...");
    await mobilePage.setViewport({ width: 320, height: 568, isMobile: true, hasTouch: true });
    await new Promise(r => setTimeout(r, 1000));

    await mobilePage.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_responsive_compact_mobile_320.png'),
      fullPage: false
    });

    await mobilePage.close();
    await adminPage.close();
    await page.close();

    console.log("🎉 All visual evidence successfully captured!");
  } catch (err) {
    console.error("❌ Error during evidence capture:", err);
  } finally {
    await browser.close();
  }
}

run();
