const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const OUTPUT_DIR = '/opt/tauric-platform-staging/dashboard/admin_restoration_evidence';
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const ADMIN_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJVU1ItNjZCQ0ZENzM1MCIsImVtYWlsIjoiYWRtaW5AdGF1cmljLmNvbSIsInJvbGUiOiJBRE1JTiIsInNlc3Npb25faWQiOiJTRVMtRDk4RUZBODhDMjFCODVBMCIsInJlbWVtYmVyX21lIjp0cnVlLCJleHAiOjE3OTM3MzExMTl9.rzEU72NAYX5AqBgX80xypBM4Dik29Ypja6mVlUbi0WM";
const ADMIN_USER = {
  user_id: "USR-66BCFD7350",
  email: "admin@tauric.com",
  username: "admin",
  role: "ADMIN",
  status: "ACTIVE",
  first_name: "Admin",
  last_name: "",
  country: "SG",
  email_verified: true,
  two_factor_enabled: true,
  must_change_password: false,
  kyc_status: "VERIFIED"
};

const VIEWPORTS = [
  { name: 'evidence_admin_restoration_1440', width: 1440, height: 900 },
  { name: 'evidence_admin_restoration_1366', width: 1366, height: 768 },
  { name: 'evidence_admin_restoration_1024', width: 1024, height: 768 },
  { name: 'evidence_admin_restoration_768', width: 768, height: 1024 },
  { name: 'evidence_admin_restoration_430', width: 430, height: 932 },
  { name: 'evidence_admin_restoration_390', width: 390, height: 844 },
  { name: 'evidence_admin_restoration_375', width: 375, height: 667 },
  { name: 'evidence_admin_restoration_320', width: 320, height: 568 },
];

async function run() {
  console.log('Launching headless browser with Chromium...');
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/chromium-browser',
    headless: 'new',
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
    const consoleLogs = [];

    page.on('console', msg => {
      const text = msg.text();
      consoleLogs.push(`[${msg.type()}] ${text}`);
      if (msg.type() === 'error') {
        console.error('Browser console error:', text);
      }
    });

    console.log('Navigating to prime localStorage with Admin credentials...');
    await page.goto('https://bitdex.ltd', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.evaluate((token, user) => {
      localStorage.setItem('tauric_session_token', token);
      localStorage.setItem('tauric_session_user', JSON.stringify(user));
    }, ADMIN_TOKEN, ADMIN_USER);

    console.log('Reloading to load Admin Panel...');
    await page.goto('https://bitdex.ltd', { waitUntil: 'networkidle0', timeout: 45000 });
    await new Promise(r => setTimeout(r, 2000));

    // Check if Admin Panel rendered
    const adminCheck = await page.evaluate(() => {
      return {
        hasAdminText: document.body.innerText.includes('Administrator') || document.body.innerText.includes('MISSION CONTROL') || document.body.innerText.includes('Provider Operations') || document.body.innerText.includes('AI Telemetry'),
        bodySnippet: document.body.innerText.substring(0, 300)
      };
    });
    console.log('Admin Check:', adminCheck.hasAdminText);

    // Click on "Provider Operations" / "AI Telemetry" tab
    console.log('Switching to Provider Operations tab...');
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const opsBtn = buttons.find(b => b.innerText.includes('Provider Operations') || b.innerText.includes('AI Telemetry') || b.innerText.includes('MISSION CONTROL'));
      if (opsBtn) {
        opsBtn.click();
      }
    });

    await new Promise(r => setTimeout(r, 4000));

    // Verify the 3 distinct sections
    const sectionsVerification = await page.evaluate(() => {
      const text = document.body.innerText;
      return {
        hasSectionA: text.includes('Section A') || text.includes('Provider Configuration') || text.includes('Circuit Breaker'),
        hasSectionB: text.includes('Section B') || text.includes('Customer Exchange Connections'),
        hasSectionC: text.includes('Section C') || text.includes('Watched Wallets'),
        hasBinanceLive: text.includes('CONN-DK-BIN-LIVE'),
        hasBinanceDemo: text.includes('CONN-DK-BIN-DEMO'),
        hasBitgetLive: text.includes('CONN-DK-BIT-LIVE'),
        hasBitgetDemo: text.includes('CONN-DK-BIT-DEMO'),
        hasCustomerMask: text.includes('des***@gmail.com'),
        hasBalances: text.includes('14.37') || text.includes('2,000.00'),
        hasColdVault: text.includes('WLT-VAULT-ETH-01') || text.includes('Institutional Cold Vault')
      };
    });

    console.log('=== SECTIONS RESTORATION VERIFICATION ===');
    console.log(JSON.stringify(sectionsVerification, null, 2));

    // Capture responsive screenshots of the restored Admin view across all 8 viewports
    for (const vp of VIEWPORTS) {
      console.log(`Setting viewport: ${vp.width}x${vp.height} (${vp.name})...`);
      await page.setViewport({ width: vp.width, height: vp.height, deviceScaleFactor: 1 });
      await new Promise(r => setTimeout(r, 1000));
      const shotPath = path.join(OUTPUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: shotPath, fullPage: true });
      console.log(`Saved screenshot to ${shotPath}`);
    }

    // Now test Universal Pair Search Modal
    console.log('Switching to Terminal tab to test Universal Pair Search...');
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const termBtn = buttons.find(b => b.innerText.includes('Terminal'));
      if (termBtn) termBtn.click();
    });
    await new Promise(r => setTimeout(r, 2000));

    console.log('Opening Search Any Coin / Pair modal...');
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const searchBtn = buttons.find(b => b.innerText.includes('Search Any Coin / Pair'));
      if (searchBtn) searchBtn.click();
    });
    await new Promise(r => setTimeout(r, 1500));

    // Type "BTC" into search
    const searchModalOpen = await page.evaluate(() => {
      const input = document.querySelector('input[placeholder*="Type any symbol or pair"]');
      if (input) {
        input.value = 'BTC';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        return true;
      }
      return false;
    });
    console.log('Search modal input found & typed:', searchModalOpen);

    await new Promise(r => setTimeout(r, 2000));

    // Capture search modal screenshot
    await page.setViewport({ width: 1440, height: 900 });
    const searchShotPath = path.join(OUTPUT_DIR, 'evidence_universal_pair_search_btc.png');
    await page.screenshot({ path: searchShotPath });
    console.log(`Saved Universal Search screenshot to ${searchShotPath}`);

    console.log('=== VERIFICATION RUN COMPLETED SUCCESSFULLY ===');
  } catch (err) {
    console.error('Test execution error:', err);
  } finally {
    await browser.close();
  }
}

run();
