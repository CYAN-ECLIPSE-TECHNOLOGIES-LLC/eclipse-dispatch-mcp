#!/usr/bin/env python3
"""Eclipse Dispatch MCP — v0.1.0, phases D0 + D1-core.

Powered by Cyan Eclipse Technologies (cetech.ai).

Eclipse Dispatch — the newsletter layer above the platforms: it drafts
once and syndicates the drafts to every sanctioned platform, unifies
the analytics, and watches your own subscriptions like a portfolio.
It never publishes without approval, and it never scrapes.

v0.1 SCOPE (spec: eclipse-dispatch-newsletter-spec-20261025):
  * D0 — analytics unification, read-only. Per-platform metric reads
    normalized for presentation but NEVER blended silently: every
    figure keeps its platform provenance and the platform's own
    definition. A combined figure is produced only when definitions
    are identical across sources; otherwise it is reported as null
    with the flag DEFINITIONS_DIFFER — flagged, never averaged.
  * D1-core — canonical draft -> per-platform DRAFTS via fixture
    adapters shaped like the sanctioned APIs (beehiiv API shape,
    Ghost Admin API shape; local stub HTTP servers in tests).
    Substack is READ-ONLY: it receives a paste pack (local files for
    owner in-app posting), never a write.
  * The canonical draft is VERSIONED and HASH-BOUND (the social-core
    pattern): approval binds to the content hash. ANY post-approval
    edit invalidates the approval — syndication recomputes the hash
    and refuses on mismatch.
  * beehiiv adapter has NO publish method (beehiiv's own design:
    drafts via API, publishing in-app). There is no auto-publish
    tool here, at any tier, for any platform.

LIVE WIRING IS OWNER-GATED WAVE 2: beehiiv signup is an open owner
item; no Ghost instance runs here. Adapters run against fixtures and
local stubs. Nothing in this process contacts a platform, sends
email, or publishes anything.

Receipts: every draft creation, approval, syndication (per platform)
and analytics run appends a hash-chained receipt — append-only,
verifiable, tamper-evident.

Transport: MCP over stdio (newline-delimited JSON-RPC 2.0), stdlib only.
State file: $ECLIPSE_DISPATCH_STATE or ./data/state.json beside this file.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import adapters as A  # noqa: E402

STATE_PATH = Path(os.environ.get(
    "ECLIPSE_DISPATCH_STATE",
    Path(__file__).parent / "data" / "state.json"))
PACK_ROOT = STATE_PATH.parent / "paste-packs"

PLATFORMS = ("beehiiv", "ghost", "substack")
CONTENT_FIELDS = ("title", "subtitle", "body", "canonical_url",
                  "tags", "audience", "variants")


class ToolError(Exception):
    pass


def now() -> int:
    return int(time.time())


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


# --------------------------------------------------------------------- state
def empty_state() -> dict:
    return {"drafts": {}, "receipts": []}


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return empty_state()


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=1))


# ------------------------------------------------------------------ receipts
def emit_receipt(state: dict, rtype: str, detail: dict) -> dict:
    """Append-only, hash-chained (house pattern)."""
    prev = state["receipts"][-1]["hash"] if state["receipts"] else "GENESIS"
    entry = {"seq": len(state["receipts"]) + 1, "ts": now(), "type": rtype,
             "prev_hash": prev, "detail": detail}
    entry["hash"] = sha(prev + canon({k: v for k, v in entry.items()
                                      if k != "hash"}))
    state["receipts"].append(entry)
    return entry


def verify_receipt_chain(receipts) -> bool:
    prev = "GENESIS"
    for e in receipts:
        if e.get("prev_hash") != prev:
            return False
        expect = sha(prev + canon({k: v for k, v in e.items() if k != "hash"}))
        if e.get("hash") != expect:
            return False
        prev = e["hash"]
    return True


# --------------------------------------------------------------------- drafts
def content_of(draft: dict) -> dict:
    return {k: draft.get(k) for k in CONTENT_FIELDS}


def content_hash(draft: dict) -> str:
    return sha(canon(content_of(draft)))


def draft_id_for(title: str, canonical_url: str) -> str:
    return "drf_" + sha(f"{title}|{canonical_url}")[:10]


def to_html(body: str) -> str:
    """Naive markdown-ish body -> simple HTML paragraphs (fixture-grade
    rendering; the platforms do their own rich rendering from drafts)."""
    paras = [p.strip() for p in body.split("\n\n") if p.strip()]
    return "\n".join(f"<p>{p}</p>" for p in paras)


def effective_for(draft: dict, platform: str) -> dict:
    """Canonical content merged with the platform's variant overrides."""
    eff = {k: draft.get(k) for k in
           ("title", "subtitle", "body", "canonical_url", "tags", "audience")}
    variant = (draft.get("variants") or {}).get(platform) or {}
    for k, v in variant.items():
        if k in eff:
            eff[k] = v
    eff["body_html"] = to_html(eff["body"])
    return eff


