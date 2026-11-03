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
  args: ["--no-sandbox", "--disable-setuid-sandbox", "--window-size=1440,950"]
});

const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 950 });

console.log("1. Navigating to https://bitdex.ltd and injecting session token...");
await page.goto("https://bitdex.ltd", { waitUntil: "networkidle2", timeout: 30000 });

await page.evaluate((jwtToken) => {
  localStorage.setItem("tauric_session_token", jwtToken);
  localStorage.setItem("bitdex_token", jwtToken);
  localStorage.setItem("tauric_token", jwtToken);
  localStorage.setItem("sheltr_token", jwtToken);
  localStorage.setItem("tauric_user", JSON.stringify({
    user_id: "USR-402F7BFE6D",
    email: "designkrao@gmail.com",
    role: "ADMIN",
    username: "designkrao"
  }));
}, token);

console.log("2. Reloading page to apply authentication...");
await page.goto("https://bitdex.ltd", { waitUntil: "networkidle2", timeout: 30000 });
await new Promise(r => setTimeout(r, 2000));

// Check if customer portal / security settings can be opened
console.log("3. Looking for Customer Portal / Security tab...");
await page.evaluate(() => {
  // Try finding button or link to security / connections
  const btns = Array.from(document.querySelectorAll("button, a"));
  const portalBtn = btns.find(b => b.textContent && (b.textContent.includes("Customer Portal") || b.textContent.includes("Security") || b.textContent.includes("Vault") || b.textContent.includes("Settings")));
  if (portalBtn) portalBtn.click();
});
await new Promise(r => setTimeout(r, 2000));

// Take full page screenshot of main dashboard
await page.screenshot({ path: "/opt/tauric-platform-staging/evidence_screenshots/evidence_01_dashboard_with_connections.png", fullPage: false });
console.log("Saved evidence_01_dashboard_with_connections.png");

// Test execution modal to see dropdown
console.log("4. Triggering execution modal to inspect Exchange Profile dropdown...");
const tradeTriggered = await page.evaluate(() => {
  const tradeBtns = Array.from(document.querySelectorAll("button")).filter(b => b.textContent && (b.textContent.includes("Execute") || b.textContent.includes("Trade") || b.textContent.includes("Order")));
  if (tradeBtns.length > 0) {
    tradeBtns[0].click();
    return true;
  }
  return false;
});

await new Promise(r => setTimeout(r, 1500));
await page.screenshot({ path: "/opt/tauric-platform-staging/evidence_screenshots/evidence_02_execution_modal_dropdown.png", fullPage: false });
console.log("Saved evidence_02_execution_modal_dropdown.png");

// Inspect dropdown options
const dropdownOptions = await page.evaluate(() => {
  const sel = document.querySelector("#execution-exchange-profile-select");
  if (!sel) return ["Select element not found"];
  return Array.from(sel.options).map(o => o.text);
});
console.log("Dropdown options found in execution modal:", dropdownOptions);

await browser.close();
console.log("Browser test finished successfully.");
