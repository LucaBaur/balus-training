// Prueft die Geraeteerkennung (geraetInfo in static/app.js) mit typischen
// User-Agents: Android-Chrome (reduzierter UA + userAgentData), iPhone-Safari,
// installierte iPhone-App, Samsung Internet, Windows, iPad. Start: node tests/geraet.test.mjs
import fs from "node:fs";
import vm from "node:vm";

const src = fs.readFileSync(new URL("../static/app.js", import.meta.url), "utf8");
const start = src.indexOf("let _geraet = null;");
const ende = src.indexOf("const geraetKurz");
if (start < 0 || ende < 0) { console.error("FEHLER geraetInfo nicht gefunden"); process.exit(1); }
const code = src.slice(start, ende);

async function erkenne({ ua, hoch = null, touch = 0, standalone = false, referrer = "", sw = true, screen = [412, 915], nav = {} }) {
  const ctx = {
    navigator: { userAgent: ua, maxTouchPoints: touch, standalone: nav.standalone,
                 userAgentData: hoch ? { getHighEntropyValues: async () => hoch } : undefined,
                 serviceWorker: sw ? { controller: {} } : {} },
    document: { referrer }, screen: { width: screen[0], height: screen[1] },
    window: { matchMedia: () => ({ matches: standalone }) }, matchMedia: () => ({ matches: standalone }),
    APP_VERSION: "v0.52.0",
  };
  vm.createContext(ctx);
  vm.runInContext(code + "\nthis.geraetInfo = geraetInfo;", ctx);
  return ctx.geraetInfo();
}

let fehler = 0;
function check(name, ist, soll) {
  const ok = Object.entries(soll).every(([k, v]) => ist[k] === v);
  console.log((ok ? "ok   " : "FEHLER ") + name + (ok ? "" : "  -> " + JSON.stringify(ist)));
  if (!ok) fehler++;
}

check("Android 13, Chrome 126, installiert (reduzierter UA meldet 10)",
  await erkenne({
    ua: "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    hoch: { model: "SM-S911B", platformVersion: "13.0.0" }, standalone: true }),
  { os: "Android 13", browser: "Chrome 126", modus: "installiert", modell: "SM-S911B", bildschirm: "412x915", sw: true });

check("Android ohne userAgentData: Version aus dem UA",
  await erkenne({ ua: "Mozilla/5.0 (Linux; Android 9; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36" }),
  { os: "Android 9", browser: "Chrome 110", modus: "Browser", modell: "" });

check("Android-APK (Trusted Web Activity)",
  await erkenne({ ua: "Mozilla/5.0 (Linux; Android 8.0.0; BAH2-W19) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.0.0 Safari/537.36",
                  referrer: "android-app://de.tvg.balu" }),
  { os: "Android 8", modus: "Android-App" });

check("iPhone Safari im Browser",
  await erkenne({ ua: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
                  screen: [390, 844], touch: 5 }),
  { os: "iOS 17", browser: "Safari 17", modus: "Browser", bildschirm: "390x844" });

check("iPhone installiert (navigator.standalone)",
  await erkenne({ ua: "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                  nav: { standalone: true }, touch: 5 }),
  { os: "iOS 16", browser: "Safari 16", modus: "installiert" });

check("iPhone mit Chrome (CriOS)",
  await erkenne({ ua: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/121.0.6167.138 Mobile/15E148 Safari/604.1", touch: 5 }),
  { os: "iOS 17", browser: "Chrome 121" });

check("iPad mit Desktop-UA (iPadOS)",
  await erkenne({ ua: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15", touch: 5 }),
  { os: "iPadOS", browser: "Safari 17" });

check("Samsung Internet",
  await erkenne({ ua: "Mozilla/5.0 (Linux; Android 13; SAMSUNG SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0.0.0 Mobile Safari/537.36" }),
  { os: "Android 13", browser: "Samsung Internet 23" });

check("Windows 11 Edge",
  await erkenne({ ua: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
                  hoch: { model: "", platformVersion: "15.0.0" }, screen: [1920, 1080] }),
  { os: "Windows 11", browser: "Edge 126" });

check("Ohne Service Worker", await erkenne({ ua: "Mozilla/5.0 (Windows NT 10.0) Chrome/126.0.0.0", sw: false }), { sw: false });

if (fehler) { console.error("\n" + fehler + " Test(s) fehlgeschlagen"); process.exit(1); }
console.log("\nAlle Tests bestanden");
