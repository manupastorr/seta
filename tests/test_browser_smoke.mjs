import assert from "node:assert/strict";
import test from "node:test";

const BASE_URL = process.env.SETA_BASE_URL || "http://127.0.0.1:8765";

async function serverAvailable() {
  try {
    const res = await fetch(`${BASE_URL}/api/library`);
    return res.ok;
  } catch (_) {
    return false;
  }
}

async function assetHostAvailable() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const res = await fetch("https://cdn.jsdelivr.net/npm/d3@7", {
      method: "HEAD",
      signal: controller.signal,
    });
    return res.ok;
  } catch (_) {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

test("browser smoke: map, filters, and empty mix-link state", async (t) => {
  if (process.env.SETA_RUN_BROWSER_SMOKE !== "1") {
    t.skip("Set SETA_RUN_BROWSER_SMOKE=1 to run browser smoke coverage");
    return;
  }
  if (!(await serverAvailable())) {
    t.skip(`Seta server is not running at ${BASE_URL}`);
    return;
  }
  if (!(await assetHostAvailable())) {
    t.skip("D3 CDN is not reachable; browser smoke requires page assets");
    return;
  }

  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch (_) {
    t.skip("Playwright is not available in this environment");
    return;
  }

  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: { width: 1365, height: 900 } });
  const pageIssues = [];
  page.on("console", msg => {
    if (["error", "warning"].includes(msg.type())) pageIssues.push(`${msg.type()}: ${msg.text()}`);
  });
  page.on("pageerror", err => pageIssues.push(`pageerror: ${err.message}`));

  await page.goto(BASE_URL, { waitUntil: "load", timeout: 15000 });
  await page.waitForSelector("#graph", { state: "attached" });

  const state = await page.evaluate(async () => {
    const library = await fetch("/api/library").then(res => res.json());
    const hasEdges = Array.isArray(library.edges) && library.edges.length > 0;
    const explore = document.getElementById("layout-explore-btn");
    const note = document.getElementById("mix-links-note");
    return {
      hasEdges,
      title: document.title,
      graphPresent: !!document.getElementById("graph"),
      playerPresent: !!document.getElementById("player-dock"),
      camelotWheelPresent: !!document.querySelector(".camelot-wheel"),
      setZoneClouds: document.querySelectorAll(".moment-cloud").length,
      exploreDisabled: !!explore?.disabled,
      noteVisible: note ? !note.hidden : false,
      helperTextPresent: document.body.innerText.includes("Click a key to filter tracks")
        || document.body.innerText.includes("Click a zone to filter tracks"),
      horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
    };
  });

  assert.equal(state.title, "Seta 🍄");
  assert.equal(state.graphPresent, true);
  assert.equal(state.playerPresent, true);
  assert.equal(state.camelotWheelPresent, true);
  assert.ok(state.setZoneClouds > 0);
  assert.equal(state.helperTextPresent, false);
  assert.equal(state.horizontalOverflow, false);
  if (!state.hasEdges) {
    assert.equal(state.exploreDisabled, true);
    assert.equal(state.noteVisible, true);
  }
  assert.deepEqual(pageIssues, []);
});
