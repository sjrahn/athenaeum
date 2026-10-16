#!/usr/bin/env bun
// bundles.ts — the twins of the export bundles and the conversation exports inside them, one layout per function:
//   meta     facebook / instagram / threads month slices (`your_<app>_activity/messages/inbox/<thread>/message_1.json`
//            beside photos/ gifs/ videos/ audio/, activity indexes, story media) and the standalone `message_1.json`
//   gchat    a Google Chat month slice (`Groups/<space>/messages.json` + `group_info.json` + attachments) and the
//            standalone `messages.json`
//   imessage a week of iMessage conversation pages (lib: conversation-page.ts)
//   proton   a Proton Mail export month (`<id>.eml` + `<id>.metadata.json` pairs)
//   photos   a photo-library period batch (originals, sidecar JSON, an edited render, a clip)
// Every bundle gets a `.capture.yaml` in its origin's shape. Fictional accounts; generated chatter; rasters from
// lib/png.ts, the gif and mp4 from the committed synthetic files, HEIC/JPG/MOV from heif-enc, ImageMagick, ffmpeg.
//
//   bun testdata/synthetic/gen/bundles.ts [--only meta,gchat,imessage,proton,photos]
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { conversationPage } from "./conversation-page.ts";
import { qp } from "./mailing.ts";
import { png } from "./lib/png.ts";
import { FIRST, LAST, int, lcg, pick, sentence } from "./lib/rand.ts";
import { dosStamp, zip, type ZipEntry } from "./lib/zip.ts";

const HERE = dirname(Bun.fileURLToPath(import.meta.url));
const SYN = join(HERE, "..");
const TMP = join(process.env.CLAUDE_JOB_DIR ?? "/tmp", "tmp", "bundles-gen");
const e = (s: string) => new TextEncoder().encode(s);
const out = (name: string, bytes: Uint8Array | string) => {
  writeFileSync(join(SYN, name), bytes);
  console.log(`wrote ${name}${typeof bytes === "string" ? "" : ` (${bytes.length} bytes)`}`);
};
const sidecar = (name: string, body: string) => writeFileSync(join(SYN, `${name}.capture.yaml`), `# provenance of a local export, as the producer leaves it beside the bytes (D-sidecar)\n${body}`);
const run = (cmd: string[]) => {
  const r = Bun.spawnSync(cmd, { stdout: "pipe", stderr: "pipe" });
  if (r.exitCode !== 0) throw new Error(`${cmd[0]}: ${r.stderr.toString()}`);
};
const GIF = new Uint8Array(readFileSync(join(SYN, "synthetic-image.gif")));
const MP4 = new Uint8Array(readFileSync(join(SYN, "countdown.mp4")));
const name = (r: () => number) => `${pick(r, FIRST)} ${pick(r, LAST)}`;
const dos = (d: number) => dosStamp(2026, 3, d, 10, 0, 0);

// ── Meta: facebook, instagram, threads ──────────────────────────────────────────────────────────────────────────────
function metaThread(r: () => number, app: "facebook" | "instagram" | "threads", slug: string, me: string, them: string[], withMedia: boolean) {
  const participants = [...them, me].map((n) => ({ name: n }));
  const messages: Record<string, unknown>[] = [];
  let t = Date.UTC(2026, 2, 28, 18, 0, 0);
  const media: ZipEntry[] = [];
  const base = app === "facebook" ? `your_facebook_activity/messages/inbox/${slug}` : app === "instagram" ? `your_instagram_activity/messages/inbox/${slug}` : `messages/inbox/${slug}`;
  for (let i = 0; i < 30; i++) {
    t -= int(r, 60, 20000) * 1000;
    const sender = i % 3 === 0 ? me : pick(r, them);
    const m: Record<string, unknown> = { sender_name: sender, timestamp_ms: t, content: sentence(r), is_geoblocked_for_viewer: false };
    if (withMedia && i % 7 === 2) {
      const p = `${base}/photos/${t}_${int(r, 1000000, 9999999)}.jpg`;
      media.push({ path: p, bytes: png(8, 8, (x, y) => [x * 30, y * 30, i * 8]), method: 0, dos: dos(28) });
      m.photos = [{ uri: p, creation_timestamp: Math.floor(t / 1000) }];
      delete m.content;
    } else if (withMedia && i % 11 === 5) {
      const p = `${base}/gifs/${t}.gif`;
      media.push({ path: p, bytes: GIF, method: 0, dos: dos(28) });
      m.gifs = [{ uri: p }];
      delete m.content;
    } else if (withMedia && i === 17 && app !== "threads") {
      const p = `${base}/videos/${t}.mp4`;
      media.push({ path: p, bytes: MP4, method: 0, dos: dos(28) });
      m.videos = [{ uri: p, creation_timestamp: Math.floor(t / 1000) }];
      delete m.content;
    }
    if (i % 5 === 1) m.reactions = [{ reaction: "ð\u009f\u0091\u008d", actor: pick(r, [...them, me]) }];
    messages.push(m);
  }
  const doc = {
    participants,
    messages,
    title: them.length > 1 ? "Quay crew" : them[0],
    is_still_participant: true,
    thread_path: `inbox/${slug}`,
    magic_words: [],
    ...(app === "threads" ? {} : { joinable_mode: { mode: 1, link: "" } }),
  };
  return { json: e(`${JSON.stringify(doc, null, 2)}\n`), media, base };
}

