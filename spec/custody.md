---
spec_id: ATH
part: IV
title: "Athenaeum Specification — Part IV: Custody"
version: 38
status: current
license: "CC BY-SA 4.0"
date_created: 2026-08-19
date_modified: 2026-08-21
---

# Athenaeum Specification — Part IV: Custody

## 1. Overview

### 1.1 What this is

**Custody** is where artifact bytes live and how a content address finds them. The corpus contract ([Part II](corpus.md) §2) promises exactly one thing about bytes: *a lookup by id produces them*. This part specifies how that promise is kept at deployment scale — across a co-located tree, bulk storage, operator-managed shares on other machines, and remote object stores — without any record ever knowing or caring where its bytes reside.

The split this part draws is **catalog vs custody**. The catalog is tracked text: records, schemas, facts — the instance repository. Custody is the byte plane beneath it: untracked, machine-specific, declared per deployment. A record's identity (the blake3 of its bytes, Part II §2) is a catalog fact; its residence is a custody fact, and the two never contaminate each other — **residence is invisible**: the same bytes may live standalone, inside a container, on an attached share, or in several places at once, and no record changes when they move.

*(This part was extracted at v26 from the location/store/scanner material that had grown inside Part II — §12.1.1, §12.9.2 and their satellites. Part II keeps pointer stubs at those numbers so existing citations resolve.)*

### 1.2 The contract

1. **An id resolves to its bytes.** Given a blake3, the corpus produces the bytes — through whichever route holds them. Every route to an id yields identical bytes by construction; a resolver may take any (Part II §2).
2. **Residence is derived, never stored.** No record stores where its bytes live. Every route is computed from declared locations, record members-blocks, or derived indexes — so bytes move freely and nothing rots.
3. **The index proposes, the hash disposes.** Derived residence maps (the location index, presented manifests) may route reads under staleness pins, but every act that mints or replicates identity — promotion, adoption, replication — verifies the full blake3 first. A wrong map can at worst misroute a read, never mint or copy a wrong identity.
4. **Nothing normative depends on custody state existing.** Location indexes, hash indexes, and manifests are regenerable deployment state. A consumer missing a row recomputes it when bytes are in hand, or reports it — never fails.

## 2. Routes

An id resolves through five route classes, in order — declared cost (§3.4) reorders *within* a class, never across identity's stronger guards:

1. **The co-located store** — `corpus/artifacts/<shard>/<id>.<ext>` (Part II §12.1), the default location.
2. **Other store locations** — content-addressed trees the corpus writes, declared in `corpus.toml` (§3).
3. **The attached-location index** — operator-managed trees whose files stay in place, resolvable by bare id once attested (§4).
4. **The member index (containment)** — bytes streamed out of a containing artifact via the members-block route (Part II §2, §12.9). A promoted record has no standalone file at all: its bytes materialize through its container.
5. **Remote hydration** — a store location with a remote transport (`rclone`, or the object-store extras) pulls bytes local on demand.

Any route yields identical bytes; a resolver may take any. A promoted record's origin lineage (`uri: corpus://<container>?<address>`) is capture **history** and is never consulted for byte lookup — residence must stay free to change out from under it (Part II §12.9).

## 3. Locations

The co-located `artifacts/` tree is the **default location**, not the only one. A corpus MAY declare additional locations in its deployment configuration — `corpus.toml`, untracked and machine-specific; the reference shape:

