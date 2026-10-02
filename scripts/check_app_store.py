#!/usr/bin/env python3
"""App Store readiness and release preflight for the iOS app.

Two modes:

- With no tag (`make appstore`, so `make verify`): the readiness audit. It
  reads the files App Store Connect and App Review judge the binary by and
  fails on anything that would bounce an upload or contradict the listing:

  - every target shares one MARKETING_VERSION and one integer
    CURRENT_PROJECT_VERSION (an extension whose version differs from its
    app is rejected on upload), and both Info.plists take their versions
    from those build settings;
  - every target is iPhone-only (TARGETED_DEVICE_FAMILY = 1) and signs with
    team 6X5YH93QNM, never the enrollment ID;
  - the project has no remote Swift package, and no Swift file imports a
    module outside Apple's SDK and the local PlantingCore package, so no
    analytics or tracking SDK can arrive unnoticed;
  - Info.plist declares export compliance (ITSAppUsesNonExemptEncryption
    false), a launch screen, and no background mode beyond the refresh task;
  - no entitlements file asks for push (aps-environment);
  - both privacy manifests say no tracking, no tracking domains and no
    collected data, and every required-reason API the Swift sources call
    has its category declared in the manifest (Apple rejects an upload
    that calls one undeclared);
  - the app icon set has every file it names, at the pixel size it names,
    with no alpha channel, including the 1024x1024 marketing icon.

- With `--release-tag vX.Y.Z` (the release workflow): the preflight. The tag
  must be stable SemVer equal to MARKETING_VERSION, the build number must be
  higher than the one at every earlier `v*` tag passed with
  `--earlier-pbxproj` (App Store Connect refuses a reused build number),
  and CHANGELOG.md must have a non-empty `## [X.Y.Z]` section, which
  `--notes-out` writes as the release notes.

`--self-test` feeds each check an input it must reject and one it must
accept, and exits non-zero if any check fails to discriminate, so a check
that has quietly stopped matching cannot report a ready app.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import re
import struct
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
IOS = ROOT / "ios"
PBXPROJ = IOS / "CAFishPlanting.xcodeproj" / "project.pbxproj"
APP_INFO = IOS / "CAFishPlanting" / "Resources" / "Info.plist"
WIDGET_INFO = IOS / "CAFishPlantingWidgets" / "Info.plist"
MANIFESTS = (
    IOS / "CAFishPlanting" / "Resources" / "PrivacyInfo.xcprivacy",
    IOS / "CAFishPlantingWidgets" / "PrivacyInfo.xcprivacy",
)
ICONSET = (
    IOS / "CAFishPlanting" / "Resources" / "Assets.xcassets" / "AppIcon.appiconset"
)
# Code that ships in the app bundle. Tests and UI tests never ship.
SHIPPED_SWIFT = (
    IOS / "CAFishPlanting",
    IOS / "CAFishPlantingWidgets",
    IOS / "PlantingCore" / "Sources",
)
CHANGELOG = ROOT / "CHANGELOG.md"

TEAM_ID = "6X5YH93QNM"
# The Apple Developer enrollment ID. It looks like a team ID and is not one.
ENROLLMENT_ID = "ACKGM9XK9V"
ALLOWED_BACKGROUND_MODES = frozenset({"fetch", "processing"})
# Apple frameworks the app may import, plus the local package. Anything else
# is a third-party module and needs a decision (DECISIONS 0002).
ALLOWED_IMPORTS = frozenset(
    {
        "AppIntents",
        "BackgroundTasks",
        "Foundation",
        "Observation",
        "OSLog",
        "PlantingCore",
        "StoreKit",
        "SwiftUI",
        "UIKit",
        "UserNotifications",
        "WidgetKit",
    }
)

# Apple's required-reason API categories and the Swift spellings that reach
# them (developer.apple.com, "Describing use of required reason API").
REQUIRED_REASON: Mapping[str, re.Pattern[str]] = {
    "NSPrivacyAccessedAPICategoryUserDefaults": re.compile(
        r"\b(?:NS)?UserDefaults\b|@AppStorage\b"
    ),
    "NSPrivacyAccessedAPICategoryFileTimestamp": re.compile(
        r"\.(?:creationDate|modificationDate|contentModificationDate"
        r"|creationDateKey|contentModificationDateKey|contentAccessDateKey)\b"
        r"|\battributesOfItem\b|\bgetattrlist\b|\b[fl]?stat\("
    ),
    "NSPrivacyAccessedAPICategorySystemBootTime": re.compile(
        r"\bsystemUptime\b|\bmach_absolute_time\b"
    ),
    "NSPrivacyAccessedAPICategoryDiskSpace": re.compile(
        r"\bvolumeAvailableCapacity\w*|\bsystemFreeSize\b|\bstatv?fs\("
    ),
    "NSPrivacyAccessedAPICategoryActiveKeyboards": re.compile(r"\bactiveInputModes\b"),
}

_SETTING = re.compile(r"^\s*(?P<key>[A-Z_]+) = (?P<value>[^;]*);", re.MULTILINE)
_IMPORT = re.compile(
    r"^[ \t]*(?:@\w+[ \t]+)*import[ \t]+"
    r"(?:(?:struct|class|enum|protocol|func|var|let|typealias)[ \t]+)?(?P<module>\w+)",
    re.MULTILINE,
)
_SEMVER_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def build_settings(pbxproj: str, key: str) -> list[str]:
    """Every value the project gives `key`, one per build configuration."""
    return [
        m.group("value").strip('"')
        for m in _SETTING.finditer(pbxproj)
        if m.group("key") == key
    ]


def check_project(pbxproj: str) -> list[str]:
    """Versions, device family, team and package references."""
    problems: list[str] = []
    versions = set(build_settings(pbxproj, "MARKETING_VERSION"))
    if len(versions) != 1:
        problems.append(f"MARKETING_VERSION differs across targets: {sorted(versions)}")
    elif not re.fullmatch(r"\d+\.\d+\.\d+", next(iter(versions))):
        problems.append(f"MARKETING_VERSION is not X.Y.Z: {sorted(versions)}")
    builds = set(build_settings(pbxproj, "CURRENT_PROJECT_VERSION"))
    if len(builds) != 1:
        problems.append(
            f"CURRENT_PROJECT_VERSION differs across targets: {sorted(builds)}"
        )
    elif not re.fullmatch(r"[1-9]\d*", next(iter(builds))):
        problems.append(
            f"CURRENT_PROJECT_VERSION is not a positive integer: {sorted(builds)}"
        )
    families = build_settings(pbxproj, "TARGETED_DEVICE_FAMILY")
    if not families or any(f != "1" for f in families):
        problems.append(
            f"TARGETED_DEVICE_FAMILY must be 1 (iPhone) everywhere: {families}"
        )
    teams = set(build_settings(pbxproj, "DEVELOPMENT_TEAM"))
    if teams != {TEAM_ID}:
        problems.append(
            f"DEVELOPMENT_TEAM must be {TEAM_ID} everywhere: {sorted(teams)}"
        )
    if ENROLLMENT_ID in pbxproj:
        problems.append(f"{ENROLLMENT_ID} is the enrollment ID, not a team ID")
    if "XCRemoteSwiftPackageReference" in pbxproj:
        problems.append("the project references a remote Swift package")
    return problems


def check_app_info(info: Mapping[str, Any]) -> list[str]:
    """The app's Info.plist."""
    problems = _check_version_keys("app Info.plist", info)
    if info.get("ITSAppUsesNonExemptEncryption") is not False:
        problems.append("Info.plist must set ITSAppUsesNonExemptEncryption to false")
    if "UILaunchScreen" not in info and "UILaunchStoryboardName" not in info:
        problems.append("Info.plist has no launch screen")
    if info.get("LSRequiresIPhoneOS") is not True:
        problems.append("Info.plist must set LSRequiresIPhoneOS")
    modes = set(info.get("UIBackgroundModes", []))
    if not modes <= ALLOWED_BACKGROUND_MODES:
        problems.append(
            f"unexpected background modes: {sorted(modes - ALLOWED_BACKGROUND_MODES)}"
        )
    return problems


