// frames.ts — writes ../frames.pdf, a hand-built four-page PDF that pins the frame a box is normalised in (spec
// §7.3.1, §10.6.3): page 1 plain; page 2 rotated 90°; page 3 with a crop box inside its media box; page 4 a
// visible word over an invisible text layer (render mode 3). Base-14 Helvetica, nothing embedded. Run from the repo
// root: bun testdata/synthetic/gen/frames.ts
import { writeFileSync } from "node:fs";
import { join } from "node:path";

const text = (x: number, y: number, s: string, mode = 0) => `BT /F1 24 Tf ${mode} Tr ${x} ${y} Td (${s}) Tj ET`;
const pages = [
  { box: "/MediaBox [0 0 600 800]", content: text(100, 700, "Plain") },
  { box: "/MediaBox [0 0 600 800] /Rotate 90", content: text(100, 700, "Turned") },
  { box: "/MediaBox [0 0 600 800] /CropBox [100 100 500 700]", content: text(200, 600, "Cropped") },
  { box: "/MediaBox [0 0 600 800]", content: `${text(100, 700, "Shown")}\n${text(100, 400, "Hidden", 3)}` },
];
const objs: string[] = [];
const add = (s: string) => objs.push(s) && objs.length;
const font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
const pagesId = 2 + pages.length * 2;
const kids: number[] = [];
for (const p of pages) {
  const c = add(`<< /Length ${p.content.length} >>\nstream\n${p.content}\nendstream`);
  kids.push(add(`<< /Type /Page /Parent ${pagesId} 0 R ${p.box} /Resources << /Font << /F1 ${font} 0 R >> >> /Contents ${c} 0 R >>`));
}
if (add(`<< /Type /Pages /Kids [${kids.map((k) => `${k} 0 R`).join(" ")}] /Count ${kids.length} >>`) !== pagesId) throw new Error("object order");
const catalog = add(`<< /Type /Catalog /Pages ${pagesId} 0 R >>`);
let out = "%PDF-1.7\n";
const offsets: number[] = [];
objs.forEach((o, i) => {
  offsets.push(out.length);
  out += `${i + 1} 0 obj\n${o}\nendobj\n`;
});
const xref = out.length;
out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n${offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("")}`;
out += `trailer\n<< /Size ${objs.length + 1} /Root ${catalog} 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
writeFileSync(join(import.meta.dir, "..", "frames.pdf"), out);