function meta(app: "facebook" | "instagram" | "threads") {
  const r = lcg(app === "facebook" ? 1 : app === "instagram" ? 2 : 3);
  const me = name(r);
  const threads = [
    { slug: `quaycrew_${int(r, 1e15, 9e15)}`, them: [name(r), name(r)] },
    { slug: `${pick(r, FIRST).toLowerCase()}${pick(r, LAST).toLowerCase()}_${int(r, 1e15, 9e15)}`, them: [name(r)] },
    { slug: `${pick(r, FIRST).toLowerCase()}${pick(r, LAST).toLowerCase()}_${int(r, 1e15, 9e15)}`, them: [name(r)] },
  ];
  const entries: ZipEntry[] = [];
  let standalone: Uint8Array | null = null;
  for (const [i, th] of threads.entries()) {
    const t = metaThread(r, app, th.slug, me, th.them, true);
    entries.push({ path: `${t.base}/message_1.json`, bytes: t.json, dos: dos(28) }, ...t.media);
    if (i === 0) standalone = metaThread(lcg(99), app, th.slug, me, th.them, false).json;
  }
  if (app === "facebook") {
    entries.push({ path: "your_facebook_activity/messages/filtered_threads/unknown_123456789/message_1.json", bytes: metaThread(r, app, "unknown_123456789", me, ["Facebook User"], false).json, dos: dos(28) });
    entries.push({ path: "your_facebook_activity/events/your_event_responses.json", bytes: e(`${JSON.stringify({ event_responses_v2: { events_joined: [{ name: "Harbour clean-up", start_timestamp: 1774000000, end_timestamp: 1774010000 }] } }, null, 2)}\n`), dos: dos(28) });
    entries.push({ path: "your_facebook_activity/posts/album/0.json", bytes: e(`${JSON.stringify({ name: "Timeline photos", photos: [{ uri: "your_facebook_activity/posts/media/your_posts/1.jpg", creation_timestamp: 1774000000 }], cover_photo: {}, last_modified_timestamp: 1774000000, description: "" }, null, 2)}\n`), dos: dos(28) });
    entries.push({ path: "your_facebook_activity/posts/media/your_posts/1.jpg", bytes: png(10, 10, (x, y) => [x * 20, 200, y * 20]), method: 0, dos: dos(28) });
  } else if (app === "instagram") {
    entries.push({ path: "your_instagram_activity/media/stories.json", bytes: e(`${JSON.stringify({ ig_stories: [{ uri: "media/stories/202603/1774000000.mp4", creation_timestamp: 1774000000, title: "" }] }, null, 2)}\n`), dos: dos(28) });
    entries.push({ path: "media/stories/202603/1774000000.mp4", bytes: MP4, method: 0, dos: dos(28) });
    entries.push({ path: "media/posts/202603/1774000001.jpg", bytes: png(10, 10, (x, y) => [200, x * 20, y * 20]), method: 0, dos: dos(28) });
  } else {
    entries.push({ path: "threads/threads_and_replies.json", bytes: e(`${JSON.stringify({ text_post_app_text_posts: [{ media: [{ title: sentence(r), creation_timestamp: 1774000000 }] }] }, null, 2)}\n`), dos: dos(28) });
    entries.push({ path: "settings/privacy_settings.json", bytes: e(`${JSON.stringify({ text_post_app_privacy_settings: [{ string_map_data: { "Private account": { value: "false" } } }] }, null, 2)}\n`), dos: dos(28) });
  }
  const acct = `${me.toLowerCase().replace(" ", ".")}`;
  out(`${app}-month-bundle.zip`, zip(entries));
  sidecar(`${app}-month-bundle.zip`, `origin: ${app}-export-bundle\nvia: export\norigin_fields:\n  period: "2026-03"\n  account: ${acct}\n  exported_at: "2026-04-02"\n  source_export: ${app}-${acct}-2026-04-02.zip\n`);
  out(`${app}-thread.json`, standalone!);
}

