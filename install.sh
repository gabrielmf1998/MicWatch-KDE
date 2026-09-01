#!/usr/bin/env bash
# Installs MicWatch for the current user, straight from this clone.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor"

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
python3 -c "import PySide6.QtWidgets" 2>/dev/null || {
    echo "PySide6 is required:  sudo dnf install python3-pyside6" >&2; exit 1; }
command -v pactl  >/dev/null || echo "warning: pactl not found (pulseaudio-utils)" >&2
command -v pw-cat >/dev/null || echo "warning: pw-cat not found (pipewire-utils)" >&2

mkdir -p "$BIN" "$APPS"

cat > "$BIN/micwatch" <<LAUNCHER
#!/usr/bin/env bash
exec env PYTHONPATH="$SRC\${PYTHONPATH:+:\$PYTHONPATH}" python3 -m micwatch "\$@"
LAUNCHER
chmod +x "$BIN/micwatch"

for s in 48 64 128 256 512; do
    install -Dm 0644 "$SRC/assets/micwatch-${s}.png" "$ICONS/${s}x${s}/apps/micwatch.png"
done
install -Dm 0644 "$SRC/assets/micwatch.svg" "$ICONS/scalable/apps/micwatch.svg"
sed "s|^Exec=micwatch$|Exec=$BIN/micwatch|" "$SRC/packaging/micwatch.desktop" > "$APPS/micwatch.desktop"
update-desktop-database "$APPS" 2>/dev/null || true

echo "Installed:"
echo "  $BIN/micwatch"
echo "  $APPS/micwatch.desktop"
echo
echo "Run it with: micwatch"
