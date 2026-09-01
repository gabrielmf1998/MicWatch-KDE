# MicWatch

A microphone in-use tray indicator for PipeWire, built for KDE Plasma.

It does one thing: **light up when the microphone is actually being used** — and it lets
you decide what "being used" means, with a threshold in dBFS that you set yourself.

![Icon styles and states](docs/states.png)

## Why not the built-in one

Plasma's microphone indicator lights up the moment any application *opens* the input
device, even when nothing is going through it. MicWatch separates the two:

| State | Meaning | Default colour |
|-------|---------|----------------|
| Idle | nothing is recording | grey `#6e7681` |
| Open, quiet | an app holds the mic, but the signal is below your threshold | amber `#e3b341` |
| In use | the signal is above your threshold | green `#3fb950` |

## Install

One command, any of the distros below:

```sh
curl -fsSL https://raw.githubusercontent.com/gabrielmf1998/MicWatch-KDE/main/install-online.sh | sh
```

Or grab a package from the [latest release](https://github.com/gabrielmf1998/MicWatch-KDE/releases/latest):

```sh
sudo dnf install ./micwatch-kde-1.0.0-1.fc46.noarch.rpm       # Fedora
sudo apt install ./micwatch-kde_1.0.0-1_all.deb               # Debian / Ubuntu
sudo pacman -U ./micwatch-kde-1.0.0-1-any.pkg.tar.zst         # Arch
chmod +x MicWatch-KDE-x86_64.AppImage && ./MicWatch-KDE-x86_64.AppImage
```

From a clone, into `~/.local` and without touching the system:

```sh
git clone https://github.com/gabrielmf1998/MicWatch-KDE.git
cd MicWatch-KDE && ./install.sh && micwatch
```

The AppImage is a thin launcher: it carries MicWatch itself and uses the system
`python3` + PySide6, so it stays under a megabyte instead of bundling all of Qt.

### Requirements

- PipeWire with `pw-cat` and `pactl` (`pipewire-utils`, `pulseaudio-utils`)
- Python 3.11+ and PySide6 (`sudo dnf install python3-pyside6`)

The native packages pull these in for you.

## Screenshots

Pick an icon, an animation and a colour per state. The three icons at the top are a live
preview — the "In use" one plays the animation you selected:

![Appearance tab](docs/settings-appearance.png)

Set the threshold against a live dB meter. The amber line is the threshold, the white line
is the peak; *Set just above noise* listens for 3 seconds and parks the threshold 7 dB
above your room noise:

![Detection tab](docs/settings-detection.png)

Start with the session, hide the icon while idle, or drop the separate "quiet" colour:

![Behaviour tab](docs/settings-behaviour.png)

## Features

- **18 icon styles** — microphone (outline/solid/circle/badge), headset mic, studio mic,
  dot, dot with ring, LED tile, record, ring meter, double ring, gauge, level bars,
  wide bars, waveform, signal waves and heartbeat line. Picked from a visual grid.
- **15 animations** — none, pulse, breathe, blink, fast strobe, glow halo, ripple rings,
  bounce, wobble, spin, heartbeat, follow-the-level, glow-with-the-level, rainbow, siren.
- **Full colour control** — one colour per state, hex field, colour picker and 12 presets.
- **User-defined threshold in dBFS** — live meter on a dB scale (−60 … 0 dB), a numeric
  readout, and a *Set just above noise* button.
- **Pick which input to measure** — follow the recording app, or pin one device.
- Fast attack / adjustable release, so the icon reacts on the first syllable and does not
  strobe between words; plus a hold time after speech stops.
- Ignores monitor-of-sink streams; virtual sources (screen share, loopback) are opt-in.
- Ignore list for apps you do not care about (`easyeffects`, `obs`, …).
- Optional: hide the icon completely while nothing is recording.
- Tooltip and menu show **which** applications are recording and from which device.
- **Start on login** from the tray menu or the Behaviour tab.

## Privacy

MicWatch never opens the microphone on its own. The level meter only runs while some other
application is already recording (or while you tick *Live meter* in the settings window to
calibrate). With the threshold turned off it never touches the microphone at all — it just
reads the list of recording streams.

## How it works

- `pactl subscribe` + `pactl -f json list source-outputs` tell MicWatch *who* is recording
  and from which source. Streams reading a sink monitor are loopback, not microphone use.
- While an app records, MicWatch opens its own `pw-cat` capture — it shows up as
  `MicWatch Meter` — and measures RMS per 30 ms block, converted to dBFS.

A quiet room measures around −50 dB and speech lands between −35 and −20 dB, which is why
the default threshold is −42 dB.

Config lives in `~/.config/micwatch/config.json`; every change in the settings window is
applied and saved immediately.

## Start with the session

Two equivalent switches, both writing `~/.config/autostart/micwatch.desktop`:

- right-click the tray icon → **Start on login**
- **Settings → Behaviour → Startup → Start MicWatch automatically on login**

It also shows up in **System Settings → Autostart**, and a single-instance lock keeps a
second copy from starting if one is already running.

To avoid two microphone icons, disable Plasma's own:
**System Settings → Quick Settings → System Tray → Entries → Microphone → Disabled**.

## Layout

```
micwatch/config.py      defaults, load/save
micwatch/audio.py       stream detection (pactl) + level meter (pw-cat)
micwatch/icons.py       every icon painted at runtime with QPainter
micwatch/tray.py        state machine: idle / open-quiet / in-use
micwatch/settings.py    settings window with the live dB meter
micwatch/autostart.py   XDG autostart entry
packaging/              rpm spec, deb/arch/AppImage build script
assets/gen_icons.py     regenerates the application icons
```

Build every package into `dist/` with `packaging/build-packages.sh`.

## License

MIT — see [LICENSE](LICENSE).