// ── Google Chat ─────────────────────────────────────────────────────────────────────────────────────────────────────
function gchat() {
  const r = lcg(44);
  const people = Array.from({ length: 4 }, () => name(r));
  const email = (n: string) => `${n.toLowerCase().replace(" ", ".")}@example.invalid`;
  const space = (id: string, members: string[], n: number, withAttachment: boolean) => {
    const messages: Record<string, unknown>[] = [];
    let t = Date.UTC(2026, 2, 1, 8, 0, 0);
    const files: ZipEntry[] = [];
    for (let i = 0; i < n; i++) {
      t += int(r, 30, 7200) * 1000;
      const who = pick(r, members);
      const d = new Date(t);
      const m: Record<string, unknown> = {
        creator: { name: who, email: email(who), user_type: "Human" },
        created_date: `${["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][d.getUTCDay()]}, ${d.toLocaleString("en-US", { month: "long", timeZone: "UTC" })} ${d.getUTCDate()}, ${d.getUTCFullYear()} at ${d.toLocaleTimeString("en-US", { timeZone: "UTC" })} UTC`,
        text: sentence(r),
        topic_id: `topic_${id}_${Math.floor(i / 6)}`,
        message_id: `msg_${id}_${i}`,
      };
      if (withAttachment && i === 9) {
        const fn = `tide-table-${i}.png`;
        files.push({ path: `Groups/${id}/${fn}`, bytes: png(12, 8, (x, y) => [x * 20, y * 30, 60]), method: 0, dos: dos(15) });
        m.attached_files = [{ original_name: fn, export_name: fn }];
        delete m.text;
      }
      messages.push(m);
    }
    return { messages: e(`${JSON.stringify({ messages }, null, 2)}\n`), info: e(`${JSON.stringify({ members: members.map((n) => ({ name: n, email: email(n), user_type: "Human" })), ...(members.length > 2 ? { name: "Quay crew" } : {}) }, null, 2)}\n`), files };
  };
  const dm = space("DM 2b3c4d5e6f7a8b9c", [people[0]!, people[1]!], 24, true);
  const sp = space("Space AAAAx1y2z3w", people, 40, false);
  const entries: ZipEntry[] = [
    { path: "Groups/DM 2b3c4d5e6f7a8b9c/messages.json", bytes: dm.messages, dos: dos(31) },
    { path: "Groups/DM 2b3c4d5e6f7a8b9c/group_info.json", bytes: dm.info, dos: dos(31) },
    ...dm.files,
    { path: "Groups/Space AAAAx1y2z3w/messages.json", bytes: sp.messages, dos: dos(31) },
    { path: "Groups/Space AAAAx1y2z3w/group_info.json", bytes: sp.info, dos: dos(31) },
  ];
  out("chat-month-bundle.zip", zip(entries));
  sidecar("chat-month-bundle.zip", `origin: google-chat-export-bundle\nvia: export\norigin_fields:\n  period: "2026-03"\n  account: ${email(people[0]!)}\n  exported_at: "2026-04-01T03:00:00Z"\n  source_export: takeout-20260401T030000Z-001.zip\n`);
  out("chat-space.json", space("Space BBBBq9r8s7t", people.slice(0, 3), 36, false).messages); // distinct bytes from the bundle's
}

