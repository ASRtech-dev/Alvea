/* Visor Standalone ALVEA — CSP strict, securityLevel: "strict", pan/zoom, copia exacta */
(() => {
  "use strict";

  let zoom = 1;
  let panX = 0;
  let panY = 0;
  let isDragging = false;
  let dragStartX = 0;
  let dragStartY = 0;

  const canvasPane = document.getElementById("sa-canvas");
  const stage = document.getElementById("sa-stage");
  const viewport = document.getElementById("sa-viewport");
  const zoomLabel = document.getElementById("sa-zoom-label");
  const sourceCode = (document.getElementById("mermaid-source")?.textContent || "").trim();
  const toasts = document.getElementById("sa-toasts");

  function notify(msg, isError = false) {
    const t = document.createElement("div");
    t.className = `toast${isError ? " toast--error" : ""}`;
    t.textContent = msg;
    toasts.appendChild(t);
    setTimeout(() => t.remove(), 3000);
  }

  function applyTransform() {
    viewport.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
    zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
  }

  function fitZoom() {
    const svg = stage.querySelector("svg");
    if (!svg) return;
    const cRect = canvasPane.getBoundingClientRect();
    const sRect = svg.getBoundingClientRect();
    if (!sRect.width || !sRect.height) return;
    const baseW = sRect.width / zoom;
    const baseH = sRect.height / zoom;
    zoom = Math.max(0.3, Math.min(1.5, (cRect.width * 0.86) / baseW, (cRect.height * 0.86) / baseH));
    panX = 0;
    panY = 0;
    applyTransform();
  }

  function buildCleanSvg(svgEl) {
    const clone = svgEl.cloneNode(true);
    clone.querySelectorAll("foreignObject, script").forEach((n) => n.remove());
    let vbX = 0;
    let vbY = 0;
    let w = 1200;
    let h = 600;
    const vb = svgEl.viewBox?.baseVal;
    if (vb && vb.width > 0 && vb.height > 0) {
      vbX = vb.x;
      vbY = vb.y;
      w = Math.ceil(vb.width);
      h = Math.ceil(vb.height);
    } else {
      const box = svgEl.getBBox();
      vbX = box.x - 20;
      vbY = box.y - 20;
      w = Math.ceil(box.width + 40);
      h = Math.ceil(box.height + 40);
      clone.setAttribute("viewBox", `${vbX} ${vbY} ${w} ${h}`);
    }
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
    clone.setAttribute("width", String(w));
    clone.setAttribute("height", String(h));
    clone.removeAttribute("style");
    const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("x", String(vbX));
    bg.setAttribute("y", String(vbY));
    bg.setAttribute("width", "100%");
    bg.setAttribute("height", "100%");
    bg.setAttribute("fill", "#ffffff");
    clone.insertBefore(bg, clone.firstChild);
    return { svgString: new XMLSerializer().serializeToString(clone), width: w, height: h };
  }

  function download(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function renderDiagram() {
    if (typeof window.mermaid === "undefined") {
      notify("No se encontró Mermaid local.", true);
      return;
    }
    window.mermaid.initialize({
      startOnLoad: false,
      theme: "default",
      securityLevel: "strict",
      htmlLabels: false,
      flowchart: { curve: "basis", useMaxWidth: false, htmlLabels: false, padding: 18 },
    });
    const { svg } = await window.mermaid.render("alvea_standalone_svg", sourceCode);
    const doc = new DOMParser().parseFromString(svg, "image/svg+xml");
    const svgEl = doc.documentElement;
    svgEl.querySelectorAll("script, iframe, object, embed, foreignObject").forEach((n) => n.remove());
    [svgEl, ...svgEl.querySelectorAll("*")].forEach((elem) => {
      for (const attr of Array.from(elem.attributes)) {
        const name = attr.name.toLowerCase();
        const val = attr.value.replace(/[\x00-\x20]+/g, "").toLowerCase();
        if (name.startsWith("on") || val.startsWith("javascript:") || val.startsWith("vbscript:") || val.startsWith("data:text/html")) {
          elem.removeAttribute(attr.name);
        }
      }
    });
    stage.replaceChildren(document.importNode(svgEl, true));
    requestAnimationFrame(() => fitZoom());
  }

  // Pan & Zoom interactivo
  canvasPane.addEventListener("wheel", (e) => {
    e.preventDefault();
    zoom = Math.max(0.25, Math.min(3.5, Number((zoom + (e.deltaY < 0 ? 0.12 : -0.12)).toFixed(2))));
    applyTransform();
  }, { passive: false });

  canvasPane.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    isDragging = true;
    dragStartX = e.clientX - panX;
    dragStartY = e.clientY - panY;
    canvasPane.classList.add("dragging");
  });
  window.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    panX = e.clientX - dragStartX;
    panY = e.clientY - dragStartY;
    applyTransform();
  });
  window.addEventListener("mouseup", () => {
    if (isDragging) {
      isDragging = false;
      canvasPane.classList.remove("dragging");
    }
  });

  document.getElementById("sa-zoom-in").addEventListener("click", () => {
    zoom = Math.min(3.5, Number((zoom + 0.2).toFixed(2)));
    applyTransform();
  });
  document.getElementById("sa-zoom-out").addEventListener("click", () => {
    zoom = Math.max(0.25, Number((zoom - 0.2).toFixed(2)));
    applyTransform();
  });
  document.getElementById("sa-zoom-reset").addEventListener("click", () => {
    zoom = 1;
    panX = 0;
    panY = 0;
    applyTransform();
  });
  document.getElementById("sa-zoom-fit").addEventListener("click", fitZoom);

  document.getElementById("sa-copy").addEventListener("click", () => {
    navigator.clipboard
      .writeText(sourceCode)
      .then(() => notify("Código fuente Mermaid copiado exactamente."))
      .catch(() => notify("No se pudo copiar al portapapeles.", true));
  });
  document.getElementById("sa-svg").addEventListener("click", () => {
    const svg = stage.querySelector("svg");
    if (!svg) return;
    const { svgString } = buildCleanSvg(svg);
    download(new Blob([svgString], { type: "image/svg+xml;charset=utf-8" }), "alvea_ejemplo.svg");
    notify("SVG descargado.");
  });
  document.getElementById("sa-png").addEventListener("click", () => {
    const svg = stage.querySelector("svg");
    if (!svg) return;
    const { svgString, width, height } = buildCleanSvg(svg);
    const scale = Math.min(3, 8192 / Math.max(width, height, 1));
    const bytes = new TextEncoder().encode(svgString);
    let bin = "";
    for (let i = 0; i < bytes.length; i += 1) bin += String.fromCharCode(bytes[i]);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(width * scale));
      canvas.height = Math.max(1, Math.round(height * scale));
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => {
        if (blob) {
          download(blob, "alvea_ejemplo_hd.png");
          notify("PNG HD (3x) descargado.");
        } else {
          notify("Error al exportar PNG.", true);
        }
      }, "image/png");
    };
    img.onerror = () => notify("Error al rasterizar SVG a PNG.", true);
    img.src = `data:image/svg+xml;base64,${btoa(bin)}`;
  });

  document.addEventListener("DOMContentLoaded", renderDiagram);
})();
