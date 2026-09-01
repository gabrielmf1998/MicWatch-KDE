# MicWatch

A microphone in-use tray indicator for PipeWire, built for KDE Plasma.

It does one thing: **light up when the microphone is actually being used** — and it lets
you decide what "being used" means, with a level threshold you set yourself.

![states](docs/states.png)

## Why not the built-in one

Plasma's microphone indicator lights up the moment any application *opens* the input
device, even when nothing is going through it. MicWatch separates the two:

| State | Meaning | Default colour |
|-------|---------|----------------|
| Idle | nothing is recording | grey `#6e7681` |
| Open, quiet | an app holds the mic, but the signal is below your threshold | amber `#e3b341` |
| In use | signal is above your threshold | green `#3fb950` |

## Features

- **6 icon styles** — outline mic, solid mic, badge, dot, ring meter, level bars.
- **5 animations** — none, pulse, blink, glow halo, or follow-the-level.
- **Full colour control** — one colour per state, hex field, colour picker and presets.
- **User-defined threshold** — with a live meter, a dB/% readout and a
  *Set just above noise* button that parks the threshold above your room noise.
- **Hold time** so the icon does not flicker between words.
- Ignores monitor-of-sink streams; virtual sources (screen share, loopback) are opt-in.
- Ignore list for apps you do not care about (`easyeffects`, `obs`, …).
- Optional: hide the icon completely while nothing is recording.
- Tooltip and menu show **which** applications are recording and from which device.

## Requirements

- PipeWire with `pw-cat` and `pactl` (`pipewire-utils`, `pulseaudio-utils`)
- Python 3.11+ and PySide6 (`sudo dnf install python3-pyside6`)

## Install

```sh
./install.sh     # creates ~/.local/bin/micwatch and the .desktop entry
micwatch         # run it
```

Enable *Start automatically on login* in **Behaviour** to autostart.

To avoid two microphone icons, disable Plasma's own:
**System Settings → Quick Settings → System Tray → Entries → Microphone → Disabled**.

## How it works

- `pactl subscribe` + `pactl -f json list source-outputs` tell MicWatch *who* is
  recording and from which source (streams reading a sink monitor are not microphone use).
- Only while some app is recording (and only if the threshold is enabled) does MicWatch
  open its own `pw-cat` capture — named `MicWatch Meter` — to measure the RMS level.
  With the threshold turned off, MicWatch never touches the microphone at all.

Config lives in `~/.config/micwatch/config.json`; every change in the settings window is
applied and saved immediately.

## Layout

```
micwatch/config.py     defaults, load/save
micwatch/audio.py      stream detection (pactl) + level meter (pw-cat)
micwatch/icons.py      every icon painted at runtime with QPainter
micwatch/tray.py       state machine: idle / open-quiet / in-use
micwatch/settings.py   settings window with live meter
```
