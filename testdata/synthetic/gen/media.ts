#!/usr/bin/env bun
// media.ts — the twins of the loose media and raster shapes, from tools (versions in README.md) and pinned by the
// committed bytes: a QuickTime clip, a 3GPP clip, raw elementary streams (H.264 Annex B, HEVC Annex B, AV1 in IVF),
// Opus in Ogg, AAC in ADTS, MPEG audio, a TIFF, an AVIF, an icon, an animated GIF. Test patterns and tones only.
//
//   bun testdata/synthetic/gen/media.ts [--only mov,3gp,h264,hevc,av1,opus,aac,mp3,tiff,avif,ico,gif]
import { dirname, join } from "node:path";

const SYN = join(dirname(Bun.fileURLToPath(import.meta.url)), "..");
const run = (cmd: string[]) => {
  const r = Bun.spawnSync(cmd, { stdout: "pipe", stderr: "pipe" });
  if (r.exitCode !== 0) throw new Error(`${cmd[0]}: ${r.stderr.toString()}`);
  console.log(`wrote ${cmd[cmd.length - 1]!.split("/").pop()}`);
};
const ff = (args: string[], outName: string) => run(["ffmpeg", "-y", "-loglevel", "error", ...args, join(SYN, outName)]);
const VID = ["-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=15"];
const AUD = ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"];
const gens: Record<string, () => void> = {
  mov: () => ff([...VID, ...AUD, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-f", "mov"], "harbour-clip.mov"),
  "3gp": () => ff([...VID, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "baseline", "-an", "-f", "3gp"], "phone-clip.3gp"),
  h264: () => ff([...VID, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-f", "h264"], "stream.h264"),
  hevc: () => ff([...VID, "-c:v", "libx265", "-pix_fmt", "yuv420p", "-x265-params", "log-level=none", "-f", "hevc"], "stream.h265"),
  av1: () => ff([...VID, "-c:v", "libaom-av1", "-pix_fmt", "yuv420p", "-cpu-used", "8", "-f", "ivf"], "stream.ivf"),
  opus: () => ff([...AUD, "-c:a", "libopus", "-b:a", "32k", "-f", "ogg"], "tone.opus"),
  aac: () => ff([...AUD, "-c:a", "aac", "-f", "adts"], "tone.aac"),
  mp3: () => ff([...AUD, "-c:a", "libmp3lame", "-b:a", "64k", "-f", "mp3"], "tone.mp3"),
  tiff: () => run(["magick", "-size", "48x32", "gradient:#2b6ca3-#e9d8a6", "-strip", join(SYN, "scan.tiff")]),
  avif: () => run(["magick", "-size", "32x32", "plasma:#3a5a2a-#ffffff", "-strip", join(SYN, "still.avif")]),
  ico: () => run(["magick", "-size", "32x32", "xc:#2d5f8a", "-fill", "#ffffff", "-draw", "circle 16,16 16,6", "-define", "icon:auto-resize=32,16", join(SYN, "favicon.ico")]),
  gif: () => ff([...VID, "-vf", "fps=5,scale=64:-1", "-t", "0.6"], "animation.gif"),
};
const only = process.argv.includes("--only") ? process.argv[process.argv.indexOf("--only") + 1]!.split(",") : Object.keys(gens);
for (const k of only) gens[k]!();
