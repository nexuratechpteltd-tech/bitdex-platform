const puppeteer = require('puppeteer');
const fs = require('fs');

async function capture() {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 950 });

  const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJVU1ItQURNLUIwMjJGNDkwIiwiZW1haWwiOiJoZWxsb0BuZXh1cmEubHRkIiwicm9sZSI6IkFETUlOIiwic2Vzc2lvbl9pZCI6IlNFUy04RTQ3RDE1MjhFMTM2RUI3IiwiZXhwIjoxNzk0ODMzMDcxfQ.ujHWcD5QOTpd0MRy4qj2_AQKO6pfwZUAwZ1_n0U8UW0';

  const userObj = {
    user_id: 'USR-ADM-B022F490',
    email: 'hello@nexura.ltd',
    username: 'Platform Owner',
    role: 'ADMIN',
    status: 'ACTIVE',
    first_name: 'Platform',
    last_name: 'Owner'
  };

  // 1. Initial navigation & session establishment
  await page.goto('http://127.0.0.1:33900/#hft', { waitUntil: 'domcontentloaded' });
  await page.evaluate((tok, u) => {
    localStorage.setItem('tauric_session_token', tok);
    localStorage.setItem('tauric_session_user', JSON.stringify(u));
    localStorage.setItem('tauric_token', tok);
    localStorage.setItem('token', tok);
    localStorage.setItem('tauric_user', JSON.stringify(u));
    localStorage.setItem('bitdex_auth_token', tok);
    localStorage.setItem('bitdex_selected_hft_account', 'EXN-CONN-02926D69E193');
    localStorage.setItem('bitdex_selected_account_id', 'EXN-CONN-02926D69E193');
    localStorage.setItem('bitdex_hft_account_USR-ADM-B022F490', 'EXN-CONN-02926D69E193');
  }, token, userObj);

  // 2. Load page directly at #hft
  await page.goto('http://127.0.0.1:33900/#hft', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 3500));

  // Verify page content
  const heading = await page.evaluate(() => {
    const h1 = document.querySelector('h1, h2');
    return h1 ? h1.textContent : document.body.innerText.slice(0, 100);
  });
  console.log('Heading on #hft:', heading);

  // Screenshot 1: Main Scalping View showing Gold #1 card & Emergency controls
  await page.screenshot({ path: '/tmp/customer_trading_scalping_main.png', fullPage: false });
  console.log('Saved /tmp/customer_trading_scalping_main.png');

  // 3. Open 7-Step Guided Strategy Execution Modal
  const modalOpened = await page.evaluate(() => {
    const btn = document.getElementById('btn-execute-trading-strategy');
    if (btn) {
      btn.click();
      return true;
    }
    return false;
  });
  console.log('Opened Guided Execution Modal:', modalOpened);

  // Wait 4s for live market data & technical indicators calculation
  await new Promise(r => setTimeout(r, 4000));

  // Screenshot 2: 7-Step Guided Workflow Modal with live technical indicators & execution proposal
  await page.screenshot({ path: '/tmp/customer_strategy_pre_execution_modal.png', fullPage: false });
  console.log('Saved /tmp/customer_strategy_pre_execution_modal.png');

  // 4. Test Preflight Dry-Run validation
  await page.evaluate(() => {
    const cb = document.querySelector('input[type="checkbox"]');
    if (cb && !cb.checked) {
      cb.click();
    }
    const confirmBtn = document.getElementById('btn-confirm-execute-strategy');
    if (confirmBtn) {
      confirmBtn.click();
    }
  });

  // Wait 3.5s for dry-run verification
  await new Promise(r => setTimeout(r, 3500));

  // Screenshot 3: Preflight Dry-Run Fill Reconciled
  await page.screenshot({ path: '/tmp/customer_strategy_dry_run_reconciled.png', fullPage: false });
  console.log('Saved /tmp/customer_strategy_dry_run_reconciled.png');

  // Close modal
  await page.evaluate(() => {
    const allBtns = Array.from(document.querySelectorAll('button'));
    const closeBtn = allBtns.find(b => b.textContent && (b.textContent.includes('Done & Return') || b.textContent.includes('Cancel') || b.textContent.includes('View Position in Dashboard')));
    if (closeBtn) closeBtn.click();
  });

  await new Promise(r => setTimeout(r, 1500));

  // 5. Scroll to Closed Trades Table
  await page.evaluate(() => {
    const sec = document.getElementById('trading-performance-section');
    if (sec) {
      sec.scrollIntoView({ behavior: 'instant', block: 'start' });
    } else {
      const table = document.querySelector('table');
      if (table) table.scrollIntoView({ behavior: 'instant', block: 'center' });
    }
  });
  await new Promise(r => setTimeout(r, 1000));

  // Screenshot 4: Closed Trades History Table with position 72158366 BUY +$2.74
  await page.screenshot({ path: '/tmp/customer_closed_trades_history.png', fullPage: false });
  console.log('Saved /tmp/customer_closed_trades_history.png');

  // 6. Navigate to Customer Connections View (#connections)
  await page.goto('http://127.0.0.1:33900/#connections', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 2500));

  // Screenshot 5: Customer Exchange Connections View
  await page.screenshot({ path: '/tmp/customer_exchange_connections_view.png', fullPage: false });
  console.log('Saved /tmp/customer_exchange_connections_view.png');

  await browser.close();
  console.log('ALL_CUSTOMER_SCREENSHOTS_SUCCESSFULLY_CAPTURED');
}

capture().catch(err => {
  console.error('ERROR during capture:', err);
  process.exit(1);
});
