/* Prevención síncrona de FOUC compatible con CSP script-src 'self' */
(() => {
  try {
    const stored = localStorage.getItem("alvea_color_scheme");
    const meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) {
      meta.content = stored === "light" || stored === "dark" ? stored : "light dark";
    }
  } catch (_) {
    /* Acceso a localStorage bloqueado: mantener preferencia del sistema */
  }
})();
