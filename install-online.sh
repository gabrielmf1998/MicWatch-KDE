#!/bin/sh
# MicWatch — online installer.
#
# Installs the native package for your distro. Distros that do not ship PySide6
# (Ubuntu 24.04, for one) and unknown distros get the self-contained build
# unpacked into ~/.local, so the one-liner works everywhere.
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

# Portable install: the self-contained AppImage, unpacked into ~/.local so it
# starts instantly and needs neither FUSE nor a system PySide6.
portable_install() {
    info "this distro has no PySide6 package — installing the self-contained build"
    case "$fam" in
        deb) $SUDO apt-get update -qq || true
             $SUDO apt-get install -y pipewire-bin pulseaudio-utils curl || true ;;
        rpm) $SUDO dnf install -y pipewire-utils pulseaudio-utils curl || true ;;
        arch) $SUDO pacman -S --needed --noconfirm pipewire libpulse curl || true ;;
    esac

    pkg="$(fetch .AppImage)"
    prefix="$HOME/.local/share/micwatch"
    info "unpacking into $prefix (about 200 MB on disk)"
    rm -rf "$prefix/AppDir"
    mkdir -p "$prefix"
    chmod +x "$pkg"
    ( cd "$tmp" && "$pkg" --appimage-extract >/dev/null ) || err "could not unpack the AppImage"
    mv "$tmp/squashfs-root" "$prefix/AppDir"

    mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
    cat > "$HOME/.local/bin/micwatch" <<LAUNCHER
#!/bin/sh
exec "$prefix/AppDir/AppRun" "\$@"
LAUNCHER
    chmod +x "$HOME/.local/bin/micwatch"
    for size in 48 64 128 256; do
        icon="$prefix/AppDir/usr/share/icons/hicolor/${size}x${size}/apps/micwatch.png"
        [ -f "$icon" ] || continue
        mkdir -p "$HOME/.local/share/icons/hicolor/${size}x${size}/apps"
        cp "$icon" "$HOME/.local/share/icons/hicolor/${size}x${size}/apps/micwatch.png"
    done
    sed "s|^Exec=micwatch$|Exec=$HOME/.local/bin/micwatch|" \
        "$prefix/AppDir/usr/share/applications/micwatch.desktop" \
        > "$HOME/.local/share/applications/micwatch.desktop" 2>/dev/null || true
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
        portable_install
    fi
else
    portable_install
fi

info "done — run it with:  micwatch"
info "enable 'Start on login' from the tray menu to bring it back at every login"