// ── iMessage week bundle ────────────────────────────────────────────────────────────────────────────────────────────
function imessage() {
  const r = lcg(12);
  const entries: ZipEntry[] = [];
  for (let i = 0; i < 4; i++) {
    const handle = i === 3 ? "Quay crew" : `+44 7700 9${String(int(r, 10000, 99999))}`;
    entries.push({ path: `${handle}.html`, bytes: e(conversationPage(handle, name(r), "2026-03", 100 + i, 12 + i * 6)), dos: dos(29) });
  }
  out("messages-week-bundle.zip", zip(entries));
  sidecar("messages-week-bundle.zip", `origin: imessage-export-bundle\nvia: export\norigin_fields:\n  period: 2026-W13\n  exported_at: "2026-03-30T04:00:00Z"\n  assembled_from: imessage-exporter 3.0.0 + inliner 1.2\n`);
}

// ── Proton Mail export month ────────────────────────────────────────────────────────────────────────────────────────
function proton() {
  const r = lcg(66);
  const me = name(r);
  const entries: ZipEntry[] = [];
  for (let i = 0; i < 6; i++) {
    const id = Buffer.from(`proton-twin-${i}-${int(r, 1e9, 9e9)}`).toString("base64").replace(/\+/g, "-").replace(/\//g, "_");
    const from = name(r);
    const t = Date.UTC(2026, 2, 1 + i * 4, 10 + i, 7, 3);
    const subject = sentence(r).replace(/[.?]$/, "");
    const body = `${sentence(r)}\n\n${sentence(r)}\n\n-- \n${from}\n`;
    const eml = [
      `From: ${from} <${from.toLowerCase().replace(" ", ".")}@example.invalid>`,
      `To: ${me} <${me.toLowerCase().replace(" ", ".")}@proton.example>`,
      `Subject: ${subject}`,
      `Date: ${new Date(t).toUTCString().replace("GMT", "+0000")}`,
      `Message-ID: <${id}@example.invalid>`,
      "MIME-Version: 1.0",
      i === 2 ? 'Content-Type: multipart/mixed; boundary="pm-twin-0002"' : 'Content-Type: text/plain; charset="utf-8"',
      i === 2 ? "" : "Content-Transfer-Encoding: quoted-printable",
      "",
      ...(i === 2
        ? ["--pm-twin-0002", 'Content-Type: text/plain; charset="utf-8"', "Content-Transfer-Encoding: quoted-printable", "", qp(body), "--pm-twin-0002", 'Content-Type: image/png; name="chart.png"', 'Content-Disposition: attachment; filename="chart.png"', "Content-Transfer-Encoding: base64", "", Buffer.from(png(6, 6, (x, y) => [x * 40, y * 40, 0])).toString("base64"), "--pm-twin-0002--", ""]
        : [qp(body)]),
    ].join("\r\n");
    const meta = { Version: 1, Payload: { ID: id, AddressID: "addr-0001", Subject: subject, Sender: { Name: from, Address: `${from.toLowerCase().replace(" ", ".")}@example.invalid` }, ToList: [{ Name: me, Address: `${me.toLowerCase().replace(" ", ".")}@proton.example` }], Time: Math.floor(t / 1000), Unread: 0, LabelIDs: ["0", "5"], ExternalID: `${id}@example.invalid`, MIMEType: i === 2 ? "multipart/mixed" : "text/plain", NumAttachments: i === 2 ? 1 : 0 } };
    entries.push({ path: `${id}.eml`, bytes: e(eml), dos: dos(1 + i * 4) }, { path: `${id}.metadata.json`, bytes: e(`${JSON.stringify(meta, null, 2)}\n`), dos: dos(1 + i * 4) });
  }
  out("mail-month-bundle.zip", zip(entries));
  sidecar("mail-month-bundle.zip", `origin: proton-mail-export\nvia: export\norigin_fields:\n  period: "2026-03"\n  account: ${me.toLowerCase().replace(" ", ".")}@proton.example\n  exported_at: "2026-04-03T01:00:00Z"\n  member_count: 6\n  sidecar_count: 6\n  date_axis: Payload.Time\n`);
}

// ── photo-library period batch ──────────────────────────────────────────────────────────────────────────────────────
function photos() {
  rmSync(TMP, { recursive: true, force: true });
  mkdirSync(TMP, { recursive: true });
  const r = lcg(88);
  const entries: ZipEntry[] = [];
  const side = (filename: string, uuid: string, t: number, extra: Record<string, unknown> = {}) =>
    e(`${JSON.stringify({ uuid, filename, original_filename: filename, date: new Date(t).toISOString(), title: "", description: "", keywords: ["harbour"], persons: [], albums: ["Quay 2026"], favorite: false, hidden: false, ismissing: false, latitude: 55.627, longitude: -6.19, place: { name: "Port Ellen, Argyll", country_code: "GB" }, exif: { camera_make: "Example", camera_model: "Phone 12" }, ...extra }, null, 2)}\n`);
  let t = Date.UTC(2026, 2, 3, 14, 0, 0);
  for (let i = 1; i <= 2; i++) {
    t += 86400000 * 2;
    const src = join(TMP, `s${i}.png`);
    writeFileSync(src, png(24, 16, (x, y) => [(x * 10 + i * 50) & 255, (y * 15) & 255, 180]));
    const heic = join(TMP, `IMG_000${i}.HEIC`);
    run(["heif-enc", "-q", "60", "-o", heic, src]);
    entries.push({ path: `IMG_000${i}.HEIC`, bytes: new Uint8Array(readFileSync(heic)), method: 0, dos: dos(3 + i * 2) });
    entries.push({ path: `IMG_000${i}.json`, bytes: side(`IMG_000${i}.HEIC`, `0000000${i}-0000-4000-8000-00000000c0de`, t), dos: dos(3 + i * 2) });
  }
  for (let i = 3; i <= 4; i++) {
    t += 86400000 * 3;
    const jpg = join(TMP, `IMG_000${i}.JPG`);
    run(["magick", "-size", "64x48", `plasma:#${(i * 1234567).toString(16).slice(0, 6)}-#ffffff`, "-quality", "70", "-strip", jpg]);
    entries.push({ path: `IMG_000${i}.JPG`, bytes: new Uint8Array(readFileSync(jpg)), method: 0, dos: dos(3 + i * 2) });
    entries.push({ path: `IMG_000${i}.json`, bytes: side(`IMG_000${i}.JPG`, `0000000${i}-0000-4000-8000-00000000c0de`, t, { hasadjustments: i === 4 }), dos: dos(3 + i * 2) });
    if (i === 4) {
      const ed = join(TMP, "IMG_0004_edited.jpeg");
      run(["magick", jpg, "-modulate", "110,120", "-strip", ed]);
      entries.push({ path: "IMG_0004_edited.jpeg", bytes: new Uint8Array(readFileSync(ed)), method: 0, dos: dos(11) });
    }
  }
  const mov = join(TMP, "IMG_0005.MOV");
  run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=15", "-f", "lavfi", "-i", "sine=frequency=330:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-f", "mov", mov]);
  entries.push({ path: "IMG_0005.MOV", bytes: new Uint8Array(readFileSync(mov)), method: 0, dos: dos(20) });
  entries.push({ path: "IMG_0005.json", bytes: side("IMG_0005.MOV", "00000005-0000-4000-8000-00000000c0de", t + 86400000 * 5, { ismovie: true, duration: 1.0 }), dos: dos(20) });
  entries.push({ path: "IMG_0006.PNG", bytes: png(32, 32, (x, y) => [x * 8, y * 8, 200]), method: 0, dos: dos(22) });
  entries.push({ path: "IMG_0006.json", bytes: side("IMG_0006.PNG", "00000006-0000-4000-8000-00000000c0de", t + 86400000 * 7, { isscreenshot: true }), dos: dos(22) });
  out("photos-month-bundle.zip", zip(entries));
  sidecar("photos-month-bundle.zip", `origin: osxphotos-export\nvia: export\norigin_fields:\n  period: "2026-03"\n  account: library@example.invalid\n  exported_at: "2026-04-05T02:00:00Z"\n  coverage: full library\n`);
  rmSync(TMP, { recursive: true, force: true });
}

const gens: Record<string, () => void> = {
  meta: () => {
    meta("facebook");
    meta("instagram");
    meta("threads");
  },
  gchat,
  imessage,
  proton,
  photos,
};
const only = process.argv.includes("--only") ? process.argv[process.argv.indexOf("--only") + 1]!.split(",") : Object.keys(gens);
for (const k of only) gens[k]!();