def adaptation_diffs(draft: dict, platform: str) -> list:
    """Every field where the platform's effective content differs from
    the canonical draft — the publisher sees every adaptation before
    approving (spec §4.2)."""
    eff = effective_for(draft, platform)
    diffs = []
    for k in ("title", "subtitle", "body", "tags", "audience"):
        if eff[k] != draft.get(k):
            diffs.append({"field": k, "canonical": draft.get(k),
                          "platform_value": eff[k],
                          "origin": "variant_override"})
    if platform == "substack":
        diffs.append({"field": "delivery", "canonical": "API draft",
                      "platform_value": "paste pack (no sanctioned write API)",
                      "origin": "platform_constraint"})
    if platform == "beehiiv":
        diffs.append({"field": "publish_step",
                      "canonical": "publish_assist to the sanctioned click",
                      "platform_value": "draft only — publish stays in-app by platform design",
                      "origin": "platform_constraint"})
    return diffs


def get_draft(state, draft_id):
    d = state["drafts"].get(draft_id)
    if not d:
        raise ToolError(f"unknown draft: {draft_id}")
    return d


def make_adapters(state):
    """Fixture transports by default; stub/real base URLs via env
    (ECLIPSE_DISPATCH_BEEHIIV_URL / _GHOST_URL) for stubbed tests and
    the future owner-gated live wiring."""
    def transport(platform):
        url = os.environ.get(f"ECLIPSE_DISPATCH_{platform.upper()}_URL")
        return A.HttpTransport(url) if url else A.FixtureTransport(platform)
    return {"beehiiv": A.BeehiivAdapter(transport("beehiiv")),
            "ghost": A.GhostAdapter(transport("ghost")),
            "substack": A.SubstackAdapter()}


# --------------------------------------------------------------------- tools
def t_draft_create(state, args):
    title = str(args["title"]).strip()
    body = str(args["body"])
    canonical_url = str(args.get("canonical_url") or "")
    draft_id = args.get("draft_id") or draft_id_for(title, canonical_url)
    existing = state["drafts"].get(draft_id)
    version = (existing["version"] + 1) if existing else 1
    draft = {
        "draft_id": draft_id, "version": version,
        "title": title, "subtitle": args.get("subtitle") or "",
        "body": body, "canonical_url": canonical_url,
        "tags": list(args.get("tags") or []),
        "audience": args.get("audience") or "free",
        "variants": args.get("variants") or {},
        "approval": None,  # any (re)creation resets approval: hash-bound
        "created_ts": now(),
    }
    draft["content_hash"] = content_hash(draft)
    state["drafts"][draft_id] = draft
    r = emit_receipt(state, "draft_created",
                     {"draft_id": draft_id, "version": version,
                      "content_hash": draft["content_hash"]})
    return {"draft_id": draft_id, "version": version,
            "content_hash": draft["content_hash"], "status": "unapproved",
            "receipt_seq": r["seq"],
            "note": "Canonical draft recorded. Approval binds to this "
                    "content hash; any edit creates a new version and "
                    "invalidates prior approval."}


