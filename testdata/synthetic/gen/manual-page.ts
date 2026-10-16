#!/usr/bin/env bun
// manual-page.ts — the twin of a service-manual page capture from a single-page application: a v52 capture banner,
// a breadcrumb nav (chrome), a repair-page title, topics as <dl> blocks (a <dt> heading with an anchor id, a <dd>
// with an important notice, paragraphs, a legal-numbered procedure list, a bullet list, a specification table with
// term/definition cells, inlined thumbnail images carrying their original src), framework markup noise, and a
// script and style bulk so the remainder is realistic. Fictional equipment, generated prose.
//
//   bun testdata/synthetic/gen/manual-page.ts
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { png } from "./lib/png.ts";
import { int, lcg, paragraph, pick, sentence } from "./lib/rand.ts";

const SYN = join(dirname(Bun.fileURLToPath(import.meta.url)), "..");
const OUT = join(SYN, "pump-service-manual.html");
const r = lcg(31);
const URL = "https://manuals.example.invalid/#/pumps/hl-200/service/impeller-replacement";
const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const b64png = (i: number) => Buffer.from(png(16, 10, (x, y) => [(x * 15 + i * 40) & 255, (y * 25) & 255, 120])).toString("base64");

const topics = [
  { id: "overview", title: "Overview", steps: 0, table: true, notice: "Isolate the pump electrically before any work below the cover." },
  { id: "removal", title: "Impeller removal", steps: 7, table: false, notice: "The retaining nut is left-hand threaded." },
  { id: "inspection", title: "Inspection", steps: 4, table: true, notice: null },
  { id: "installation", title: "Impeller installation", steps: 8, table: false, notice: "Torque the retaining nut in two stages." },
  { id: "specifications", title: "Specifications", steps: 0, table: true, notice: null },
];
const crumbs = ["Pumps", "HL-200", "Service", "Impeller replacement"];
const crumb = (c: string, i: number) =>
  `<li ptooltip="${c}" class="p-element ng-star-inserted" aria-disabled="false" data-pc-section="menuitem"><a class="p-menuitem-link ng-star-inserted" target="_self" href="#/${crumbs.slice(0, i + 1).map((x) => x.toLowerCase().replace(/ /g, "-")).join("/")}" tabindex="0"><span class="p-menuitem-text ng-star-inserted">${c}</span></a></li>${i < crumbs.length - 1 ? '<li class="p-menuitem-separator ng-star-inserted" data-pc-section="separator"><chevronrighticon class="p-element p-icon-wrapper ng-star-inserted"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" class="p-icon" aria-hidden="true"><path d="M5 2l4 5-4 5" fill="currentColor"></path></svg></chevronrighticon></li>' : ""}`;

let fig = 0;
const topic = (tp: (typeof topics)[number]) => {
  const dd: string[] = [];
  if (tp.notice) dd.push(`<div class="important"><p><b>IMPORTANT:</b> <b class="bold">${esc(tp.notice)}</b></p></div>`);
  dd.push(`<p>${esc(paragraph(r, 3))}</p>`);
  if (tp.steps) {
    dd.push(`<ol class="ordered-legal">${Array.from({ length: tp.steps }, (_, i) => `<li class="withspace">${esc(sentence(r))}${i === 2 ? ` <a href="#/pumps/hl-200/service/tools" temp-url="x">See the tool list.</a>` : ""}</li>`).join("")}</ol>`);
    fig++;
    dd.push(
      `<div class="thumbnail-container"><a class="preview-text open-new-tab" id="fig-${fig}"><img class="thumbnail" id="img-${fig}" src="data:image/png;base64,${b64png(fig)}" data-corpus-original-src="https://manuals.example.invalid/assets/figures/hl200-${fig}.png" alt="Figure ${fig}"><i class="app-icon-zoom-in"></i></a><span class="open-new-tab-label">Figure ${fig}. ${esc(sentence(r).replace(/[.?]$/, ""))}</span></div>`,
    );
  }
  dd.push(`<ul class="unordered-bullet">${Array.from({ length: int(r, 2, 4) }, () => `<li><b class="bold">${esc(pick(r, ["Note", "Check", "Tip"]))}:</b> ${esc(sentence(r))}</li>`).join("")}</ul>`);
  if (tp.table) {
    const rows = [
      ["Impeller diameter", `${int(r, 120, 180)} mm`],
      ["Retaining nut torque", `${int(r, 18, 40)} N·m`],
      ["Clearance to volute", `0.${int(r, 2, 9)} mm`],
      ["Shaft seal", pick(r, ["mechanical, carbon/ceramic", "lip seal, nitrile"])],
    ];
    dd.push(`<table class="blltnHdr"><tbody>${rows.map(([k, v]) => `<tr><td class="term" style="width:40%">${k}</td><td class="definition" width="60%" style="">${v}</td></tr>`).join("")}</tbody></table>`);
  }
  if (tp.id === "overview") dd.push(`<div class="notice">${esc(sentence(r))}</div>`);
  return `<dl><dt><a id="${tp.id}"></a>${tp.title}</dt><dd>${dd.join("\n")}</dd></dl>`;
};

const script = `<script>${Array.from({ length: 400 }, (_, i) => `function f${i}(a,b){return (a*${i}+b)%97;}`).join("")}</script>`;
const style = `<style>${Array.from({ length: 300 }, (_, i) => `.ng-${i}{display:block;margin:${i % 13}px;color:#${(i * 71 % 4096).toString(16).padStart(3, "0")}}`).join("")}</style>`;
const html = `<head><meta name="corpus-capture-url" content="${URL}"><meta name="corpus-fetched-at" content="2026-05-20T15:02:11Z"><meta name="corpus-fidelity" content="lean"></head><!DOCTYPE html>
<html lang="en" data-critters-container="">
<head><meta charset="utf-8"><title>Impeller replacement - HL-200 - Manuals</title>${style}</head>
<body class="p-component">
<router-outlet></router-outlet>
<ad-repair-breadcrumb class="ad-repair-breadcrumb"><ad-uib-breadcrumb class="ng-star-inserted"><div class="breadcrumb-container"><p-breadcrumb class="p-element"><nav data-pc-name="breadcrumb" data-pc-section="root" class="ad-uib-breadcrumb p-breadcrumb p-component"><ol class="p-breadcrumb-list" data-pc-section="menu">${crumbs.map(crumb).join("")}</ol></nav></p-breadcrumb></div></ad-uib-breadcrumb></ad-repair-breadcrumb>
<h3 class="repair-page-title ng-star-inserted">Impeller replacement</h3>
<div id="repair-content" class="ng-star-inserted">
${topics.map(topic).join("\n")}
</div>
<router-outlet></router-outlet>
${script}
</body></html>
`;
writeFileSync(OUT, html);
console.log(`wrote ${OUT} (${html.length} chars, ${topics.length} topics)`);
