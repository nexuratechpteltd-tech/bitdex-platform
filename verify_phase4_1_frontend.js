const puppeteer = require('/opt/tauric-platform-staging/dashboard/node_modules/puppeteer');
const fs = require('fs');

const SCREENSHOT_DIR = '/opt/tauric-platform-staging/phase4_1_screenshots';
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function verify() {
  console.log('================================================================================');
  console.log('BITDEX PHASE 4.1 FRONTEND & RESPONSIVE VERIFICATION');
  console.log('================================================================================');

  // 1. Generate valid session token for test customer via local backend python
  const { execSync } = require('child_process');
  const tokenScript = [
    'import sys, uuid, time, jwt',
    "sys.path.append('/opt/tauric-platform-staging/backend')",
    'from app.services.saas_db import get_db_connection',
    'from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM',
    "user_id = 'USR-P41-TEST-VERIFY'",
    "email = 'verify_customer@bitdex.ltd'",
    'conn = get_db_connection()',
    "conn.execute('INSERT OR IGNORE INTO users (user_id, email, password_hash, role, status, email_verified, kyc_status, created_at, updated_at) VALUES (?, ?, \"hash\", \"CUSTOMER\", \"ACTIVE\", 1, \"VERIFIED\", datetime(\"now\"), datetime(\"now\"))', (user_id, email))",
    "session_id = 'SES-P41-VERIFY-01'",
    "token_hash = f'th_{uuid.uuid4().hex}'",
    "conn.execute('INSERT OR REPLACE INTO sessions (session_id, user_id, token_hash, expires_at, revoked, created_at) VALUES (?, ?, ?, ?, 0, datetime(\"now\"))', (session_id, user_id, token_hash, time.time() + 86400))",
    'conn.commit()',
    'conn.close()',
    "print(jwt.encode({'sub': user_id, 'session_id': session_id, 'exp': time.time() + 86400}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM))"
  ].join('\n');

  const token = execSync(`/opt/tauric-platform-staging/backend/.venv/bin/python3 -c "${tokenScript.replace(/"/g, '\\"')}"`).toString().trim();
  console.log('Generated verified customer session token.');

  // Pre-seed a customer demo connection for UI presentation
  const seedConnScript = [
    'import sys, httpx, asyncio',
    "sys.path.append('/opt/tauric-platform-staging/backend')",
    'async def seed():',
    '    async with httpx.AsyncClient() as client:',
    `        r = await client.post('http://127.0.0.1:8002/api/v1/hft/exness/demo/connect', headers={'Authorization': 'Bearer ${token}'}, json={`,
    "            'account_login': '77889900',",
    "            'password': 'Password123!',",
    "            'server_name': 'Exness-MT5Trial',",
    "            'use_mock': True,",
    "            'account_label': 'Verified Customer Primary Demo'",
    '        })',
    "        print('Seed demo connection response:', r.status_code)",
    'asyncio.run(seed())'
  ].join('\n');

  execSync(`/opt/tauric-platform-staging/backend/.venv/bin/python3 -c "${seedConnScript.replace(/"/g, '\\"')}"`);

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  const user = JSON.stringify({ user_id: 'USR-P41-TEST-VERIFY', email: 'verify_customer@bitdex.ltd', role: 'CUSTOMER', status: 'ACTIVE' });

  await page.evaluateOnNewDocument((t, u) => {
    localStorage.setItem('tauric_session_token', t);
    localStorage.setItem('tauric_session_user', u);
    localStorage.setItem('bitdex_auth_token', t);
    localStorage.setItem('tauric_token', t);
  }, token, user);

  async function clickNav(labelSubstring) {
    return await page.evaluate((label) => {
      const aside = document.querySelector('aside');
      if (!aside) return false;
      const btns = Array.from(aside.querySelectorAll('button'));
      const target = btns.find((b) => b.innerText.toLowerCase().includes(label.toLowerCase()));
      if (target) {
        target.click();
        return true;
      }
      return false;
    }, labelSubstring);
  }

  // 1. VERIFY CONNECTIONS PAGE (#connections)
  console.log('Testing #connections...');
  await page.goto('https://bitdex.ltd/#connections', { waitUntil: 'networkidle2', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 2000));

  await page.screenshot({ path: `${SCREENSHOT_DIR}/p41_connections_1440.png`, fullPage: false });
  console.log('Saved p41_connections_1440.png');

  const connDom = await page.evaluate(() => {
    const text = document.body.innerText;
    return {
      hasTraderApiCard: text.includes('EXNESS TRADER API'),
      hasDemoCard: text.includes('EXNESS MT5 DEMO'),
      hasRealCard: text.includes('EXNESS MT5 REAL'),
      hasOnboardingSteps: text.includes('Step A: Trader API') || text.includes('Step B: MT5 Demo'),
      hasConnectedDemo: text.includes('77****00') || text.includes('CONNECTED'),
      hasDisconnectBtn: text.includes('Disconnect'),
      hasPreferredBadge: text.includes('Preferred') || text.includes('PREFERRED') || text.includes('ACTIVE')
    };
  });
  console.log('Connections DOM checks:', connDom);

  // 2. VERIFY FUNDING & TRANSFERS PAGE (#funding)
  console.log('Testing #funding...');
  await clickNav('Funding & Transfers');
  await new Promise((r) => setTimeout(r, 2000));
  await page.screenshot({ path: `${SCREENSHOT_DIR}/p41_funding_1440.png`, fullPage: false });
  console.log('Saved p41_funding_1440.png');

  const fundingDom = await page.evaluate(() => {
    const text = document.body.innerText;
    return {
      hasFundingTitle: text.includes('Funding & Transfers'),
      hasStatusBadge: text.includes('STATUS:') || text.includes('CONNECTED') || text.includes('NOT_CONNECTED'),
      hasInternalTransfers: text.includes('Internal Transfers') || text.includes('SECTION A'),
      hasDepositTopUp: text.includes('Deposit') || text.includes('Top Up') || text.includes('SECTION B') || text.includes('TOP UP EXNESS'),
      hasCryptoInvestigation: text.includes('Binance Pay') || text.includes('USDT') || text.includes('Blockchain Network Fees'),
      hasZeroBrokerFeeNotice: text.includes('0.00%') || text.includes('0%')
    };
  });
  console.log('Funding DOM checks:', fundingDom);

  // Click Top Up Exness button to verify modal
  const clickedTopUp = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const topUp = btns.find(b => b.innerText.includes('TOP UP EXNESS') || b.innerText.includes('TOP UP'));
    if (topUp) {
      topUp.click();
      return true;
    }
    return false;
  });
  if (clickedTopUp) {
    await new Promise((r) => setTimeout(r, 800));
    await page.screenshot({ path: `${SCREENSHOT_DIR}/p41_deposit_modal_1440.png` });
    console.log('Saved p41_deposit_modal_1440.png');
    // Close modal
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const cancel = btns.find(b => b.innerText.includes('Cancel') || b.innerText.includes('Close') || b.innerText.includes('Nevermind'));
      if (cancel) cancel.click();
    });
    await new Promise((r) => setTimeout(r, 500));
  }

  // 3. VERIFY TRADING TERMINAL MODAL (#terminal)
  console.log('Testing #terminal trade execution modal...');
  await clickNav('Trading Dashboard');
  await new Promise((r) => setTimeout(r, 2000));

  const executeBtn = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const target = btns.find(b => b.innerText.includes('EXECUTE TRADE'));
    if (target) {
      target.click();
      return true;
    }
    return false;
  });
  console.log('Clicked EXECUTE TRADE:', executeBtn);
  await new Promise((r) => setTimeout(r, 1000));

  await page.screenshot({ path: `${SCREENSHOT_DIR}/p41_terminal_modal_demo_1440.png` });
  console.log('Saved p41_terminal_modal_demo_1440.png');

  // Inspect modal content
  const modalDemoInspection = await page.evaluate(() => {
    const text = document.body.innerText;
    return {
      hasAccountSelector: text.includes('Select Account') || text.includes('77****00') || text.includes('Demo'),
      hasDemoEnvSelected: text.includes('DEMO ACCOUNT')
    };
  });
  console.log('Modal Demo Inspection:', modalDemoInspection);

  // Switch to REAL ACCOUNT tab
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const realTab = btns.find(b => b.innerText.includes('REAL ACCOUNT'));
    if (realTab) realTab.click();
  });
  await new Promise((r) => setTimeout(r, 800));

  await page.screenshot({ path: `${SCREENSHOT_DIR}/p41_terminal_modal_real_1440.png` });
  console.log('Saved p41_terminal_modal_real_1440.png');

  const modalRealInspection = await page.evaluate(() => {
    const text = document.body.innerText;
    return {
      hasConsentNotice: text.includes('consent') || text.includes('capital at risk') || text.includes('Real execution'),
      hasSafetyLockWarning: text.includes('LOCKED') || text.includes('live_trading_locked') || text.includes('Safety Lock')
    };
  });
  console.log('Modal Real Inspection:', modalRealInspection);

  // Close modal
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const cancel = btns.find(b => b.innerText.includes('Cancel'));
    if (cancel) cancel.click();
  });
  await new Promise((r) => setTimeout(r, 500));

  // 4. CHARTLESS MANDATE INSPECTION
  const chartInspection = await page.evaluate(() => {
    const canvases = document.querySelectorAll('canvas').length;
    const tvWidgets = document.querySelectorAll("[class*='tradingview'], [id*='tradingview']").length;
    const recharts = document.querySelectorAll('.recharts-wrapper, .recharts-surface').length;
    const candlesticks = document.querySelectorAll("[class*='candlestick']").length;
    return {
      canvases,
      tvWidgets,
      recharts,
      candlesticks,
      totalCharts: canvases + tvWidgets + recharts + candlesticks
    };
  });
  console.log('Chartless Compliance Inspection:', chartInspection);

  // 5. RESPONSIVE VIEWPORT SWEEP (360, 390, 430, 768, 1024, 1440)
  const viewports = [360, 390, 430, 768, 1024, 1440];
  console.log('Running 6-viewport responsive check on #connections...');
  for (const w of viewports) {
    await page.setViewport({ width: w, height: 800 });
    await clickNav('Exchange Connections');
    await new Promise((r) => setTimeout(r, 600));
    await page.screenshot({ path: `${SCREENSHOT_DIR}/p41_connections_vp_${w}px.png` });
    console.log(`Saved p41_connections_vp_${w}px.png`);
  }

  console.log('Running 6-viewport responsive check on #funding...');
  for (const w of viewports) {
    await page.setViewport({ width: w, height: 800 });
    await clickNav('Funding & Transfers');
    await new Promise((r) => setTimeout(r, 600));
    await page.screenshot({ path: `${SCREENSHOT_DIR}/p41_funding_vp_${w}px.png` });
    console.log(`Saved p41_funding_vp_${w}px.png`);
  }

  await browser.close();
  console.log('================================================================================');
  console.log('PHASE 4.1 FRONTEND VERIFICATION COMPLETE!');
  console.log('================================================================================');
}

verify().catch(err => {
  console.error('Frontend verification failed:', err);
  process.exit(1);
});
