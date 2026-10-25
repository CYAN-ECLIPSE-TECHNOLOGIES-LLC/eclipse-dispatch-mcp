"""Eclipse Dispatch — platform adapters (v0.1, D0 + D1-core).

Powered by Cyan Eclipse Technologies (cetech.ai).

Every adapter integrates through a SANCTIONED interface shape only:
official REST APIs (beehiiv, Ghost Admin API) or public feeds offered
for consumption (Substack RSS). v0.1 runs them against FIXTURES and
local stub HTTP servers shaped like the real APIs — live wiring is
owner-gated Wave 2 (beehiiv signup pending; no Ghost instance here).

Hard postures, by spec (eclipse-dispatch-newsletter-spec §3/§4/§7):
  * beehiiv adapter creates DRAFTS ONLY. It has no publish method —
    beehiiv's own official MCP also stops at drafts; publishing is
    the publisher's in-app act. The absence is deliberate and tested.
  * Substack adapter is READ-ONLY. No sanctioned write surface
    exists (no draft creation, no post management, no Notes). Any
    write attempt raises a NAMED refusal (ReadOnlyRefusal). Substack
    receives paste-ready packs (local files the owner posts in-app,
    as TWR packs work today) — never a platform write.
  * No scraping anywhere. Public RSS of the owner's OWN publication
    is consumption as offered, at human scale.
"""
import json
import threading
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


class ReadOnlyRefusal(Exception):
    """Raised when a write is attempted against the read-only
    Substack adapter. The refusal is named on every surface."""


