"use strict";

function defaultBackendUrl() {
  const host = window.location.hostname;
  const isLocal = host === "localhost" || host === "127.0.0.1" || /^(\d{1,3}\.){3}\d{1,3}$/.test(host);
  return isLocal ? `http://${host}:8000` : "http://localhost:8000";
}

const STORAGE_KEY = "asset-generator.settings.v1";
const DATABASE_NAME = "asset-generator";
const STORE_NAME = "assets";
const defaults = {
  backendUrl: "",
  apiKey: "",
  imageResolution: "1024",
  autoBackground: true,
  basePrompt: "isolated, centered, no background",
  negativePrompt: "blurry, cropped, text, watermark",
  polycount: "15000",
  textureResolution: "1024",
  pbrMaps: true,
  exportFormat: "glb",
};
const form = document.querySelector("#settings-form");
const saveStatus = document.querySelector("#save-status");
const workspaceStatus = document.querySelector("#workspace-status");
const connectionStatus = document.querySelector("#connection-status");
let connectionController = null;
const workspaceButtons = [
  document.querySelector("#export-workspace"),
  document.querySelector("#import-workspace"),
  document.querySelector("#clear-assets"),
];

function validateSettings(settings) {
  if (!settings || typeof settings !== "object" || Array.isArray(settings)) {
    throw new Error("Ungültige Einstellungen.");
  }
  for (const [key, value] of Object.entries(defaults)) {
    if (typeof settings[key] !== typeof value) throw new Error(`Ungültiger Wert für ${key}.`);
  }
  for (const [key, allowed] of Object.entries({
    imageResolution: ["512", "1024"],
    polycount: ["5000", "15000", "30000"],
    textureResolution: ["1024", "2048"],
    exportFormat: ["glb", "fbx", "obj"],
  })) {
    if (!allowed.includes(settings[key])) throw new Error(`Ungültiger Wert für ${key}.`);
  }
  if (settings.backendUrl) {
    let url;
    try {
      url = new URL(settings.backendUrl);
    } catch {
      throw new Error("Bitte eine gültige Backend-URL eingeben.");
    }
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new Error("Die Backend-URL muss HTTP(S) verwenden und darf keine Zugangsdaten, Query oder Fragment enthalten.");
    }
  }
  return Object.fromEntries(Object.keys(defaults).map((key) => [key, settings[key]]));
}

function readForm() {
  const settings = {};
  for (const [key, value] of Object.entries(defaults)) {
    const field = form.elements.namedItem(key);
    settings[key] = typeof value === "boolean" ? field.checked : field.value.trim();
  }
  return validateSettings(settings);
}

function fillForm(settings) {
  for (const [key, value] of Object.entries(settings)) {
    const field = form.elements.namedItem(key);
    if (typeof value === "boolean") field.checked = value;
    else field.value = value;
  }
}

function showStatus(element, message, error = false) {
  element.textContent = message;
  element.classList.toggle("is-error", error);
}

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE_NAME, { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("Die Datenbank ist durch einen anderen Tab blockiert."));
  });
}

async function withStore(mode, operation) {
  const db = await openDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, mode);
      let result;
      try {
        result = operation(transaction.objectStore(STORE_NAME));
      } catch (error) {
        transaction.abort();
        reject(error);
        return;
      }
      transaction.oncomplete = () => resolve(result && result.result);
      transaction.onabort = () => reject(transaction.error || new Error("Datenbanktransaktion abgebrochen."));
      transaction.onerror = () => reject(transaction.error);
    });
  } finally {
    db.close();
  }
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

async function updateStorage() {
  const text = document.querySelector("#storage-text");
  const progress = document.querySelector("#storage-usage");
  if (!navigator.storage || !navigator.storage.estimate) {
    text.textContent = "Speicherschätzung nicht verfügbar";
    progress.removeAttribute("value");
    return;
  }
  try {
    const { usage, quota } = await navigator.storage.estimate();
    if (!Number.isFinite(usage) || !Number.isFinite(quota) || quota <= 0) throw new Error("Keine Speicherwerte verfügbar.");
    text.textContent = `${formatBytes(usage)} / ${formatBytes(quota)}`;
    progress.value = Math.min(100, usage / quota * 100);
  } catch (error) {
    text.textContent = `Speicherschätzung nicht verfügbar: ${error.message}`;
    progress.removeAttribute("value");
  }
}

function validateAsset(asset) {
  if (!asset || typeof asset !== "object" || Array.isArray(asset) ||
      typeof asset.id !== "string" || !asset.id ||
      !["2d", "3d"].includes(asset.kind) ||
      typeof asset.name !== "string" ||
      typeof asset.createdAt !== "string" || !Number.isFinite(Date.parse(asset.createdAt)) ||
      !(asset.data instanceof Blob) ||
      (asset.linkedAssetId !== null && typeof asset.linkedAssetId !== "string")) {
    throw new Error("Das Backup enthält ein ungültiges Asset.");
  }
  return { id: asset.id, kind: asset.kind, name: asset.name, createdAt: asset.createdAt, linkedAssetId: asset.linkedAssetId, data: asset.data };
}

