const puppeteer = require('puppeteer');
const fs = require('fs');
const { execSync } = require('child_process');

let TOKEN = process.env.BITDEX_TEST_TOKEN || '';
if (!TOKEN) {
  try {
    TOKEN = execSync('/opt/tauric-platform-staging/backend/.venv/bin/python3 /opt/tauric-platform-staging/backend/scripts/create_ephemeral_test_token.py USR-904424B4FB', { encoding: 'utf-8' }).trim();
  } catch (e) {}
}

const TEST_USER = process.env.BITDEX_TEST_USER ? JSON.parse(process.env.BITDEX_TEST_USER) : {
  user_id: process.env.BITDEX_TEST_USER_ID || 'USR-904424B4FB',
  email: process.env.BITDEX_TEST_EMAIL || 'test_trader@bitdex.io',
  username: 'Test Trader',
  role: 'CUSTOMER',
  status: 'ACTIVE',
  first_name: 'Test',
  last_name: 'Trader',
  country: 'PK',
  email_verified: true,
  two_factor_enabled: true,
  must_change_password: false,
  kyc_status: 'VERIFIED'
};

async function capture() {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 950 });

  const TEST_USER = process.env.BITDEX_TEST_USER ? JSON.parse(process.env.BITDEX_TEST_USER) : {
    user_id: process.env.BITDEX_TEST_USER_ID || "USR-TEST-CUST",
    email: process.env.BITDEX_TEST_EMAIL || "test_trader@bitdex.io",
    username: "Test Trader",
    role: "CUSTOMER",
    status: "ACTIVE",
    first_name: "Test",
    last_name: "Trader",
    country: "PK",
    email_verified: true,
    two_factor_enabled: true,
    must_change_password: false,
    kyc_status: "VERIFIED"
  };

  // 1. Navigate to domain and populate localStorage with Ali's customer session
  await page.goto('http://127.0.0.1:33900/#hft', { waitUntil: 'domcontentloaded' });
  await page.evaluate((tok, usr) => {
    localStorage.clear();
    localStorage.setItem("tauric_session_token", tok);
    localStorage.setItem("tauric_session_user", JSON.stringify(usr));
    localStorage.setItem("tauric_auth_token", tok);
    localStorage.setItem("bitdex_auth_token", tok);
  }, TOKEN, TEST_USER);

  // 2. Reload directly into #hft
  await page.goto('http://127.0.0.1:33900/#hft', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 3000));

  // 3. Capture main view of Ali Ajmal in Automated Scalping
  await page.screenshot({ path: '/tmp/ali_broker_scalping_main.png' });

  // 4. Open Demo Account dropdown
  await page.evaluate(() => {
    const card = document.querySelector('#card-select-demo-account') || document.querySelector('[id*="demo-account"]');
    if (card) card.click();
  });
  await new Promise(r => setTimeout(r, 1200));
  await page.screenshot({ path: '/tmp/ali_broker_account_selector_dropdown.png' });

  await browser.close();
  console.log("SCREENSHOTS_CAPTURED_SUCCESS");
}

capture().catch(err => {
  console.error("ERROR", err);
  process.exit(1);
});