# ------------------------------------------------------------------ transports
class HttpTransport:
    """Minimal JSON-over-HTTP client (stdlib urllib). Used against the
    local stub servers in tests; the base URL shape matches the real
    platform APIs."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer fixture-token"},
            method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get(self, path: str) -> dict:
        req = urllib.request.Request(
            self.base_url + path,
            headers={"Authorization": "Bearer fixture-token"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))


class FixtureTransport:
    """In-process stand-in with the same call signature as
    HttpTransport. Records every call (the receipt trail in tests)
    and answers from the shipped fixtures. Used by the stdio server
    when no stub URL is configured."""

    def __init__(self, platform: str):
        self.platform = platform
        self.calls = []

    def post(self, path: str, payload: dict) -> dict:
        self.calls.append({"method": "POST", "path": path, "payload": payload})
        if self.platform == "beehiiv":
            return {"data": {"id": f"fixture-beehiiv-post-{len(self.calls)}",
                             "status": "draft",
                             "title": payload.get("title")}}
        if self.platform == "ghost":
            post = payload["posts"][0]
            return {"posts": [{"id": f"fixture-ghost-post-{len(self.calls)}",
                               "status": "draft", "title": post.get("title")}]}
        raise ReadOnlyRefusal(
            f"READ-ONLY adapter: {self.platform} accepts no POST writes "
            f"(attempted {path}). No sanctioned write surface exists.")

    def get(self, path: str) -> dict:
        self.calls.append({"method": "GET", "path": path})
        return {}


def load_analytics(platform: str) -> dict:
    """D0 reads: per-platform analytics fixture. Each metric carries
    the platform's own name AND definition — unification never strips
    them (spec §4.5)."""
    return json.loads((FIXTURES / f"analytics_{platform}.json").read_text())


# --------------------------------------------------------------------- beehiiv
class BeehiivAdapter:
    """beehiiv-shaped adapter. Creates DRAFTS ONLY — deliberately no
    publish/send method exists on this class (spec §3: beehiiv's own
    design keeps publishing in-app)."""

    PLATFORM = "beehiiv"
    PUB_ID = "fixture-pub"

    def __init__(self, transport):
        self.transport = transport

    def create_draft(self, effective: dict) -> dict:
        payload = {
            "title": effective["title"],
            "subtitle": effective.get("subtitle") or "",
            "content_html": effective["body_html"],
            "status": "draft",  # the only status this adapter can set
            "audience": effective.get("audience", "free"),
        }
        resp = self.transport.post(
            f"/v2/publications/{self.PUB_ID}/posts", payload)
        data = resp.get("data", {})
        return {"platform": self.PLATFORM, "remote_id": data.get("id"),
                "remote_status": data.get("status"), "mode": "DRAFT_API"}

    def analytics(self) -> dict:
        return load_analytics(self.PLATFORM)


# ----------------------------------------------------------------------- ghost
class GhostAdapter:
    """Ghost Admin-API-shaped adapter. Creates drafts via the Admin
    API shape (POST /ghost/api/admin/posts/). Publishing is not
    exposed in v0.1: publish stays an owner-approved, per-item act
    (spec §4.4), and the fixture scope is draft syndication."""

    PLATFORM = "ghost"

    def __init__(self, transport):
        self.transport = transport

    def create_draft(self, effective: dict) -> dict:
        payload = {"posts": [{
            "title": effective["title"],
            "html": effective["body_html"],
            "status": "draft",
            "tags": [{"name": t} for t in effective.get("tags", [])],
            "canonical_url": effective.get("canonical_url") or None,
        }]}
        resp = self.transport.post("/ghost/api/admin/posts/?source=html",
                                   payload)
        post = (resp.get("posts") or [{}])[0]
        return {"platform": self.PLATFORM, "remote_id": post.get("id"),
                "remote_status": post.get("status"), "mode": "DRAFT_API"}

    def analytics(self) -> dict:
        return load_analytics(self.PLATFORM)


# -------------------------------------------------------------------- substack
class SubstackAdapter:
    """Substack adapter — READ-ONLY by construction (spec §3/§4.6).

    Sanctioned surface used: public RSS of the owner's own
    publication + analytics fixture reads shaped like the official
    MCP's read-only analytics. There is NO write path: create_draft
    and friends raise ReadOnlyRefusal, named on the surface.

    What Substack gets instead of a write: a PASTE PACK — local
    files (post.md, checklist.txt) the owner posts in-app by hand,
    exactly as TWR packs work today."""

    PLATFORM = "substack"

    def __init__(self, feed_path: Path = None):
        self.feed_path = feed_path or (FIXTURES / "substack_feed.xml")

    # -- sanctioned reads ------------------------------------------------
    def analytics(self) -> dict:
        return load_analytics(self.PLATFORM)

    def ingest_own_feed(self) -> dict:
        """Parse the owner's own publication RSS (consumption as
        offered). Returns items with title/link/date/summary."""
        tree = ET.parse(self.feed_path)
        items = []
        for item in tree.getroot().iter("item"):
            def txt(tag):
                el = item.find(tag)
                return (el.text or "").strip() if el is not None else ""
            items.append({"title": txt("title"), "link": txt("link"),
                          "pub_date": txt("pubDate"),
                          "summary": txt("description")})
        return {"platform": self.PLATFORM, "source": self.feed_path.name,
                "items": items, "count": len(items)}

    # -- the refusal ------------------------------------------------------
    def _refuse(self, attempted: str):
        raise ReadOnlyRefusal(
            f"Substack adapter is READ-ONLY: '{attempted}' refused. No "
            "sanctioned Substack write surface exists (no draft creation, "
            "post management, or Notes API — spec §3/§4.6). Substack "
            "receives a paste pack for owner in-app posting instead.")

    def create_draft(self, effective: dict) -> dict:
        self._refuse("create_draft")

    def publish(self, *a, **k):
        self._refuse("publish")

    # -- paste pack (a local export, NOT a platform write) -----------------
    def paste_pack(self, effective: dict, pack_dir: Path) -> dict:
        pack_dir.mkdir(parents=True, exist_ok=True)
        post = pack_dir / "post.md"
        post.write_text(
            f"# {effective['title']}\n\n"
            + (f"*{effective['subtitle']}*\n\n" if effective.get("subtitle") else "")
            + effective["body"] + "\n")
        checklist = pack_dir / "checklist.txt"
        checklist.write_text(
            "SUBSTACK PASTE PACK — owner posts in-app (no sanctioned write API).\n"
            "1. Substack > New post. Paste post.md content (title, subtitle, body).\n"
            f"2. Audience: {effective.get('audience', 'free')}.\n"
            f"3. Canonical home: {effective.get('canonical_url') or '(none set)'}"
            " — syndicated copies defer to the home original.\n"
            "4. Publish in-app when ready; Dispatch records the pack, not the click.\n")
        return {"platform": self.PLATFORM, "mode": "PREP_PACK",
                "pack_dir": str(pack_dir),
                "files": [post.name, checklist.name],
                "remote_id": None, "remote_status": "not_written"}


# ------------------------------------------------------------- stub HTTP servers
def _stub_server(handler_cls):
    srv = HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def make_beehiiv_stub():
    """Local HTTP server shaped like the beehiiv v2 API. Records
    requests on server.requests for test assertions."""
    class H(BaseHTTPRequestHandler):
        requests = []

        def log_message(self, *a):
            pass

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n) or b"{}")
            H.requests.append({"path": self.path, "payload": payload})
            if "/posts" in self.path:
                if payload.get("status") != "draft":
                    return self._json(422, {"error": "stub accepts drafts only"})
                return self._json(201, {"data": {
                    "id": f"stub-beehiiv-{len(H.requests)}",
                    "status": "draft", "title": payload.get("title")}})
            return self._json(404, {"error": "unknown path"})

    srv, url = _stub_server(H)
    srv.requests = H.requests
    return srv, url


def make_ghost_stub():
    """Local HTTP server shaped like the Ghost Admin API."""
    class H(BaseHTTPRequestHandler):
        requests = []

        def log_message(self, *a):
            pass

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n) or b"{}")
            H.requests.append({"path": self.path, "payload": payload})
            if self.path.startswith("/ghost/api/admin/posts"):
                post = (payload.get("posts") or [{}])[0]
                if post.get("status") != "draft":
                    return self._json(422, {"errors": [
                        {"message": "stub accepts drafts only"}]})
                return self._json(201, {"posts": [{
                    "id": f"stub-ghost-{len(H.requests)}",
                    "status": "draft", "title": post.get("title"),
                    "slug": "fixture-post"}]})
            return self._json(404, {"errors": [{"message": "unknown path"}]})

    srv, url = _stub_server(H)
    srv.requests = H.requests
    return srv, url
