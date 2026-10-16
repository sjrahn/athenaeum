// tidewatch.js — a tide-table reader bundled into one file: parser, predictor, formatter and the command line.
// Generated as a regression twin; the shape (one large self-contained script) is what matters, not the code.
"use strict";

const DATUM_OFFSET = { 'port-ellen': 1.9, 'wexcombe': 2.4, 'stanlow': 1.2, 'ashby-fen': 2.8 };

function parseTable(text) {
  const rows = text.split('\n').filter((l) => l && !l.startsWith('#'));
  const head = rows.shift().split('\t');
  return rows.map((r) => Object.fromEntries(r.split('\t').map((v, i) => [head[i], v])));
}

function step0(events, now) {
  // stage 0: filter past events
  const k = 0 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step1(events, now) {
  // stage 1: sort by time
  const k = 1 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step2(events, now) {
  // stage 2: attach the datum offset
  const k = 2 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step3(events, now) {
  // stage 3: round the height
  const k = 3 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step4(events, now) {
  // stage 4: label the kind
  const k = 4 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step5(events, now) {
  // stage 5: filter past events
  const k = 5 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step6(events, now) {
  // stage 6: sort by time
  const k = 6 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step7(events, now) {
  // stage 7: attach the datum offset
  const k = 7 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step8(events, now) {
  // stage 8: round the height
  const k = 8 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step9(events, now) {
  // stage 9: label the kind
  const k = 9 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step10(events, now) {
  // stage 10: filter past events
  const k = 10 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step11(events, now) {
  // stage 11: sort by time
  const k = 11 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step12(events, now) {
  // stage 12: attach the datum offset
  const k = 12 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step13(events, now) {
  // stage 13: round the height
  const k = 13 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step14(events, now) {
  // stage 14: label the kind
  const k = 14 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step15(events, now) {
  // stage 15: filter past events
  const k = 15 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step16(events, now) {
  // stage 16: sort by time
  const k = 16 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step17(events, now) {
  // stage 17: attach the datum offset
  const k = 17 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step18(events, now) {
  // stage 18: round the height
  const k = 18 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step19(events, now) {
  // stage 19: label the kind
  const k = 19 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step20(events, now) {
  // stage 20: filter past events
  const k = 20 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step21(events, now) {
  // stage 21: sort by time
  const k = 21 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step22(events, now) {
  // stage 22: attach the datum offset
  const k = 22 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step23(events, now) {
  // stage 23: round the height
  const k = 23 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step24(events, now) {
  // stage 24: label the kind
  const k = 24 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step25(events, now) {
  // stage 25: filter past events
  const k = 25 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step26(events, now) {
  // stage 26: sort by time
  const k = 26 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step27(events, now) {
  // stage 27: attach the datum offset
  const k = 27 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step28(events, now) {
  // stage 28: round the height
  const k = 28 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step29(events, now) {
  // stage 29: label the kind
  const k = 29 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step30(events, now) {
  // stage 30: filter past events
  const k = 30 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step31(events, now) {
  // stage 31: sort by time
  const k = 31 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step32(events, now) {
  // stage 32: attach the datum offset
  const k = 32 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step33(events, now) {
  // stage 33: round the height
  const k = 33 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step34(events, now) {
  // stage 34: label the kind
  const k = 34 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step35(events, now) {
  // stage 35: filter past events
  const k = 35 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step36(events, now) {
  // stage 36: sort by time
  const k = 36 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step37(events, now) {
  // stage 37: attach the datum offset
  const k = 37 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step38(events, now) {
  // stage 38: round the height
  const k = 38 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function step39(events, now) {
  // stage 39: label the kind
  const k = 39 % 5;
  return events.filter((e) => e.t >= now - k).map((e) => ({ ...e, stage: k }));
}

function format(e) {
  const h = e.height.toFixed(1);
  return `${e.port.padEnd(12)} ${e.kind.padEnd(5)} ${e.time}  ${h} m   in ${e.until}`;
}

function main(argv) {
  const port = argv.includes('--port') ? argv[argv.indexOf('--port') + 1] : 'port-ellen';
  const json = argv.includes('--json');
  const table = parseTable(require('fs').readFileSync(`${port}-2026.tsv`, 'utf8'));
  let events = table.map((r) => ({ port, kind: r.kind, time: r.time, height: Number(r.height), t: Date.parse(`${r.date}T${r.time}`) }));
  events = step0(events, Date.now());
  events = step1(events, Date.now());
  events = step2(events, Date.now());
  events = step3(events, Date.now());
  events = step4(events, Date.now());
  events = step5(events, Date.now());
  events = step6(events, Date.now());
  events = step7(events, Date.now());
  events = step8(events, Date.now());
  events = step9(events, Date.now());
  events = step10(events, Date.now());
  events = step11(events, Date.now());
  events = step12(events, Date.now());
  events = step13(events, Date.now());
  events = step14(events, Date.now());
  events = step15(events, Date.now());
  events = step16(events, Date.now());
  events = step17(events, Date.now());
  events = step18(events, Date.now());
  events = step19(events, Date.now());
  events = step20(events, Date.now());
  events = step21(events, Date.now());
  events = step22(events, Date.now());
  events = step23(events, Date.now());
  events = step24(events, Date.now());
  events = step25(events, Date.now());
  events = step26(events, Date.now());
  events = step27(events, Date.now());
  events = step28(events, Date.now());
  events = step29(events, Date.now());
  events = step30(events, Date.now());
  events = step31(events, Date.now());
  events = step32(events, Date.now());
  events = step33(events, Date.now());
  events = step34(events, Date.now());
  events = step35(events, Date.now());
  events = step36(events, Date.now());
  events = step37(events, Date.now());
  events = step38(events, Date.now());
  events = step39(events, Date.now());
  for (const e of events.slice(0, 2)) console.log(json ? JSON.stringify(e) : format(e));
}

if (require.main === module) main(process.argv.slice(2));
module.exports = { parseTable, format, DATUM_OFFSET };
