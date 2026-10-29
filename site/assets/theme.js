/* Light or dark, shared by every page through one localStorage key, so a
   choice made on the control room holds on the docs and the FAQ too.

   The first visit takes its cue from the operating system; after that the
   viewer's own choice wins. Every storage access is guarded because it throws
   outright in some embedding contexts. This runs in the head, before the body
   paints, so a saved choice never flashes the other theme first. */
(function(){
  const root = document.documentElement;
  let theme = null;
  try { theme = localStorage.getItem("hrm-theme"); } catch (e) { /* not available */ }
  if (theme !== "Light" && theme !== "Dark")
    theme = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "Dark" : "Light";

  function apply(){
    root.setAttribute("data-theme", theme.toLowerCase());
    const btn = document.getElementById("theme");
    if (btn){
      const label = "Switch to " + (theme === "Dark" ? "light" : "dark") + " mode";
      btn.title = label;
      btn.setAttribute("aria-label", label);
    }
  }
  apply();

  document.addEventListener("DOMContentLoaded", () => {
    apply();
    const btn = document.getElementById("theme");
    if (!btn) return;
    btn.addEventListener("click", () => {
      root.classList.add("theme-anim");
      theme = theme === "Dark" ? "Light" : "Dark";
      apply();
      try { localStorage.setItem("hrm-theme", theme); } catch (e) { /* not available */ }
      setTimeout(() => root.classList.remove("theme-anim"), 300);
    });
  });
})();
