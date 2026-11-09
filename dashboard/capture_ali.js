const puppeteer = require('puppeteer');
const fs = require('fs');

async function capture() {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 950 });

  const ALI_USER = {
    user_id: "USR-904424B4FB",
    email: "aliajmaltca22@gmail.com",
    username: "Ali Ajmal TCA",
    role: "CUSTOMER",
    status: "ACTIVE",
    first_name: "Ali",
    last_name: "Ajmal TCA",
    country: "PK",
    email_verified: true,
    two_factor_enabled: true,
    must_change_password: false,
    kyc_status: "VERIFIED"
  };

  // 1. Navigate to domain and populate localStorage with Ali's customer session
  await page.goto('http://127.0.0.1:33900/#hft', { waitUntil: 'domcontentloaded' });
  await page.evaluate((usr) => {
    localStorage.clear();
    localStorage.setItem("tauric_session_token", "b7d6d912df5963b8e209cad8454ba0dc3daed1abbcc0477428d4a618b9e3c6a8");
    localStorage.setItem("tauric_session_user", JSON.stringify(usr));
    localStorage.setItem("tauric_auth_token", "b7d6d912df5963b8e209cad8454ba0dc3daed1abbcc0477428d4a618b9e3c6a8");
  }, ALI_USER);

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
