#!/usr/bin/env bun
// pages.ts — the twins of the generic web-page captures: an article page, a product page (schema.org microdata), an
// order page (a table of lines and totals), a property listing (address, price, facts). Each under a v52 capture
// banner with navigation and footer chrome and a script bulk. Fictional sites and goods; generated prose.
//
//   bun testdata/synthetic/gen/pages.ts
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { int, lcg, paragraph, sentence } from "./lib/rand.ts";

const SYN = join(dirname(Bun.fileURLToPath(import.meta.url)), "..");
const r = lcg(808);
const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const chrome = (site: string) => `<header class="site-header"><nav class="site-nav"><a href="/">${site}</a> <a href="/about/">About</a> <a href="/contact/">Contact</a><form action="/search" method="get"><input name="q" placeholder="Search"><button type="submit">Go</button></form></nav></header>`;
const footer = `<footer class="site-footer"><p>© 2026 Example sites. Fictional pages for the regression suite.</p><ul><li><a href="/terms/">Terms</a></li><li><a href="/privacy/">Privacy</a></li></ul></footer>`;
const script = `<script>${Array.from({ length: 150 }, (_, i) => `window.__m${i}=function(a){return a*${i}};`).join("")}</script>`;
const page = (url: string, at: string, title: string, body: string) =>
  `<head><meta name="corpus-capture-url" content="${url}"><meta name="corpus-fetched-at" content="${at}"><meta name="corpus-fidelity" content="lean"></head><!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${esc(title)}</title></head>\n<body>\n${chrome(new URL(url).hostname)}\n<main id="main">\n${body}\n</main>\n${footer}${script}\n</body></html>\n`;
const out = (name: string, html: string) => {
  writeFileSync(join(SYN, name), html);
  console.log(`wrote ${name} (${html.length} chars)`);
};

out(
  "harbour-article.html",
  page(
    "https://news.example.invalid/harbour/2026/03/dredging-plan-approved",
    "2026-03-16T08:12:40Z",
    "Dredging plan approved for the inner harbour | Harbour News",
    `<article class="post" itemscope itemtype="https://schema.org/NewsArticle">
<h1 class="post-title" itemprop="headline">Dredging plan approved for the inner harbour</h1>
<p class="byline">By <span class="author" itemprop="author">Ida Thorn</span> · <time class="published" itemprop="datePublished" datetime="2026-03-15T17:30:00Z">15 March 2026</time></p>
<figure class="lead"><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" alt="The inner harbour at low water"><figcaption>The inner harbour at low water.</figcaption></figure>
<div class="post-body" itemprop="articleBody">
${Array.from({ length: 7 }, () => `<p>${esc(paragraph(r))}</p>`).join("\n")}
<h2>What happens next</h2>
${Array.from({ length: 3 }, () => `<p>${esc(paragraph(r))}</p>`).join("\n")}
<blockquote class="pull-quote"><p>${esc(sentence(r))}</p><cite>Harbour master</cite></blockquote>
</div>
<ul class="tags"><li><a href="/tag/harbour/">harbour</a></li><li><a href="/tag/dredging/">dredging</a></li></ul>
</article>
<section class="comments"><h3>Comments</h3><ol>${Array.from({ length: 3 }, (_, i) => `<li class="comment"><span class="comment-author">reader${i + 1}</span> <time datetime="2026-03-1${6 + i}T10:00:00Z">16 March</time><p>${esc(sentence(r))}</p></li>`).join("")}</ol></section>`,
  ),
);

out(
  "rope-product.html",
  page(
    "https://shop.example.invalid/products/mooring-rope-12mm",
    "2026-02-20T19:44:02Z",
    "Mooring rope 12 mm, 3-strand nylon | Harbour Stores",
    `<div class="product" itemscope itemtype="https://schema.org/Product">
<h1 class="product-title" itemprop="name">Mooring rope 12 mm, 3-strand nylon</h1>
<div class="gallery"><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" alt="Mooring rope 12 mm"><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" alt="Rope end detail"></div>
<div class="offer" itemprop="offers" itemscope itemtype="https://schema.org/Offer"><span class="price" itemprop="price" content="2.40">£2.40</span> <span class="unit">per metre</span> <meta itemprop="priceCurrency" content="GBP"><link itemprop="availability" href="https://schema.org/InStock"><span class="availability">In stock</span></div>
<p class="sku">SKU <span itemprop="sku">HS-ROPE-12-3S</span> · Brand <span itemprop="brand">Quayline</span></p>
<div class="description" itemprop="description">${Array.from({ length: 3 }, () => `<p>${esc(paragraph(r))}</p>`).join("")}</div>
<table class="specs"><caption>Specifications</caption><tbody><tr><th>Diameter</th><td>12 mm</td></tr><tr><th>Construction</th><td>3-strand</td></tr><tr><th>Material</th><td>Nylon</td></tr><tr><th>Breaking load</th><td>${int(r, 2000, 3500)} kg</td></tr><tr><th>Colour</th><td>Navy</td></tr></tbody></table>
<section class="reviews"><h2>Reviews</h2>${Array.from({ length: 4 }, (_, i) => `<div class="review" itemprop="review" itemscope itemtype="https://schema.org/Review"><span class="rating" itemprop="reviewRating">${5 - (i % 2)}/5</span> <span class="reviewer" itemprop="author">buyer${i + 1}</span><p itemprop="reviewBody">${esc(sentence(r))}</p></div>`).join("")}</section>
</div>`,
  ),
);

