#!/usr/bin/env bash
# Installs the launcher and desktop entry for the current user.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"

mkdir -p "$BIN" "$APPS"

cat > "$BIN/micwatch" <<LAUNCHER
#!/usr/bin/env bash
exec env PYTHONPATH="$SRC\${PYTHONPATH:+:\$PYTHONPATH}" python3 -m micwatch "\$@"
LAUNCHER
chmod +x "$BIN/micwatch"

sed "s|^Exec=micwatch$|Exec=$BIN/micwatch|" "$SRC/micwatch.desktop" > "$APPS/micwatch.desktop"
update-desktop-database "$APPS" 2>/dev/null || true

echo "Installed:"
echo "  $BIN/micwatch"
echo "  $APPS/micwatch.desktop"
echo
echo "Run it with: micwatch"
