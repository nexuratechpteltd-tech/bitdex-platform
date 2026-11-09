const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const OUTPUT_DIR = '/opt/tauric-platform-staging/dashboard/admin_restoration_evidence';
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const ADMIN_TOKEN = process.env.BITDEX_ADMIN_TOKEN || "";
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
  console.log('Starting Puppeteer headless browser...');
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
    page.setDefaultNavigationTimeout(45000);

    // Seed localStorage
    console.log('Visiting landing page to set admin token in localStorage...');
    await page.goto('https://bitdex.ltd', { waitUntil: 'domcontentloaded' });
    await page.evaluate((token, user) => {
      localStorage.setItem('tauric_session_token', token);
      localStorage.setItem('tauric_session_user', JSON.stringify(user));
    }, ADMIN_TOKEN, ADMIN_USER);

    // Navigate to admin console
    console.log('Navigating to load Admin Console...');
    await page.goto('https://bitdex.ltd', { waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 2000));

    // Verify Admin is loaded
    const title = await page.evaluate(() => document.body.innerText.substring(0, 200));
    console.log('Page header preview:', title.replace(/\n+/g, ' '));

    // Click specifically on "AI & Data Provider Operations" tab
    console.log('Clicking on tab: "AI & Data Provider Operations"...');
    const tabClicked = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const btn = buttons.find(b => b.innerText.includes('AI & Data Provider Operations'));
      if (btn) {
        btn.click();
        return true;
      }
      return false;
    });
    console.log('AI & Data Provider Operations tab clicked:', tabClicked);

    // Wait for provider operations data to load
    await new Promise(r => setTimeout(r, 4000));

    // Check verification of the 3 sections
    const verification = await page.evaluate(() => {
      const text = document.body.innerText;
      return {
        hasSectionA: text.includes('Section A') || text.includes('Circuit Breakers & Provider Configuration'),
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
    console.log('=== ADMIN RESTORATION SECTIONS VERIFIED ===');
    console.log(JSON.stringify(verification, null, 2));

    // Capture screenshots across all 8 required viewports
    for (const vp of VIEWPORTS) {
      console.log(`Capturing viewport: ${vp.width}x${vp.height} (${vp.name})...`);
      await page.setViewport({ width: vp.width, height: vp.height, deviceScaleFactor: 1 });
      await new Promise(r => setTimeout(r, 800));
      const shotPath = path.join(OUTPUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: shotPath, fullPage: true });
    }

    // Now switch to Signals Terminal to test Universal Pair Search
    console.log('Switching to Signals Terminal tab...');
    await page.setViewport({ width: 1440, height: 900 });
    const termClicked = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const btn = buttons.find(b => b.innerText.includes('Signals Terminal'));
      if (btn) {
        btn.click();
        return true;
      }
      return false;
    });
    console.log('Signals Terminal tab clicked:', termClicked);
    await new Promise(r => setTimeout(r, 3000));

    console.log('Clicking "Search Any Coin / Pair" button...');
    const searchModalOpened = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const btn = buttons.find(b => b.innerText.includes('Search Any Coin / Pair'));
      if (btn) {
        btn.click();
        return true;
      }
      return false;
    });
    console.log('Search modal button clicked:', searchModalOpened);
    await new Promise(r => setTimeout(r, 1000));

    // Type "BTC" into search box
    console.log('Typing "BTC" into universal market search...');
    await page.evaluate(() => {
      const input = document.querySelector('input[placeholder*="Type any symbol or pair"]');
      if (input) {
        input.value = 'BTC';
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
    });

    // Wait for debounced search results (Binance USDT + BTC pairs)
    await new Promise(r => setTimeout(r, 2000));

    const searchResultsCheck = await page.evaluate(() => {
      const text = document.body.innerText;
      return {
        hasBtcUsdt: text.includes('BTC/USDT') || text.includes('BTCUSDT'),
        hasBinance: text.includes('Binance') || text.includes('BINANCE'),
        snippet: text.substring(text.indexOf('Universal Pair Search'), text.indexOf('Universal Pair Search') + 500)
      };
    });
    console.log('Search results check:', JSON.stringify(searchResultsCheck, null, 2));

    const searchShotPath = path.join(OUTPUT_DIR, 'evidence_universal_pair_search_btc.png');
    await page.screenshot({ path: searchShotPath });
    console.log(`Saved Universal Search screenshot to ${searchShotPath}`);

    console.log('All verification captures completed successfully!');
  } catch (err) {
    console.error('Error in verification run:', err);
  } finally {
    await browser.close();
  }
}

run();
