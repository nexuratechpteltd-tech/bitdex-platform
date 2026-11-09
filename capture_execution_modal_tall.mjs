import puppeteer from "/opt/tauric-platform/node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js";
import { execSync } from "child_process";

const credsOutput = execSync(`PYTHONPATH=/opt/tauric-platform-staging/backend /opt/tauric-platform-staging/backend/.venv/bin/python3 -c '
import sqlite3, jwt, time, json
from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM
token = jwt.encode({"sub": "USR-402F7BFE6D", "exp": int(time.time() + 86400)}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
print(json.dumps({"token": token}))
'`).toString();

const token = JSON.parse(credsOutput).token;

const browser = await puppeteer.launch({
  executablePath: "/root/.cache/puppeteer/chrome/linux-148.0.7778.97/chrome-linux64/chrome",
  headless: "new",
  args: ["--no-sandbox", "--disable-setuid-sandbox", "--window-size=1440,1400"]
});

const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 1400 });
await page.setExtraHTTPHeaders({
  "X-Forwarded-Host": "bitdex.ltd",
  "X-Forwarded-Proto": "https"
});

await page.goto("http://127.0.0.1:33900/#trading", { waitUntil: "domcontentloaded", timeout: 30000 });

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

await page.goto("http://127.0.0.1:33900/#trading", { waitUntil: "networkidle2", timeout: 30000 });
await new Promise(r => setTimeout(r, 2500));

// Open Technical Analysis modal on first card
console.log("1. Opening Technical Analysis modal...");
await page.evaluate(() => {
  const cards = Array.from(document.querySelectorAll("button"));
  const taBtn = cards.find(b => b.textContent && b.textContent.includes("Technical Analysis"));
  if (taBtn) taBtn.click();
});
await new Promise(r => setTimeout(r, 1500));

// Click Execute Trade in footer
console.log("2. Clicking Execute Trade in modal footer...");
const clicked = await page.evaluate(() => {
  const btns = Array.from(document.querySelectorAll("button"));
  const execBtn = btns.find(b => b.textContent && b.textContent.trim().includes("Execute Trade"));
  if (execBtn) {
    execBtn.scrollIntoView();
    execBtn.click();
    return true;
  }
  return false;
});
console.log("Execute Trade button clicked:", clicked);

await new Promise(r => setTimeout(r, 2000));

// Inspect dropdown options
const dropdownOptions = await page.evaluate(() => {
  const sel = document.querySelector("#execution-exchange-profile-select");
  if (!sel) return ["Select element not found"];
  sel.scrollIntoView({ block: "center" });
  return Array.from(sel.options).map(o => o.text);
});
console.log("Dropdown options found:", dropdownOptions);

await page.screenshot({ path: "/opt/tauric-platform-staging/evidence_screenshots/evidence_execution_modal_dropdown_final.png" });
console.log("Saved evidence_execution_modal_dropdown_final.png");

await browser.close();
console.log("Finished execution modal capture!");
