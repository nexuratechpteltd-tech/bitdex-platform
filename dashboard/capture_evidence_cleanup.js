const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const OUTPUT_DIR = '/opt/tauric-platform-staging/dashboard/evidence_cleanup_output';
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const CUST_TOKEN = process.env.BITDEX_TEST_TOKEN || "";
const CUST_USER = {
  user_id: process.env.BITDEX_TEST_USER_ID || "USR-TEST-CUST",
  email: process.env.BITDEX_TEST_EMAIL || "test_customer@bitdex.io",
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

const ADMIN_TOKEN = process.env.BITDEX_ADMIN_TOKEN || "";
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
  console.log("🚀 Starting Puppeteer Targeted Evidence Capture...");
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
      console.log('Dialog popped up:', dialog.message());
      await dialog.dismiss();
    });

    // ─────────────────────────────────────────────────────────────────────────
    // 1. CUSTOMER PORTAL - DESKTOP 1440x900 (HEADER & SIGNAL CARDS)
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [1/8] Capturing Customer Portal (1440x900)...");
    await page.setViewport({ width: 1440, height: 900 });
    await page.goto(`${BASE_URL}/`, { waitUntil: 'domcontentloaded' });
    
    // Inject Customer Session
    await page.evaluate((tok, usr) => {
      localStorage.clear();
      localStorage.setItem("tauric_session_token", tok);
      localStorage.setItem("tauric_session_user", JSON.stringify(usr));
    }, CUST_TOKEN, CUST_USER);

    await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 2500));

    // Scroll to Signal Cards to show NO green execute button
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
    // 2. FOUR-ENGINE DECISION BOARD WITH CREDIT-GATED EXECUTION
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [2/8] Clicking Technical Analysis to open FourEngineDecisionBoard...");
    const clicked = await page.evaluate(() => {
      const allButtons = Array.from(document.querySelectorAll('button'));
      const techBtn = allButtons.find(b => b.innerText && b.innerText.includes('Technical Analysis'));
      if (techBtn) {
        techBtn.click();
        return true;
      }
      return false;
    });
    console.log(`Technical Analysis button found and clicked: ${clicked}`);
    // Wait for the four-engine API call to finish and modal to render
    await new Promise(r => setTimeout(r, 6000));

    // Scroll down inside modal if needed to show trade setup and execution action
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

    // Close modal if open
    await page.evaluate(() => {
      const closeButtons = Array.from(document.querySelectorAll('button'));
      const closeBtn = closeButtons.find(b => b.innerText && (b.innerText.includes('Close') || b.innerText.includes('Dismiss')));
      if (closeBtn) closeBtn.click();
    });
    await new Promise(r => setTimeout(r, 1000));

    // ─────────────────────────────────────────────────────────────────────────
    // 3. BALANCES DASHBOARD (CLEANED - NO $100K PAPER SIMULATION BASE CARD)
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [3/8] Switching to Balances Tab...");
    await page.evaluate(() => {
      const tab = document.querySelector('[data-testid="tab-balances"]') || Array.from(document.querySelectorAll('button')).find(b => b.innerText && b.innerText.includes('Balances'));
      if (tab) tab.click();
    });
    await new Promise(r => setTimeout(r, 2000));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_customer_balances_cleaned_1440.png'),
      fullPage: false
    });

    // ─────────────────────────────────────────────────────────────────────────
    // 4. ADMIN PANEL - HEADER WITH TAURIC/JEV PILLS
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [4/8] Switching to Admin Panel...");
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
    // 5. ADMIN PANEL - SECTION B CUSTOMER EXCHANGE CONNECTIONS
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [5/8] Switching Admin to Provider Operations (Section B)...");
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
    // 6. TABLET RESPONSIVE (1024x768)
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [6/8] Capturing Tablet Customer Portal (1024x768)...");
    await page.setViewport({ width: 1024, height: 768 });
    await page.evaluate(() => {
      const tab = Array.from(document.querySelectorAll('button')).find(b => b.innerText && b.innerText.includes('Signal Intelligence') || b.innerText.includes('Signals'));
      if (tab) tab.click();
    });
    await new Promise(r => setTimeout(r, 1500));
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_responsive_tablet_1024.png'),
      fullPage: false
    });

    // ─────────────────────────────────────────────────────────────────────────
    // 7. MOBILE RESPONSIVE (390x844)
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [7/8] Capturing Mobile Customer Portal (390x844)...");
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
    await new Promise(r => setTimeout(r, 2500));

    await mobilePage.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_responsive_mobile_390.png'),
      fullPage: false
    });

    // Also trigger Technical Analysis on mobile to show responsive board
    console.log("📸 [7b/8] Opening FourEngine on Mobile (390x844)...");
    await mobilePage.evaluate(() => {
      const allButtons = Array.from(document.querySelectorAll('button'));
      const techBtn = allButtons.find(b => b.innerText && b.innerText.includes('Technical Analysis'));
      if (techBtn) techBtn.click();
    });
    await new Promise(r => setTimeout(r, 6000));
    await mobilePage.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_mobile_four_engine_board_390.png'),
      fullPage: false
    });

    // ─────────────────────────────────────────────────────────────────────────
    // 8. COMPACT MOBILE RESPONSIVE (320x568)
    // ─────────────────────────────────────────────────────────────────────────
    console.log("📸 [8/8] Capturing Compact Mobile Customer Portal (320x568)...");
    await mobilePage.setViewport({ width: 320, height: 568, isMobile: true, hasTouch: true });
    await new Promise(r => setTimeout(r, 1000));

    await mobilePage.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_responsive_compact_mobile_320.png'),
      fullPage: false
    });

    await mobilePage.close();
    await adminPage.close();
    await page.close();

    console.log("✅ All evidence captured successfully!");
  } catch (err) {
    console.error("❌ Error during evidence capture:", err);
  } finally {
    await browser.close();
  }
}

run();
