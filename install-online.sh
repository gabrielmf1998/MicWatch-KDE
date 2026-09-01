#!/bin/sh
# MicWatch — online installer. Detects the distro and installs the matching
# package from the latest GitHub release. Unknown distros get the AppImage.
#
#   curl -fsSL https://raw.githubusercontent.com/gabrielmf1998/MicWatch-KDE/main/install-online.sh | sh
set -eu

BASE="https://github.com/gabrielmf1998/MicWatch-KDE/releases/latest/download"
info() { printf '\033[1m==>\033[0m %s\n' "$*"; }
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
fetch() { info "downloading $1"; curl -fL "$BASE/$1" -o "$tmp/$1" || err "download failed: $1"; }

case "$fam" in
    rpm)
        fetch micwatch-kde-1.0.0-1.fc46.noarch.rpm
        info "installing with dnf"
        $SUDO dnf install -y "$tmp/micwatch-kde-1.0.0-1.fc46.noarch.rpm" ;;
    deb)
        fetch micwatch-kde_1.0.0-1_all.deb
        info "installing with apt"
        $SUDO apt-get update -qq || true
        $SUDO apt-get install -y "$tmp/micwatch-kde_1.0.0-1_all.deb" \
            || { $SUDO dpkg -i "$tmp/micwatch-kde_1.0.0-1_all.deb"; $SUDO apt-get -f install -y; } ;;
    arch)
        fetch micwatch-kde-1.0.0-1-any.pkg.tar.zst
        info "installing with pacman"
        $SUDO pacman -U --noconfirm "$tmp/micwatch-kde-1.0.0-1-any.pkg.tar.zst" ;;
    *)
        info "unknown distro — installing the AppImage into ~/.local/bin"
        fetch MicWatch-KDE-x86_64.AppImage
        mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
        install -m 0755 "$tmp/MicWatch-KDE-x86_64.AppImage" "$HOME/.local/bin/micwatch"
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
