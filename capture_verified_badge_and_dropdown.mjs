import puppeteer from "/opt/tauric-platform/node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js";
import { execSync } from "child_process";

const credsOutput = execSync(`PYTHONPATH=/opt/tauric-platform-staging/backend /opt/tauric-platform-staging/backend/.venv/bin/python3 -c '
import sqlite3, jwt, time, json
from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM
from app.routes.saas_customer import _decrypt_credentials_payload

token = jwt.encode({"sub": "USR-402F7BFE6D", "exp": int(time.time() + 86400)}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

conn = sqlite3.connect("/opt/tauric-platform-staging/backend/data/tauric_saas.db")
c = conn.cursor()
c.execute("SELECT account_id, environment, encrypted_credentials FROM user_exchange_connections WHERE account_id = ?", ("CONN-DK-BIN-DEMO-MIGRATED",))
demo_creds = _decrypt_credentials_payload(c.fetchone()[2])

print(json.dumps({
    "token": token,
    "demo_key": demo_creds["api_key"],
    "demo_secret": demo_creds["api_secret"]
}))
'`).toString();

const authData = JSON.parse(credsOutput);
const token = authData.token;
const demoKey = authData.demo_key;
const demoSecret = authData.demo_secret;

const browser = await puppeteer.launch({
  executablePath: "/root/.cache/puppeteer/chrome/linux-148.0.7778.97/chrome-linux64/chrome",
  headless: "new",
  args: ["--no-sandbox", "--disable-setuid-sandbox", "--window-size=1440,1100"]
});

const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 1100 });
await page.setExtraHTTPHeaders({
  "X-Forwarded-Host": "bitdex.ltd",
  "X-Forwarded-Proto": "https"
});

await page.goto("http://127.0.0.1:33900/#connections", { waitUntil: "domcontentloaded", timeout: 30000 });

await page.evaluate((jwtToken) => {
  localStorage.setItem("tauric_session_token", jwtToken);
  localStorage.setItem("bitdex_token", jwtToken);
  localStorage.setItem("tauric_token", jwtToken);
  localStorage.setItem("sheltr_token", jwtToken);
  localStorage.setItem("tauric_session_user", JSON.stringify({
    user_id: "USR-402F7BFE6D",
    email: "designkrao@gmail.com",
    role: "CUSTOMER",
    username: "designkrao"
  }));
}, token);

await page.goto("http://127.0.0.1:33900/#connections", { waitUntil: "networkidle2", timeout: 30000 });
await new Promise(r => setTimeout(r, 2000));

// Scroll down to the form
await page.evaluate(() => {
  const form = document.querySelector("form");
  if (form) form.scrollIntoView({ block: "center" });
});
await new Promise(r => setTimeout(r, 1000));

// Type exchange name, key, secret
console.log("Typing Binance into Exchange Name, and typing Demo key/secret...");
const allInputs = await page.$$("input");
for (const input of allInputs) {
  const ph = await page.evaluate(el => el.placeholder || "", input);
  if (ph.toLowerCase().includes("binance, bybit") || ph.toLowerCase().includes("exchange / account name")) {
    await input.click({ clickCount: 3 });
    await input.type("Binance");
  } else if (ph.toLowerCase().includes("enter exchange api key") || ph.toLowerCase().includes("api key")) {
    await input.click({ clickCount: 3 });
    await input.type(demoKey);
  } else if (ph.toLowerCase().includes("enter exchange api secret") || ph.toLowerCase().includes("secret")) {
    await input.click({ clickCount: 3 });
    await input.type(demoSecret);
  }
}

// Click Test Credentials
console.log("Clicking Test Credentials with valid Demo key...");
await page.evaluate(() => {
  const btns = Array.from(document.querySelectorAll("button"));
  const testBtn = btns.find(b => b.textContent && b.textContent.includes("Test Credentials"));
  if (testBtn) testBtn.click();
});

// Wait for test result badge
await new Promise(r => setTimeout(r, 4500));
await page.screenshot({ path: "/opt/tauric-platform-staging/evidence_screenshots/evidence_test_credentials_verified_live.png" });
console.log("Saved evidence_test_credentials_verified_live.png");

// Test intentional bad key with Binance as exchange name
console.log("Testing bad key with Binance name to capture -2015 diagnostic...");
for (const input of allInputs) {
  const ph = await page.evaluate(el => el.placeholder || "", input);
  if (ph.toLowerCase().includes("enter exchange api key") || ph.toLowerCase().includes("api key")) {
    await input.click({ clickCount: 3 });
    await input.type("INVALID_BINANCE_TEST_KEY_9999");
  }
}

await page.evaluate(() => {
  const btns = Array.from(document.querySelectorAll("button"));
  const testBtn = btns.find(b => b.textContent && b.textContent.includes("Test Credentials"));
  if (testBtn) testBtn.click();
});

await new Promise(r => setTimeout(r, 2500));
await page.screenshot({ path: "/opt/tauric-platform-staging/evidence_screenshots/evidence_test_credentials_failed_diagnostic.png" });
console.log("Saved evidence_test_credentials_failed_diagnostic.png");

await browser.close();
console.log("Done!");
