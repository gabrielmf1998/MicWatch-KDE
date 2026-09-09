Name:           micwatch-kde
Version:        1.3.0
Release:        1%{?dist}
Summary:        Microphone in-use tray indicator with a user-defined threshold

License:        MIT
URL:            https://github.com/gabrielmf1998/MicWatch-KDE
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch


Requires:       python3
Requires:       python3-pyside6
Requires:       pipewire-utils
Requires:       pulseaudio-utils
Requires:       curl

# only needed for the global keyboard shortcuts
Recommends:     python3-evdev

%description
MicWatch is a tray indicator that lights up when an application is actually
using the microphone, and lets you mute one application's microphone without
touching the others. It separates "an app opened the input device" from
"sound is really going through it": you set a threshold in dBFS, and the icon
only lights up above it. 26 icon styles, 25 animations and a colour per state, A global keyboard shortcut can mute one
application without touching the others, and it can check GitHub for updates
and upgrade itself in one click, when you press the button.

It never opens the microphone on its own: the level meter runs only while some
other application is already recording.

%prep
%autosetup -n %{name}-%{version}

%install
install -d %{buildroot}%{_datadir}/%{name}/micwatch
install -m 0644 micwatch/*.py %{buildroot}%{_datadir}/%{name}/micwatch/
install -Dm 0755 packaging/micwatch %{buildroot}%{_bindir}/micwatch
install -Dm 0644 packaging/micwatch.desktop \
    %{buildroot}%{_datadir}/applications/micwatch.desktop
for s in 48 64 128 256 512; do
    install -Dm 0644 assets/micwatch-${s}.png \
        %{buildroot}%{_datadir}/icons/hicolor/${s}x${s}/apps/micwatch.png
done
install -Dm 0644 assets/micwatch.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/micwatch.svg
install -Dm 0644 LICENSE %{buildroot}%{_datadir}/licenses/%{name}/LICENSE
install -Dm 0644 README.md %{buildroot}%{_datadir}/doc/%{name}/README.md

%files
%license LICENSE
%doc README.md
%{_bindir}/micwatch
%{_datadir}/%{name}/
%{_datadir}/applications/micwatch.desktop
%{_datadir}/icons/hicolor/*/apps/micwatch.*

%changelog
* Wed Sep 09 2026 Gabriel Marques Ferrarezi <110578985+gabrielmf1998@users.noreply.github.com> - 1.3.0-1
- Global shortcut per application, read from /dev/input so it works in fullscreen
- List of every application that has used the microphone, browsers included

* Wed Sep 02 2026 Gabriel Marques Ferrarezi <110578985+gabrielmf1998@users.noreply.github.com> - 1.2.1-1
- Update check is on demand only: the daily background check is gone

* Wed Sep 02 2026 Gabriel Marques Ferrarezi <110578985+gabrielmf1998@users.noreply.github.com> - 1.2.0-1
- 26 icon styles, 25 animations (glitch, crazy rainbow, neon, jelly...), 24 colour presets
- Built-in update checker with a one-click upgrade

* Wed Sep 02 2026 Gabriel Marques Ferrarezi <110578985+gabrielmf1998@users.noreply.github.com> - 1.1.0-1
- Per-application mute and capture volume, device mute, muted tray state

* Tue Sep 01 2026 Gabriel Marques Ferrarezi <110578985+gabrielmf1998@users.noreply.github.com> - 1.0.1-1
- Bigger icons: every style now fills the tray slot, plus an Icon size slider

* Mon Aug 31 2026 Gabriel Marques Ferrarezi <110578985+gabrielmf1998@users.noreply.github.com> - 1.0.0-1
- First release: dBFS threshold, 18 icon styles, 15 animations, autostart switch
