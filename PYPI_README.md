# eclipse-dispatch

**What this is:** `eclipse-dispatch` is the MCP server edition of
**Eclipse Dispatch** — Cyan Eclipse Technologies' newsletter layer
above the platforms: it drafts once and syndicates the drafts to every
sanctioned platform, unifies the analytics, and watches your own
subscriptions like a portfolio.

**What this is not:** it **never publishes** — there is no publish
tool, at any tier, for any platform — and it never scrapes. In v0.1
the adapters run against shipped fixtures and local stub HTTP servers
shaped like the real APIs; nothing contacts a platform.

## Use

```console
$ pip install eclipse-dispatch
$ eclipse-dispatch          # MCP server over stdio
```

Or run it as a container: `ghcr.io/cyan-eclipse-technologies-llc/eclipse-dispatch-mcp:0.1.0`.

Local stdio transport, Python stdlib only.

## Tools (6)

| Tool | What it does |
|---|---|
| `draft_create` | Create the **canonical draft** (title, body, subtitle, canonical URL, tags, audience, per-platform variants). Versioned and **hash-bound**: returns the `content_hash` approval will bind to. |
| `draft_preview` | Per-platform rendered previews plus **every adaptation diff** vs the canonical draft. |
| `draft_approve` | Record owner approval; returns a token **bound to the content hash**. |
| `syndicate_drafts` | Fan the approved draft out: beehiiv/Ghost **drafts** via API-shaped adapters; Substack gets a **paste pack**. Requires the approval token and an un-invalidated hash. Receipt per platform. |
| `analytics_report` | Unified analytics, read-only. Figures carry platform provenance + the platform's own definition; a combined figure appears **only** where definitions are identical, otherwise flagged `DEFINITIONS_DIFFER` — never silently averaged. |
| `receipt_list` | Hash-chained receipts (drafts, approvals, syndications, analytics runs) + chain verification. |

## Honest scope

- **Hash-bound approval.** Any post-approval edit invalidates the
  approval; syndication recomputes the hash and refuses by name.
- **The beehiiv adapter has no publish method** — deliberately, mirroring
  the platform's own design. **The Substack adapter is read-only**;
  write attempts raise a named refusal.
- Live platform wiring is owner-gated later-phase scope and is **not**
  in v0.1.

Powered by Cyan Eclipse Technologies LLC (cetech.ai) — a Veteran-Owned
Small Business. MIT licensed.
