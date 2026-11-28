"use strict";

(function () {
  const STORAGE_KEY = "asset-generator.theme";
  const root = document.documentElement;
  const toggle = document.querySelector("#theme-toggle");
  const meta = document.querySelector('meta[name="theme-color"]');

  function apply(theme) {
    const dark = theme === "dark";
    root.dataset.theme = dark ? "dark" : "light";
    if (meta) meta.setAttribute("content", dark ? "#16101a" : "#fdf4f7");
    if (toggle) {
      const label = dark ? "Light Mode aktivieren" : "Dark Mode aktivieren";
      toggle.setAttribute("aria-label", label);
      toggle.setAttribute("title", label);
    }
  }

  apply(localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light");

  if (toggle) {
    toggle.addEventListener("click", () => {
      const next = root.dataset.theme === "dark" ? "light" : "dark";
      apply(next);
      localStorage.setItem(STORAGE_KEY, next);
    });
  }
})();
