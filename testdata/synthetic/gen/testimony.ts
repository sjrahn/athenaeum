// testimony.ts — the testimony every synthetic export arrives with, beside it as `<file>.testimony.yaml` (spec §9.2.1),
// in the contract's shape (§9.4): the artifact's full hash as `subject`, the producer that made the export, where
// the bytes came from in the producer's own terms under `source`, and the producer's further keys as it wrote them.
// Fictional accounts and hosts throughout. The generators call `writeTestimony` after writing an artifact; run alone,
// `bun testdata/synthetic/gen/testimony.ts` rewrites every sidecar from the committed bytes.
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { blake3Hex } from "../../../ath/packages/kit/src/hash.ts";

const SYN = join(import.meta.dir, "..");

type V = string | number | boolean | V[] | { [k: string]: V };

export const TESTIMONY: Record<string, { producer: { tool: string; version: string; at: string }; source: Record<string, V>; [k: string]: V }> = {
  "account-confirmation.pdf": {
    "producer": {
      "tool": "banking-document",
      "version": "1",
      "at": "2026-03-20T00:00:00Z"
    },
    "source": {
      "institution": "Example Building Society",
      "document_type": "account-confirmation",
      "account_kind": "current",
      "account_ref": "****5678"
    },
    "via": "export"
  },
  "agent-session.zip": {
    "producer": {
      "tool": "claude-code-session",
      "version": "2.1.0",
      "at": "2026-03-20T11:00:00Z"
    },
    "source": {
      "session_id": "00000000-0000-4000-8000-00000000c0de",
      "host": "lantern",
      "project_dir": "/home/owner/work/harbour",
      "cwd": "/home/owner/work/harbour",
      "claude_code_version": "2.1.0",
      "record_count": 46,
      "message_count": 40,
      "subagent_count": 1,
      "captured_at": "2026-03-20T11:00:00Z",
      "activity_start": "2026-03-20T10:00:00Z",
      "activity_end": "2026-03-20T10:04:33Z"
    },
    "via": "export"
  },
  "card-dump.zip": {
    "producer": {
      "tool": "camera-sd-dump",
      "version": "1",
      "at": "2026-03-02T18:00:00Z"
    },
    "source": {
      "card_uuid": "0000-C0DE",
      "card_filesystem": "exfat",
      "card_capacity_bytes": 128000000000,
      "reader": "usb",
      "copied_at": "2026-03-02T18:00:00Z",
      "copy_method": "rsync",
      "dump_file_count": 9,
      "dump_bytes": 0,
      "excluded": [],
      "already_held": 0,
      "command": "corpus assemble",
      "actor": "owner",
      "redacted": "none"
    },
    "via": "export"
  },
  "chart-printout.pdf": {
    "producer": {
      "tool": "health-record",
      "version": "1",
      "at": "2026-03-05T10:12:00Z"
    },
    "source": {
      "provider": "Quay Medical Practice",
      "practitioner": "Dr B. Calder",
      "system": "ExampleEMR 9",
      "document_type": "chart print-out",
      "printed_at": "2026-03-05T10:12:00Z",
      "covers_from": "2025-09-01",
      "covers_to": "2026-03-01",
      "delivered_via": "in person",
      "actor": "owner",
      "redacted": "none"
    },
    "via": "export"
  },
  "chat-month-bundle.zip": {
    "producer": {
      "tool": "google-chat-export-bundle",
      "version": "1",
      "at": "2026-04-01T03:00:00Z"
    },
    "source": {
      "period": "2026-03",
      "account": "fay.frost@example.invalid",
      "exported_at": "2026-04-01T03:00:00Z",
      "source_export": "takeout-20260401T030000Z-001.zip"
    },
    "via": "export"
  },
  "contact-card.vcf": {
    "producer": {
      "tool": "icloud-contacts-card",
      "version": "1",
      "at": "2026-03-01T00:00:00Z"
    },
    "source": {
      "account": "ada.abbott@example.invalid",
      "exported_at": "2026-03-01"
    },
    "via": "export"
  },
  "design-export.pdf": {
    "producer": {
      "tool": "claude-export",
      "version": "1",
      "at": "2026-03-20T00:00:00Z"
    },
    "source": {
      "surface": "design"
    },
    "via": "export"
  },
  "drive-folder.zip": {
    "producer": {
      "tool": "google-drive-export",
      "version": "2026.03",
      "at": "2026-03-18T16:00:00Z"
    },
    "source": {
      "account": "ada.abbott@example.invalid",
      "folder": "Harbour plans"
    },
    "via": "export",
    "coverage": "the folder, whole",
    "part": "001"
  },
  "facebook-month-bundle.zip": {
    "producer": {
      "tool": "facebook-export-bundle",
      "version": "1",
      "at": "2026-04-02T00:00:00Z"
    },
    "source": {
      "period": "2026-03",
      "account": "eli.hale",
      "exported_at": "2026-04-02",
      "source_export": "facebook-eli.hale-2026-04-02.zip"
    },
    "via": "export"
  },
  "health-export.zip": {
    "producer": {
      "tool": "apple-health-export",
      "version": "1",
      "at": "2026-04-01T07:00:00Z"
    },
    "source": {
      "exported_at": "2026-04-01T07:00:00Z",
      "account": "ada.abbott@example.invalid",
      "device": "Phone 12"
    },
    "via": "export"
  },
  "host-diagnostics.zip": {
    "producer": {
      "tool": "host-diagnostic",
      "version": "1",
      "at": "2026-03-12T09:15:00Z"
    },
    "source": {
      "host": "lantern",
      "system": "unraid 7.0.0",
      "command": "diagnostics",
      "produced_at": "2026-03-12T09:15:00Z",
      "produced_on": "lantern",
      "actor": "owner",
      "redacted": "none"
    },
    "via": "export"
  },
  "instagram-month-bundle.zip": {
    "producer": {
      "tool": "instagram-export-bundle",
      "version": "1",
      "at": "2026-04-02T00:00:00Z"
    },
    "source": {
      "period": "2026-03",
      "account": "eli.judd",
      "exported_at": "2026-04-02",
      "source_export": "instagram-eli.judd-2026-04-02.zip"
    },
    "via": "export"
  },
  "location-history.json": {
    "producer": {
      "tool": "google-timeline-export",
      "version": "1",
      "at": "2026-04-01T00:00:00Z"
    },
    "source": {
      "account": "ada.abbott@example.invalid",
      "device": "Phone 12",
      "exported_at": "2026-04-01"
    },
    "via": "export"
  },
  "mail-month-bundle.zip": {
    "producer": {
      "tool": "proton-mail-export",
      "version": "1",
      "at": "2026-04-03T01:00:00Z"
    },
    "source": {
      "period": "2026-03",
      "account": "fay.frost@proton.example",
      "exported_at": "2026-04-03T01:00:00Z",
      "member_count": 6,
      "sidecar_count": 6,
      "date_axis": "Payload.Time"
    },
    "via": "export"
  },
  "messages-week-bundle.zip": {
    "producer": {
      "tool": "imessage-export-bundle",
      "version": "1",
      "at": "2026-03-30T04:00:00Z"
    },
    "source": {
      "period": "2026-W13",
      "exported_at": "2026-03-30T04:00:00Z",
      "assembled_from": "imessage-exporter 3.0.0 + inliner 1.2"
    },
    "via": "export"
  },
  "orders-delivery.zip": {
    "producer": {
      "tool": "amazon-export",
      "version": "1",
      "at": "2026-03-10T00:00:00Z"
    },
    "source": {
      "category": "Your Orders",
      "delivery": "Request My Data 2026-03-10",
      "exported_at": "2026-03-10",
      "exported_at_basis": "delivery email",
      "account": "harbour.orders@example.invalid"
    },
    "via": "export"
  },
  "owner-statement.md": {
    "producer": {
      "tool": "owner-statement",
      "version": "1",
      "at": "2026-03-12T21:40:00Z"
    },
    "source": {
      "channel": "talk",
      "channel_ref": "2026-03-12-evening",
      "authored_at": "2026-03-12T21:40:00Z",
      "target": "mooring plan",
      "recorded_by": "assistant",
      "transform": "verbatim",
      "redacted": "none"
    },
    "via": "upload"
  },
  "photos-month-bundle.zip": {
    "producer": {
      "tool": "osxphotos-export",
      "version": "1",
      "at": "2026-04-05T02:00:00Z"
    },
    "source": {
      "period": "2026-03",
      "account": "library@example.invalid",
      "exported_at": "2026-04-05T02:00:00Z",
      "coverage": "full library"
    },
    "via": "export"
  },
  "policy-schedule.pdf": {
    "producer": {
      "tool": "insurance-document",
      "version": "1",
      "at": "2026-03-20T00:00:00Z"
    },
    "source": {
      "insurer": "Example Mutual",
      "brand": "Harbour Cover",
      "policy_number": "HC-0000001",
      "line": "home contents",
      "document_type": "schedule",
      "effective_date": "2026-04-01",
      "expiry_date": "2027-03-31"
    },
    "via": "export"
  },
  "profile-year.zip": {
    "producer": {
      "tool": "facebook-profile-year",
      "version": "1",
      "at": "2026-04-02T09:00:00Z"
    },
    "source": {
      "profile": "bo.calder",
      "profile_id": "100000000000001",
      "profile_name": "Bo Calder",
      "year": 2026,
      "captured_at": "2026-04-02T09:00:00Z",
      "harvester": "harvest 1.4",
      "converter": "convert 1.4",
      "redacted": "none",
      "counts": {
        "posts": 6,
        "comments": 5,
        "photos": 3,
        "videos": 1
      },
      "short": false
    },
    "via": "export"
  },
  "quay-messages.html": {
    "producer": {
      "tool": "imessage-export",
      "version": "3.0.0",
      "at": "2026-04-01T06:00:00Z"
    },
    "source": {
      "schema": "imessage-export",
      "handle": "+44 7700 900456",
      "period": "2026-03"
    },
    "via": "export",
    "fetched_at": "2026-04-01T06:00:00Z",
    "snapshot_engine": "imessage-exporter 3.0.0"
  },
  "rides-export.zip": {
    "producer": {
      "tool": "uber-export",
      "version": "1",
      "at": "2026-03-20T00:00:00Z"
    },
    "source": {
      "request_id": "00000000-0000-4000-8000-00000000c0de",
      "account": "ada.abbott@example.invalid"
    },
    "via": "export"
  },
  "sms-2026-03.ndjson": {
    "producer": {
      "tool": "sms-backup",
      "version": "1",
      "at": "2026-03-20T00:00:00Z"
    },
    "source": {
      "contact_name": "Bo Calder",
      "handle": "+44 7700 900456",
      "period": "2026-03"
    },
    "via": "export"
  },
  "statement-2026-03.pdf": {
    "producer": {
      "tool": "bank-statement",
      "version": "1",
      "at": "2026-03-31T00:00:00Z"
    },
    "source": {
      "institution": "Example Building Society",
      "product": "Everyday account",
      "account_ref": "****5678",
      "account_kind": "current",
      "statement_date": "2026-03-31",
      "coverage": "2026-03"
    },
    "via": "export"
  },
  "statements-year.zip": {
    "producer": {
      "tool": "bank-statement",
      "version": "1",
      "at": "2026-03-20T00:00:00Z"
    },
    "source": {
      "institution": "Example Building Society",
      "product": "Everyday account",
      "account_ref": "****5678",
      "account_kind": "current",
      "statement_date": "monthly",
      "coverage": 2025
    },
    "via": "export"
  },
  "takeout-slice.zip": {
    "producer": {
      "tool": "google-takeout",
      "version": "1",
      "at": "2026-04-01T03:00:00Z"
    },
    "source": {
      "account": "ada.abbott@example.invalid",
      "exported_at": "2026-04-01T03:00:00Z",
      "services": [
        "Fit",
        "Contacts",
        "Maps",
        "Keep",
        "Calendar",
        "Saved"
      ],
      "part": "001",
      "job": "takeout-20260401T030000Z"
    },
    "via": "export"
  },
  "tax-slip-2025.pdf": {
    "producer": {
      "tool": "tax-slip",
      "version": "1",
      "at": "2026-03-02T00:00:00Z"
    },
    "source": {
      "slip_type": "remuneration",
      "tax_year": 2025,
      "issuer": "Harbour Stores Ltd",
      "slip_status": "original",
      "as_of": "2026-03-02"
    },
    "via": "export"
  },
  "threads-month-bundle.zip": {
    "producer": {
      "tool": "threads-export-bundle",
      "version": "1",
      "at": "2026-04-02T00:00:00Z"
    },
    "source": {
      "period": "2026-03",
      "account": "eli.lowe",
      "exported_at": "2026-04-02",
      "source_export": "threads-eli.lowe-2026-04-02.zip"
    },
    "via": "export"
  },
  "vault-subtree.zip": {
    "producer": {
      "tool": "obsidian-vault",
      "version": "1",
      "at": "2026-03-14T20:00:00Z"
    },
    "source": {
      "vault_name": "Harbour",
      "vault_root": "~/Documents/Harbour",
      "subtree": "/",
      "host": "lantern",
      "exported_at": "2026-03-14T20:00:00Z",
      "note_count": 7,
      "excluded": [
        ".trash"
      ],
      "command": "corpus assemble",
      "actor": "owner",
      "redacted": "none"
    },
    "via": "export"
  },
  "vendor-share.zip": {
    "producer": {
      "tool": "vendor-download",
      "version": "1",
      "at": "2026-02-02T11:00:00Z"
    },
    "source": {
      "vendor": "Example Boards",
      "category": "HL series downloads",
      "share_cid": "00000000c0de",
      "retrieved_at": "2026-02-02T11:00:00Z"
    },
    "via": "export"
  }
};

