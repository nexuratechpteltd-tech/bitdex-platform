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

  // 1. Initial navigation to establish origin and set session
  await page.goto('http://127.0.0.1:33900', { waitUntil: 'domcontentloaded' });
  await page.evaluate((tok, u) => {
    localStorage.setItem('tauric_session_token', tok);
    localStorage.setItem('tauric_session_user', JSON.stringify(u));
    localStorage.setItem('tauric_token', tok);
    localStorage.setItem('token', tok);
    localStorage.setItem('tauric_user', JSON.stringify(u));
    localStorage.setItem('bitdex_selected_hft_account', 'EXN-CONN-02926D69E193');
    localStorage.setItem('bitdex_selected_account_id', 'EXN-CONN-02926D69E193');
  }, token, userObj);

  // 2. Load page
  await page.goto('http://127.0.0.1:33900', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 2000));

  // 3. Find and click "Automated Scalping" button in the sidebar
  const clicked = await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('button, a, [role="button"]'));
    const btn = all.find(el => el.textContent && el.textContent.includes('Automated Scalping'));
    if (btn) {
      btn.click();
      return true;
    }
    return false;
  });
  console.log('Clicked Automated Scalping button:', clicked);

  await new Promise(r => setTimeout(r, 3500));

  // Capture Main Automated Scalping View
  await page.screenshot({ path: '/tmp/owner_scalping_main.png', fullPage: false });

  // 4. Try clicking the Account Selector button on the scalping view
  try {
    const dropClicked = await page.evaluate(() => {
      const all = Array.from(document.querySelectorAll('button'));
      const drop = all.find(el => {
        const t = el.textContent || '';
        return t.includes('Exness') || t.includes('Demo') || t.includes('17000660016') || t.includes('Standard') || t.includes('016');
      });
      if (drop) {
        drop.click();
        return true;
      }
      return false;
    });
    console.log('Clicked Dropdown:', dropClicked);
    if (dropClicked) {
      await new Promise(r => setTimeout(r, 1200));
      await page.screenshot({ path: '/tmp/owner_scalping_dropdown.png', fullPage: false });
    }
  } catch (e) {
    console.log('Dropdown error:', e);
  }

  await browser.close();
  console.log('SCALPING_SCREENSHOTS_CAPTURED');
}

capture().catch(err => {
  console.error('ERROR', err);
  process.exit(1);
});
