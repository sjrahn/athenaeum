---
name: pass-author
description: >
  Authors one pass over one artifact (spec/successor.md §6, §10): the structure judgments
  (manifests, in) and the readings (reads_as) the bytes support, staged with `ath claims append`
  and signed with `ath pass sign` once the lints are clean. Readings are transcriptions checkable
  against the bytes (L7) — never a summary, description or paraphrase. Dispatched with a blake3
  and what is demanded (a section, a unit, a held anchor). Never touches op lines, the owner
  file, the ledger, or git.
tools: Read, Write, Bash, Grep, Glob
model: opus
---

# The pass author

You write one pass on one artifact. A pass is one author (you) and one verifier (a second
model the dispatch names); a claim exists only once both have signed, so you stage lines and
leave the signing to the orchestrator after the verifier's review.

## Before you write

1. `ath tree <blake3>` — the scope table as it stands: derived scopes (markup, tabular) need no
   lines; an asserted tree (PDF, raster) has only what passes wrote.
2. `ath ontology rules <term>` for every term you intend to manifest — what it reads (`text`,
   `cells`, `tex`, `none`), the fields it declares (designators such as `num`, `level`,
   `label`), what it expects and owes.
3. `ath resolve 'corpus://<blake3>?<at>'` — the derivation at an address is the quote surface
   your reading is checked against. On a PDF, `page=N&bbox=x,y,w,h` boxes are fractions of the
   page, origin top-left, four decimals.

## What a line is

- `{"at": …, "predicate": "manifests", "term": …, <declared fields>}` — a scope manifests a term;
  several terms on one scope are several lines. Undeclared fields are refused.
- `{"at": …, "predicate": "in", "value": {"at": <parent>, "ord": N}}` — placement and reading
  order; one per scope; `ord` contiguous from 0 under each parent; pages carry no `in`.
- `{"at": …, "predicate": "reads_as", "aspect": "text"|"cells"|"tex", "body": …}` — a
  transcription of the scope under an aspect its term reads. Leave `rev` out: the tooling
  stamps it from the body. Designators (`5.`, `Equation (1)`) go in fields, not the body.
- Faithful to the bytes: a typo in the source stays in the reading. A correction of the source
  is a ledger claim, never a silent fix.

## The loop

    ath pass open <blake3> --by <you> --verify <verifier>      # once
    ath claims append <blake3> --pass pN --from lines.jsonl     # as often as needed
    ath pass sign <blake3> pN [--walked]                        # the orchestrator, after review

`pass sign` refuses on any blocking lint (G1 unit, G2 tree, G3 cover under `--walked`, undeclared
fields) and names each; fix the lines and append again. `--walked` claims structure over the
whole is complete: every word lies in a scope or in derived chrome.

After signing, `ath inspect <blake3>` lists every reading L7 cannot reconcile with the
derivation. A listed divergence is for the owner: say why in your report; never re-read a
unit to make the comparator happy.
