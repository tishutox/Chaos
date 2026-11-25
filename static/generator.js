"use strict";

const generatorForm = document.querySelector("#generator-form");
const generatorStatus = document.querySelector("#generator-status");
const preview = document.querySelector("#asset-preview");
const download = document.querySelector("#download-asset");
let previewUrl = null;

function saveAsset(blob, name) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("asset-generator", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("assets", { keyPath: "id" });
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("Die Datenbank ist durch einen anderen Tab blockiert."));
    request.onsuccess = () => {
      const db = request.result;
      try {
        const transaction = db.transaction("assets", "readwrite");
        transaction.objectStore("assets").add({
          id: crypto.randomUUID(),
          kind: "2d",
          name,
          createdAt: new Date().toISOString(),
          linkedAssetId: null,
          data: blob,
        });
        transaction.oncomplete = () => { db.close(); resolve(); };
        transaction.onabort = transaction.onerror = () => {
          db.close();
          reject(transaction.error || new Error("Asset konnte nicht gespeichert werden."));
        };
      } catch (error) {
        db.close();
        reject(error);
      }
    };
  });
}

generatorForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = generatorForm.querySelector("button");
  const prompt = document.querySelector("#asset-prompt").value.trim();
  if (!prompt) {
    generatorStatus.textContent = "Bitte eine Asset-Idee eingeben.";
    generatorStatus.classList.add("is-error");
    return;
  }
  button.disabled = true;
  generatorStatus.classList.remove("is-error");
  generatorStatus.textContent = "Asset wird erstellt. Das kann einige Minuten dauern …";
  try {
    const settings = JSON.parse(localStorage.getItem("asset-generator.settings.v1") || "{}");
    if (!settings || typeof settings !== "object" || Array.isArray(settings) ||
        (settings.backendUrl !== undefined && typeof settings.backendUrl !== "string") ||
        (settings.basePrompt !== undefined && typeof settings.basePrompt !== "string")) {
      throw new Error("Die gespeicherten Einstellungen sind ungültig.");
    }
    const base = new URL(settings.backendUrl || "http://localhost:8000");
    if (!["http:", "https:"].includes(base.protocol) || base.username || base.password || base.search || base.hash) {
      throw new Error("Die Backend-URL ist ungültig.");
    }
    const response = await fetch(`${base.href.replace(/\/+$/, "")}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "omit",
      body: JSON.stringify({ prompt, base_prompt: settings.basePrompt ?? "isolated, centered, no background" }),
    });
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      if (response.headers.get("content-type")?.includes("application/json")) {
        const error = await response.json();
        if (typeof error.detail === "string") detail = error.detail;
      }
      throw new Error(detail);
    }
    const blob = await response.blob();
    if (blob.type !== "image/png") throw new Error("Das Backend hat kein PNG zurückgegeben.");
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(blob);
    preview.src = previewUrl;
    preview.hidden = false;
    download.href = previewUrl;
    download.hidden = false;
    document.querySelector("#preview-placeholder").hidden = true;
    try {
      await saveAsset(blob, prompt);
    } catch (error) {
      throw new Error(`PNG erstellt, aber nicht lokal gespeichert: ${error.message}. Der Download ist weiterhin verfügbar.`);
    }
    generatorStatus.textContent = "Asset erstellt und lokal gespeichert.";
  } catch (error) {
    generatorStatus.textContent = `Fehler: ${error.message}`;
    generatorStatus.classList.add("is-error");
  } finally {
    button.disabled = false;
  }
});
