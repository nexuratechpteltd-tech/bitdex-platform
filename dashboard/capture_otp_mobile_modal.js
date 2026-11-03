const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });

    await page.goto('http://127.0.0.1:33900/', { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1000));

    // Click Sign In
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const signInBtn = buttons.find(b => b.textContent && b.textContent.trim() === 'Sign In');
      if (signInBtn) signInBtn.click();
    });

    await new Promise(r => setTimeout(r, 1000));
    await page.waitForSelector('input[type="email"]');
    await page.type('input[type="email"]', 'test.customer@sheltr.agency');
    await page.type('input[type="password"]', 'TestCustomer2026!');

    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const submitBtn = buttons.find(b => b.textContent && (b.textContent.includes('Sign In with Verification') || b.textContent.includes('Sending verification code')));
      if (submitBtn) submitBtn.click();
    });

    await page.waitForFunction(() => {
      return document.body.innerText.includes('6-Digit Email Verification Code') || document.body.innerText.includes('Code dispatched to:');
    }, { timeout: 35000 });

    await new Promise(r => setTimeout(r, 2000));

    await page.screenshot({ path: '/opt/tauric-platform-staging/otp_verified_mobile.png', fullPage: false });
    console.log('Mobile screenshot saved successfully!');
  } finally {
    await browser.close();
  }
})();
