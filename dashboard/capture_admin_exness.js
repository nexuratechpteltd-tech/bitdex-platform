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

  await page.goto('http://127.0.0.1:33900', { waitUntil: 'domcontentloaded' });
  await page.evaluate((tok, u) => {
    localStorage.setItem('tauric_session_token', tok);
    localStorage.setItem('tauric_session_user', JSON.stringify(u));
  }, token, userObj);

  await page.goto('http://127.0.0.1:33900', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 2000));

  // Click "Exchanges" on the Admin sidebar
  await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('button, a, div, span'));
    const btn = all.find(el => el.textContent && el.textContent.trim().startsWith('Exchanges'));
    if (btn) btn.click();
  });

  await new Promise(r => setTimeout(r, 2500));

  // Scroll down to the table
  await page.evaluate(() => {
    window.scrollBy(0, 480);
  });
  await new Promise(r => setTimeout(r, 1000));

  await page.screenshot({ path: '/tmp/admin_exness_registry_table.png', fullPage: false });

  await browser.close();
  console.log('TABLE_CAPTURED');
}

capture().catch(err => {
  console.error('ERROR', err);
  process.exit(1);
});
