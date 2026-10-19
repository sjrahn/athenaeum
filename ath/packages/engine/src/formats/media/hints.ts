// hints.ts — the hints over a recording (spec §10.6.2). `media.subtitles@1`: candidate regions `t=a,b` with the text of
// an embedded subtitle track (3GPP timed text, WebVTT samples). `audio.speech@1`: candidate regions with the speech a
// recogniser bound on the host heard (§5.6 `host.yaml`); with none bound, there is no hint. Neither is bound or stored.
import { registerOp, type Unit } from "../ops.ts";
import { type Box, boxes, child, children, str4, top, u16, u32, u64, version } from "./bmff.ts";

/** A recogniser the host binds: given the bytes and their mime, the regions it heard speech in. */
export type Recogniser = (bytes: Uint8Array, mime: string) => Promise<{ start: number; end: number; text: string }[]>;
let recogniser: Recogniser | null = null;
export const bindRecogniser = (r: Recogniser | null) => {
  recogniser = r;
};

const sec = (x: number) => Math.round(x * 1000) / 1000;

/** Every subtitle sample of every text track: its time span and its text. */
function subtitleUnits(b: Uint8Array): Unit[] {
  const moov = top(b, "moov");
  if (!moov) return [];
  const out: Unit[] = [];
  for (const trak of children(b, moov, "trak")) {
    const mdia = child(b, trak, "mdia");
    const hdlr = child(b, mdia, "hdlr");
    const mdhd = child(b, mdia, "mdhd");
    const stbl = child(b, child(b, mdia, "minf"), "stbl");
    if (!hdlr || !mdhd || !stbl || !["text", "sbtl", "subt"].includes(str4(b, hdlr.body + 8))) continue;
    const scale = version(b, mdhd) === 1 ? u32(b, mdhd.body + 20) : u32(b, mdhd.body + 12);
    const stsd = child(b, stbl, "stsd");
    const fourcc = stsd ? (boxes(b, stsd.body + 8, stsd.end)[0]?.type ?? "") : "";
    const stts = child(b, stbl, "stts");
    const stsz = child(b, stbl, "stsz");
    const stsc = child(b, stbl, "stsc");
    const stco = child(b, stbl, "stco") ?? child(b, stbl, "co64");
    if (!stts || !stsz || !stsc || !stco || !scale) continue;
    const deltas: number[] = [];
    for (let i = 0, n = u32(b, stts.body + 4); i < n; i++)
      for (let k = 0, c = u32(b, stts.body + 8 + 8 * i); k < c; k++) deltas.push(u32(b, stts.body + 12 + 8 * i));
    const fixed = u32(b, stsz.body + 4);
    const count = u32(b, stsz.body + 8);
    const size = (i: number) => (fixed ? fixed : u32(b, stsz.body + 12 + 4 * i));
    const runs: { first: number; per: number }[] = [];
    for (let i = 0, n = u32(b, stsc.body + 4); i < n; i++)
      runs.push({ first: u32(b, stsc.body + 8 + 12 * i), per: u32(b, stsc.body + 12 + 12 * i) });
    let s = 0;
    let t = 0;
    for (let c = 1, chunks = u32(b, stco.body + 4); c <= chunks && s < count; c++) {
      let per = 0;
      for (const r of runs) if (r.first <= c) per = r.per;
      let off = stco.type === "co64" ? u64(b, stco.body + 8 + 8 * (c - 1)) : u32(b, stco.body + 8 + 4 * (c - 1));
      for (let k = 0; k < per && s < count; k++, s++) {
        const n = size(s);
        const d = deltas[s] ?? 0;
        let text = "";
        if (fourcc === "tx3g" || fourcc === "text") text = new TextDecoder().decode(b.subarray(off + 2, off + 2 + u16(b, off)));
        else if (fourcc === "wvtt") {
          const payl = boxes(b, off, off + n).flatMap((cue) => (cue.type === "vttc" ? [child(b, cue as Box, "payl")] : []));
          text = payl.map((p) => (p ? new TextDecoder().decode(b.subarray(p.body, p.end)) : "")).join("\n");
        }
        if (text.trim()) out.push({ text, at: `t=${sec(t / scale)},${sec((t + d) / scale)}` });
        off += n;
        t += d;
      }
    }
  }
  return out;
}

const within = (u: Unit, r: { t?: readonly [number, number]; whole?: true }) => {
  if (r.whole || !r.t) return true;
  const [a, b] = u.at.slice(2).split(",").map(Number) as [number, number];
  return a >= r.t[0] && b <= r.t[1];
};

registerOp<Unit[]>({
  name: "media.subtitles@1",
  kind: "hint",
  family: "media",
  parse: (bytes) => subtitleUnits(bytes),
  hint: (units, r) => {
    if (r.path !== undefined || (!r.whole && !r.t)) return null;
    const us = units.filter((u) => within(u, r));
    return us.length ? { text: us.map((u) => u.text).join("\n"), units: us } : null;
  },
});

registerOp<{ bytes: Uint8Array }>({
  name: "audio.speech@1",
  kind: "hint",
  family: "media",
  parse: (bytes) => ({ bytes }),
  hint: async (d, r) => {
    if (!recogniser || r.path !== undefined || (!r.whole && !r.t)) return null;
    const heard = await recogniser(d.bytes, "");
    const units = heard.map((h) => ({ text: h.text, at: `t=${sec(h.start)},${sec(h.end)}` })).filter((u) => within(u, r));
    return units.length ? { text: units.map((u) => u.text).join("\n"), units } : null;
  },
});
