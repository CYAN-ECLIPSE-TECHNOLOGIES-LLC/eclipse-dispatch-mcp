#!/usr/bin/env python3
# Eclipse Dispatch MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# Eclipse Dispatch v0.1 (D0 + D1-core) — unit tests.

"""Eclipse Dispatch v0.1 (D0 + D1-core) — unit tests.
Run: python3 -m unittest discover tests"""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import adapters as A  # noqa: E402
import server as S  # noqa: E402

ROOT = Path(__file__).parent.parent

DRAFT_ARGS = {
    "title": "The Quiet Week in Loud Markets",
    "subtitle": "Fixture edition",
    "body": "First paragraph of the fixture dispatch.\n\nSecond paragraph, with the actual argument.",
    "canonical_url": "https://fixture.example.com/articles/quiet-week",
    "tags": ["markets", "fixture"],
    "audience": "free",
    "variants": {"substack": {"subtitle": "Fixture edition (Substack cut)"}},
}


def created(state=None):
    st = state if state is not None else S.empty_state()
    out = S.t_draft_create(st, dict(DRAFT_ARGS))
    return st, out


class TestHashBoundApproval(unittest.TestCase):
    def test_create_is_unapproved_with_hash(self):
        st, out = created()
        self.assertEqual(out["status"], "unapproved")
        d = st["drafts"][out["draft_id"]]
        self.assertIsNone(d["approval"])
        self.assertEqual(d["content_hash"], out["content_hash"])
        self.assertEqual(d["content_hash"], S.content_hash(d))

    def test_edit_after_approval_invalidates(self):
        st, out = created()
        did = out["draft_id"]
        appr = S.t_draft_approve(st, {"draft_id": did})
        # post-approval edit: re-version the draft with a changed body
        S.t_draft_create(st, {**DRAFT_ARGS, "draft_id": did,
                              "body": "EDITED after approval."})
        d = st["drafts"][did]
        self.assertEqual(d["version"], 2)
        self.assertIsNone(d["approval"])  # approval did not survive the edit
        with self.assertRaises(S.ToolError) as ctx:
            S.t_syndicate_drafts(st, {"draft_id": did,
                                      "approval_token": appr["approval_token"]})
        self.assertIn("not approved", str(ctx.exception))

    def test_tampered_content_hash_mismatch_named(self):
        st, out = created()
        did = out["draft_id"]
        appr = S.t_draft_approve(st, {"draft_id": did})
        st["drafts"][did]["body"] = "silently tampered"  # no re-version
        with self.assertRaises(S.ToolError) as ctx:
            S.t_syndicate_drafts(st, {"draft_id": did,
                                      "approval_token": appr["approval_token"]})
        self.assertIn("APPROVAL INVALIDATED", str(ctx.exception))

    def test_syndicate_requires_approval_and_token(self):
        st, out = created()
        did = out["draft_id"]
        with self.assertRaises(S.ToolError):
            S.t_syndicate_drafts(st, {"draft_id": did, "approval_token": "x"})
        S.t_draft_approve(st, {"draft_id": did})
        with self.assertRaises(S.ToolError) as ctx:
            S.t_syndicate_drafts(st, {"draft_id": did,
                                      "approval_token": "apr_wrong"})
        self.assertIn("does not match", str(ctx.exception))


class TestAdapters(unittest.TestCase):
    def test_beehiiv_has_no_publish_method(self):
        adapter = A.BeehiivAdapter(A.FixtureTransport("beehiiv"))
        for name in ("publish", "publish_post", "send", "send_post",
                     "create_and_publish"):
            self.assertFalse(hasattr(adapter, name),
                             f"beehiiv adapter must not expose {name}")
        # and the server exposes no publish tool at all
        self.assertFalse(any("publish" in name for name in S.TOOLS),
                         "no tool name may offer publishing")

    def test_beehiiv_draft_via_stub_http(self):
        srv, url = A.make_beehiiv_stub()
        try:
            adapter = A.BeehiivAdapter(A.HttpTransport(url))
            res = adapter.create_draft({
                "title": "T", "subtitle": "", "body_html": "<p>x</p>",
                "audience": "free"})
            self.assertEqual(res["remote_status"], "draft")
            self.assertEqual(srv.requests[0]["payload"]["status"], "draft")
            self.assertIn("/v2/publications/", srv.requests[0]["path"])
        finally:
            srv.shutdown()

    def test_ghost_draft_via_stub_http(self):
        srv, url = A.make_ghost_stub()
        try:
            adapter = A.GhostAdapter(A.HttpTransport(url))
            res = adapter.create_draft({
                "title": "T", "body_html": "<p>x</p>", "tags": ["a"],
                "canonical_url": "https://fixture.example.com/x"})
            self.assertEqual(res["remote_status"], "draft")
            self.assertTrue(srv.requests[0]["path"].startswith(
                "/ghost/api/admin/posts"))
            self.assertEqual(
                srv.requests[0]["payload"]["posts"][0]["status"], "draft")
        finally:
            srv.shutdown()

    def test_substack_read_only_named_refusal(self):
        adapter = A.SubstackAdapter()
        with self.assertRaises(A.ReadOnlyRefusal) as ctx:
            adapter.create_draft({"title": "x", "body": "y"})
        msg = str(ctx.exception)
        self.assertIn("READ-ONLY", msg)
        self.assertIn("create_draft", msg)
        with self.assertRaises(A.ReadOnlyRefusal):
            adapter.publish()

    def test_substack_feed_ingest(self):
        out = A.SubstackAdapter().ingest_own_feed()
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["items"][0]["title"],
                         "Markets Held Their Breath This Week")