def t_draft_preview(state, args):
    draft = get_draft(state, args["draft_id"])
    previews = {}
    for platform in PLATFORMS:
        eff = effective_for(draft, platform)
        previews[platform] = {
            "mode": "PREP_PACK" if platform == "substack" else "DRAFT_API",
            "title": eff["title"], "subtitle": eff["subtitle"],
            "body_preview": eff["body"][:280],
            "body_html_preview": eff["body_html"][:280],
            "tags": eff["tags"], "audience": eff["audience"],
            "canonical_url": eff["canonical_url"],
            "adaptation_diffs": adaptation_diffs(draft, platform)}
    r = emit_receipt(state, "preview_pack",
                     {"draft_id": draft["draft_id"],
                      "content_hash": draft["content_hash"]})
    return {"draft_id": draft["draft_id"], "version": draft["version"],
            "content_hash": draft["content_hash"],
            "approved": draft.get("approval") is not None,
            "previews": previews, "receipt_seq": r["seq"]}


def t_draft_approve(state, args):
    draft = get_draft(state, args["draft_id"])
    h = content_hash(draft)
    token = "apr_" + sha(canon({"draft_id": draft["draft_id"], "hash": h,
                                "version": draft["version"],
                                "approved_by": args.get("approved_by", "owner"),
                                "ts": now()}))[:20]
    draft["approval"] = {"token": token, "content_hash": h,
                         "version": draft["version"],
                         "approved_by": args.get("approved_by", "owner"),
                         "ts": now()}
    r = emit_receipt(state, "draft_approved",
                     {"draft_id": draft["draft_id"], "content_hash": h,
                      "version": draft["version"]})
    return {"draft_id": draft["draft_id"], "approval_token": token,
            "content_hash": h, "version": draft["version"],
            "receipt_seq": r["seq"],
            "note": "Approval is bound to this exact content hash. Any "
                    "edit invalidates it."}


def t_syndicate_drafts(state, args):
    draft = get_draft(state, args["draft_id"])
    approval = draft.get("approval")
    if not approval:
        raise ToolError("syndication refused: draft is not approved. "
                        "Review the preview pack and approve first "
                        "(review-first is standing law).")
    if args.get("approval_token") != approval["token"]:
        raise ToolError("syndication refused: approval_token does not "
                        "match the recorded approval.")
    current = content_hash(draft)
    if current != approval["content_hash"]:
        raise ToolError(
            "syndication refused: APPROVAL INVALIDATED — the draft's "
            f"content changed after approval (approved hash "
            f"{approval['content_hash'][:12]}…, current {current[:12]}…). "
            "Re-preview and re-approve the edited draft.")
    platforms = args.get("platforms") or list(PLATFORMS)
    adapters = make_adapters(state)
    results = []
    for platform in platforms:
        if platform not in PLATFORMS:
            raise ToolError(f"unknown platform: {platform}")
        eff = effective_for(draft, platform)
        if platform == "substack":
            res = adapters["substack"].paste_pack(
                eff, PACK_ROOT / draft["draft_id"])
        else:
            res = adapters[platform].create_draft(eff)
        r = emit_receipt(state, "syndicated_draft",
                         {"draft_id": draft["draft_id"], "platform": platform,
                          "mode": res["mode"], "remote_id": res.get("remote_id"),
                          "content_hash": current})
        results.append({**res, "receipt_seq": r["seq"]})
    return {"draft_id": draft["draft_id"], "content_hash": current,
            "results": results,
            "note": "Drafts only. beehiiv publishing remains the owner's "
                    "in-app act; Substack received a paste pack, not a write."}


def t_analytics_report(state, args):
    platforms = args.get("platforms") or list(PLATFORMS)
    adapters = make_adapters(state)
    by_metric = {}
    sources = {}
    for platform in platforms:
        data = adapters[platform].analytics()
        sources[platform] = {"period": data["period"], "source": data["source"]}
        for m in data["metrics"]:
            by_metric.setdefault(m["key"], []).append({
                "platform": platform, "value": m["value"], "unit": m["unit"],
                "platform_metric": m["platform_metric"],
                "definition": m["definition"]})
    metrics = {}
    for key, figures in sorted(by_metric.items()):
        definitions = {f["definition"] for f in figures}
        units = {f["unit"] for f in figures}
        combined, flag = None, None
        if len(figures) > 1:
            if len(definitions) == 1 and len(units) == 1 \
                    and figures[0]["unit"] == "count":
                combined = sum(f["value"] for f in figures)
            elif len(definitions) == 1 and len(units) == 1:
                combined = round(sum(f["value"] for f in figures), 2)
                flag = ("combined is a SUM of identical-definition parts "
                        "(e.g. rates are not summed — see figures)")
                if figures[0]["unit"] == "percent":
                    combined, flag = None, (
                        "DEFINITIONS_MATCH_BUT_RATE: percentages are never "
                        "summed or averaged across platforms")
            else:
                flag = ("DEFINITIONS_DIFFER: definitions differ across "
                        "platforms — figures are NOT blended (spec §4.5)")
        metrics[key] = {"figures": figures, "combined": combined,
                        "flag": flag}
    r = emit_receipt(state, "analytics_report",
                     {"platforms": platforms, "metrics": sorted(metrics)})
    return {"sources": sources, "metrics": metrics, "receipt_seq": r["seq"],
            "note": "Every figure carries its platform provenance and "
                    "definition. Nothing is silently blended."}


