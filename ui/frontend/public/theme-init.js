"use strict";

(function () {
  var theme = "light";
  try {
    var stored = window.localStorage.getItem("fms-ui-theme");
    if (stored === "dark" || stored === "light") {
      theme = stored;
    } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      theme = "dark";
    }
  } catch (error) {
    theme = "light";
  }
  document.documentElement.dataset.theme = theme;
})();
