# Proposal: an `ath` CLI umbrella, with `corpus` and `codex` as routed layers

**Status:** **proposed** — decision pending sjrahn. No code written.
**Scope:** packaging + CLI entry points for `tools/corpus` (the shared tooling distribution); introduces a new top-level `ath` command and a new `codex` command surface reachable only through it. Touches `pyproject.toml [project.scripts]`, adds a thin `ath` dispatcher, and reserves a `codex` package/dispatcher for the codex-runtime tooling. Existing `corpus` / `corpus-api` behavior is unchanged.
**Decision owner:** sjrahn (CLI naming + layer topology is his domain). This write-up is the engineering recommendation.
**Relates to:** `spec-athenaeum.md` (the two-layer architecture + the corpus↔codex contract), `impl-codex.md` §5 (runtime resolution) + §7 (build) — the runtime/build this CLI would implement. **Non-normative:** CLI naming is tooling ergonomics, so this needs no spec change.

---

## 1. The question

We will want tooling for the codex layer — the runtime that mounts codices + corpora, resolves `corpus://`/`codex://` references, and builds a codex's deliverables. It will lean on pieces of the corpus tooling (discovery, reading, probably a work queue). Two questions:

1. **One CLI banner or separate commands?**
2. **How do we avoid a bare `codex` command** — it clashes with OpenAI's `codex` CLI when that's installed.

The floated idea: make `corpus` and `codex` **router subcommands of an `ath` (Athenaeum) CLI**.

## 2. Recommendation

**Adopt the `ath` umbrella.** Ship three console scripts — `ath`, `corpus`, `corpus-api` — and deliberately **not** a fourth named `codex`. The codex surface is reachable only as `ath codex …`.

```
ath corpus <verb>     # delegates to the existing corpus dispatcher
ath codex  <verb>     # new codex-runtime dispatcher
ath api    …          # (optional) delegate to corpus-api
corpus <verb>         # permanent first-class alias — identical to `ath corpus <verb>`
corpus-api …          # unchanged
#  (no bare `codex` — the OpenAI clash exists only if we put that name on $PATH)
```

### 2.1 Why the umbrella

- **It dodges the clash by construction.** The OpenAI conflict is a `$PATH` collision on the bare name `codex`. If we never install a `codex` script, there is nothing to collide. `ath codex` is unaffected by whatever `codex` resolves to globally.
- **It mirrors the architecture.** `spec-athenaeum.md` defines exactly two layers — corpus (foundation) + codex (the expert-agent layer above it). One `ath` banner with a subcommand per layer is a direct reflection of that. "ath" is already how CLAUDE.md and the skill abbreviate the system.
- **It is nearly free.** `corpus._cli` is already a lazy-import `dispatch(argv)` router with grouped help (`_COMMANDS` / `_GROUP_ORDER`). The `ath` entry point is a thin shim: read the first token, delegate to `corpus._cli.dispatch(rest)` or the new `codex` dispatcher. The corpus internals do not change.
- **Room to grow.** System-level, cross-layer commands have a natural home later (`ath mount`, `ath config`, `ath doctor`) without polluting either layer's verb namespace.

### 2.2 The deliberate asymmetry: keep `corpus`, never ship `codex`

`corpus` stays a **permanent, first-class** top-level command — same code path as `ath corpus`, just a second entry point. This is not a deprecation-with-shim; both are first-class forever.

- Every existing doc, gotcha, workflow runbook, spec reference, and your muscle memory uses `corpus <verb>`. Keeping the script means **zero migration** and nothing to re-teach.
- `codex` gets **no** bare alias because its short name is taken. The asymmetry isn't arbitrary — corpus's name is free, codex's isn't. Anyone wanting brevity can `alias cdx='ath codex'` in their own shell.

Net surface: `ath` (umbrella + the only path to codex), `corpus` (convenience alias for the foundation layer), `corpus-api` (unchanged).

## 3. The agnosticism guardrail — what `ath codex` may and may not own

This is the part to fix up front, because it's the easiest thing to get wrong. The shared tooling is **agnostic to codex topology** (`spec-athenaeum.md`; the skill repeats it as a load-bearing rule). `impl-codex.md` is explicitly *non-normative* — the spec fixes exactly one thing about the codex layer: the **consumption contract** (`corpus://` scheme, the read API, derived views; spec §2.3, §3.6–3.7). So `ath codex` must be scoped to the **contract/runtime side**, never the expert agent's editorial workflow.

**In scope (genuinely shared; reuses corpus primitives):**

- **Mount** a config-declared set of codices + corpora — exactly the join `impl-codex.md` §5.1 describes, and exactly how `corpus.api.config` already maps corpus *ids → roots*. Config-driven, never a hardcoded codex.
- **Resolve** `codex://{name}/{id}` and cross-container `corpus://{name}/{hash}` against the mounted set (impl-codex §5.2) — rides the existing resolver + URI index.
- **Build** — the resolution/compile pass (impl-codex §7): walk a deliverable, resolve wikilinks/footnote-URIs/embeds, emit the target format. Reuses derived views + the resolver for embed materialization.
- **Regen cascade detection** (impl-codex §6.3): walk loaded codices' footnote URIs for `codex://{this}/…` dependents before a regeneration.
- **Reference / backlink lint** across the mounted set (impl-codex §5.3) — unresolved-reference reporting as authoring follow-ups.

