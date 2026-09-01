#!/bin/sh
# MicWatch — online installer. Detects the distro and installs the matching
# package from the latest GitHub release. Unknown distros get the AppImage.
#
#   curl -fsSL https://raw.githubusercontent.com/gabrielmf1998/MicWatch-KDE/main/install-online.sh | sh
set -eu

REPO="gabrielmf1998/MicWatch-KDE"
API="https://api.github.com/repos/$REPO/releases/latest"
# everything informational goes to stderr: fetch() returns a path on stdout
info() { printf '\033[1m==>\033[0m %s\n' "$*" >&2; }
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

# Resolve an asset by suffix, so the installer survives version bumps.
fetch() {
    suffix="$1"
    url="$(curl -fsSL "$API" \
        | tr ',' '\n' | grep '"browser_download_url"' | cut -d'"' -f4 \
        | grep -- "$suffix\$" | head -1)"
    [ -n "$url" ] || err "no asset ending in '$suffix' in the latest release"
    out="$tmp/${url##*/}"
    info "downloading ${url##*/}"
    curl -fL --progress-bar "$url" -o "$out" || err "download failed: $url"
    printf '%s' "$out"
}

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
    *)
        info "unknown distro — installing the AppImage into ~/.local/bin"
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
        info "the AppImage needs python3 + PySide6 on the system" ;;
esac

info "done — run it with:  micwatch"
info "enable 'Start on login' from the tray menu to bring it back at every login"
