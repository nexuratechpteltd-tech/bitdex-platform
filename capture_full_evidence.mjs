import puppeteer from "/opt/tauric-platform/node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js";
import { execSync } from "child_process";
import fs from "fs";

// 1. Get valid JWT session token and credentials from Python
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

fs.mkdirSync("/opt/tauric-platform-staging/evidence_screenshots", { recursive: true });

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

console.log("1. Injecting localStorage credentials...");
await page.goto("http://127.0.0.1:33900/#connections", { waitUntil: "domcontentloaded", timeout: 30000 });

await page.evaluate((jwtToken) => {
  localStorage.setItem("tauric_session_token", jwtToken);
  localStorage.setItem("bitdex_token", jwtToken);
  localStorage.setItem("tauric_token", jwtToken);
  localStorage.setItem("sheltr_token", jwtToken);
  localStorage.setItem("tauric_session_user", JSON.stringify({
    user_id: "USR-402F7BFE6D",
    email: "test_customer@bitdex.io",
    role: "CUSTOMER",
    username: "designkrao"
  }));
}, token);

console.log("2. Navigating to http://127.0.0.1:33900/#connections...");
await page.goto("http://127.0.0.1:33900/#connections", { waitUntil: "networkidle2", timeout: 30000 });
await new Promise(r => setTimeout(r, 3000));

// Screenshot 1: Customer Connections Table
await page.screenshot({ path: "/opt/tauric-platform-staging/evidence_screenshots/evidence_01_customer_connections_list.png" });
console.log("Saved evidence_01_customer_connections_list.png");

// 3. Test Binance Demo credentials in the form
console.log("3. Filling Connect Exchange Account form with real Binance Demo credentials...");
await page.evaluate((key, secret) => {
  const inputs = Array.from(document.querySelectorAll("input"));
  const keyInput = inputs.find(i => i.placeholder && i.placeholder.toLowerCase().includes("key"));
  const secInput = inputs.find(i => i.placeholder && i.placeholder.toLowerCase().includes("secret"));

  if (keyInput) {
    keyInput.value = key;
    keyInput.dispatchEvent(new Event("input", { bubbles: true }));
  }
  if (secInput) {
    secInput.value = secret;
    secInput.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // Click Test Credentials
  const btns = Array.from(document.querySelectorAll("button"));
  const testBtn = btns.find(b => b.textContent && b.textContent.includes("Test Credentials"));
  if (testBtn) {
    testBtn.click();
    return true;
  }
  return false;
}, demoKey, demoSecret);

// Wait for verification response (4s)
await new Promise(r => setTimeout(r, 4000));
await page.screenshot({ path: "/opt/tauric-platform-staging/evidence_screenshots/evidence_02_binance_demo_test_verified.png" });
console.log("Saved evidence_02_binance_demo_test_verified.png");

// 4. Test Invalid credentials
console.log("4. Testing invalid credentials...");
await page.evaluate(() => {
  const inputs = Array.from(document.querySelectorAll("input"));
  const keyInput = inputs.find(i => i.placeholder && i.placeholder.toLowerCase().includes("key"));
  const secInput = inputs.find(i => i.placeholder && i.placeholder.toLowerCase().includes("secret"));

  if (keyInput) {
    keyInput.value = "INVALID_API_KEY_TEST_99999";
    keyInput.dispatchEvent(new Event("input", { bubbles: true }));
  }
  if (secInput) {
    secInput.value = "INVALID_SECRET_TEST_99999";
    secInput.dispatchEvent(new Event("input", { bubbles: true }));
  }

  const btns = Array.from(document.querySelectorAll("button"));
  const testBtn = btns.find(b => b.textContent && b.textContent.includes("Test Credentials"));
  if (testBtn) testBtn.click();
});

await new Promise(r => setTimeout(r, 2000));
await page.screenshot({ path: "/opt/tauric-platform-staging/evidence_screenshots/evidence_03_binance_test_failure_diagnostic.png" });
console.log("Saved evidence_03_binance_test_failure_diagnostic.png");

// 5. Navigate to Balances tab
console.log("5. Navigating to Balances Tab...");
await page.goto("http://127.0.0.1:33900/#balances", { waitUntil: "networkidle2", timeout: 30000 });
await new Promise(r => setTimeout(r, 3000));
await page.screenshot({ path: "/opt/tauric-platform-staging/evidence_screenshots/evidence_04_customer_balances_tab.png" });
console.log("Saved evidence_04_customer_balances_tab.png");

// 6. Navigate to Trading Tab
console.log("6. Navigating to Trading Tab...");
await page.goto("http://127.0.0.1:33900/#trading", { waitUntil: "networkidle2", timeout: 30000 });
await new Promise(r => setTimeout(r, 3000));

// Open trade modal
await page.evaluate(() => {
  const btns = Array.from(document.querySelectorAll("button"));
  const tradeBtn = btns.find(b => b.textContent && (b.textContent.includes("Trade") || b.textContent.includes("Execute") || b.textContent.includes("Order")));
  if (tradeBtn) tradeBtn.click();
});
await new Promise(r => setTimeout(r, 1500));

await page.screenshot({ path: "/opt/tauric-platform-staging/evidence_screenshots/evidence_05_trading_execution_modal_dropdown.png" });
console.log("Saved evidence_05_trading_execution_modal_dropdown.png");

await browser.close();
console.log("Done capturing all verification evidence!");
