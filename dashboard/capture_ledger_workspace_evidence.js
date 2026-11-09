const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://127.0.0.1:33900';
const OUTPUT_DIR = '/opt/tauric-platform-staging/dashboard/ledger_workspace_evidence';
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const CUSTOMER_JWT = process.env.BITDEX_TEST_TOKEN || '';
const CUSTOMER_USER = {
  user_id: process.env.BITDEX_TEST_USER_ID || 'USR-TEST-CUST',
  email: process.env.BITDEX_TEST_EMAIL || 'test_customer@bitdex.io',
  username: 'billal95',
  role: 'ADMIN',
  status: 'ACTIVE',
  kyc_status: 'VERIFIED',
  two_factor_enabled: 0
};

async function run() {
  console.log('Launching Puppeteer for Ledger Workspace Evidence Capture...');
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

    // ─── 1. Desktop: Order History Tab with BCH/USDT Order 537182101 Expanded ───
    console.log('Navigating to #orders...');
    await page.goto(`${BASE_URL}/#orders`, { waitUntil: 'networkidle2' });
    await new Promise((r) => setTimeout(r, 3000));

    // Ensure Order History tab is active
    await page.evaluate(() => {
      const tab = document.querySelector('#tab-order-history');
      if (tab) tab.click();
    });
    await new Promise((r) => setTimeout(r, 1500));

    // Expand BCH/USDT Order if chevron exists
    await page.evaluate(() => {
      const allRows = Array.from(document.querySelectorAll('tr'));
      const bchRow = allRows.find(r => r.textContent && r.textContent.includes('537182101'));
      if (bchRow) {
        const expandBtn = bchRow.querySelector('button');
        if (expandBtn) expandBtn.click();
      }
    });
    await new Promise((r) => setTimeout(r, 1000));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_desktop_order_history_bch_expanded.png'),
      fullPage: false
    });
    console.log('Captured evidence_desktop_order_history_bch_expanded.png');

    // ─── 2. Desktop: Slide-Over Execution Audit Dossier for Order 537182101 ───
    console.log('Opening Execution Audit Dossier for Order 537182101...');
    await page.evaluate(() => {
      const allRows = Array.from(document.querySelectorAll('tr'));
      const bchRow = allRows.find(r => r.textContent && r.textContent.includes('537182101'));
      if (bchRow) bchRow.click();
    });
    await new Promise((r) => setTimeout(r, 2000));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_desktop_audit_dossier_drawer_bch.png'),
      fullPage: false
    });
    console.log('Captured evidence_desktop_audit_dossier_drawer_bch.png');

    // Close the dossier
    await page.evaluate(() => {
      const closeBtn = document.querySelector('button[title="Download Raw Audit JSON"]')?.nextElementSibling;
      if (closeBtn) closeBtn.click();
    });
    await new Promise((r) => setTimeout(r, 800));

    // ─── 3. Desktop: Trade History / Fills Tab (Granular Matching Engine Fills) ───
    console.log('Switching to Trade History / Fills tab...');
    await page.evaluate(() => {
      const tab = document.querySelector('#tab-trade-history');
      if (tab) tab.click();
    });
    await new Promise((r) => setTimeout(r, 2000));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_desktop_trade_history_fills.png'),
      fullPage: false
    });
    console.log('Captured evidence_desktop_trade_history_fills.png');

    // ─── 4. Desktop: Open Orders Tab (Helper Banner when 0 working orders) ───
    console.log('Switching to Open Orders tab...');
    await page.evaluate(() => {
      const tab = document.querySelector('#tab-open-orders');
      if (tab) tab.click();
    });
    await new Promise((r) => setTimeout(r, 1500));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_desktop_open_orders_empty_banner.png'),
      fullPage: false
    });
    console.log('Captured evidence_desktop_open_orders_empty_banner.png');

    // ─── 5. Desktop: Receipt Deep-Link Execution Test ───
    console.log('Navigating to #trading to test execution drawer deep-link...');
    await page.goto(`${BASE_URL}/#trading`, { waitUntil: 'networkidle2' });
    await new Promise((r) => setTimeout(r, 2500));

    // Open Drawer
    await page.evaluate(() => {
      const allBtns = Array.from(document.querySelectorAll('button'));
      const execBtn = allBtns.find(b => b.textContent && b.textContent.includes('Execute Setup'));
      if (execBtn) execBtn.click();
    });
    await new Promise((r) => setTimeout(r, 1200));

    // Select Binance Demo profile
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
    await new Promise((r) => setTimeout(r, 1000));

    // Check confirmation checkbox
    await page.evaluate(() => {
      const cb = document.querySelector('input[type="checkbox"]');
      if (cb && !cb.checked) cb.click();
    });
    await new Promise((r) => setTimeout(r, 500));

    // Submit Demo Order
    await page.evaluate(() => {
      const allBtns = Array.from(document.querySelectorAll('button'));
      const submitBtn = allBtns.find(b => b.textContent && b.textContent.includes('SUBMIT DEMO'));
      if (submitBtn) submitBtn.click();
    });
    await new Promise((r) => setTimeout(r, 4500));

    // Capture receipt drawer showing [View Order & Trade Ledger →] button
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_execution_receipt_deep_link_button.png'),
      fullPage: false
    });
    console.log('Captured evidence_execution_receipt_deep_link_button.png');

    // Click [View Order & Trade Ledger →]
    await page.evaluate(() => {
      const allBtns = Array.from(document.querySelectorAll('button'));
      const deepLinkBtn = allBtns.find(b => b.textContent && b.textContent.includes('View Order & Trade Ledger'));
      if (deepLinkBtn) deepLinkBtn.click();
    });
    await new Promise((r) => setTimeout(r, 3000));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_deep_link_landed_on_ledger.png'),
      fullPage: false
    });
    console.log('Captured evidence_deep_link_landed_on_ledger.png');

    // ─── 6. Mobile Screen Test (< 768px: 390x844) ───
    console.log('Switching to mobile viewport (390x844)...');
    await page.setViewport({ width: 390, height: 844, isMobile: true });
    await page.goto(`${BASE_URL}/#orders`, { waitUntil: 'networkidle2' });
    await new Promise((r) => setTimeout(r, 3000));

    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_mobile_ledger_view.png'),
      fullPage: false
    });
    console.log('Captured evidence_mobile_ledger_view.png');

    console.log('All visual evidence captured successfully!');
  } catch (err) {
    console.error('Error during evidence capture:', err);
  } finally {
    await browser.close();
  }
}

run();