```toml
[[corpus.location]]
name   = "bulk"
kind   = "store"               # content-addressed tree the corpus writes
path   = "/mnt/slow/artifacts"
ingest = ["application/x-openzim"]   # optional placement policy: these formats land here.
                                     # `ingest = true` instead makes this the DEFAULT
                                     # destination — every new artifact lands here unless a
                                     # format list on another location claims it; the
                                     # co-located tree is the fallback when nothing matches
ingest_origins = ["download.geofabrik.de"]   # origin claims: artifacts whose minting origin
                                     # matched one of these origin overlays (by overlay id,
                                     # Part II §7.2) land here — beats format claims

[[corpus.location]]
name   = "datasets"
kind   = "attached"            # operator-managed tree, files in place
path   = "/mnt/slow/datasets"

[[corpus.location]]
name     = "nas-media"
kind     = "attached"
path     = "/mnt/nas/media"
manifest = true                # presented manifest: the host's own residence scanner
                               # maintains <path>/.athenaeum/; attest reads it instead
                               # of walking the tree (§5)

[[corpus.location]]
name   = "offsite"
kind   = "store"
remote = "rclone:b2-corpus"    # transport, not layout — hydrates via ensure_local
```

### 3.1 Store locations

A **store** location is a content-addressed `<shard>/<hash>.<ext>` tree the corpus itself writes — Part II §12.1's layout at another root. Ingest placement policy MAY direct new artifacts of declared formats there instead of the co-located tree (tens-of-GB mirrors belong on bulk storage, not beside the repo) — or, with `ingest = true`, ALL new artifacts. The most specific claim wins: origin claim → format claim → default → co-located; within one axis, declaration order breaks ties. An origin claim (`ingest_origins`) matches against the origin overlay id the minting origin resolved to — no second pattern syntax; the overlay IS the origin's identity. An artifact minted with no matched origin overlay can never satisfy an origin claim; `put`/`ensure_local` address every store location symmetrically. The object-store backends (the azure/s3 extras) are store locations with a remote transport — **rclone** generalizes that transport to anything it reaches (SMB shares, B2, SFTP, …), an optional extra in the same guarded mold as every other backend.

### 3.2 Attached locations

An **attached** location is an operator-managed tree the corpus reads but never rewrites: files keep their own names and paths — never renamed, never moved into content-addressed form (**adoption**, §6.2, copies them into one, leaving the tree untouched). An **attest pass** (`corpus location attest <name>`) streams and hashes the tree — hash-while-in-hand: the pass opportunistically fills the derived hash index too (Part II §12.9.1) — or, where the location presents its own manifest (§5), ingests that instead of walking — and writes the **location index** (§4): blake3 → `(location, relpath, size, mtime)`. From then on those files resolve by bare id like any artifact.

