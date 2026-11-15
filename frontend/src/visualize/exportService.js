/**
 * frontend/src/visualize/exportService.js
 * Multi-page PDF export via html2canvas & jsPDF (off-screen, landscape 16:9, scale 2),
 * PNG export, and CSV data export.
 */

import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";
import { CANVAS_W, CANVAS_H } from "./constants";

export async function exportElementAsPng(
  element,
  filename = "dashboard.png",
  exportTheme = "current",
  currentTheme = "light"
) {
  if (!element) return;
  element.classList.add("rpt-export-clean");
  const root = element.closest(".rpt-dashboard-root");
  const origTheme = root?.getAttribute("data-theme") || currentTheme;
  const targetTheme = exportTheme === "current" ? origTheme : exportTheme;

  if (root && targetTheme !== origTheme) {
    root.setAttribute("data-theme", targetTheme);
  }

  try {
    const bgColor = targetTheme === "light" ? "#ffffff" : "#09090b";
    const canvas = await html2canvas(element, {
      scale: 2,
      useCORS: true,
      backgroundColor: bgColor,
      logging: false,
    });
    const link = document.createElement("a");
    link.download = filename.endsWith(".png") ? filename : `${filename}.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  } finally {
    element.classList.remove("rpt-export-clean");
    if (root && targetTheme !== origTheme) {
      root.setAttribute("data-theme", origTheme);
    }
  }
}

export async function exportDashboardPdf({
  dashboard,
  datasetFilename = "report",
  onProgress = null,
  canvasRef = null,
  exportTheme = "current",
  currentTheme = "light",
}) {
  const visiblePages = (dashboard?.pages || []).filter((p) => !p.hidden);
  if (visiblePages.length === 0) {
    alert("No visible pages to export.");
    return;
  }

  const root = canvasRef?.current?.closest(".rpt-dashboard-root");
  const origTheme = root?.getAttribute("data-theme") || currentTheme;
  const targetTheme = exportTheme === "current" ? origTheme : exportTheme;

  if (root && targetTheme !== origTheme) {
    root.setAttribute("data-theme", targetTheme);
  }

  const firstPage = visiblePages[0];
  const firstW = firstPage?.size?.w || CANVAS_W;
  const firstH = firstPage?.size?.h || CANVAS_H;

  const pdf = new jsPDF({
    orientation: firstW >= firstH ? "landscape" : "portrait",
    unit: "px",
    format: [firstW, firstH],
    hotfixes: ["px_scaling"],
  });

  const totalPages = visiblePages.length;
  const bgColor = targetTheme === "light" ? "#ffffff" : "#09090b";

  try {
    for (let i = 0; i < totalPages; i++) {
      const page = visiblePages[i];
      const pageW = page.size?.w || CANVAS_W;
      const pageH = page.size?.h || CANVAS_H;
      const orientation = pageW >= pageH ? "landscape" : "portrait";

      if (onProgress) {
        onProgress(`Exporting page ${i + 1} of ${totalPages}: ${page.name}...`);
      }

      // Capture the current canvas if it matches active page, or offscreen
      if (canvasRef && canvasRef.current) {
        canvasRef.current.classList.add("rpt-export-clean");
        try {
          const canvas = await html2canvas(canvasRef.current, {
            scale: 2,
            useCORS: true,
            backgroundColor: bgColor,
            logging: false,
          });

          const imgData = canvas.toDataURL("image/jpeg", 0.95);
          if (i > 0) {
            pdf.addPage([pageW, pageH], orientation);
          }
          pdf.addImage(imgData, "JPEG", 0, 0, pageW, pageH);

          // Add clean page footer
          pdf.setFontSize(10);
          pdf.setTextColor(targetTheme === "light" ? 113 : 161, targetTheme === "light" ? 113 : 161, targetTheme === "light" ? 122 : 170);
          pdf.text(
            `${page.name} | Page ${i + 1} of ${totalPages}`,
            pageW / 2,
            pageH - 12,
            { align: "center" }
          );
        } finally {
          canvasRef.current.classList.remove("rpt-export-clean");
        }
      }
    }

    const cleanFilename = `${(datasetFilename || "dashboard").replace(/\.[^/.]+$/, "")}_dashboard.pdf`;
    pdf.save(cleanFilename);
  } finally {
    if (root && targetTheme !== origTheme) {
      root.setAttribute("data-theme", origTheme);
    }
    if (onProgress) onProgress(null);
  }
}

export function exportDataAsCsv(filename = "data.csv", rows = [], headers = []) {
  if (!rows || rows.length === 0) {
    alert("No data available to export.");
    return;
  }

  const cols = headers.length > 0 ? headers : Object.keys(rows[0] || {});
  const csvLines = [cols.join(",")];

  rows.forEach((r) => {
    const line = cols.map((c) => {
      let val = r[c] !== undefined && r[c] !== null ? String(r[c]) : "";
      if (val.includes(",") || val.includes('"') || val.includes("\n")) {
        val = `"${val.replace(/"/g, '""')}"`;
      }
      return val;
    });
    csvLines.push(line.join(","));
  });

  const blob = new Blob([csvLines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename.endsWith(".csv") ? filename : `${filename}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