out(
  "order-detail.html",
  page(
    "https://shop.example.invalid/account/orders/HS-2026-00418",
    "2026-03-02T21:05:11Z",
    "Order HS-2026-00418 | Harbour Stores",
    `<div class="order">
<h1 class="order-title">Order HS-2026-00418</h1>
<dl class="order-meta"><dt>Placed</dt><dd><time datetime="2026-02-27T14:22:00Z">27 February 2026</time></dd><dt>Status</dt><dd class="status">Delivered</dd><dt>Payment</dt><dd>Card ending 4242</dd><dt>Deliver to</dt><dd class="address">Ada Abbott, 14 Mill Lane, Port Ellen</dd></dl>
<table class="order-lines"><thead><tr><th>Item</th><th>Qty</th><th>Unit</th><th>Total</th></tr></thead><tbody>
<tr class="line"><td class="item">Mooring rope 12 mm, 3-strand nylon (20 m)</td><td class="qty">1</td><td class="unit">£48.00</td><td class="total">£48.00</td></tr>
<tr class="line"><td class="item">Shackle, galvanised, 10 mm</td><td class="qty">4</td><td class="unit">£3.95</td><td class="total">£15.80</td></tr>
<tr class="line"><td class="item">Chandlery tape</td><td class="qty">2</td><td class="unit">£3.20</td><td class="total">£6.40</td></tr>
</tbody><tfoot><tr><th colspan="3">Subtotal</th><td class="subtotal">£70.20</td></tr><tr><th colspan="3">Delivery</th><td>£4.99</td></tr><tr><th colspan="3">Total</th><td class="grand-total">£75.19</td></tr></tfoot></table>
<section class="tracking"><h2>Tracking</h2><ol class="events"><li><time datetime="2026-02-28T09:10:00Z">28 Feb 09:10</time> Dispatched</li><li><time datetime="2026-03-01T13:40:00Z">1 Mar 13:40</time> Out for delivery</li><li><time datetime="2026-03-01T15:02:00Z">1 Mar 15:02</time> Delivered</li></ol></section>
</div>`,
  ),
);

out(
  "cottage-listing.html",
  page(
    "https://homes.example.invalid/listing/12 Quay Street Port Ellen/A1234567",
    "2026-01-29T16:30:55Z",
    "12 Quay Street, Port Ellen – 2 bed cottage | Harbour Homes",
    `<div class="listing" itemscope itemtype="https://schema.org/Residence">
<h1 class="listing-title"><span class="street" itemprop="streetAddress">12 Quay Street</span>, <span class="locality" itemprop="addressLocality">Port Ellen</span></h1>
<p class="price"><span class="amount">£${int(r, 180, 320)},000</span> <span class="qualifier">Offers over</span></p>
<ul class="facts"><li class="beds">2 bedrooms</li><li class="baths">1 bathroom</li><li class="area">68 m²</li><li class="type">Cottage</li><li class="tenure">Freehold</li></ul>
<div class="photos">${Array.from({ length: 5 }, (_, i) => `<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" alt="Photo ${i + 1}">`).join("")}</div>
<div class="description" itemprop="description">${Array.from({ length: 4 }, () => `<p>${esc(paragraph(r))}</p>`).join("")}</div>
<section class="rooms"><h2>Rooms</h2><ul>${["Living room 4.2 × 3.8 m", "Kitchen 3.1 × 2.6 m", "Bedroom 1 3.9 × 3.0 m", "Bedroom 2 2.8 × 2.6 m", "Bathroom 2.1 × 1.9 m"].map((x) => `<li class="room">${x}</li>`).join("")}</ul></section>
<section class="agent"><h2>Agent</h2><p class="agent-name">Harbour Homes, Port Ellen</p><p class="agent-phone">+44 7700 900789</p></section>
<p class="listed">Listed <time datetime="2026-01-20">20 January 2026</time> · Ref A1234567</p>
</div>`,
  ),
);
