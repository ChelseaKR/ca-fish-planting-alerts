"""scripts/preflight_app_store_live.py, run offline against a fake network.

No test here touches the network: ``http_get`` is replaced by a dictionary of
canned answers. Every negative control asserts that its sabotage changed the
input before it asserts that the preflight caught it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from cfpa import site

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "preflight_app_store_live.py"


def _load():
    spec = importlib.util.spec_from_file_location("preflight_app_store_live", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pre = _load()
PBX = pre.PBXPROJ.read_text(encoding="utf-8")
OWNER = pre.OWNER_STEPS.read_text(encoding="utf-8")
VERSION, BUILD = pre.docs_version_and_build(OWNER)


def _lookup(**over) -> bytes:
    app = {
        "trackId": int(site.APP_STORE_ID),
        "bundleId": pre.APP_BUNDLE_ID,
        "version": VERSION,
    }
    app.update(over)
    return json.dumps({"resultCount": 1, "results": [app]}).encode()


class FakeNet:
    def __init__(self, listing=200, lookup_status=200, lookup_body=None):
        self.calls: list[str] = []
        self.listing = listing
        self.lookup_status = lookup_status
        self.lookup_body = _lookup() if lookup_body is None else lookup_body

    def __call__(self, url: str):
        self.calls.append(url)
        if url == site.APP_STORE_CANONICAL_URL:
            return pre.Response(self.listing, b"<html></html>")
        if url.startswith("https://itunes.apple.com/lookup"):
            return pre.Response(self.lookup_status, self.lookup_body)
        raise AssertionError(f"unexpected request: {url}")


def _failed(results) -> list[str]:
    return [r.name for r in results if not r.ok]


@pytest.fixture(scope="module")
def surfaces():
    return pre.check_surfaces()


def test_everything_passes_when_the_store_agrees(surfaces):
    net = FakeNet()
    results = pre.run_all(net, pbxproj=PBX, owner_steps=OWNER)
    assert _failed(results) == []
    assert len(results) >= 8
    # read-only: two GETs, the listing and the lookup, nothing else
    assert net.calls == [
        site.APP_STORE_CANONICAL_URL,
        f"https://itunes.apple.com/lookup?id={site.APP_STORE_ID}&country=us",
    ]


def test_the_repo_docs_and_project_agree_today():
    versions, builds = pre.project_versions(PBX)
    assert (versions, builds) == ({VERSION}, {BUILD})


def test_surfaces_pass_on_and_off(surfaces):
    assert _failed(surfaces) == []
    assert len(surfaces) == 2


def test_the_listing_not_found_fails():
    results = pre.run_all(FakeNet(listing=404), pbxproj=PBX, owner_steps=OWNER)
    assert "listing opens" in _failed(results)


def test_lookup_failure_fails():
    net = FakeNet(lookup_status=503)
    assert "store lookup" in _failed(pre.run_all(net, pbxproj=PBX, owner_steps=OWNER))


def test_lookup_that_is_not_json_fails():
    net = FakeNet(lookup_body=b"<html>nope</html>")
    assert "store lookup" in _failed(pre.run_all(net, pbxproj=PBX, owner_steps=OWNER))


def test_lookup_with_no_result_fails():
    body = json.dumps({"resultCount": 0, "results": []}).encode()
    results = pre.run_all(FakeNet(lookup_body=body), pbxproj=PBX, owner_steps=OWNER)
    assert "store lists this app" in _failed(results)


def test_a_different_listing_id_fails():
    body = _lookup(trackId=6818637465)  # Queer Frame's
    assert body != _lookup()  # the sabotage landed
    results = pre.run_all(FakeNet(lookup_body=body), pbxproj=PBX, owner_steps=OWNER)
    assert "store lists this app" in _failed(results)


def test_a_different_bundle_id_fails():
    body = _lookup(bundleId="com.example.other")
    results = pre.run_all(FakeNet(lookup_body=body), pbxproj=PBX, owner_steps=OWNER)
    assert "store lists this app" in _failed(results)


def test_a_store_version_the_docs_do_not_name_fails():
    body = _lookup(version="0.9.0")
    assert body != _lookup()  # the sabotage landed
    results = pre.run_all(FakeNet(lookup_body=body), pbxproj=PBX, owner_steps=OWNER)
    assert "store version matches project and docs" in _failed(results)


def test_docs_that_name_another_build_fail():
    stale = OWNER.replace(f"`{VERSION}`, build `{BUILD}`", f"`{VERSION}`, build `1`")
    assert stale != OWNER  # the sabotage landed
    results = pre.run_all(FakeNet(), pbxproj=PBX, owner_steps=stale)
    assert "docs match the project" in _failed(results)


def test_docs_without_the_row_fail():
    gone = OWNER.replace("Version, build", "Edition")
    assert gone != OWNER  # the sabotage landed
    results = pre.run_all(FakeNet(), pbxproj=PBX, owner_steps=gone)
    assert "docs match the project" in _failed(results)


def test_a_project_with_two_builds_fails():
    split = PBX.replace(
        "CURRENT_PROJECT_VERSION = " + BUILD, "CURRENT_PROJECT_VERSION = 99", 1
    )
    assert split != PBX  # the sabotage landed
    results = pre.run_all(FakeNet(), pbxproj=split, owner_steps=OWNER)
    assert "project has one version and one build" in _failed(results)


def test_a_wrong_address_fails(monkeypatch):
    monkeypatch.setattr(
        site, "APP_STORE_CANONICAL_URL", "https://apps.apple.com/us/app/id1"
    )
    assert pre.check_address().ok is False


def test_a_half_on_site_fails(monkeypatch, surfaces):
    """If the banner stopped following the switch, the surfaces check says so."""
    from cfpa import launch_check

    real = launch_check.surface_problems

    def sabotaged(out, *, live, url=site.APP_STORE_CANONICAL_URL):
        found = real(out, live=live, url=url)
        return found + (["banner disagrees"] if live else [])

    monkeypatch.setattr(launch_check, "surface_problems", sabotaged)
    results = pre.check_surfaces()
    assert "site built on: every surface agrees" in _failed(results)
    assert "site built off: every surface agrees" not in _failed(results)


def test_http_get_refuses_a_plain_http_address():
    with pytest.raises(ValueError, match="https"):
        pre.http_get("http://apps.apple.com/us/app/id1")


def test_main_prints_a_verdict_and_exits_by_it(monkeypatch, capsys):
    monkeypatch.setattr(pre, "http_get", FakeNet())
    assert pre.main([]) == 0
    out = capsys.readouterr().out
    assert "READY to flip" in out
    word = "ON" if site.APP_STORE_LIVE_DEFAULT else "off"
    assert f"committed default (site.APP_STORE_LIVE_DEFAULT): {word}" in out
    monkeypatch.setattr(pre, "http_get", FakeNet(listing=500))
    assert pre.main([]) == 1
    assert "NOT READY" in capsys.readouterr().out
