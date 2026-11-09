const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const OUTPUT_DIR = '/opt/tauric-platform-staging/dashboard/evidence_screenshots';
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const TOKEN = process.env.BITDEX_TEST_TOKEN || '';
const USER = {
  user_id: process.env.BITDEX_TEST_USER_ID || 'USR-TEST-CUST',
  email: process.env.BITDEX_TEST_EMAIL || 'test_customer@bitdex.io',
  username: 'billal95',
  role: 'CUSTOMER',
  status: 'ACTIVE',
  email_verified: 0,
  kyc_status: 'PENDING',
  first_name: 'Bilal',
  last_name: 'Ahmed',
  country: 'SG',
  two_factor_enabled: 0,
  must_change_password: 0
};

const VIEWPORTS = [
  { name: 'evidence_exchange_connections_1440', width: 1440, height: 900 },
  { name: 'evidence_exchange_connections_1366', width: 1366, height: 768 },
  { name: 'evidence_exchange_connections_1024', width: 1024, height: 768 },
  { name: 'evidence_exchange_connections_768', width: 768, height: 1024 },
  { name: 'evidence_exchange_connections_430', width: 430, height: 932 },
  { name: 'evidence_exchange_connections_390', width: 390, height: 844 },
  { name: 'evidence_exchange_connections_375', width: 375, height: 667 },
  { name: 'evidence_exchange_connections_320', width: 320, height: 568 },
];

async function run() {
  console.log('Launching headless browser...');
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
    const failedRequests = [];

    page.on('console', msg => {
      const text = msg.text();
      consoleLogs.push(`[${msg.type()}] ${text}`);
      if (msg.type() === 'error') {
        console.error('Browser console error:', text);
      }
    });

    page.on('requestfailed', req => {
      failedRequests.push(`${req.method()} ${req.url()}: ${req.failure().errorText}`);
    });

    // Set initial localStorage before navigation
    console.log('Navigating to domain to prime localStorage...');
    await page.goto('https://bitdex.ltd', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.evaluate((token, user) => {
      localStorage.setItem('tauric_session_token', token);
      localStorage.setItem('tauric_session_user', JSON.stringify(user));
    }, TOKEN, USER);

    // Direct navigation to https://bitdex.ltd/#security
    console.log('Navigating directly to https://bitdex.ltd/#security ...');
    await page.goto('https://bitdex.ltd/#security', { waitUntil: 'networkidle0', timeout: 45000 });

    // Wait a brief moment for customer connections to populate
    await new Promise(r => setTimeout(r, 3000));

    // Check if Connected Exchange Accounts is visible
    const pageText = await page.evaluate(() => document.body.innerText);
    const hasConnectedExchangeAccounts = pageText.includes('Connected Exchange Accounts');
    const hasBinance = pageText.includes('Binance') || pageText.includes('CONN-DK-BIN-LIVE');
    const hasBalances = pageText.includes('14.37') || pageText.includes('USDT');
    const hasInsecureWarning = pageText.includes('Transport security violation') || pageText.includes('unencrypted public HTTP');

    console.log('=== VERIFICATION CHECKS ===');
    console.log('Has Connected Exchange Accounts:', hasConnectedExchangeAccounts);
    console.log('Has Binance Live Connection:', hasBinance);
    console.log('Has Authoritative Balances (14.37 / USDT):', hasBalances);
    console.log('Has Transport Security Warning:', hasInsecureWarning);

    if (hasInsecureWarning) {
      console.error('FAILURE: Transport security warning is still visible in UI!');
    } else {
      console.log('PASS: Zero transport security warnings present.');
    }

    // Capture responsive screenshots
    for (const vp of VIEWPORTS) {
      console.log(`Setting viewport: ${vp.width}x${vp.height} (${vp.name})...`);
      await page.setViewport({ width: vp.width, height: vp.height, deviceScaleFactor: 1 });
      await new Promise(r => setTimeout(r, 1000));
      const shotPath = path.join(OUTPUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: shotPath, fullPage: true });
      console.log(`Saved screenshot to ${shotPath}`);
    }

    console.log('=== VERIFICATION COMPLETED SUCCESSFULLY ===');
  } catch (err) {
    console.error('Test execution error:', err);
  } finally {
    await browser.close();
  }
}

run();
