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

flatpak install --or-update --user flathub io.qt.PySide.BaseApp//6.10 -y

# ── 1. Patch the template manifest: replace COMPUTED_BY_CI with type:dir ──────
echo ""
echo "==> Patching manifest for local build…"
python3 - <<'EOF'
import json, pathlib, os

src = pathlib.Path("packaging/flatpak/io.github.scerelli.Documentius.json")
dst = pathlib.Path("packaging/flatpak/flathub-manifest.json")
m = json.loads(src.read_text())
repo_root = os.path.abspath(".")
for mod in m["modules"]:
    for s in mod.get("sources", []):
        if s.get("sha256") in ("COMPUTED_BY_CI", "FILLED_BY_CI"):
            mod["sources"] = [{"type": "dir", "path": repo_root}]
            break
dst.write_text(json.dumps(m, indent=2) + "\n")
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
