# Eclipse Dispatch MCP

**Powered by Cyan Eclipse Technologies** — https://cetech.ai

**Eclipse Dispatch — the newsletter layer above the platforms: it drafts once and syndicates the drafts to every sanctioned platform, unifies the analytics, and watches your own subscriptions like a portfolio. It never publishes without approval, and it never scrapes.**

## Why this exists

A publisher multi-homed across beehiiv, Ghost, and Substack writes once and re-enters everywhere, then reads three dashboards with three different definitions of an "open." Each platform's own tooling stops at its own wall: Substack's official MCP is read-only analytics gated to Bestseller admins; beehiiv's official MCP drafts into beehiiv only. Dispatch is the cross-platform layer none of them will build — one canonical draft, per-platform drafts via sanctioned routes, analytics unified without silent blending, and review-first as a property of the code, not a policy memo.

## Status — honest labels

v0.1.0, phases **D0 + D1-core**. **Bench pending — no certification claimed.** Local stdio transport, Python stdlib only. **Adapters run against shipped fixtures and local stub HTTP servers shaped like the real APIs — nothing in this build contacts a platform.** Live wiring is **owner-gated Wave 2**: the beehiiv signup is an open owner item, and no Ghost instance runs here. The reader face (spec §5, phase D2 — subscription portfolio, renewal radar, engagement truth) is **not in v0.1**; neither is the §4.6 unofficial-endpoint module, which the spec recommends not building in v1 at all.

## Tools (6)

| Tool | What it does |
|---|---|
| `draft_create` | Create the **canonical draft** (title, body, subtitle, `canonical_url` pointing home, tags, audience, per-platform variants). Versioned and **hash-bound**: returns the `content_hash` approval will bind to. Re-creating an existing `draft_id` makes a **new version and resets approval to none**. |
| `draft_preview` | The review artifact: per-platform rendered previews plus **every adaptation diff** vs the canonical draft — variant overrides *and* platform constraints (Substack = paste pack; beehiiv = draft-only, publish in-app). |
| `draft_approve` | Record owner approval; returns a token **bound to the content hash**. |
| `syndicate_drafts` | Fan the approved draft out: beehiiv/Ghost **drafts** via the API-shaped adapters; Substack gets a **paste pack** (local files the owner posts in-app). Requires the approval token **and** an un-invalidated hash. Receipt per platform. |
| `analytics_report` | D0 unified analytics, read-only. Figures normalized by metric key, each carrying **platform provenance + the platform's own definition**. A combined figure appears **only** where definitions are identical across sources; otherwise `combined: null` flagged `DEFINITIONS_DIFFER` — flagged, never averaged. |
| `receipt_list` | Hash-chained receipts (drafts, approvals, syndications, analytics runs) + chain verification. |

## The invariants (encoded + tested)

- **Hash-bound approval.** Approval binds to the canonical draft's content hash. *Any* post-approval edit — a new version, or a silent in-place tamper — invalidates it; syndication recomputes the hash and refuses by name. There is no path from "edited" to "sent" that passes through a stale approval.
- **The beehiiv adapter has no publish method.** Deliberate, mirroring the platform's own design (its official MCP also stops at drafts; publishing is the publisher's in-app act). A unit test asserts the method's absence. The server exposes **no publish tool at all** — no auto-publish, at any tier, for any platform.
- **The Substack adapter is read-only.** No sanctioned write surface exists, so write attempts raise a **named refusal** (`ReadOnlyRefusal`: "Substack adapter is READ-ONLY…"). Substack receives paste packs, never writes. The spec's unofficial-endpoint module is **not built** (spec decision 3 recommendation: not in v1) — its absence changes nothing.
- **Analytics never blend silently.** Three platforms define "open rate" over three different populations (the fixtures say so, in each definition). Dispatch labels every figure and refuses to average across definitions.
- **No scraping.** Public RSS of the owner's *own* publication is consumption as offered; bulk extraction does not exist here (spec §7).

## Receipts

Draft creations, preview packs, approvals, per-platform syndications, and analytics runs append **hash-chained receipts** — append-only and machine-verifiable (`verify_receipt_chain`); tampering with any entry breaks the chain and is detected by test.

## Run it

```bash
python3 server.py                      # MCP over stdio, stdlib only
python3 smoke.py                       # end-to-end smoke over real stdio (temp state, fixture adapters)
python3 -m unittest discover -s tests  # 15 tests
```

State persists in `data/state.json` beside the server (override with `ECLIPSE_DISPATCH_STATE`); paste packs land in `data/paste-packs/`. `data/` is gitignored. Adapter base URLs can be pointed at stub (or, in Wave 2, real) endpoints via `ECLIPSE_DISPATCH_BEEHIIV_URL` / `ECLIPSE_DISPATCH_GHOST_URL`; with none set, in-process fixture transports answer.

### Fixtures

`fixtures/` ships per-platform analytics (each metric with the platform's own name and definition — the beehiiv and Ghost revenue figures deliberately use *different* definitions, period gross vs MRR, so the no-blending rule has something honest to catch) and `substack_feed.xml`, the owner's own publication RSS in fixture form. Stub servers shaped like the beehiiv v2 API and the Ghost Admin API live in `adapters.py` and are exercised over real local HTTP by the tests.

## Roadmap (per spec)

- **D2** — reader face: subscription portfolio graph, renewal radar, engagement truth, cancel prep (own data only, strictest data tier).
- **D3** — Substack depth *as the sanctioned surface grows* — design waits for sanctioned writes; no scraping milestone exists.
- **Wave 2 (owner-gated)** — live beehiiv wiring after the owner's signup; live Ghost against a real instance.

## License / attribution

A Cyan Eclipse Technologies product. The "Powered by Cyan Eclipse Technologies" attribution travels with it.
