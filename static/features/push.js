import { api } from "../core/api.js";
import { aktBenutzer } from "../core/konto.js";
import { renderMitteilungen } from "./mitteilungen.js";
import { icon } from "../core/router.js";
import { toast } from "../core/ui.js";

// ------------------------------------------------------------- Web-Push ----
function pushMoeglich() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}
function base64ZuUint8(base64) {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + pad).replace(/-/g, "+").replace(/_/g, "/");
  const roh = atob(b64);
  const arr = new Uint8Array(roh.length);
  for (let i = 0; i < roh.length; i++) arr[i] = roh.charCodeAt(i);
  return arr;
}
export async function pushStatus() {
  if (!pushMoeglich()) return "nicht_unterstuetzt";
  if (Notification.permission === "denied") return "blockiert";
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    return sub ? "aktiv" : "aus";
  } catch (_) { return "aus"; }
}
export async function pushAktivieren() {
  if (!pushMoeglich()) { toast("Push wird von diesem Gerät nicht unterstützt."); return; }
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") { toast("Benachrichtigungen nicht erlaubt."); return renderPushBox(); }
    const { publicKey } = await api("/api/push/vapid");
    if (!publicKey) { toast("Kein Push-Schlüssel am Server."); return; }
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64ZuUint8(publicKey),
    });
    const j = sub.toJSON();
    await api("/api/push/subscribe", "POST", { endpoint: j.endpoint, keys: j.keys });
    toast("Benachrichtigungen aktiviert ✓");
  } catch (e) { toast("Fehler: " + e.message); }
  renderPushBox();
}
export async function pushTest() {
  try {
    const r = await api("/api/push/test", "POST");
    toast(r.gesendet ? "Test gesendet – Benachrichtigung kommt gleich."
      : "Kein aktives Abo auf diesem Gerät.");
  } catch (e) { toast("Fehler: " + e.message); }
}
export async function pushDeaktivieren() {
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      await api("/api/push/unsubscribe", "POST", { endpoint: sub.endpoint }).catch(() => {});
      await sub.unsubscribe();
    }
    toast("Benachrichtigungen aus.");
  } catch (e) { toast("Fehler: " + e.message); }
  renderPushBox();
}
// Home: ein kleiner Hinweis, solange Mitteilungen auf diesem Gerät aus sind. "Später" blendet
// ihn für zwei Wochen aus; alles Weitere steht unter Profil -> Mitteilungen.
async function renderPushHinweis() {
  const el = document.getElementById("push-box");
  if (!el) return;
  const st = await pushStatus();
  let weg = false;
  try { weg = Number(localStorage.getItem("push_hinweis_bis") || 0) > Date.now(); } catch (_) {}
  if (st !== "aus" || weg || !aktBenutzer || aktBenutzer.ansicht_als) { el.innerHTML = ""; return; }
  el.innerHTML = `<div class="push-karte"><span class="pk-icon">${icon("bell")}</span>
    <span class="pk-text"><b>Mitteilungen anschalten?</b><span>Abfahrt, neue Videos, Feedback – nur was dich betrifft.</span></span>
    <button type="button" class="primaer" data-push="an">Anschalten</button>
    <button type="button" class="pk-spaeter" data-push="spaeter">Später</button></div>`;
  el.querySelector('[data-push="an"]').addEventListener("click", pushAktivieren);
  el.querySelector('[data-push="spaeter"]').addEventListener("click", () => {
    try { localStorage.setItem("push_hinweis_bis", String(Date.now() + 14 * 86400000)); } catch (_) {}
    el.innerHTML = "";
  });
}
export async function renderPushBox() {
  renderPushHinweis();
  const v = document.getElementById("view-mitteilungen");
  if (v && !v.classList.contains("hidden")) renderMitteilungen();
}
