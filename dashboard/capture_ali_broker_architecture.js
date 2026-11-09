const puppeteer = require('puppeteer');
const fs = require('fs');

async function capture() {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  // 1. Authenticate as Ali Ajmal TCA (USR-904424B4FB)
  await page.goto('http://127.0.0.1:3002', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    localStorage.setItem('tauric_token', 'mock_token_ali');
    localStorage.setItem('token', 'mock_token_ali');
    localStorage.setItem('tauric_user', JSON.stringify({
      user_id: 'USR-904424B4FB',
      email: 'aliajmaltca22@gmail.com',
      username: 'Ali Ajmal TCA',
      role: 'CUSTOMER',
      status: 'ACTIVE',
      first_name: 'Ali',
      last_name: 'Ajmal TCA'
    }));
  });

  // Reload to apply authenticated session
  await page.goto('http://127.0.0.1:3002', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 2000));

  // Navigate to Automated Scalping tab
  const scalpingTab = await page.;
  if (scalpingTab) {
    await scalpingTab.click();
    await new Promise(r => setTimeout(r, 2000));
  }

  // Capture 1: Main Scalping View showing Ali's account and live quote
  await page.screenshot({ path: '/tmp/ali_broker_scalping_main.png' });

  // Capture 2: Open account selector dropdown to show Demo account ******9575
  const demoDrop = await page.;
  if (demoDrop) {
    await demoDrop.click();
    await new Promise(r => setTimeout(r, 1000));
    await page.screenshot({ path: '/tmp/ali_broker_account_selector_dropdown.png' });
  }

  await browser.close();
  console.log(SCREENSHOTS_CAPTURED);
}

capture().catch(err => {
  console.error(ERROR, err);
  process.exit(1);
});
