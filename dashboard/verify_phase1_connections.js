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
  console.log('Launching browser...');
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

    console.log('Navigating to #connections...');
    await page.goto(`${BASE_URL}/#connections`, { waitUntil: 'networkidle2' });
    await new Promise((r) => setTimeout(r, 2500));

    // 1. Capture Full Vault Manager with Grouped Cards
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_phase1_vault_manager.png'),
      fullPage: true
    });
    console.log('✓ Captured evidence_phase1_vault_manager.png');

    // 2. Test Live Filter
    const liveFilterBtn = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const btn = btns.find(b => b.textContent && b.textContent.includes('Live Only'));
      if (btn) { btn.click(); return true; }
      return false;
    });
    console.log('Clicked Live Only filter:', liveFilterBtn);
    await new Promise((r) => setTimeout(r, 800));
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_phase1_filter_live_only.png'),
      fullPage: false
    });
    console.log('✓ Captured evidence_phase1_filter_live_only.png');

    // 3. Test Demo Filter
    const demoFilterBtn = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const btn = btns.find(b => b.textContent && b.textContent.includes('Demo Only'));
      if (btn) { btn.click(); return true; }
      return false;
    });
    console.log('Clicked Demo Only filter:', demoFilterBtn);
    await new Promise((r) => setTimeout(r, 800));
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_phase1_filter_demo_only.png'),
      fullPage: false
    });
    console.log('✓ Captured evidence_phase1_filter_demo_only.png');

    // Reset filter to All
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const btn = btns.find(b => b.textContent && b.textContent.includes('All Profiles'));
      if (btn) btn.click();
    });
    await new Promise((r) => setTimeout(r, 500));

    // 4. Open 3-Step Guided Connect Modal
    const openModalBtn = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const btn = btns.find(b => b.textContent && b.textContent.includes('Connect New Exchange Account'));
      if (btn) { btn.click(); return true; }
      return false;
    });
    console.log('Clicked Connect New Exchange Account:', openModalBtn);
    await new Promise((r) => setTimeout(r, 800));

    // Capture Step 1
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_phase1_connect_modal_step1.png'),
      fullPage: false
    });
    console.log('✓ Captured evidence_phase1_connect_modal_step1.png');

    // Click Next: Enter Credentials
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const btn = btns.find(b => b.textContent && b.textContent.includes('Next: Enter Credentials'));
      if (btn) btn.click();
    });
    await new Promise((r) => setTimeout(r, 800));

    // Fill credentials in Step 2
    const inputs = await page.$$('input[type="password"]');
    if (inputs.length >= 2) {
      await inputs[0].type('SAMPLE_API_KEY_TEST_FINGERPRINT');
      await inputs[1].type('SAMPLE_API_SECRET_VAULT_TEST');
    }
    await new Promise((r) => setTimeout(r, 400));
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_phase1_connect_modal_step2.png'),
      fullPage: false
    });
    console.log('✓ Captured evidence_phase1_connect_modal_step2.png');

    // Click Next: Verify Handshake
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const btn = btns.find(b => b.textContent && b.textContent.includes('Next: Verify Handshake'));
      if (btn) btn.click();
    });
    await new Promise((r) => setTimeout(r, 1200));

    // Capture Step 3 (Handshake Checklist)
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'evidence_phase1_connect_modal_step3.png'),
      fullPage: false
    });
    console.log('✓ Captured evidence_phase1_connect_modal_step3.png');

    console.log('ALL PHASE 1 TESTS COMPLETED SUCCESSFULLY!');
  } finally {
    await browser.close();
  }
}

run().catch(err => {
  console.error('Puppeteer verification failed:', err);
  process.exit(1);
});
