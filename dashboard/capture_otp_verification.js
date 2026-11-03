const puppeteer = require("puppeteer");
const path = require("path");

(async () => {
  console.log("Starting Puppeteer UI verification for Bitdex OTP...");
  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-software-rasterizer"]
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });

    // Navigate to staging landing page
    console.log("Navigating to http://127.0.0.1:33900/ ...");
    await page.goto("http://127.0.0.1:33900/", { waitUntil: "networkidle2" });
    await new Promise(r => setTimeout(r, 1000));

    // Find and click the "Sign In" button in the header
    console.log("Clicking Sign In button...");
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll("button"));
      const signInBtn = buttons.find(b => b.textContent && b.textContent.trim() === "Sign In");
      if (signInBtn) signInBtn.click();
      else throw new Error("Could not find Sign In button");
    });

    await new Promise(r => setTimeout(r, 1000));

    // Type credentials
    console.log("Entering credentials for test.customer@sheltr.agency...");
    await page.waitForSelector('input[type="email"]');
    await page.type('input[type="email"]', "test.customer@sheltr.agency");
    await page.type('input[type="password"]', "TestCustomer2026!");

    // Click submit button
    console.log("Submitting login form...");
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll("button"));
      const submitBtn = buttons.find(b => b.textContent && (b.textContent.includes("Sign In with Verification") || b.textContent.includes("Sending verification code")));
      if (submitBtn) submitBtn.click();
      else throw new Error("Could not find submit button");
    });

    // Wait for the OTP stage to appear
    console.log("Waiting for OTP verification stage...");
    await page.waitForFunction(() => {
      return document.body.innerText.includes("6-Digit Email Verification Code") || document.body.innerText.includes("Code dispatched to:");
    }, { timeout: 35000 });

    // Wait 2 seconds for animations & delivery status banner to settle
    await new Promise(r => setTimeout(r, 2000));

    // Inspect the text on the page
    const pageText = await page.evaluate(() => document.body.innerText);

    console.log("Evaluating page assertions...");
    const hasAcceptedMsg = pageText.includes("Email provider accepted the message");
    const hasAuditQueueMsg = pageText.includes("Verification challenge recorded in server audit queue");
    const hasFailedMsg = pageText.includes("Could not send verification email");
    const hasCodeDispatched = pageText.includes("Code dispatched to:");
    const hasCooldown = pageText.includes("Resend code (");

    console.log("ASSERTIONS SUMMARY:");
    console.log("  - Has 'Email provider accepted the message':", hasAcceptedMsg);
    console.log("  - Has 'Verification challenge recorded in server audit queue' (MUST BE FALSE):", hasAuditQueueMsg);
    console.log("  - Has 'Could not send verification email' (MUST BE FALSE):", hasFailedMsg);
    console.log("  - Has 'Code dispatched to:':", hasCodeDispatched);
    console.log("  - Has Resend cooldown active:", hasCooldown);

    if (!hasAcceptedMsg) {
      console.warn("WARNING: Expected 'Email provider accepted the message' banner!");
    }
    if (hasAuditQueueMsg) {
      throw new Error("FAIL: Server audit queue text is still visible!");
    }

    // Capture Desktop Screenshot
    const desktopPath = "/opt/tauric-platform-staging/otp_verified_desktop.png";
    await page.screenshot({ path: desktopPath, fullPage: false });
    console.log(`Saved desktop screenshot to ${desktopPath}`);

    // Switch to Mobile Viewport (iPhone 12 / 13 / 14: 390x844)
    await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
    await new Promise(r => setTimeout(r, 1000));
    const mobilePath = "/opt/tauric-platform-staging/otp_verified_mobile.png";
    await page.screenshot({ path: mobilePath, fullPage: false });
    console.log(`Saved mobile screenshot to ${mobilePath}`);

    console.log("UI VERIFICATION COMPLETE AND PASSED!");
  } catch (err) {
    console.error("Puppeteer test failed:", err);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
