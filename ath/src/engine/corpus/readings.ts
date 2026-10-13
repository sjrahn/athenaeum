// readings.ts — a reading's revision (D-rev): `b3:` + 16 hex of BLAKE3 over the body, a string as UTF-8, anything
// else as compact JSON. Stamping and checking stored reads_as lines.
import { bodyRev } from "../../lib/hash.ts";
import type { JsonObject } from "../../lib/jsonl.ts";

export { bodyRev };

/** Fill in `rev` where absent; report where a given rev does not match its body. */
export async function stampRevisions(
  lines: JsonObject[],
): Promise<{ stamped: number; mismatched: { at: string; given: string; computed: string }[] }> {
  let stamped = 0;
  const mismatched: { at: string; given: string; computed: string }[] = [];
  for (const l of lines) {
    if (l.predicate !== "reads_as") continue;
    const computed = await bodyRev(l.body);
    if (l.rev === undefined) {
      l.rev = computed;
      stamped++;
    } else if (l.rev !== computed) mismatched.push({ at: String(l.at), given: String(l.rev), computed });
  }
  return { stamped, mismatched };
}