const KEYWORD = /^(true|false|null|yes|no|on|off|~)$/i;
const scalar = (v: V): string =>
  typeof v !== "string"
    ? String(v)
    : /^[A-Za-z][A-Za-z0-9 _.@/+:,-]*$/.test(v) && !/: |:$| $/.test(v) && !KEYWORD.test(v)
      ? v
      : JSON.stringify(v);
const emit = (o: Record<string, V>, ind = ""): string =>
  Object.entries(o)
    .map(([k, v]) =>
      Array.isArray(v)
        ? `${ind}${k}: [${v.map(scalar).join(", ")}]\n`
        : v && typeof v === "object"
          ? `${ind}${k}:\n${emit(v, `${ind}  `)}`
          : `${ind}${k}: ${scalar(v)}\n`,
    )
    .join("");

/** Write `<name>.testimony.yaml` beside the committed artifact `<name>`, about its bytes as they now are. */
export async function writeTestimony(name: string): Promise<void> {
  const t = TESTIMONY[name];
  if (!t) throw new Error(`no testimony declared for ${name}`);
  const subject = await blake3Hex(new Uint8Array(readFileSync(join(SYN, name))));
  const { producer, source, ...rest } = t;
  writeFileSync(join(SYN, `${name}.testimony.yaml`), emit({ subject: `b3:${subject}`, producer, source, ...rest }));
}

if (import.meta.main) for (const name of Object.keys(TESTIMONY)) await writeTestimony(name);