This is the containment model generalized: an attached location is, functionally, a container whose manifest is the location index — members stay in place, resolution routes through a derived map, and **promotion mints records without moving bytes** (Part II §8.1's shape: identity verified by the full hash at mint; the origin block records the location provenance under its scheme family, Part II §7.2 — and, as with container lineage, that origin is history, never a lookup route).

**In-place files are mutable, and the map is honest about it.** An attached row pins `size` + `mtime`; a mismatch at resolution time makes the row **stale** — the route reports unresolvable (health surfaces it) rather than serving bytes that may no longer match their id, and re-attest re-hashes. Promotion always verifies the full blake3 at mint: the index proposes, the hash disposes.

### 3.3 Move semantics

Residence is mutable because it is invisible. `corpus location move` relocates a record's **standalone copy** between store locations — the co-located tree counting as one — by copy-verify-then-remove: the bytes are copied into the destination's content-addressed path via a temporary name, the full blake3 is verified against the record id before the rename unveils them, and only then is the source copy removed — at no instant is the id unresolvable by the route being replaced, and a failed verify leaves the source untouched. Attached-location files never move (operator-managed — adoption is the custody-transfer path, not a move); a containment-only member has no standalone copy to move — materializing one is `replicate`'s job, not `move`'s. A destination already holding the file is idempotent success: verify, then remove the source. The remove half owes redundancy floors the same honesty as `rm`: a move is location-neutral in copy *count*, but where a floor counts *distinct* locations a same-location dedupe is not. `move` MAY take a **batch form** — every record whose standalone copy resides at a named source location — with per-record outcomes, continuing past failures and reporting them.

### 3.4 Route preference

Part II §2's license — any route yields identical bytes, and a resolver may take any — has always permitted choosing well; **cost** names the signal. A location MAY declare `cost = N` (any non-negative integer; lower is nearer). Undeclared, cost defaults by class in the §2 resolution order — the co-located store nearest, then store locations, then attached — so a zero-config deployment behaves exactly as before; a declaration reorders *within* the standing route classes (a remote store location declares itself costlier than a local one; a remote attached mount costlier than an in-chassis tree), it does not promote a route class past identity's stronger guards. When bytes must actually move — resolution's local materialization, adoption's source read, `replicate`'s top-up — the resolver takes the **cheapest residency whose pins verify**, falling through to the next on staleness exactly as it falls through routes. The same declaration serves the dedup economics: `locate` orders a hash's residencies by cost, and replicate's planner reads it as "copy from the nearest, toward the floor."

## 4. The location index

The attached-location route's derived map — blake3 → `(location, relpath, size, mtime)`, plus row provenance and the advisory `mime_claim` where a manifest supplied one. Untracked, never authoritative; reference shape a single SQLite file, `corpus/cache/locations.db`.

It differs from the member index in one load-bearing way: the member index is rebuilt-on-start from records (Part II §12.15) because every row derives from a members block, but an attached file may have **no record yet** — pre-promotion, this index is the only memory of its hash, and recomputing a row means re-streaming the file (a 100 GB mirror makes that hours, not milliseconds). So it **persists**, exactly as the derived hash index persists (Part II §12.9.1): recomputation needs *bytes*, which is the test for earning persistence. Wiping it is always safe — nothing normative depends on it (§1.2) — at the cost of one re-attest per location. Rows go stale by `size`/`mtime` drift (§3.2) and refresh only by re-attest, never silently at read time.

Rows record their **provenance** — `computed` (attest streamed and hashed the bytes itself) or `presented` (a host claim the corpus has not independently observed, §5) — and a presented import is stamped with the manifest **generation** it came from, so re-attest on a presenting location skips generations already ingested: incremental by construction.

## 5. Presented manifests — the residence scanner

An attached location on a remote host MAY declare `manifest = true` — the tree **presents its own manifest**, maintained by the **residence scanner** (`scanner/` in the distribution), a shared tool run *on the host, against the local filesystem*. The locality is load-bearing twice over: hashing happens at disk speed with nothing crossing the wire but the manifest itself, and the scanner's change model — identity `(dev, ino) → (size, mtime) → blake3` — is only sound where inodes are real (through an SMB/NFS mount they are synthetic). Under that model an unchanged stat tuple is never re-hashed, a rename is a path row onto a known identity (zero re-hash), hardlinks collapse to one hash, and an interrupted pass resumes at per-file granularity — so a scheduled incremental run stays cheap forever after the cold pass.

The manifest lives at the location root (reference shape `<path>/.athenaeum/`: the scanner's private working state beside a **published** manifest database — a complete, checkpointed copy unveiled by temp-then-rename at each generation close, so a reader over the mount only ever sees a whole generation, never a write in flight). Its **byte format is the scanner's own versioned cross-language contract**, deliberately outside this spec so the writer is swappable without a spec change. Attest on a presenting location reads the manifest instead of walking — a whole share becomes attestable over a mount that only ever transfers the manifest, retiring the tree-walk scale limit — and the manifest directory itself is infrastructure, excluded from indexing as content.

**Trust.** Location-index rows imported from a manifest carry `presented` provenance (§4). The standing rule holds — the index proposes, the hash disposes: presented rows serve resolution under the same staleness pins as computed rows, and every act that mints or replicates identity verifies the full blake3 exactly as before — promotion at mint, adoption during its copy — so a false claim can at worst misroute a read, never mint or replicate a wrong identity. A deployment wanting more than the pins MAY re-verify presented rows with an ordinary walking attest; bit-rot scrub duty on the tree belongs to the scanner on the host, where the bytes are local.

**Catalog metadata.** The manifest is a **light catalog**, not just a residence map. An identity carries the universal stat facts — size and mtime (the pins), ctime, mode, and birth time where the filesystem has one (nullable) — refreshed by the walk whenever they drift, at no cost beyond the stat the walk already performs. `atime` is deliberately excluded (noise the scan's own reads would perturb); owner ids are deferred until a need names them. One derived fact rides along: a **mime claim**, sniffed from the leading bytes once per new identity while the bytes are in hand at hash time, so format questions — what formats reside where, which artifacts would a placement claim route — are answerable **without touching bytes over the wire**. Like the presented hash it qualifies, a mime claim is advisory — ingest's own detection (Part II §12.3.2) is authoritative and undisturbed, and nothing normative may depend on a claim being present or right. The location index imports the mime claim beside the pins; the remaining catalog facts stay queryable in the location's cached manifest rather than being copied forward.

## 6. Custody operations

### 6.1 Residency query — `corpus locate`

`corpus locate <blake3>` answers, for a bare hash, **where those bytes reside** — across the co-located store, store locations, the location index (computed and presented rows alike), the member index, and remote objects — and whether a record exists for them. It is read-only and works for hashes the corpus has never minted; that is the point: an external hash can be checked against every attached residence without moving a byte over the wire, making locate the natural precursor to promotion and adoption. A hash with **multiple residencies** is the dedup surface: locate lists them all (ordered by cost, §3.4); health's shadowed-copy signal (§6.2) is the special case where one residency is a store copy, and the general case — the same bytes at two paths, on one tree or two — surfaces the same way: candidates for the operator's reclaim judgment, never automatic deletion.

### 6.2 Adoption

`corpus location adopt <attached> <dest>` transfers a file's **primary custody** from an attached location to a store — owner-initiated, never implicit, and **non-destructive by default**: the destination store gains a copy under `move`'s contract (streamed to a temp name, full blake3 verified against the record id before the rename unveils it), and the attached original stays exactly where it is, untouched. From then on every consumer is served the store copy — the resolution order (store locations before the attached index, §2) shadows the attached row with no further mechanism — while the row itself persists honestly in the location index: the shadowed copy is invisible in use but **surfacable** (a health signal lists records holding both a store copy and a current attached row — dedup/reclaim candidates; and two copies are genuinely two, counting toward a redundancy floor). Removing the original is a separate explicit act (a reclaim flag, or the operator's own management of the tree) — never adoption's default, and for a read-only attached tree never possible at all. Files without a promoted record are refused (adoption transfers custody of a record's bytes, it does not mint — promote first); a stale index row is refused exactly as promotion refuses it (re-attest first).

### 6.3 Redundancy floors

With locations, "how many places hold these bytes" is countable. A mime or origin overlay MAY declare `replicas: N` (Part II §7.1); the resolved floor is the **max** across layers — a declaration strengthens custody, never weakens it. A health signal counts distinct locations holding a route to the record's bytes — a standalone copy in any store location, a container residence, a remote object, an attached-location file each count once — and reports records under their floor. `corpus replicate` (planned) tops up by copying to a store location; `rm` names the floor a removal would break. Nothing enforces at write time — ingest with one copy is still ingest; the floor is a standing health obligation, not a gate.

### 6.4 GC interplay

The resolver-cache sweep (`corpus gc`, Part II §12.8) **excludes by name** the persistent custody and identity indexes — `hashes.db` (Part II §12.9.1), `locations.db` (§4), `refidx/` (the `ref://` adapters' sidecar indexes, Part III §6.5) — regenerable in principle (nothing normative depends on any of them) but hours-expensive in practice (backfill needs bytes in hand; a sidecar rebuild re-scans a multi-GB mirror), the opposite economics of the resolver-output cache the sweep exists to prune. Their reclamation is a deliberate deletion, never an age sweep.

## 7. Out of scope

`corpus replicate` (the floor top-up verb) is planned, not yet specified beyond §6.3's semantics. Scanner scheduling (when hosts rescan) is deployment policy. Cross-instance byte sharing, custody delegation to third parties, and any custody-aware network protocol are unspecified. An unsupported surface fails explicitly or stays inert.