def _check_version_keys(label: str, info: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if info.get("CFBundleShortVersionString") != "$(MARKETING_VERSION)":
        problems.append(
            f"{label}: CFBundleShortVersionString must be $(MARKETING_VERSION)"
        )
    if info.get("CFBundleVersion") != "$(CURRENT_PROJECT_VERSION)":
        problems.append(f"{label}: CFBundleVersion must be $(CURRENT_PROJECT_VERSION)")
    return problems


def check_manifest(
    label: str, manifest: Mapping[str, Any], used: Iterable[str]
) -> list[str]:
    """A privacy manifest against the posture and the APIs the code calls."""
    problems: list[str] = []
    if manifest.get("NSPrivacyTracking") is not False:
        problems.append(f"{label}: NSPrivacyTracking must be false")
    if manifest.get("NSPrivacyTrackingDomains"):
        problems.append(f"{label}: NSPrivacyTrackingDomains must be empty")
    if manifest.get("NSPrivacyCollectedDataTypes"):
        problems.append(
            f"{label}: NSPrivacyCollectedDataTypes must be empty (Data Not Collected)"
        )
    declared = {
        entry.get("NSPrivacyAccessedAPIType")
        for entry in manifest.get("NSPrivacyAccessedAPITypes", [])
        if entry.get("NSPrivacyAccessedAPITypeReasons")
    }
    for category in sorted(set(used) - declared):
        problems.append(
            f"{label}: the code calls a {category} API the manifest does not declare"
        )
    return problems


def required_reason_uses(sources: Mapping[str, str]) -> dict[str, list[str]]:
    """Category -> 'file:line' for each required-reason API call."""
    found: dict[str, list[str]] = {}
    for name, text in sources.items():
        for number, line in enumerate(text.splitlines(), 1):
            code = line.split("//", 1)[0]
            for category, pattern in REQUIRED_REASON.items():
                if pattern.search(code):
                    found.setdefault(category, []).append(f"{name}:{number}")
    return found


def foreign_imports(sources: Mapping[str, str]) -> list[str]:
    """'file: module' for every import outside the allowed set."""
    return [
        f"{name}: {m.group('module')}"
        for name, text in sources.items()
        for m in _IMPORT.finditer(text)
        if m.group("module") not in ALLOWED_IMPORTS
    ]


def png_header(data: bytes) -> tuple[int, int, bool]:
    """(width, height, has_alpha) from a PNG's IHDR chunk."""
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    width, height, _depth, color_type = struct.unpack(">IIBB", data[16:26])
    # Color types 4 and 6 carry an alpha channel. A tRNS chunk adds one too.
    return width, height, color_type in (4, 6) or b"tRNS" in data[:4096]


def check_iconset(contents: Mapping[str, Any], pngs: Mapping[str, bytes]) -> list[str]:
    """Every icon named exists, at its pixel size, opaque; 1024 is present."""
    problems: list[str] = []
    has_marketing = False
    for image in contents.get("images", []):
        filename = image.get("filename")
        if not filename:
            problems.append(
                f"icon slot {image.get('size')} @{image.get('scale')} has no file"
            )
            continue
        if filename not in pngs:
            problems.append(f"icon {filename} is named in Contents.json but missing")
            continue
        points = float(str(image["size"]).split("x")[0])
        scale = int(str(image.get("scale", "1x")).rstrip("x"))
        expected = round(points * scale)
        width, height, alpha = png_header(pngs[filename])
        if (width, height) != (expected, expected):
            problems.append(
                f"icon {filename} is {width}x{height}, expected {expected}x{expected}"
            )
        if alpha:
            problems.append(f"icon {filename} has an alpha channel")
        if image.get("idiom") == "ios-marketing" and expected == 1024:
            has_marketing = True
    if not has_marketing:
        problems.append("the icon set has no 1024x1024 ios-marketing image")
    return problems


def check_entitlements(label: str, entitlements: Mapping[str, Any]) -> list[str]:
    if "aps-environment" in entitlements:
        return [
            f"{label}: aps-environment would add push; every alert is local (DECISIONS 0001)"
        ]
    return []


def changelog_section(changelog: str, version: str) -> str:
    """The body of `## [version]`, or '' when there is none."""
    pattern = re.compile(
        r"^## \[" + re.escape(version) + r"\][^\n]*\n(?P<body>.*?)(?=^## \[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(changelog)
    return m.group("body").strip() if m else ""


def changelog_dated(changelog: str, version: str) -> bool:
    """True when `## [version]` carries a release date, `- YYYY-MM-DD`."""
    pattern = r"^## \[" + re.escape(version) + r"\] - \d{4}-\d{2}-\d{2}[ \t]*$"
    return re.search(pattern, changelog, re.MULTILINE) is not None


def check_changelog_has_version(pbxproj: str, changelog: str) -> list[str]:
    """The current MARKETING_VERSION has a CHANGELOG section (dated or TBD)."""
    versions = set(build_settings(pbxproj, "MARKETING_VERSION"))
    if len(versions) != 1:
        return []  # check_project reports the drift
    version = next(iter(versions))
    if not re.search(r"^## \[" + re.escape(version) + r"\]", changelog, re.MULTILINE):
        return [f"CHANGELOG.md has no '## [{version}]' section for MARKETING_VERSION"]
    return []


def check_release(
    tag: str, pbxproj: str, changelog: str, earlier_builds: Mapping[str, int]
) -> tuple[list[str], str]:
    """Preflight for one release tag. Returns (problems, release notes)."""
    problems: list[str] = []
    if not _SEMVER_TAG.match(tag):
        return [f"release tag {tag!r} must be stable SemVer, vX.Y.Z"], ""
    version = tag[1:]
    marketing = set(build_settings(pbxproj, "MARKETING_VERSION"))
    if marketing != {version}:
        problems.append(
            f"tag {tag} does not match MARKETING_VERSION {sorted(marketing)}"
        )
    builds = set(build_settings(pbxproj, "CURRENT_PROJECT_VERSION"))
    build = (
        int(next(iter(builds)))
        if len(builds) == 1 and next(iter(builds)).isdigit()
        else 0
    )
    for earlier_tag, earlier_build in sorted(earlier_builds.items()):
        if build <= earlier_build:
            problems.append(
                f"build {build} is not higher than build {earlier_build} at {earlier_tag}; "
                "raise CURRENT_PROJECT_VERSION"
            )
    notes = changelog_section(changelog, version)
    if not notes:
        problems.append(f"CHANGELOG.md has no non-empty '## [{version}]' section")
    elif not changelog_dated(changelog, version):
        problems.append(
            f"CHANGELOG.md '## [{version}]' has no release date (it still says TBD?); "
            "write the notes and date it (OWNER-STEPS step 9)"
        )
    return problems, notes


def _earlier_builds(pairs: Iterable[str], tag: str) -> dict[str, int]:
    """CURRENT_PROJECT_VERSION per earlier tag, from TAG=PATH arguments.

    The release workflow writes each earlier tag's project.pbxproj to a file
    (`git show <tag>:ios/CAFishPlanting.xcodeproj/project.pbxproj`) and
    passes it here, so this script stays file reads only.
    """
    builds: dict[str, int] = {}
    for pair in pairs:
        other, _, path = pair.partition("=")
        if other == tag or not _SEMVER_TAG.match(other) or not path:
            continue
        values = build_settings(
            Path(path).read_text(encoding="utf-8"), "CURRENT_PROJECT_VERSION"
        )
        numbers = [int(v) for v in values if v.isdigit()]
        if numbers:
            builds[other] = max(numbers)
    return builds


def _swift_sources(roots: Iterable[Path]) -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for root in roots
        for path in sorted(root.rglob("*.swift"))
    }


def _plist(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data: dict[str, Any] = plistlib.load(handle)
    return data


def readiness() -> list[str]:
    pbxproj = PBXPROJ.read_text(encoding="utf-8")
    problems = check_project(pbxproj)
    problems += check_app_info(_plist(APP_INFO))
    problems += _check_version_keys("widget Info.plist", _plist(WIDGET_INFO))
    problems += check_changelog_has_version(
        pbxproj, CHANGELOG.read_text(encoding="utf-8")
    )
    sources = _swift_sources(SHIPPED_SWIFT)
    problems += [f"non-Apple import: {item}" for item in foreign_imports(sources)]
    used = required_reason_uses(sources)
    for manifest in MANIFESTS:
        problems += check_manifest(
            manifest.relative_to(ROOT).as_posix(), _plist(manifest), used
        )
    for entitlements in sorted(IOS.rglob("*.entitlements")):
        problems += check_entitlements(
            entitlements.relative_to(ROOT).as_posix(), _plist(entitlements)
        )
    contents = json.loads((ICONSET / "Contents.json").read_text(encoding="utf-8"))
    pngs = {p.name: p.read_bytes() for p in ICONSET.glob("*.png")}
    problems += check_iconset(contents, pngs)
    return problems


def _png(width: int, height: int, color_type: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0dIHDR"
        + struct.pack(">IIBB", width, height, 8, color_type)
    )


def self_test() -> list[str]:
    """Each check must reject its bad input and accept its good one."""
    good_proj = (
        "MARKETING_VERSION = 1.0.0;\nCURRENT_PROJECT_VERSION = 3;\nTARGETED_DEVICE_FAMILY = 1;\n"
        f"DEVELOPMENT_TEAM = {TEAM_ID};\n"
    )
    good_info: dict[str, Any] = {
        "CFBundleShortVersionString": "$(MARKETING_VERSION)",
        "CFBundleVersion": "$(CURRENT_PROJECT_VERSION)",
        "ITSAppUsesNonExemptEncryption": False,
        "UILaunchScreen": {},
        "LSRequiresIPhoneOS": True,
        "UIBackgroundModes": ["fetch", "processing"],
    }
    good_manifest: dict[str, Any] = {
        "NSPrivacyTracking": False,
        "NSPrivacyTrackingDomains": [],
        "NSPrivacyCollectedDataTypes": [],
        "NSPrivacyAccessedAPITypes": [],
    }
    declared = {
        **good_manifest,
        "NSPrivacyAccessedAPITypes": [
            {
                "NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategoryUserDefaults",
                "NSPrivacyAccessedAPITypeReasons": ["CA92.1"],
            }
        ],
    }
    icons = {
        "images": [
            {
                "filename": "a.png",
                "idiom": "ios-marketing",
                "size": "1024x1024",
                "scale": "1x",
            }
        ]
    }
    changelog = (
        "## [Unreleased]\n\n## [1.0.0] - 2026-10-01\n\n### Added\n\n- The app.\n"
    )
    cases: list[tuple[str, bool, bool]] = [
        ("project ok", not check_project(good_proj), True),
        (
            "version drift",
            bool(check_project(good_proj + "MARKETING_VERSION = 1.0.1;\n")),
            True,
        ),
        (
            "build not int",
            bool(check_project(good_proj.replace("= 3;", "= 3.1;"))),
            True,
        ),
        (
            "ipad",
            bool(check_project(good_proj + 'TARGETED_DEVICE_FAMILY = "1,2";\n')),
            True,
        ),
        (
            "enrollment id",
            bool(check_project(good_proj.replace(TEAM_ID, ENROLLMENT_ID))),
            True,
        ),
        (
            "remote package",
            bool(check_project(good_proj + "/* XCRemoteSwiftPackageReference */")),
            True,
        ),
        ("info ok", not check_app_info(good_info), True),
        (
            "no export flag",
            bool(check_app_info({**good_info, "ITSAppUsesNonExemptEncryption": True})),
            True,
        ),
        (
            "push mode",
            bool(
                check_app_info(
                    {**good_info, "UIBackgroundModes": ["remote-notification"]}
                )
            ),
            True,
        ),
        (
            "hardcoded version",
            bool(check_app_info({**good_info, "CFBundleVersion": "1"})),
            True,
        ),
        ("manifest ok", not check_manifest("m", good_manifest, []), True),
        (
            "tracking",
            bool(check_manifest("m", {**good_manifest, "NSPrivacyTracking": True}, [])),
            True,
        ),
        (
            "collected",
            bool(
                check_manifest(
                    "m",
                    {**good_manifest, "NSPrivacyCollectedDataTypes": [{"x": 1}]},
                    [],
                )
            ),
            True,
        ),
        (
            "undeclared api",
            bool(
                check_manifest(
                    "m", good_manifest, ["NSPrivacyAccessedAPICategoryUserDefaults"]
                )
            ),
            True,
        ),
        (
            "declared api",
            not check_manifest(
                "m", declared, ["NSPrivacyAccessedAPICategoryUserDefaults"]
            ),
            True,
        ),
        (
            "finds defaults",
            bool(required_reason_uses({"a": "let d = UserDefaults.standard"})),
            True,
        ),
        (
            "finds timestamp",
            bool(required_reason_uses({"a": "attrs[.modificationDate]"})),
            True,
        ),
        (
            "ignores type name",
            not required_reason_uses({"a": "let l = AppStorageLayout(directory: d)"}),
            True,
        ),
        (
            "ignores comment",
            not required_reason_uses({"a": "// no UserDefaults here"}),
            True,
        ),
        (
            "foreign import",
            bool(foreign_imports({"a": "import FirebaseAnalytics\n"})),
            True,
        ),
        (
            "apple import",
            not foreign_imports(
                {
                    "a": "import SwiftUI\n@preconcurrency import StoreKit\nimport struct Foundation.URL\n"
                }
            ),
            True,
        ),
        ("icon ok", not check_iconset(icons, {"a.png": _png(1024, 1024, 2)}), True),
        (
            "icon alpha",
            bool(check_iconset(icons, {"a.png": _png(1024, 1024, 6)})),
            True,
        ),
        ("icon size", bool(check_iconset(icons, {"a.png": _png(512, 512, 2)})), True),
        ("icon missing", bool(check_iconset(icons, {})), True),
        (
            "push entitlement",
            bool(check_entitlements("e", {"aps-environment": "production"})),
            True,
        ),
        (
            "release ok",
            not check_release("v1.0.0", good_proj, changelog, {"v0.9.0": 2})[0],
            True,
        ),
        (
            "release notes",
            check_release("v1.0.0", good_proj, changelog, {})[1]
            == "### Added\n\n- The app.",
            True,
        ),
        (
            "tag mismatch",
            bool(check_release("v1.0.1", good_proj, changelog, {})[0]),
            True,
        ),
        ("not semver", bool(check_release("v1.0", good_proj, changelog, {})[0]), True),
        (
            "build reused",
            bool(check_release("v1.0.0", good_proj, changelog, {"v0.9.0": 3})[0]),
            True,
        ),
        (
            "undated notes",
            bool(
                check_release(
                    "v1.0.0", good_proj, changelog.replace("2026-10-01", "TBD"), {}
                )[0]
            ),
            True,
        ),
        (
            "changelog has version",
            not check_changelog_has_version(
                good_proj, changelog.replace("2026-10-01", "TBD")
            ),
            True,
        ),
        (
            "changelog lacks version",
            bool(check_changelog_has_version(good_proj, "## [Unreleased]\n")),
            True,
        ),
        (
            "no notes",
            bool(check_release("v1.0.0", good_proj, "## [Unreleased]\n", {})[0]),
            True,
        ),
    ]
    return [name for name, got, want in cases if got != want]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--self-test", action="store_true", help="check the checks, then exit"
    )
    parser.add_argument(
        "--release-tag", help="run the release preflight for this vX.Y.Z tag"
    )
    parser.add_argument(
        "--notes-out", type=Path, help="write the tag's CHANGELOG section here"
    )
    parser.add_argument(
        "--earlier-pbxproj",
        action="append",
        default=[],
        metavar="TAG=PATH",
        help="an earlier release tag and a copy of its project.pbxproj (repeatable)",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        failures = self_test()
        for name in failures:
            print(f"self-test failed: {name}", file=sys.stderr)
        print(f"check_app_store self-test: {'FAILED' if failures else 'ok'}")
        return 1 if failures else 0
    problems = readiness()
    notes = ""
    if args.release_tag:
        release_problems, notes = check_release(
            args.release_tag,
            PBXPROJ.read_text(encoding="utf-8"),
            CHANGELOG.read_text(encoding="utf-8"),
            _earlier_builds(args.earlier_pbxproj, args.release_tag),
        )
        problems += release_problems
    for problem in problems:
        print(f"app store: {problem}", file=sys.stderr)
    if problems:
        print(f"app store check: FAILED ({len(problems)} problems)", file=sys.stderr)
        return 1
    if args.notes_out:
        args.notes_out.write_text(notes + "\n", encoding="utf-8")
    print(
        "app store check: ok" + (f" for {args.release_tag}" if args.release_tag else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
