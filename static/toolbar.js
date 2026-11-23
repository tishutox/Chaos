const mobileToggle = document.querySelector(".mobile-toggle");
const toolbar = document.querySelector(".toolbar");
const exportButton = document.querySelector(".export-button");
const exportMenu = document.querySelector(".export-menu");

function setExportOpen(open) {
  exportButton.setAttribute("aria-expanded", String(open));
  exportMenu.hidden = !open;
}

function setMobileOpen(open) {
  mobileToggle.setAttribute("aria-expanded", String(open));
  mobileToggle.setAttribute("aria-label", open ? "Menü schließen" : "Menü öffnen");
  toolbar.classList.toggle("is-open", open);
  if (!open) setExportOpen(false);
}

mobileToggle.addEventListener("click", () => {
  setMobileOpen(mobileToggle.getAttribute("aria-expanded") !== "true");
});

exportButton.addEventListener("click", () => {
  setExportOpen(exportButton.getAttribute("aria-expanded") !== "true");
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".export")) setExportOpen(false);
  if (!event.target.closest(".topbar")) setMobileOpen(false);
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!exportMenu.hidden) {
    setExportOpen(false);
    exportButton.focus();
  } else if (mobileToggle.getAttribute("aria-expanded") === "true") {
    setMobileOpen(false);
    mobileToggle.focus();
  }
});

window.matchMedia("(min-width: 701px)").addEventListener("change", (event) => {
  if (event.matches) setMobileOpen(false);
});
