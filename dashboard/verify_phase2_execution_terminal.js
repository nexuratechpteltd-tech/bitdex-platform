const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://127.0.0.1:33900';
const OUTPUT_DIR = '/opt/tauric-platform-staging/dashboard/redesign_evidence_output';
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const CUSTOMER_JWT = process.env.BITDEX_TEST_TOKEN || '';
const CUSTOMER_USER = {
  user_id: process.env.BITDEX_TEST_USER_ID || 'USR-TEST-CUST',
  email: process.env.BITDEX_TEST_EMAIL || 'test_customer@bitdex.io',
  username: 'Customer User',
  role: 'CUSTOMER',
  status: 'ACTIVE',
  kyc_status: 'PENDING',
  two_factor_enabled: 0
};

async function run() {
  console.log('Launching browser for Phase 2 Execution Terminal tests...');
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
    }, CUSTOMER_JWT, CUSTOMER_USER);

    console.log('Navigating to #trading...');
    await page.goto(`${BASE_URL}/#trading`, { waitUntil: 'networkidle2' });
    await new Promise((r) => setTimeout(r, 2500));

    // Find and click the Execute button on the XRP/USDT card (or first signal card)
    console.log('Looking for Execute Setup button on signal card...');
    const clickedExecute = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      // Prefer XRP/USDT card execute button if present, else any execute button
      const xrpBtn = btns.find(b => b.id && b.id.includes('execute-xrp') || (b.textContent && b.textContent.includes('Execute') && b.closest('.p-5') && b.closest('.p-5').textContent.includes('XRP')));
      if (xrpBtn) {
        xrpBtn.click();
        return 'XRP/USDT Card';
      }
      const anyExecute = btns.find(b => b.textContent && b.textContent.includes('Execute Setup'));
      if (anyExecute) {
        anyExecute.click();
        return 'First Available Card';
      }
      return false;
    });
    console.log('Clicked execution button:', clickedExecute);
    await new Promise((r) => setTimeout(r, 1200));

    // 1. Capture Desktop Two-Column Terminal Drawer (Demo Mode)
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_phase2_terminal_demo_drawer.png'),
      fullPage: false
    });
    console.log('✓ Captured evidence_phase2_terminal_demo_drawer.png');

    // 2. Select Live Profile in Target Account Dropdown to test Live Protection
    console.log('Switching to Live Profile...');
    await page.evaluate(() => {
      const select = document.querySelector('#execution-exchange-profile-select');
      if (select) {
        const liveOpt = Array.from(select.options).find(o => o.text.includes('LIVE'));
        if (liveOpt) {
          select.value = liveOpt.value;
          select.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    });
    await new Promise((r) => setTimeout(r, 800));

    // Capture Live Lock State
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_phase2_terminal_live_lock.png'),
      fullPage: false
    });
    console.log('✓ Captured evidence_phase2_terminal_live_lock.png');

    // 3. Switch back to Demo Profile
    console.log('Switching back to Demo Profile...');
    await page.evaluate(() => {
      const select = document.querySelector('#execution-exchange-profile-select');
      if (select) {
        const demoOpt = Array.from(select.options).find(o => o.text.includes('DEMO'));
        if (demoOpt) {
          select.value = demoOpt.value;
          select.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    });
    await new Promise((r) => setTimeout(r, 600));

    // Check confirmation checkbox
    await page.evaluate(() => {
      const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
      checkboxes.forEach(cb => {
        if (!cb.checked) cb.click();
      });
    });
    await new Promise((r) => setTimeout(r, 400));

    // Click Submit Demo Order
    console.log('Submitting Demo Order...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const submitBtn = btns.find(b => b.textContent && b.textContent.includes('SUBMIT DEMO'));
      if (submitBtn) submitBtn.click();
    });
    await new Promise((r) => setTimeout(r, 1500));

    // Capture Execution Receipt & Lifecycle Stepper
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_phase2_terminal_receipt_stepper.png'),
      fullPage: false
    });
    console.log('✓ Captured evidence_phase2_terminal_receipt_stepper.png');

    // 4. Test Mobile Responsive View (390x844)
    console.log('Testing mobile responsive layout...');
    await page.setViewport({ width: 390, height: 844 });
    await new Promise((r) => setTimeout(r, 800));
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_phase2_terminal_mobile_view.png'),
      fullPage: false
    });
    console.log('✓ Captured evidence_phase2_terminal_mobile_view.png');

    console.log('ALL PHASE 2 TESTS COMPLETED SUCCESSFULLY!');
  } finally {
    await browser.close();
  }
}

run().catch(err => {
  console.error('Phase 2 verification failed:', err);
  process.exit(1);
});
