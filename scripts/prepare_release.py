import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _git(*args) -> str:
    return subprocess.check_output(["git", *args], text=True, cwd=ROOT).strip()


def last_tag() -> str:
    try:
        return _git("describe", "--tags", "--abbrev=0")
    except subprocess.CalledProcessError:
        return "v0.0.0"


def commits_since(tag: str) -> list[str]:
    try:
        out = _git("log", f"{tag}..HEAD", "--format=%s")
        return [l for l in out.splitlines() if l.strip()]
    except subprocess.CalledProcessError:
        return []


def next_version(override: str | None = None) -> str:
    if override:
        return override.lstrip("v")

    tag = last_tag()
    major, minor, patch = (int(x) for x in tag.lstrip("v").split("."))

    messages = commits_since(tag)
    if not messages:
        return f"{major}.{minor}.{patch + 1}"

    bump = "patch"
    for msg in messages:
        if re.search(r"^(\w+)(\(.*\))?!:", msg) or "BREAKING CHANGE" in msg:
            bump = "major"
            break
        if re.match(r"^feat(\(.*\))?:", msg):
            bump = "minor"

    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


PACKAGES = [
    ("PyMuPDF",             "python3-pymupdf",    "cp310-abi3"),
    ("shiboken6",           "python3-pyside6",    "cp39-abi3"),
    ("PySide6_Essentials",  "python3-pyside6",    "cp39-abi3"),
    ("PySide6_Addons",      "python3-pyside6",    "cp39-abi3"),
    ("PySide6",             "python3-pyside6",    "cp39-abi3"),
    ("QtPy",                "python3-qtawesome",  "none-any"),
    ("QtAwesome",           "python3-qtawesome",  "none-any"),
]

ARCH_MAP = {
    "x86_64":  "x86_64",
    "aarch64": "aarch64",
}


def _pypi_data(package: str) -> dict:
    url = f"https://pypi.org/pypi/{package}/json"
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def best_wheel(package: str, abi_hint: str, arch: str) -> dict:
    data = _pypi_data(package)
    version = data["info"]["version"]
    files = data["releases"].get(version, [])

    for f in files:
        if f["packagetype"] != "bdist_wheel":
            continue
        fn = f["filename"]
        if abi_hint == "none-any":
            if "py3-none-any" in fn or "py2.py3-none-any" in fn:
                return dict(url=f["url"], sha256=f["digests"]["sha256"],
                            filename=fn, version=version)
        else:
            if abi_hint in fn and arch in fn and "macosx" not in fn and "win" not in fn:
                return dict(url=f["url"], sha256=f["digests"]["sha256"],
                            filename=fn, version=version)

    raise RuntimeError(
        f"No wheel found for {package} {abi_hint} {arch} "
        f"(version {version}). Check PyPI manually."
    )


def wheel_source(w: dict) -> dict:
    return {"type": "file", "url": w["url"],
            "sha256": w["sha256"], "dest-filename": w["filename"]}


def bump_pyproject(version: str) -> None:
    path = ROOT / "pyproject.toml"
    text = path.read_text()
    text = re.sub(r'^version = ".*"', f'version = "{version}"', text, flags=re.M)
    path.write_text(text)
    print(f"  pyproject.toml → {version}")


def add_metainfo_release(version: str) -> None:
    path = ROOT / "packaging" / "io.github.scerelli.Documentius.metainfo.xml"
    if not path.exists():
        candidates = list((ROOT / "packaging").glob("*.metainfo.xml"))
        if not candidates:
            print("  metainfo.xml not found — skipping")
            return
        path = candidates[0]

    text = path.read_text()
    today = date.today().isoformat()
    entry = (
        f'    <release version="{version}" date="{today}">\n'
        f'      <description><p>Release {version}.</p></description>\n'
        f'    </release>\n'
    )
    if f'version="{version}"' in text:
        print(f"  metainfo.xml: release {version} already present")
        return
    text = text.replace("<releases>\n", f"<releases>\n{entry}")
    path.write_text(text)
    print(f"  metainfo.xml → added release {version} ({today})")


def write_manifest(version: str, repo: str, arch: str,
                   module_sources: dict[str, list[dict]]) -> Path:
    flatpak_dir = ROOT / "packaging" / "flatpak"
    candidates = [
        p for p in flatpak_dir.glob("*.json")
        if p.name not in ("flathub.json", "flathub-manifest.json")
    ]
    if not candidates:
        raise FileNotFoundError("No Flatpak manifest found in packaging/flatpak/")
    manifest_path = candidates[0]
    manifest = json.loads(manifest_path.read_text())

    tarball = f"documentius-{version}.tar.gz"
    tarball_url = (
        f"https://github.com/{repo}/releases/download/"
        f"v{version}/{tarball}"
    )

    for module in manifest["modules"]:
        name = module["name"] if isinstance(module, dict) else None
        if name in module_sources:
            module["sources"] = module_sources[name]
        elif name == manifest["modules"][-1]["name"]:
            module["sources"] = [{
                "type": "archive",
                "url": tarball_url,
                "sha256": "COMPUTED_BY_CI",
                "strip-components": 1,
            }]

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"  manifest → {manifest_path.name}")

    out = ROOT / "packaging" / "flatpak" / "flathub-manifest.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", help="GitHub repo, e.g. alice/documentius")
    ap.add_argument("--version", default=None,
                    help="Override auto-detected version (e.g. 2.0.0)")
    ap.add_argument("--arch", default="x86_64", choices=list(ARCH_MAP))
    args = ap.parse_args()

    version = next_version(args.version)
    arch = ARCH_MAP[args.arch]
    print(f"\nPreparing release {version} ({arch})\n")

    module_sources: dict[str, list[dict]] = {}
    for pkg, mod, abi in PACKAGES:
        print(f"  PyPI: {pkg} …", end=" ", flush=True)
        w = best_wheel(pkg, abi, arch)
        print(f"{w['version']}  {w['filename']}")
        module_sources.setdefault(mod, []).append(wheel_source(w))

    print()
    bump_pyproject(version)
    add_metainfo_release(version)
    write_manifest(version, args.repo, arch, module_sources)

    print(f"\nVERSION={version}")

    print("\nDone. Commit, tag, and release as usual.\n")


if __name__ == "__main__":
    main()
