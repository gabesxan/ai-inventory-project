// Visual review captures against a built app served with the fixture API.
// Usage: node capture.mjs <appBaseUrl> <outDir> [fixtureApiUrl]
// PLAYWRIGHT_MODULE may point at a playwright install outside the project.
import { mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");

const [base, out, api = "http://127.0.0.1:8199"] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const results = { base, checks: {} };

async function setState(replenishment) {
  await fetch(`${api}/__state`, { method: "POST", body: JSON.stringify({ replenishment }) });
}

async function newPage(browser, width, height, extra = {}) {
  const context = await browser.newContext({ viewport: { width, height }, ...extra });
  await context.addInitScript(() => localStorage.setItem("inventory_auth_token", "fixture-token"));
  const page = await context.newPage();
  const errors = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  return { context, page, errors };
}

async function open(page, path) {
  await page.goto(`${base}${path}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(250);
}

const overflow = (page) =>
  // visualViewport: mobile emulation widens innerWidth to fit overflowing content.
  page.evaluate(() => document.documentElement.scrollWidth - Math.round(window.visualViewport.width));

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
await setState("ready");

for (const [w, h] of [[1440, 900], [390, 844]]) {
  const { context, page, errors } = await newPage(browser, w, h, w < 500 ? { hasTouch: true, isMobile: true } : {});
  await open(page, "/");
  await page.screenshot({ path: `${out}/dashboard-${w}.png`, fullPage: true });
  results.checks[`dashboard-${w}-overflowX`] = await overflow(page);
  await open(page, "/relatorios?tab=replenishment");
  await page.screenshot({ path: `${out}/reposicao-${w}.png`, fullPage: true });
  results.checks[`reposicao-${w}-overflowX`] = await overflow(page);

  // Touch targets for main actions (buttons, tabs, nav links) at this width.
  results.checks[`targets-${w}`] = await page.evaluate(() =>
    Array.from(document.querySelectorAll(".btn, [role=tab], .nav-link, .seg-btn"))
      .filter((el) => el.offsetParent !== null)
      .map((el) => {
        const r = el.getBoundingClientRect();
        return { text: (el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 32), w: Math.round(r.width), h: Math.round(r.height) };
      })
      .filter((t) => t.h < 44 || t.w < 44)
  );

  // Scroll legibility: content passing under the sticky bar.
  await page.mouse.wheel(0, 420);
  await page.waitForTimeout(200);
  await page.screenshot({ path: `${out}/reposicao-${w}-scrolled.png` });
  results.checks[`console-errors-${w}`] = errors;
  await context.close();
}

// 200% zoom equivalent: 1440 CSS px window at 2x = 720 CSS px layout viewport.
{
  const { context, page } = await newPage(browser, 720, 450, { deviceScaleFactor: 2 });
  await open(page, "/");
  results.checks["zoom200-dashboard-overflowX"] = await overflow(page);
  await page.screenshot({ path: `${out}/zoom200-dashboard.png` });
  await open(page, "/relatorios?tab=replenishment");
  results.checks["zoom200-reposicao-overflowX"] = await overflow(page);
  await page.screenshot({ path: `${out}/zoom200-reposicao.png`, fullPage: true });
  await context.close();
}

// Opaque variant: no backdrop-filter support and reduced transparency.
{
  const { context, page } = await newPage(browser, 1440, 900);
  await open(page, "/relatorios?tab=replenishment");
  const glass = () =>
    page.evaluate(() =>
      Array.from(document.querySelectorAll("*"))
        .filter((el) => {
          const s = getComputedStyle(el);
          return s.backdropFilter && s.backdropFilter !== "none";
        })
        .map((el) => ({ cls: String(el.className), bg: getComputedStyle(el).backgroundColor }))
    );
  results.checks["glass-surfaces-enhanced"] = await glass();
  // Simulate a browser without backdrop-filter: the opaque base must remain.
  await page.addStyleTag({
    content:
      ".app-topbar{-webkit-backdrop-filter:none!important;backdrop-filter:none!important;background:#2c2e2c!important}",
  });
  await page.mouse.wheel(0, 420);
  await page.waitForTimeout(200);
  await page.screenshot({ path: `${out}/opaque-no-blur-scrolled.png` });
  results.checks["glass-surfaces-opaque"] = await glass();
  await context.close();
}

// Reduced transparency is a real media feature only in some engines; check the rule ships.
{
  const { context, page } = await newPage(browser, 1440, 900);
  await open(page, "/");
  results.checks.reducedTransparencyRule = await page.evaluate(() =>
    Array.from(document.styleSheets).some((sheet) =>
      Array.from(sheet.cssRules).some((r) => r.cssText.includes("prefers-reduced-transparency"))
    )
  );
  await context.close();
}

// Keyboard: tab order and visible focus on the Replenishment report.
{
  const { context, page } = await newPage(browser, 1440, 900);
  await open(page, "/relatorios?tab=replenishment");
  const order = [];
  for (let i = 0; i < 22; i++) {
    await page.keyboard.press("Tab");
    order.push(
      await page.evaluate(() => {
        const el = document.activeElement;
        if (!el) return null;
        const s = getComputedStyle(el);
        const visible = (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0) || (s.boxShadow && s.boxShadow !== "none");
        return { tag: el.tagName, text: (el.getAttribute("aria-label") || el.textContent || el.id || "").trim().slice(0, 40), focusVisible: visible };
      })
    );
    if (i === 3) await page.screenshot({ path: `${out}/keyboard-focus.png` });
  }
  results.checks.tabOrder = order;
  await context.close();
}

// Reduced motion: transitions should collapse.
{
  const { context, page } = await newPage(browser, 1440, 900, { reducedMotion: "reduce" });
  await open(page, "/");
  results.checks.reducedMotionBtnTransition = await page.evaluate(() => {
    const b = document.querySelector(".btn");
    return b ? getComputedStyle(b).transitionDuration : null;
  });
  await context.close();
}

await browser.close();
writeFileSync(`${out}/results.json`, JSON.stringify(results, null, 2));
console.log(JSON.stringify(results.checks, null, 1).slice(0, 4000));
