// mbox.ts — a mailbox's roster (D-mbox): messages delimited by `From ` lines at the file start or after a blank line
// (mboxrd), each member's bytes un-stuffed (`>From ` → `From `, one `>` removed from every `>+From ` line) and
// hashed over the un-stuffed bytes; members are routed `path=<1-based ordinal>`. Nothing lands on a mailbox: text
// is a member's aspect.
import { blake3Hex } from "@ath/kit/hash.ts";
import { type AttestResult, registerAttester } from "../registry.ts";
import { header, parseHeaders } from "./parse.ts";

const latin1 = new TextDecoder("latin1");
const FROM = [0x46, 0x72, 0x6f, 0x6d, 0x20]; // "From "

function isFromLine(b: Uint8Array, at: number): boolean {
  for (let k = 0; k < FROM.length; k++) if (b[at + k] !== FROM[k]) return false;
  return true;
}

/** The byte offsets of every `From ` separator line. */
export function separators(b: Uint8Array): number[] {
  const out: number[] = [];
  let i = 0;
  let prevBlank = true;
  while (i < b.length) {
    let nl = b.indexOf(0x0a, i);
    if (nl === -1) nl = b.length;
    const lineEnd = nl > i && b[nl - 1] === 0x0d ? nl - 1 : nl;
    if (prevBlank && isFromLine(b, i)) out.push(i);
    prevBlank = lineEnd === i;
    i = nl + 1;
  }
  return out;
}

/** Remove one `>` from every line matching `^>+From `. */
export function unstuff(b: Uint8Array): Uint8Array {
  const out: number[] = [];
  let i = 0;
  let changed = false;
  while (i < b.length) {
    let nl = b.indexOf(0x0a, i);
    nl = nl === -1 ? b.length : nl + 1;
    let j = i;
    while (b[j] === 0x3e) j++;
    if (j > i && isFromLine(b, j)) {
      changed = true;
      for (let k = i + 1; k < nl; k++) out.push(b[k]!);
    } else for (let k = i; k < nl; k++) out.push(b[k]!);
    i = nl;
  }
  return changed ? Uint8Array.from(out) : b;
}

export interface MboxMember {
  path: string;
  bytes: Uint8Array;
  blake3: string;
  message_id: string | null;
}

export async function mboxMembers(b: Uint8Array): Promise<MboxMember[]> {
  const seps = separators(b);
  const out: MboxMember[] = [];
  for (let k = 0; k < seps.length; k++) {
    const sepLine = b.indexOf(0x0a, seps[k]!);
    const start = sepLine === -1 ? b.length : sepLine + 1;
    let end = seps[k + 1] ?? b.length;
    // the blank line before the next separator is the delimiter's, not the message's
    if (k + 1 < seps.length) {
      if (end > start && b[end - 1] === 0x0a) end--;
      if (end > start && b[end - 1] === 0x0d) end--;
    }
    const bytes = unstuff(b.subarray(start, end));
    const headerEnd = (() => {
      const lf = latin1.decode(bytes.subarray(0, 65536)).search(/\r?\n\r?\n/);
      return lf === -1 ? Math.min(bytes.length, 65536) : lf;
    })();
    const message_id = header(parseHeaders(bytes, 0, headerEnd), "Message-ID");
    out.push({ path: String(k + 1), bytes, blake3: await blake3Hex(bytes), message_id });
  }
  return out;
}

export async function attestMbox(bytes: Uint8Array, mime: string): Promise<AttestResult> {
  const members = await mboxMembers(bytes);
  return {
    value: {
      mime,
      bytes: bytes.length,
      messages: members.length,
      members: members.map((m) => ({
        path: m.path,
        bytes: m.bytes.length,
        blake3: m.blake3,
        ...(m.message_id ? { message_id: m.message_id } : {}),
      })),
    },
    members: members.map((m) => ({ path: m.path, bytes: m.bytes, blake3: m.blake3, name: `${m.path}.eml` })),
  };
}

registerAttester("application/mbox", attestMbox);
