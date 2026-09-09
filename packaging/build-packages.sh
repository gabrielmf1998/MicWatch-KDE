#!/usr/bin/env bash
# Builds every package into dist/:  .rpm (Fedora), .deb (Debian/Ubuntu),
# .pkg.tar.zst (Arch) and an .AppImage (thin: uses the system python3+PySide6).
set -euo pipefail

NAME=micwatch-kde
BIN=micwatch
VERSION=1.3.0
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
Depends: python3, python3-pyside6.qtwidgets | python3-pyside6, pipewire-bin | pipewire, pulseaudio-utils, curl
Recommends: python3-evdev
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
optdepend = python-evdev: global keyboard shortcuts
PKGINFO
( cd "$PKG"
  TAROPTS=(--no-xattrs --no-fflags --uid 0 --gid 0 --uname root --gname root)
  LANG=C bsdtar "${TAROPTS[@]}" -czf .MTREE --format=mtree \
      --options='!all,use-set,type,uid,gid,mode,time,size,md5,sha256,link' \
      .PKGINFO usr
  LANG=C bsdtar "${TAROPTS[@]}" -cf - .PKGINFO .MTREE usr |
      zstd -q -c -T0 -18 > "$DIST/$NAME-$VERSION-$RELEASE-any.pkg.tar.zst" )

# ── AppImage (self-contained: Python + PySide6 + evdev) ─────
# SKIP_APPIMAGE=1 keeps an already-built one, so iterating on the native
# packages does not re-download 150 MB of Qt every time.
say "AppImage"
if [ -n "${SKIP_APPIMAGE:-}" ]; then
    say "  skipped (SKIP_APPIMAGE set)"
    AT=""
    BASE_URL=""
fi
if [ -z "${SKIP_APPIMAGE:-}" ]; then
if AT="$(command -v appimagetool 2>/dev/null)"; then :; else
    AT="$WORK/appimagetool"
    curl -fsSL -o "$AT" \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage \
        && chmod +x "$AT" || AT=""
fi
PYVER=3.12
BASE_URL="$(curl -fsSL "https://api.github.com/repos/niess/python-appimage/releases/tags/python$PYVER" \
    | tr ',' '\n' | grep '"browser_download_url"' | cut -d'"' -f4 \
    | grep manylinux2014_x86_64 | head -1)"
if [ -n "$AT" ] && [ -n "$BASE_URL" ] \
   && curl -fsSL -o "$WORK/python.AppImage" "$BASE_URL"; then
    chmod +x "$WORK/python.AppImage"
    ( cd "$WORK" && ./python.AppImage --appimage-extract >/dev/null )
    APPDIR="$WORK/squashfs-root"
    SITE="$APPDIR/opt/python$PYVER/lib/python$PYVER/site-packages"

    say "  bundling PySide6 and evdev (a ~150 MB download)"
    "$APPDIR/AppRun" -m pip install --quiet --no-warn-script-location \
        PySide6-Essentials evdev >"$WORK/pip.log" 2>&1 \
        || { tail -5 "$WORK/pip.log"; exit 1; }

    # Drop what a tray indicator never touches: QML, Qt translations, tooling.
    ( cd "$SITE/PySide6" \
      && rm -rf Qt/qml Qt/translations Qt/metatypes Qt/libexec \
                Qt/plugins/qmltooling Qt/plugins/sqldrivers Qt/plugins/designer \
      && rm -f Qt/lib/libQt6Quick*.so.6* Qt/lib/libQt6Qml*.so.6* \
               Qt/lib/libQt6Designer*.so.6* Qt/lib/libQt6Help*.so.6* \
               Qt/lib/libQt6Test*.so.6* Qt/lib/libQt6Sql*.so.6* \
               Qt/lib/libQt6UiTools*.so.6* Qt/lib/libQt6Multimedia*.so.6* \
      && rm -f QtQuick*.abi3.so QtQml*.abi3.so QtDesigner*.abi3.so \
               QtHelp*.abi3.so QtTest*.abi3.so QtSql*.abi3.so \
               QtUiTools*.abi3.so QtMultimedia*.abi3.so )
    rm -rf "$SITE/pip" "$SITE/setuptools" "$SITE/pkg_resources"
    find "$SITE" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

    install -d "$SITE/micwatch"
    install -m 0644 "$ROOT"/micwatch/*.py "$SITE/micwatch/"

    rm -f "$APPDIR"/*.desktop "$APPDIR"/python.png "$APPDIR"/.DirIcon
    rm -rf "$APPDIR/usr/share/applications" "$APPDIR/usr/share/metainfo"
    install -Dm 0644 "$ROOT/packaging/$BIN.desktop" "$APPDIR/$BIN.desktop"
    install -Dm 0644 "$ROOT/packaging/$BIN.desktop" \
        "$APPDIR/usr/share/applications/$BIN.desktop"
    install -Dm 0644 "$ROOT/assets/$BIN-256.png" "$APPDIR/$BIN.png"
    install -Dm 0644 "$ROOT/assets/$BIN-256.png" \
        "$APPDIR/usr/share/icons/hicolor/256x256/apps/$BIN.png"
    ( cd "$APPDIR" && ln -sf "$BIN.png" .DirIcon )

    # run MicWatch instead of dropping the user in a Python prompt
    python3 - "$APPDIR/AppRun" "$PYVER" <<'PY'
import sys, pathlib
run, pyver = pathlib.Path(sys.argv[1]), sys.argv[2]
text = run.read_text()
old = f'"$APPDIR/opt/python{pyver}/bin/python{pyver}" "$@"'
new = f'"$APPDIR/opt/python{pyver}/bin/python{pyver}" -m micwatch "$@"'
assert old in text, "python-appimage AppRun changed shape"
run.write_text(text.replace(old, new))
PY

    ARCH=x86_64 "$AT" --appimage-extract-and-run "$APPDIR" \
        "$DIST/MicWatch-KDE-x86_64.AppImage" >"$WORK/appimage.log" 2>&1 \
        && say "  AppImage built ($(du -h "$DIST/MicWatch-KDE-x86_64.AppImage" | cut -f1), runs with no system PySide6)" \
        || { say "AppImage build failed:"; tail -15 "$WORK/appimage.log"; }
else
    say "appimagetool or the Python base is unavailable — skipping AppImage"
fi
fi

# ── checksums ───────────────────────────────────────────────
( cd "$DIST" && sha256sum ./*.rpm ./*.deb ./*.pkg.tar.zst ./*.AppImage > SHA256SUMS 2>/dev/null || true )
say "done. Artifacts in dist/:"
ls -1sh "$DIST"