def t_receipt_list(state, args):
    limit = int(args.get("limit", 50))
    receipts = state["receipts"][-limit:]
    return {"receipts": receipts, "count": len(state["receipts"]),
            "chain_valid": verify_receipt_chain(state["receipts"])}


TOOLS = {
    "draft_create": (t_draft_create, "Create (or re-version) the canonical draft: title, body, subtitle, canonical_url (home), tags, audience, per-platform variants. Hash-bound: the returned content_hash is what approval binds to. Re-creating an existing draft_id makes a NEW version and resets approval to none.",
                     {"title": {"type": "string"}, "body": {"type": "string"},
                      "subtitle": {"type": "string"}, "canonical_url": {"type": "string"},
                      "tags": {"type": "array"}, "audience": {"type": "string"},
                      "variants": {"type": "object"}, "draft_id": {"type": "string"}}, ["title", "body"]),
    "draft_preview": (t_draft_preview, "The review artifact: per-platform rendered previews + every adaptation diff against the canonical draft (variant overrides and platform constraints, e.g. Substack = paste pack, beehiiv = draft-only).",
                      {"draft_id": {"type": "string"}}, ["draft_id"]),
    "draft_approve": (t_draft_approve, "Record owner approval of the current version. Returns an approval token bound to the content hash; any later edit invalidates it.",
                      {"draft_id": {"type": "string"}, "approved_by": {"type": "string"}}, ["draft_id"]),
    "syndicate_drafts": (t_syndicate_drafts, "Fan the approved draft out to per-platform DRAFTS via the fixture adapters (beehiiv/Ghost draft APIs-shaped; Substack gets a paste pack — read-only adapter, never a write). Requires the approval token and an un-invalidated approval hash. There is no publish path.",
                         {"draft_id": {"type": "string"}, "approval_token": {"type": "string"},
                          "platforms": {"type": "array"}}, ["draft_id", "approval_token"]),
    "analytics_report": (t_analytics_report, "D0 unified analytics (read-only): per-platform figures normalized by metric key, each carrying platform provenance + the platform's own definition. Combined figures appear ONLY where definitions are identical; differing definitions are flagged DEFINITIONS_DIFFER, never averaged.",
                         {"platforms": {"type": "array"}}, []),
    "receipt_list": (t_receipt_list, "List hash-chained receipts (draft creations, approvals, syndications per platform, analytics runs) and verify the chain.",
                     {"limit": {"type": "integer"}}, []),
}


def tool_list():
    return [{"name": name, "description": desc,
             "inputSchema": {"type": "object", "properties": props, "required": req}}
            for name, (_, desc, props, req) in TOOLS.items()]


def handle(req: dict):
    method, rid = req.get("method", ""), req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": req.get("params", {}).get("protocolVersion", "2025-03-26"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "eclipse-dispatch", "version": "0.1.0"}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": tool_list()}}
    if method == "tools/call":
        name = req["params"]["name"]
        args = req["params"].get("arguments", {})
        if name not in TOOLS:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
        state = load_state()
        try:
            out = TOOLS[name][0](state, args)
            save_state(state)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(out, indent=1)}]}}
        except (ToolError, A.ReadOnlyRefusal) as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}}
    if rid is not None:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return None  # notification


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            resp = handle(json.loads(line))
        except Exception as e:  # never crash the transport
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
