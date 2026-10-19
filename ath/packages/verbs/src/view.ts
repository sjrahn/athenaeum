// view.ts — what a verb sees of an artifact: its record across the chain, its format and class, its shape by
// classification (§11.5), and its tree — derived from the parse through the shape on a structured artifact (§11.7),
// stored on a rendered one (§8.4), proposed from the shape and the hints on a rendered one that has none (§11.7.5) —
// and its chrome by the declared rules (§8.4.6).
import type { Resolved } from "@ath/custody";
import { type Format, formatOf, intrinsicsOf } from "@ath/engine/formats/index.ts";
import { allPages } from "@ath/engine/formats/pdf/words.ts";
import { sniffMime } from "@ath/engine/formats/sniff.ts";
import { type ContainerRef, containersIndex, type Instance, recordView } from "@ath/engine/instance/instance.ts";
import type { RecordDoc, Scope } from "@ath/engine/record/document.ts";
import { selectParse } from "@ath/engine/select/select.ts";
import { type ChromeRun, chromeOf, type DScope, deriveTree } from "@ath/engine/structure/derive.ts";
import { type Classification, classify } from "@ath/engine/vocab/classify.ts";
import { all, type LoadedVocabulary, loadVocabulary, refinesChain } from "@ath/engine/vocab/load.ts";

type J = Record<string, unknown>;

export interface View {
  hash: string;
  record: RecordDoc | null;
  holder: Instance | null;
  intrinsics: J;
  mime: string;
  format: Format;
  shape: Classification;
  /** `derived` on a structured artifact; `stored` once a rendered record is formed; `proposed` from the shape before. */
  tree: { kind: "derived" | "stored" | "proposed" | "none"; scopes: (DScope | Scope)[] };
  chrome: ChromeRun[];
}

export interface Viewer {
  vocab: LoadedVocabulary;
  containers: Map<string, ContainerRef[]>;
  view(hash: string): Promise<View>;
  shapeOf(hash: string): Promise<string | null>;
}

export function viewer(inst: Instance, resolve: (h: string) => Promise<Resolved>): Viewer {
  const vocab = loadVocabulary(inst);
  const v = vocab.vocab;
  const containers = containersIndex(inst);
  const bytesMemo = new Map<string, Promise<Uint8Array | null>>();
  const bytes = (h: string) => {
    let p = bytesMemo.get(h);
    if (!p) {
      p = resolve(h).then(
        (r) => r.bytes,
        () => null,
      );
      bytesMemo.set(h, p);
    }
    return p;
  };
  const shapes = new Map<string, Promise<Classification>>();
  const intrinsicsMemo = new Map<string, Promise<J>>();
  const intrinsicsFor = (h: string): Promise<J> => {
    let p = intrinsicsMemo.get(h);
    if (!p) {
      p = (async () => {
        const r = recordView(inst, h)?.record.intrinsics;
        if (r) return r;
        const b = await bytes(h);
        if (!b) return { mime: "application/octet-stream" };
        return (await intrinsicsOf(b, sniffMime(b, containers.get(h)?.[0]?.path.split("/").pop()))).value;
      })();
      intrinsicsMemo.set(h, p);
    }
    return p;
  };
  const classOf = (h: string): Promise<Classification> => {
    let p = shapes.get(h);
    if (!p) {
      p = (async () => {
        const rec = recordView(inst, h)?.record ?? null;
        const intr = await intrinsicsFor(h);
        return classify(
          v,
          {
            mime: String(intr.mime),
            intrinsics: intr,
            origins: rec?.origins ?? [],
            within: containers.get(h) ?? [],
            bytes: () => bytes(h),
            shapeOf: async (c) => (await classOf(c)).shape,
          },
          rec?.shape,
        );
      })();
      shapes.set(h, p);
    }
    return p;
  };
  return {
    vocab,
    containers,
    shapeOf: async (h) => (await classOf(h)).shape,
    async view(hash) {
      const rv = recordView(inst, hash);
      const intrinsics = await intrinsicsFor(hash);
      const mime = String(intrinsics.mime);
      const format = formatOf(mime);
      const shape = await classOf(hash);
      const record = rv?.record ?? null;
      let tree: View["tree"] = { kind: "none", scopes: [] };
      let chrome: ChromeRun[] = [];
      const b = await bytes(hash);
      const parse = b ? selectParse(b, mime, (intrinsics.constituents as { path: string }[] | undefined) ?? []) : null;
      if (format.class === "structured" && shape.shape && b)
        tree = { kind: "derived", scopes: deriveTree(v, shape.shape, mime, b, parse, intrinsics) };
      else if (record?.scopes) tree = { kind: "stored", scopes: record.scopes };
      else if (format.class === "rendered" && shape.shape && b) {
        const proposed = deriveTree(v, shape.shape, mime, b, parse, intrinsics);
        if (proposed.length) tree = { kind: "proposed", scopes: proposed };
      }
      const rules = [
        ...(shape.shape ? refinesChain(v, "shapes", shape.shape).flatMap((s) => all(v.shapes.get(s), "chrome") as J[]) : []),
        ...(record?.chrome ?? []),
      ];
      if (rules.length && b)
        chrome = chromeOf(rules, parse, mime === "application/pdf" && rules.some((r) => r.repeats) ? await allPages(b) : null);
      return { hash, record, holder: rv?.holder ?? null, intrinsics, mime, format, shape, tree, chrome };
    },
  };
}