function encodeBlob(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",", 2)[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

function decodeAsset(asset) {
  if (!asset || typeof asset !== "object" || typeof asset.data !== "string" || typeof asset.mimeType !== "string") {
    throw new Error("Das Backup enthält ungültige Asset-Daten.");
  }
  let binary;
  try {
    binary = atob(asset.data);
  } catch {
    throw new Error("Das Backup enthält ungültige Binärdaten.");
  }
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return validateAsset({ ...asset, data: new Blob([bytes], { type: asset.mimeType }) });
}

async function workspaceAction(action) {
  workspaceButtons.forEach((button) => { button.disabled = true; });
  try {
    await action();
  } catch (error) {
    showStatus(workspaceStatus, `Fehler: ${error.message}`, true);
  } finally {
    workspaceButtons.forEach((button) => { button.disabled = false; });
    await updateStorage();
  }
}

try {
  const stored = localStorage.getItem(STORAGE_KEY);
  fillForm(stored === null ? defaults : validateSettings(JSON.parse(stored)));
} catch (error) {
  fillForm(defaults);
  showStatus(saveStatus, `Gespeicherte Einstellungen konnten nicht geladen werden: ${error.message}`, true);
}
updateStorage();

form.addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(readForm()));
    showStatus(saveStatus, "Einstellungen gespeichert.");
    updateStorage();
  } catch (error) {
    showStatus(saveStatus, `Einstellungen konnten nicht gespeichert werden: ${error.message}`, true);
  }
});

document.querySelector("#test-connection").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const controller = new AbortController();
  connectionController = controller;
  const timeout = setTimeout(() => controller.abort(), 10000);
  button.disabled = true;
  showStatus(connectionStatus, "Verbindung wird geprüft …");
  connectionStatus.classList.remove("is-connected");
  try {
    const backendUrl = readForm().backendUrl;
    const url = `${(backendUrl || defaultBackendUrl()).replace(/\/+$/, "")}/health`;
    const response = await fetch(url, { signal: controller.signal, credentials: "omit", cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    if (connectionController !== controller) return;
    showStatus(connectionStatus, "Verbunden");
    connectionStatus.classList.add("is-connected");
  } catch (error) {
    if (connectionController === controller) {
      showStatus(connectionStatus, `Fehler: ${error.name === "AbortError" ? "Zeitüberschreitung" : error.message}`, true);
    }
  } finally {
    clearTimeout(timeout);
    if (connectionController === controller) connectionController = null;
    button.disabled = false;
  }
});

document.querySelector("#backend-url").addEventListener("input", () => {
  if (connectionController) {
    connectionController.abort();
    connectionController = null;
  }
  showStatus(connectionStatus, "Nicht getestet");
  connectionStatus.classList.remove("is-connected");
});

document.querySelector("#export-workspace").addEventListener("click", () => workspaceAction(async () => {
  const stored = localStorage.getItem(STORAGE_KEY);
  const settings = stored === null ? { ...defaults } : validateSettings(JSON.parse(stored));
  delete settings.apiKey;
  const assets = await withStore("readonly", (store) => store.getAll());
  const encoded = await Promise.all(assets.map(async (item) => {
    const asset = validateAsset(item);
    return { ...asset, mimeType: asset.data.type, data: await encodeBlob(asset.data) };
  }));
  const json = JSON.stringify({ format: "asset-generator-workspace", version: 1, settings, assets: encoded });
  const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "backup.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  showStatus(workspaceStatus, "Backup erstellt. Ungespeicherte Änderungen sind nicht enthalten.");
}));

const backupFile = document.querySelector("#backup-file");
document.querySelector("#import-workspace").addEventListener("click", () => backupFile.click());
backupFile.addEventListener("change", () => {
  const file = backupFile.files[0];
  if (!file) return;
  workspaceAction(async () => {
    const backup = JSON.parse(await file.text());
    if (!backup || backup.format !== "asset-generator-workspace" || backup.version !== 1 || !Array.isArray(backup.assets) ||
        !backup.settings || Object.hasOwn(backup.settings, "apiKey")) {
      throw new Error("Unbekanntes oder ungültiges Backup-Format.");
    }
    const previous = localStorage.getItem(STORAGE_KEY);
    const current = previous === null ? defaults : validateSettings(JSON.parse(previous));
    const settings = validateSettings({ ...backup.settings, apiKey: current.apiKey });
    const assets = backup.assets.map(decodeAsset);
    if (new Set(assets.map((asset) => asset.id)).size !== assets.length) throw new Error("Das Backup enthält doppelte Asset-IDs.");
    if (!window.confirm("Vorhandene Einstellungen und Assets durch das Backup ersetzen? Der API-Key bleibt erhalten.")) return;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    try {
      await withStore("readwrite", (store) => {
        store.clear();
        for (const asset of assets) store.add(asset);
      });
    } catch (error) {
      try {
        if (previous === null) localStorage.removeItem(STORAGE_KEY);
        else localStorage.setItem(STORAGE_KEY, previous);
      } catch (rollbackError) {
        throw new Error(`Import fehlgeschlagen: ${error.message}. Einstellungen konnten nicht wiederhergestellt werden: ${rollbackError.message}`);
      }
      throw error;
    }
    fillForm(settings);
    if (connectionController) {
      connectionController.abort();
      connectionController = null;
    }
    showStatus(saveStatus, "");
    showStatus(connectionStatus, "Nicht getestet");
    connectionStatus.classList.remove("is-connected");
    showStatus(workspaceStatus, "Workspace importiert.");
  }).finally(() => { backupFile.value = ""; });
});

document.querySelector("#clear-assets").addEventListener("click", () => workspaceAction(async () => {
  if (!window.confirm("Alle lokal gespeicherten Assets unwiderruflich löschen? Die Einstellungen bleiben erhalten.")) return;
  await withStore("readwrite", (store) => store.clear());
  showStatus(workspaceStatus, "Lokale Assets gelöscht.");
}));