**Out of scope (agent-owned; stays convention, never assumed by tooling):**

- Authoring codex records, the codex's internal record format, the synthesis system prompt. The expert agent just writes markdown; the tooling never assumes a fixed codex shape (a codex whose deliverable isn't a record set lays itself out entirely differently — impl-codex §2, §4.1).

**The discipline that keeps agnosticism intact:** the codex CLI is *config-driven* — you `mount` a set, you never bake in a codex id or layout — the same rule as `--corpus id=path` / `ATH_API_CORPORA`. If a verb would only make sense for one particular codex's internal structure, it doesn't belong in the shared tooling.

## 4. Packaging / layering (the secondary decision)

**Recommendation: one distribution, three import packages**, preserving a clean upward-only dependency direction.

```
tools/corpus/                 (one uv project; one wheel)
└── src/
    ├── corpus/   — the foundation. imports nothing upward.            (unchanged)
    ├── codex/    — depends on corpus. implements impl-codex §5–7.     (new)
    └── ath/      — tiny glue. imports both dispatchers.               (new)
```

- **Dependency direction matches the architecture:** codex consumes corpus, never the reverse (spec §2.3). `corpus` never imports `codex`, so the foundation package stays pure and the layers remain separable.
- **Single install, max reuse:** `codex` imports `corpus.resolver` / the URI index / `derived_views` / `store` directly — no duplication, no second project to sync.
- **`ath` is glue only:** first token `corpus` → `corpus._cli.dispatch`; `codex` → `codex._cli.dispatch`; `api` → `corpus.api.__main__`.

**Rejected alternative — a `corpus.codex` submodule.** Less packaging work, but it leaks codex-runtime code into the *foundation* package, which is exactly the layering the two-layer architecture exists to keep separate. Avoid.

**Optional, follow-on (cosmetic, not blocking):** rename the distribution `ath-corpus` → `athenaeum`, since it would then provide `ath`/`corpus`/`corpus-api` and ship `corpus`/`codex`/`ath` packages. This is taste; do it after the umbrella lands, if at all.

## 5. Concrete wiring

`pyproject.toml`:

```toml
[project.scripts]
ath        = "ath._cli:main"          # new umbrella router
corpus     = "corpus._cli:main"       # unchanged — first-class alias for the corpus layer
corpus-api = "corpus.api.__main__:main"  # unchanged
# (intentionally NO `codex` script)
```

`ath._cli:main` (sketch — mirrors the existing lazy dispatcher's discipline):

```python
_LAYERS = {            # first token → (module, dispatch attr)
    "corpus": ("corpus._cli", "dispatch"),
    "codex":  ("codex._cli",  "dispatch"),
    "api":    ("corpus.api.__main__", "main"),   # optional convenience
}

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        return _print_overview()          # lists the two layers + their --help
    layer, *rest = argv
    if layer not in _LAYERS:
        ...                                # error: unknown layer, show overview
    mod, attr = _LAYERS[layer]
    return getattr(importlib.import_module(mod), attr)(rest)
```

`corpus._cli` already exposes `dispatch` and `main` (`__all__ = ["dispatch", "main"]`), so the corpus delegation needs no change to existing code. The new `codex._cli` follows the same `_COMMANDS` / `dispatch(argv)` shape — lazy-import per verb, grouped help — so the two layers feel identical.

## 6. Proposed initial codex verb set (sketch — for discussion, not part of the decision)

Grounded in impl-codex §5–7. Not building these yet; listed so the surface is concrete.

| verb | group | what it does |
|------|-------|--------------|
| `mount` | Runtime | show/validate the configured codices+corpora join (impl-codex §5.1) |
| `resolve` | Runtime | resolve a `codex://{name}/{id}` or cross-container `corpus://…` → path/metadata (§5.2) |
| `links` | Runtime | a record/chapter's outbound refs + which resolve vs. dangle (§5.3) — the codex-side mirror of `corpus links` |
| `build` | Build | run the resolution/compile pass for a deliverable → target format (§7) |
| `regen` | Lifecycle | detect `codex://{this}/…` dependents + surface the cascade before regeneration (§6.3) |

(A codex-side work queue — "probably queueing" — would reuse the corpus queue primitives; deferred until the regen/build flows stabilize, same way the corpus queue grew out of real loop use.)

## 7. What this does NOT change

- `corpus <verb>` and `corpus-api` behavior, help text, and exit codes — identical.
- The corpus library, API, and web app — untouched.
- The specs — no normative change (CLI naming is non-normative ergonomics; the runtime/build the codex CLI implements is already described in impl-codex §5/§7, which gains implementation notes when we build).

## 8. Decisions to confirm

1. **Adopt the `ath` umbrella** with the `corpus`-stays / no-bare-`codex` asymmetry? (recommended)
2. **One distribution, three packages** (`corpus` / `codex` / `ath`)? (recommended) — vs. a `corpus.codex` submodule (rejected here).
3. **Distribution rename** `ath-corpus` → `athenaeum` — yes / later / never? (cosmetic)
4. Park the **codex verb set** (§6) for a follow-up once §8.1–8.2 are settled?
