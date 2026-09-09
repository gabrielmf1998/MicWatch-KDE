#!/bin/sh
# MicWatch — online installer.
#
# Installs the native package for your distro. Distros that do not ship PySide6
# (Ubuntu 24.04, for one) get a self-contained install with a private
# virtualenv instead, so the one-liner works everywhere.
#
#   curl -fsSL https://raw.githubusercontent.com/gabrielmf1998/MicWatch-KDE/main/install-online.sh | sh
set -eu

REPO="gabrielmf1998/MicWatch-KDE"
API="https://api.github.com/repos/$REPO/releases/latest"

# everything informational goes to stderr: fetch() returns a path on stdout
info() { printf '\033[1m==>\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
err()  { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || err "curl is required"

fam=""
[ -r /etc/os-release ] && . /etc/os-release
for t in "${ID:-}" ${ID_LIKE:-}; do
    case "$t" in
        fedora|rhel|centos|rocky|almalinux) fam=rpm; break ;;
        debian|ubuntu|linuxmint|pop) fam=deb; break ;;
        arch|manjaro|endeavouros|cachyos) fam=arch; break ;;
    esac
done

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

release_json() {
    [ -f "$tmp/release.json" ] || curl -fsSL "$API" -o "$tmp/release.json" \
        || err "could not reach the GitHub release API"
    cat "$tmp/release.json"
}

# Resolve an asset by suffix, so the installer survives version bumps.
fetch() {
    suffix="$1"
    url="$(release_json | tr ',' '\n' | grep '"browser_download_url"' | cut -d'"' -f4 \
        | grep -- "$suffix\$" | head -1)"
    [ -n "$url" ] || err "no asset ending in '$suffix' in the latest release"
    out="$tmp/${url##*/}"
    info "downloading ${url##*/}"
    curl -fL --progress-bar "$url" -o "$out" || err "download failed: $url"
    printf '%s' "$out"
}

latest_tag() {
    release_json | tr ',' '\n' | grep '"tag_name"' | cut -d'"' -f4 | head -1
}

have_pyside() { python3 -c 'import PySide6.QtWidgets' >/dev/null 2>&1; }

# Does this distro package PySide6 at all? Ubuntu 24.04, for example, does not.
distro_has_pyside() {
    case "$fam" in
        rpm)  dnf -q list --available python3-pyside6 >/dev/null 2>&1 \
              || dnf -q list --installed python3-pyside6 >/dev/null 2>&1 ;;
        deb)  apt-cache show python3-pyside6.qtwidgets >/dev/null 2>&1 \
              || apt-cache show python3-pyside6 >/dev/null 2>&1 ;;
        arch) pacman -Si pyside6 >/dev/null 2>&1 ;;
        *)    return 1 ;;
    esac
}

