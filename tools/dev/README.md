# dev/ — scaffolding for #85 (the held-record re-addressing pass)

Four read-only diagnostics for deciding what a §12.28-held record's over-wide legacy
intervals actually covered. They answer the questions `corpus remap-el --override` needs
answered before it can be given a judgment. Run them from a corpus root:

```bash
uv run --project tools --no-sync python tools/dev/<script>.py <corpus-root> <args…>

collisions.py  <root> <record…>          # the labelled collision report — which addresses
                                         #   converge on one path, and what each segment IS.
                                         #   Start here: it separates the widening-interval
                                         #   chains (#85's work) from image+text pairs
                                         #   sharing one legacy address (#73's, leave alone).
showmap.py     <root> <record>           # every el= address → what §6.1.1 maps it to.
findpath.py    <root> <record> <snippet> # tightest element containing a snippet — the
                                         #   "which element IS this prose?" question.
kids.py        <root> <record> <path> [lo] [hi]   # element children of a path, with previews;
                                         #   how a sibling range's endpoints get chosen.
pixeltest.py   <root> [record…]          # for a text segment sitting at a member's address:
                                         #   pixels or borrowed page prose? Asks the artifact
                                         #   whether the text is in the DOM. Separates #73's
                                         #   dropped markers from #88's mis-addressed prose.
```

**Delete this directory when #85 closes.** It is scaffolding for one migration, not part of
the distribution — nothing in `src/` imports it and no test covers it.