class TestSyndication(unittest.TestCase):
    def test_full_flow_fixture_adapters(self):
        st, out = created()
        did = out["draft_id"]
        appr = S.t_draft_approve(st, {"draft_id": did})
        res = S.t_syndicate_drafts(
            st, {"draft_id": did, "approval_token": appr["approval_token"]})
        by_platform = {r["platform"]: r for r in res["results"]}
        self.assertEqual(by_platform["beehiiv"]["remote_status"], "draft")
        self.assertEqual(by_platform["ghost"]["remote_status"], "draft")
        sub = by_platform["substack"]
        self.assertEqual(sub["mode"], "PREP_PACK")
        self.assertEqual(sub["remote_status"], "not_written")
        pack = Path(sub["pack_dir"])
        self.assertTrue((pack / "post.md").exists())
        self.assertTrue((pack / "checklist.txt").exists())
        types = [r["type"] for r in st["receipts"]]
        self.assertEqual(types.count("syndicated_draft"), 3)
        self.assertTrue(S.verify_receipt_chain(st["receipts"]))

    def test_preview_shows_adaptation_diffs(self):
        st, out = created()
        prev = S.t_draft_preview(st, {"draft_id": out["draft_id"]})
        sub_diffs = prev["previews"]["substack"]["adaptation_diffs"]
        fields = {d["field"] for d in sub_diffs}
        self.assertIn("subtitle", fields)   # variant override surfaced
        self.assertIn("delivery", fields)   # platform constraint surfaced
        bee_diffs = prev["previews"]["beehiiv"]["adaptation_diffs"]
        self.assertIn("publish_step", {d["field"] for d in bee_diffs})
        self.assertFalse(prev["approved"])


class TestAnalytics(unittest.TestCase):
    def test_definitions_labeled_and_never_blended(self):
        st = S.empty_state()
        rep = S.t_analytics_report(st, {})
        open_rate = rep["metrics"]["open_rate"]
        defs = {f["definition"] for f in open_rate["figures"]}
        self.assertEqual(len(defs), 3)  # three distinct definitions survive
        joined = " ".join(defs)
        self.assertIn("Apple Mail Privacy Protection", joined)
        self.assertIn("do not blend", joined.lower())
        self.assertIsNone(open_rate["combined"])
        self.assertIn("DEFINITIONS_DIFFER", open_rate["flag"])
        for f in open_rate["figures"]:
            self.assertIn("platform", f)
            self.assertIn("definition", f)
            self.assertIn("platform_metric", f)

    def test_identical_definition_counts_combine(self):
        st = S.empty_state()
        rep = S.t_analytics_report(st, {})
        subs = rep["metrics"]["subscribers"]
        self.assertEqual(subs["combined"], 1240 + 865 + 2210)
        self.assertIsNone(subs["flag"])

    def test_revenue_definitions_differ_flagged(self):
        st = S.empty_state()
        rep = S.t_analytics_report(st, {})
        rev = rep["metrics"]["revenue"]
        self.assertIsNone(rev["combined"])
        self.assertIn("DEFINITIONS_DIFFER", rev["flag"])


class TestReceipts(unittest.TestCase):
    def test_chain_verifies_and_tamper_detected(self):
        st, out = created()
        did = out["draft_id"]
        appr = S.t_draft_approve(st, {"draft_id": did})
        S.t_syndicate_drafts(st, {"draft_id": did,
                                  "approval_token": appr["approval_token"]})
        lst = S.t_receipt_list(st, {})
        self.assertTrue(lst["chain_valid"])
        self.assertGreaterEqual(lst["count"], 5)
        st["receipts"][1]["detail"]["content_hash"] = "0" * 64
        self.assertFalse(S.verify_receipt_chain(st["receipts"]))


if __name__ == "__main__":
    unittest.main()

# Eclipse Dispatch MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
