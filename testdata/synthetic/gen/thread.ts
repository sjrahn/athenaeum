#!/usr/bin/env bun
// thread.ts — the twin of the XenForo thread capture: a v52 capture banner, html#XF[data-template=thread_view], a
// thread title, ten posts (author, user id, member title, post number, time with a datetime attribute, body with
// line breaks; two of them quoting an earlier post in XenForo's markup, which carries the source on the attribution link, not on the blockquote), the chrome the term declares (nav, breadcrumbs, action bars,
// user stats, footer, forms, buttons), and a script and style blob so the remainder is realistic. Fictional forum.
//
//   bun testdata/synthetic/gen/thread.ts
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { FIRST, LAST, int, lcg, paragraph, pick } from "./lib/rand.ts";

const OUT = join(dirname(Bun.fileURLToPath(import.meta.url)), "..", "harbourboard-thread.html");
const r = lcg(2026);
const SITE = "harbourboard.example";
const URL = "https://www.harbourboard.example/threads/mooring-line-chafe.48213/";
const TITLE = "Mooring line chafe — ✓ sorted";
const members = Array.from({ length: 5 }, (_, i) => ({
  id: 1000 + i * 37,
  name: `${pick(r, FIRST)}_${pick(r, LAST)}`.toLowerCase(),
  title: ["Registered", "Registered", "Moderator", "Registered", "Harbour staff"][i]!,
}));
const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const stamp = (i: number) => new Date(Date.UTC(2026, 3, 3 + i, 7 + i, (i * 17) % 60, (i * 23) % 60)).toISOString().replace(/\.000Z$/, ".000Z");
const shown = (iso: string) => {
  const d = new Date(iso);
  return `${["Jan", "Feb", "Mar", "Apr", "May", "Jun"][d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
};

const posts = Array.from({ length: 10 }, (_, i) => {
  const m = members[[0, 1, 0, 2, 0, 3, 0, 2, 0, 4][i]!]!;
  const body: string[] = [];
  for (let k = 0; k < int(r, 1, 3); k++) body.push(esc(paragraph(r)));
  return { n: i + 1, id: 48213 * 10 + i + 1, m, at: stamp(i), body, quotes: i === 4 ? 3 : i === 7 ? 6 : null };
});

const chrome = `<div class="p-nav"><nav><a href="/">Home</a> <a href="/forums/">Forums</a> <a href="/whats-new/">What's new</a></nav><form action="/search/" method="post"><input name="keywords" placeholder="Search…"><button type="submit">Search</button></form></div>
<ul class="p-breadcrumbs"><li><a href="/forums/">Forums</a></li><li><a href="/forums/moorings.12/">Moorings and berths</a></li></ul>`;

const post = (p: (typeof posts)[number]) => `<article class="message message--post js-post" data-content="post-${p.id}" id="js-post-${p.id}">
<div class="message-cell message-cell--user"><h4 class="message-name"><a href="/members/${p.m.name}.${p.m.id}/" class="username" data-user-id="${p.m.id}">${p.m.name}</a></h4><h5 class="userTitle">${p.m.title}</h5>
<div class="message-userStats"><dl><dt>Joined</dt><dd>Mar ${1 + (p.m.id % 28)}, 2019</dd></dl><dl><dt>Messages</dt><dd>${(p.m.id * 7) % 900}</dd></dl></div></div>
<div class="message-cell message-cell--main"><header class="message-attribution"><a href="/threads/mooring-line-chafe.48213/post-${p.id}" qid="post-number" class="message-attribution-opposite">
 #${p.n}
 </a><time class="u-dt" dir="auto" datetime="${p.at}" data-time="${Math.floor(Date.parse(p.at) / 1000)}" qid="post-date-time" title="${shown(p.at)} at 7:${String(p.n * 7 % 60).padStart(2, "0")} AM">${shown(p.at)}</time></header>
<div class="bbWrapper">${p.quotes ? `<blockquote class="bbCodeBlock bbCodeBlock--expandable bbCodeBlock--quote"><div class="bbCodeBlock-title"><a href="/goto/post?id=${posts[p.quotes - 1]!.id}" class="bbCodeBlock-sourceJump" data-xf-click="attribution" data-content-selector="#post-${posts[p.quotes - 1]!.id}">${posts[p.quotes - 1]!.m.name} said:</a></div><div class="bbCodeBlock-content"><div class="bbCodeBlock-expandContent js-expandContent">${posts[p.quotes - 1]!.body[0]}</div><div class="bbCodeBlock-expandLink js-expandLink"><a role="button">Click to expand...</a></div></div></blockquote>` : ""}${p.body.join("<br>\n<br>\n")}</div>
<footer class="message-footer"><div class="message-actionBar actionBar"><a href="#" class="actionBar-action">Like</a> <a href="#" class="actionBar-action">Reply</a> <button type="button" class="button--link">Report</button></div></footer></div>
</article>`;

const script = `<script>(function(){var XF=window.XF={};XF.config={url:"${URL}",userId:0,enablePush:false};${Array.from({ length: 120 }, (_, i) => `XF.fn${i}=function(a,b){return a+b*${i};};`).join("")}})();</script>`;
const style = `<style>${Array.from({ length: 80 }, (_, i) => `.u-${i}{margin:${i}px;padding:${i % 7}px;color:#${(i * 37 % 4096).toString(16).padStart(3, "0")}}`).join("")}</style>`;

const html = `<head><meta name="corpus-capture-url" content="${URL}"><meta name="corpus-fetched-at" content="2026-08-15T23:40:36Z"><meta name="corpus-fidelity" content="lean"></head><!DOCTYPE html>
<html id="XF" lang="en-GB" dir="LTR" data-app="public" data-template="thread_view" data-container-key="node-12" data-content-key="thread-48213" data-logged-in="false" data-cookie-prefix="xf_" data-site="${SITE}" data-version="2026050200">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${esc(TITLE)} | Harbour Board</title>${style}</head>
<body data-template="thread_view">
<div class="p-pageWrapper">${chrome}
<div class="p-body"><div class="p-body-header"><div class="p-title"><h1 class="p-title-value" qid="page-header">${esc(TITLE)}</h1></div><div class="p-description"><a class="username" data-user-id="${posts[0]!.m.id}">${posts[0]!.m.name}</a> · <time datetime="${posts[0]!.at}">${shown(posts[0]!.at)}</time></div></div>
<div class="block block--messages"><div class="block-body js-replyNewMessageContainer">
${posts.map(post).join("\n")}
</div></div>
<form action="/threads/mooring-line-chafe.48213/add-reply" method="post" class="block"><textarea name="message" placeholder="Write your reply..."></textarea><button type="submit" class="button--primary">Post reply</button></form>
</div>
<footer class="p-footer"><div class="p-footer-inner"><ul class="p-footer-linkList"><li><a href="/help/terms/">Terms and rules</a></li><li><a href="/help/privacy-policy/">Privacy policy</a></li><li><a href="/help/">Help</a></li></ul><div class="p-footer-copyright">Community platform by Example Software © 2026</div></div></footer>
</div>${script}</body></html>
`;
writeFileSync(OUT, html);
console.log(`wrote ${OUT} (${html.length} chars)`);
