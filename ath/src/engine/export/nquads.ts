// nquads.ts — the RDF projection (spec §4.1, §11): every line is one quad — subject IRI, predicate IRI, the line's
// payload as a JSON literal, and the attestation as the graph. The round trip (lines → quads → lines, byte-identical)
// is the format's conformance test. The predicate and datatype namespace is a URN: a name, claiming no domain.
import type { JsonObject } from "../../lib/jsonl.ts";
import { canonicalLine, orderKeys } from "../../lib/jsonl.ts";

export const NS = {
  ath: "urn:athenaeum:ns:",
  corpus: "corpus://",
  ledger: "ledger://",
  ontology: "ontology://",
  pass: "pass://",
  op: "op://",
};

const esc = (s: string) => s.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n").replace(/\r/g, "\\r");
const UNESC: Record<string, string> = { n: "\n", r: "\r", '"': '"', "\\": "\\", t: "\t" };
const unesc = (s: string) => s.replace(/\\(.)/g, (_m, c: string) => UNESC[c] ?? `\\${c}`);

export type Tree = "corpus" | "ledger" | "ontology" | "owner";

export function lineToQuad(tree: Tree, id: string, l: JsonObject): string {
  const subject =
    tree === "corpus" || tree === "owner"
      ? `<${NS.corpus}${id}?${encodeURI(String(l.at))}>`
      : tree === "ledger"
        ? `<${NS.ledger}${id}>`
        : `<${NS.ontology}${id}>`;
  const predicate = `<${NS.ath}${String(l.predicate)}>`;
  const payload: JsonObject = {};
  for (const k of orderKeys(l)) if (!["at", "subject", "predicate", "by", "pass"].includes(k)) payload[k] = l[k];
  const object = `"${esc(JSON.stringify(payload))}"^^<${NS.ath}json>`;
  const graph =
    typeof l.pass === "string"
      ? `<${NS.pass}${id}#${l.pass}>`
      : typeof l.by === "string"
        ? `<${NS.op}${encodeURIComponent(l.by)}>`
        : tree === "ontology"
          ? `<${NS.ontology}${id}>`
          : null;
  return `${subject} ${predicate} ${object}${graph ? ` ${graph}` : ""} .`;
}

export function quadToLine(quad: string): { tree: Tree; id: string; line: JsonObject } {
  const m = /^<([^>]+)> <([^>]+)> "((?:[^"\\]|\\.)*)"\^\^<[^>]+>(?: <([^>]+)>)? \.$/.exec(quad.trim());
  if (!m) throw new Error(`not an ath quad: ${quad.slice(0, 120)}`);
  const [, subj, pred, lit, graph] = m;
  const predicate = pred!.slice(NS.ath.length);
  const payload = JSON.parse(unesc(lit!)) as JsonObject;
  let tree: Tree;
  let id: string;
  const line: JsonObject = {};
  if (subj!.startsWith(NS.corpus)) {
    tree = predicate === "inspected" ? "owner" : "corpus";
    const q = subj!.indexOf("?");
    id = subj!.slice(NS.corpus.length, q);
    line.at = decodeURI(subj!.slice(q + 1));
  } else if (subj!.startsWith(NS.ledger)) {
    tree = "ledger";
    id = subj!.slice(NS.ledger.length);
    line.subject = id;
  } else {
    tree = "ontology";
    id = subj!.slice(NS.ontology.length);
    line.subject = id;
  }
  line.predicate = predicate;
  for (const [k, v] of Object.entries(payload)) line[k] = v;
  if (graph?.startsWith(NS.pass)) line.pass = graph.slice(graph.indexOf("#") + 1);
  else if (graph?.startsWith(NS.op)) line.by = decodeURIComponent(graph.slice(NS.op.length));
  return { tree, id, line };
}

export function toNQuads(tree: Tree, id: string, lines: readonly JsonObject[]): string {
  return lines.map((l) => `${lineToQuad(tree, id, l)}\n`).join("");
}

/** Round trip: lines → quads → lines, compared canonically. */
export function roundTrips(tree: Tree, id: string, lines: readonly JsonObject[]): boolean {
  const back = toNQuads(tree, id, lines)
    .split("\n")
    .filter(Boolean)
    .map((q) => quadToLine(q).line);
  return lines.map(canonicalLine).join("\n") === back.map(canonicalLine).join("\n");
}