# Self-contained install: source from the tag plus PySide6 from PyPI in a venv
# under ~/.local, no root beyond the audio tools.
venv_install() {
    info "this distro has no PySide6 package — installing a private one instead"
    case "$fam" in
        deb) $SUDO apt-get update -qq || true
             $SUDO apt-get install -y python3 python3-venv pipewire-bin pulseaudio-utils curl
             # PySide6 wheels link against the system Qt runtime libraries; a desktop
             # already has these, but install them anyway so a slim system works too
             for lib in libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0 libdbus-1-3 \
                        libfontconfig1 libglib2.0-0t64 libglib2.0-0; do
                 $SUDO apt-get install -y "$lib" >/dev/null 2>&1 || true
             done ;;
        rpm) $SUDO dnf install -y python3 pipewire-utils pulseaudio-utils curl ;;
        arch) $SUDO pacman -S --needed --noconfirm python pipewire libpulse curl ;;
    esac
    command -v python3 >/dev/null 2>&1 || err "python3 is required"

    tag="$(latest_tag)"; [ -n "$tag" ] || err "could not read the latest tag"
    info "downloading MicWatch $tag source"
    curl -fL --progress-bar "https://github.com/$REPO/archive/refs/tags/$tag.tar.gz" \
        -o "$tmp/src.tar.gz" || err "source download failed"
    tar -C "$tmp" -xzf "$tmp/src.tar.gz"
    src="$(find "$tmp" -maxdepth 1 -type d -name 'MicWatch-KDE-*' | head -1)"
    [ -n "$src" ] || err "unexpected source tarball layout"

    prefix="$HOME/.local/share/micwatch"
    info "creating a virtualenv in $prefix/venv (PySide6 is a ~100 MB download)"
    rm -rf "$prefix/venv"
    mkdir -p "$prefix"
    python3 -m venv "$prefix/venv" || err "python3 -m venv failed (install python3-venv)"
    "$prefix/venv/bin/python" -m pip install --quiet --upgrade pip
    "$prefix/venv/bin/python" -m pip install --quiet PySide6-Essentials \
        || "$prefix/venv/bin/python" -m pip install --quiet PySide6 \
        || err "could not install PySide6 from PyPI"
    # optional: only the global keyboard shortcuts need it
    "$prefix/venv/bin/python" -m pip install --quiet evdev >/dev/null 2>&1 || true

    rm -rf "$prefix/micwatch"
    cp -r "$src/micwatch" "$prefix/micwatch"
    mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" \
             "$HOME/.local/share/icons/hicolor/scalable/apps"
    cat > "$HOME/.local/bin/micwatch" <<LAUNCHER
#!/bin/sh
exec env PYTHONPATH="$prefix" "$prefix/venv/bin/python" -m micwatch "\$@"
LAUNCHER
    chmod +x "$HOME/.local/bin/micwatch"
    cp "$src/assets/micwatch.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/" 2>/dev/null || true
    for s in 48 64 128 256 512; do
        [ -f "$src/assets/micwatch-$s.png" ] || continue
        mkdir -p "$HOME/.local/share/icons/hicolor/${s}x${s}/apps"
        cp "$src/assets/micwatch-$s.png" "$HOME/.local/share/icons/hicolor/${s}x${s}/apps/micwatch.png"
    done
    sed "s|^Exec=micwatch$|Exec=$HOME/.local/bin/micwatch|" \
        "$src/packaging/micwatch.desktop" > "$HOME/.local/share/applications/micwatch.desktop"
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) warn "$HOME/.local/bin is not in your PATH" ;;
    esac
}

native_install() {
    case "$fam" in
        rpm)
            pkg="$(fetch .noarch.rpm)"
            info "installing with dnf"
            $SUDO dnf install -y "$pkg" ;;
        deb)
            pkg="$(fetch _all.deb)"
            info "installing with apt"
            $SUDO apt-get update -qq || true
            $SUDO apt-get install -y "$pkg" \
                || { $SUDO dpkg -i "$pkg"; $SUDO apt-get -f install -y; } ;;
        arch)
            pkg="$(fetch .pkg.tar.zst)"
            info "installing with pacman"
            $SUDO pacman -U --noconfirm "$pkg" ;;
    esac
}

if [ -n "$fam" ]; then
    if distro_has_pyside; then
        native_install
    else
        venv_install
    fi
elif have_pyside; then
    info "unknown distro, but PySide6 is present — installing the AppImage into ~/.local/bin"
    pkg="$(fetch .AppImage)"
    mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
    install -m 0755 "$pkg" "$HOME/.local/bin/micwatch"
    cat > "$HOME/.local/share/applications/micwatch.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=MicWatch
Comment=Tray indicator that lights up when the microphone is in use
Exec=$HOME/.local/bin/micwatch
Icon=audio-input-microphone
Terminal=false
Categories=AudioVideo;Audio;Utility;
DESKTOP
else
    venv_install
fi

info "done — run it with:  micwatch"
info "enable 'Start on login' from the tray menu to bring it back at every login"
