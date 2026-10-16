// index.ts — importing this module registers every attester (by mime) and every derivation op (by name); `attest`
// runs the right attester for a mime, and `opFor` is how the ontology's `derivation` line reaches its op.
import { sha256Hex } from "../../lib/hash.ts";
import "./csv/attest.ts";
import "./csv/parse.ts";
import "./epub/attest.ts";
import "./html/attest.ts";
import "./html/text.ts";
import "./image/headers.ts";
import "./mail/attest.ts";
import "./mail/mbox.ts";
import "./mail/text.ts";
import "./pdf/attest.ts";
import "./pdf/words.ts";
import "./zip/roster.ts";
import { type AttestResult, attesterFor } from "./registry.ts";

export { argProblem, type DerivationOp, type Family, formKey, INGEST_OP, opFor, opNames } from "./registry.ts";

/** The attestation for bytes of a mime; unknown mimes attest mime, size and sha256 only. */
export async function attest(bytes: Uint8Array, mime: string): Promise<AttestResult> {
  const fn = attesterFor(mime);
  if (fn) return fn(bytes, mime);
  return { value: { mime, bytes: bytes.length, sha256: sha256Hex(bytes) } };
}
