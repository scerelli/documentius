#!/usr/bin/env bash
# Build and test Documentius locally with Flatpak, exactly as Flathub would.
# Run from the repo root:   bash scripts/build-local.sh
set -euo pipefail

APP_ID="io.github.scerelli.Documentius"
MANIFEST="packaging/flatpak/${APP_ID}.json"
GENERATED="packaging/flatpak/flathub-manifest.json"

# ── 0. Prerequisites ──────────────────────────────────────────────────────────
flatpak remote-add --if-not-exists --user flathub \
    https://dl.flathub.org/repo/flathub.flatpakrepo

# ── 1. Fetch real PyPI sha256s and generate a buildable manifest ──────────────
echo ""
echo "==> Fetching dependency sha256s from PyPI…"
python3 scripts/prepare_release.py scerelli/documentius --version 0.0.0-local

# prepare_release.py writes flathub-manifest.json but fills the app source
# with COMPUTED_BY_CI — replace that stanza with type:dir for local dev
python3 - <<'EOF'
import json, pathlib, os

p = pathlib.Path("packaging/flatpak/flathub-manifest.json")
m = json.loads(p.read_text())
repo_root = os.path.abspath(".")
for mod in m["modules"]:
    for src in mod.get("sources", []):
        if src.get("sha256") in ("COMPUTED_BY_CI", "FILLED_BY_CI") \
                or src.get("url") in ("FILLED_BY_CI",):
            mod["sources"] = [{"type": "dir", "path": repo_root}]
            break
p.write_text(json.dumps(m, indent=2) + "\n")
print("  manifest patched for local build (type:dir)")
EOF

# ── 2. Lint the metainfo ──────────────────────────────────────────────────────
echo ""
echo "==> Linting metainfo…"
flatpak run --command=flatpak-builder-lint org.flatpak.Builder \
    appstream "packaging/${APP_ID}.metainfo.xml" && echo "  metainfo OK"

# ── 3. Lint the manifest ──────────────────────────────────────────────────────
echo ""
echo "==> Linting manifest…"
flatpak run --command=flatpak-builder-lint org.flatpak.Builder \
    manifest "$GENERATED" && echo "  manifest OK"

# ── 4. Build ──────────────────────────────────────────────────────────────────
echo ""
echo "==> Building (this will take a while the first time)…"
flatpak-builder \
    --force-clean \
    --user \
    --install-deps-from=flathub \
    --install \
    builddir "$GENERATED"

# ── 5. Run ────────────────────────────────────────────────────────────────────
echo ""
echo "==> Build complete. Run with:"
echo "    flatpak run ${APP_ID}"
echo ""
flatpak run "$APP_ID"
