#!/usr/bin/env bash
# Builds every package into dist/:  .rpm (Fedora), .deb (Debian/Ubuntu),
# .pkg.tar.zst (Arch) and an .AppImage (thin: uses the system python3+PySide6).
set -euo pipefail

NAME=micwatch-kde
BIN=micwatch
VERSION=1.2.1
RELEASE=1
MAINT="Gabriel Marques Ferrarezi <110578985+gabrielmf1998@users.noreply.github.com>"
URL="https://github.com/gabrielmf1998/MicWatch-KDE"
SUMMARY="Microphone in-use tray indicator with a user-defined threshold"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
say() { printf '\033[1m==>\033[0m %s\n' "$*"; }

rm -rf "$DIST"; mkdir -p "$DIST"

# Lay the install tree the same way every package does.
stage_tree() {
    local d="$1"
    install -d "$d/usr/share/$NAME/micwatch"
    install -m 0644 "$ROOT"/micwatch/*.py            "$d/usr/share/$NAME/micwatch/"
    install -Dm 0755 "$ROOT/packaging/$BIN"          "$d/usr/bin/$BIN"
    install -Dm 0644 "$ROOT/packaging/$BIN.desktop"  "$d/usr/share/applications/$BIN.desktop"
    for s in 48 64 128 256 512; do
        install -Dm 0644 "$ROOT/assets/$BIN-${s}.png" \
            "$d/usr/share/icons/hicolor/${s}x${s}/apps/$BIN.png"
    done
    install -Dm 0644 "$ROOT/assets/$BIN.svg" \
        "$d/usr/share/icons/hicolor/scalable/apps/$BIN.svg"
    install -Dm 0644 "$ROOT/LICENSE"   "$d/usr/share/licenses/$NAME/LICENSE"
    install -Dm 0644 "$ROOT/README.md" "$d/usr/share/doc/$NAME/README.md"
}

# ── source tarball (for the RPM) ────────────────────────────
say "source tarball"
SRCDIR="$WORK/$NAME-$VERSION"; mkdir -p "$SRCDIR"
cp -r "$ROOT"/{micwatch,assets,packaging,docs,LICENSE,README.md,install.sh,install-online.sh} "$SRCDIR/"
rm -rf "$SRCDIR/micwatch/__pycache__" "$SRCDIR/packaging/build-packages.sh" "$SRCDIR/assets/gen_icons.py"
tar -C "$WORK" -czf "$WORK/$NAME-$VERSION.tar.gz" "$NAME-$VERSION"

# ── RPM ─────────────────────────────────────────────────────
if command -v rpmbuild >/dev/null; then
    say "RPM"
    TOP="$WORK/rpm"; mkdir -p "$TOP"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
    cp "$WORK/$NAME-$VERSION.tar.gz" "$TOP/SOURCES/"
    cp "$ROOT/packaging/fedora/$NAME.spec" "$TOP/SPECS/"
    rpmbuild --define "_topdir $TOP" -bb "$TOP/SPECS/$NAME.spec" >"$WORK/rpm.log" 2>&1 \
        || { tail -30 "$WORK/rpm.log"; exit 1; }
    find "$TOP/RPMS" -name '*.rpm' -exec cp {} "$DIST/" \;
fi

# ── DEB ─────────────────────────────────────────────────────
if command -v dpkg-deb >/dev/null; then
    say "DEB"
    DEB="$WORK/deb"; stage_tree "$DEB"
    mkdir -p "$DEB/DEBIAN"
    cat > "$DEB/DEBIAN/control" <<CONTROL
Package: $NAME
Version: $VERSION-$RELEASE
Architecture: all
Maintainer: $MAINT
Section: sound
Priority: optional
Homepage: $URL
Depends: python3, python3-pyside6.qtwidgets, python3-pyside6.qtsvg, pipewire-bin, pulseaudio-utils, curl
Description: $SUMMARY
 MicWatch lights up in the system tray when an application is actually using
 the microphone. You set a threshold in dBFS, so the icon separates "an app
 opened the input device" from "sound is really going through it".
 .
 18 icon styles, 15 animations, one colour per state, a live dB meter with a
 noise-floor calibration button, and a switch to start with the session.
 .
 The level meter only runs while another application is already recording, so
 MicWatch never opens the microphone on its own.
CONTROL
    dpkg-deb --root-owner-group --build "$DEB" "$DIST/${NAME}_${VERSION}-${RELEASE}_all.deb" >/dev/null
fi

# ── Arch ────────────────────────────────────────────────────
say "Arch package"
PKG="$WORK/pkg"; stage_tree "$PKG"
SIZE=$(du -sb "$PKG" | cut -f1)
cat > "$PKG/.PKGINFO" <<PKGINFO
pkgname = $NAME
pkgbase = $NAME
pkgver = $VERSION-$RELEASE
pkgdesc = $SUMMARY
url = $URL
builddate = $(date +%s)
packager = $MAINT
size = $SIZE
arch = any
license = MIT
depend = python
depend = pyside6
depend = pipewire
depend = libpulse
depend = curl
PKGINFO
( cd "$PKG"
  TAROPTS=(--no-xattrs --no-fflags --uid 0 --gid 0 --uname root --gname root)
  LANG=C bsdtar "${TAROPTS[@]}" -czf .MTREE --format=mtree \
      --options='!all,use-set,type,uid,gid,mode,time,size,md5,sha256,link' \
      .PKGINFO usr
  LANG=C bsdtar "${TAROPTS[@]}" -cf - .PKGINFO .MTREE usr |
      zstd -q -c -T0 -18 > "$DIST/$NAME-$VERSION-$RELEASE-any.pkg.tar.zst" )

# ── AppImage (thin: system python3 + PySide6) ───────────────
say "AppImage"
if AT="$(command -v appimagetool 2>/dev/null)"; then :; else
    AT="$WORK/appimagetool"
    curl -fsSL -o "$AT" \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage \
        && chmod +x "$AT" || AT=""
fi
if [ -n "$AT" ]; then
    APPDIR="$WORK/AppDir"
    install -d "$APPDIR/usr/share/$NAME/micwatch"
    install -m 0644 "$ROOT"/micwatch/*.py "$APPDIR/usr/share/$NAME/micwatch/"
    install -Dm 0644 "$ROOT/assets/$BIN-256.png" "$APPDIR/$BIN.png"
    install -Dm 0644 "$ROOT/assets/$BIN-256.png" \
        "$APPDIR/usr/share/icons/hicolor/256x256/apps/$BIN.png"
    install -Dm 0644 "$ROOT/packaging/$BIN.desktop" "$APPDIR/$BIN.desktop"
    cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
# MicWatch AppImage launcher: a thin wrapper around the system python3+PySide6.
HERE="$(dirname "$(readlink -f "$0")")"
if ! python3 -c "import PySide6.QtWidgets" 2>/dev/null; then
    echo "MicWatch needs PySide6 installed on the system:" >&2
    echo "  Fedora: sudo dnf install python3-pyside6" >&2
    echo "  Debian/Ubuntu: sudo apt install python3-pyside6.qtwidgets" >&2
    echo "  Arch: sudo pacman -S pyside6" >&2
    exit 1
fi
command -v pw-cat >/dev/null 2>&1 || echo "MicWatch: pw-cat not found; level metering will not work." >&2
command -v pactl  >/dev/null 2>&1 || echo "MicWatch: pactl not found; stream detection will not work." >&2
export PYTHONPATH="$HERE/usr/share/micwatch-kde${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m micwatch "$@"
APPRUN
    chmod +x "$APPDIR/AppRun"
    ARCH=x86_64 "$AT" --appimage-extract-and-run "$APPDIR" \
        "$DIST/MicWatch-KDE-x86_64.AppImage" >"$WORK/appimage.log" 2>&1 \
        && say "AppImage built" || { say "AppImage build failed:"; tail -15 "$WORK/appimage.log"; }
else
    say "appimagetool unavailable — skipping AppImage"
fi

# ── checksums ───────────────────────────────────────────────
( cd "$DIST" && sha256sum ./*.rpm ./*.deb ./*.pkg.tar.zst ./*.AppImage > SHA256SUMS 2>/dev/null || true )
say "done. Artifacts in dist/:"
ls -1sh "$DIST"
