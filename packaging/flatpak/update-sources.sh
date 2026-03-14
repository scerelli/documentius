#!/usr/bin/env bash
# Run this script to regenerate the correct wheel URLs and SHA256 hashes
# for the Flatpak manifest using flatpak-pip-generator.
#
# Requirements:
#   pip install flatpak-pip-generator   (or use the one in flathub tools)
#   flatpak-pip-generator PyMuPDF PySide6 --output python3-deps.json
#
# Then merge the generated sources into the manifest.

set -euo pipefail

command -v flatpak-pip-generator >/dev/null 2>&1 || {
  echo "Installing flatpak-pip-generator..."
  pip3 install flatpak-pip-generator --break-system-packages
}

flatpak-pip-generator \
  --runtime org.kde.Sdk//6.8 \
  PyMuPDF PySide6 \
  --output python3-deps.json

echo "Done — import python3-deps.json sources into the manifest."
