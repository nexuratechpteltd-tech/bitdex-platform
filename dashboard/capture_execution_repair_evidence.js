const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://127.0.0.1:33900';
const OUTPUT_DIR = '/opt/tauric-platform-staging/dashboard/execution_repair_evidence';
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

// Valid active token for test_customer@bitdex.io
const CUSTOMER_JWT = process.env.BITDEX_TEST_TOKEN || '';
const CUSTOMER_USER = {
  user_id: process.env.BITDEX_TEST_USER_ID || 'USR-TEST-CUST',
  email: process.env.BITDEX_TEST_EMAIL || 'test_customer@bitdex.io',
  username: 'Design Krao',
  role: 'ADMIN',
  status: 'ACTIVE',
  kyc_status: 'VERIFIED',
  two_factor_enabled: 0
};

async function run() {
  console.log('Launching browser for Execution Repair Visual Evidence Capture...');
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 950 });

    await page.evaluateOnNewDocument((token, user) => {
      localStorage.setItem('tauric_session_token', token);
      localStorage.setItem('tauric_session_user', JSON.stringify(user));
      localStorage.setItem('bitdex_token', token);
      localStorage.setItem('bitdex_auth_token', token);
    }, CUSTOMER_JWT, CUSTOMER_USER);

    // 1. Capture Trade Execution Terminal Drawer
    console.log('Navigating to #trading...');
    await page.goto(`${BASE_URL}/#trading`, { waitUntil: 'networkidle2' });
    await new Promise((r) => setTimeout(r, 3000));

    console.log('Triggering Execute Setup drawer...');
    await page.evaluate(() => {
      const allBtns = Array.from(document.querySelectorAll('button'));
      const execBtn = allBtns.find(b => b.textContent && b.textContent.includes('Execute Setup'));
      if (execBtn) execBtn.click();
    });
    await new Promise((r) => setTimeout(r, 1500));

    console.log('Selecting Binance Demo account in Target Execution Account select...');
    await page.evaluate(() => {
      const sel = document.querySelector('#execution-exchange-profile-select');
      if (sel) {
        const opt = Array.from(sel.options).find(o => 
          o.value === 'CONN-DK-BIN-DEMO-MIGRATED' || 
          (o.text.includes('BINANCE') && o.text.includes('DEMO'))
        );
        if (opt) {
          sel.value = opt.value;
          sel.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    });
    await new Promise((r) => setTimeout(r, 1200));

    // Check the confirmation checkbox
    console.log('Checking parameters confirmation checkbox...');
    await page.evaluate(() => {
      const cb = document.querySelector('input[type="checkbox"]');
      if (cb && !cb.checked) cb.click();
    });
    await new Promise((r) => setTimeout(r, 500));

    // Submit the demo order
    console.log('Submitting Demo Order through Drawer...');
    const submitClicked = await page.evaluate(() => {
      const allBtns = Array.from(document.querySelectorAll('button'));
      const submitBtn = allBtns.find(b => b.textContent && b.textContent.includes('SUBMIT DEMO'));
      if (submitBtn) {
        submitBtn.click();
        return true;
      }
      return false;
    });

    console.log('Order submit clicked:', submitClicked);
    // Wait for Binance API call and state update
    await new Promise((r) => setTimeout(r, 5000));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_binance_demo_execution_receipt.png'),
      fullPage: false
    });
    console.log('Captured evidence_binance_demo_execution_receipt.png');

    // Close the drawer modal so it doesn't block the screen
    console.log('Closing drawer modal...');
    await page.evaluate(() => {
      const allBtns = Array.from(document.querySelectorAll('button'));
      const closeBtn = allBtns.find(b => b.textContent && b.textContent.trim() === 'Close');
      if (closeBtn) closeBtn.click();
    });
    await new Promise((r) => setTimeout(r, 1000));

    // 2. Capture Open Positions Tab in 3-Tab Ledger
    console.log('Navigating to #positions...');
    await page.goto(`${BASE_URL}/#positions`, { waitUntil: 'networkidle2' });
    await new Promise((r) => setTimeout(r, 3000));

    // Ensure Demo environment is selected and Positions subtab
    await page.evaluate(() => {
      const demoBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent && b.textContent.includes('DEMO SANDBOX'));
      if (demoBtn) demoBtn.click();
      const posTab = document.querySelector('#ledger-tab-positions');
      if (posTab) posTab.click();
    });
    await new Promise((r) => setTimeout(r, 2000));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_ledger_open_positions_exchange_confirmed.png'),
      fullPage: false
    });
    console.log('Captured evidence_ledger_open_positions_exchange_confirmed.png');

    // 3. Capture Working Orders Tab
    console.log('Switching to Working Orders Tab...');
    await page.evaluate(() => {
      const ordTab = document.querySelector('#ledger-tab-orders');
      if (ordTab) ordTab.click();
    });
    await new Promise((r) => setTimeout(r, 2000));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_ledger_working_orders_binance_resting.png'),
      fullPage: false
    });
    console.log('Captured evidence_ledger_working_orders_binance_resting.png');

    // 4. Capture Closed Trade History Tab
    console.log('Switching to Closed Trade History Tab...');
    await page.evaluate(() => {
      const histTab = document.querySelector('#ledger-tab-history');
      if (histTab) histTab.click();
    });
    await new Promise((r) => setTimeout(r, 2000));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_ledger_trade_history_numeric_ids.png'),
      fullPage: false
    });
    console.log('Captured evidence_ledger_trade_history_numeric_ids.png');

    console.log('All visual evidence captured successfully!');
  } catch (err) {
    console.error('Error during evidence capture:', err);
  } finally {
    await browser.close();
  }
}

run();
