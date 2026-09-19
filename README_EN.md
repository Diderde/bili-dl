# bili-dl — Bilibili Audio & Video Download Tool

[简体中文](README.md) | English

[![CI](https://github.com/Diderde/bili-dl/actions/workflows/ci.yml/badge.svg)](https://github.com/Diderde/bili-dl/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows95)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
![License](https://img.shields.io/badge/license-GPL--2.0--or--later-informational)

A Windows desktop tool to download Bilibili audio & video — save video and audio as **separate streams** or merge them into a **single file**. Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp), with a [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) interface (dark / light / follow system). Tested on Windows 11 only.

## Features

- Downloads the best video and audio streams **separately** (default — no FFmpeg needed), or **merges them into a single file** (FFmpeg required; grab a portable build with one click from the UI, or install it yourself)
- Quality caps: 480p (default) / 720p / 1080p / best available
- Modern Chrome headers and request throttling for Bilibili endpoints
- Reads login cookies from Chrome / Edge / Firefox, or a Netscape-format cookies.txt
- Cancel a download at any time; live progress with speed and ETA
- Run-log panel; warnings and errors surface in the status bar
- Common failures ("No video formats found", locked cookie databases, …) are translated into plain, actionable guidance
- Remembers your preferences: quality, cookie source, audio/video mode, and theme (stored in `%APPDATA%\bili_dl\settings.json`; the **save location resets on every launch** to the `downloads` folder next to the program — a relative path that travels with the app, temporarily changeable via Browse, and never recorded)

> Note: browser TLS fingerprint impersonation (curl_cffi) ships with the app but is off by default — in testing it makes the playurl endpoint return an empty format list. Flip `impersonate` to `True` in code if you ever need it.

## Quick start

1. Keep `run.bat`, `bootstrap.py` and `src/` in the same folder.
2. Double-click `run.bat`. The launcher first prints an **environment & dependency checklist** (Python / tkinter / yt-dlp / curl_cffi / customtkinter / bili_dl, plus optional ffmpeg): if everything is green it bumps yt-dlp to the nightly build and starts the app; anything missing triggers an automatic rebuild, then the checklist runs again.
3. Details are saved to `environment_report.txt`.

## Manual installation

```powershell
cd bilibili_downloader
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m bili_dl
```

Once installed, the `bili-dl` command works too.

## Usage

1. Paste a BV number, an av number, or a bilibili.com / b23.tv link (a whole sentence containing a link works just as well).
2. Pick the save folder, a quality cap, and how to handle audio & video (separate by default — no FFmpeg; merging requires FFmpeg on the system).
3. Normally, keep "do not read browser cookies". If you hit HTTP 412: sign in to Bilibili in Chrome / Edge / Firefox, make sure the video plays there, then pick that same browser as the login source and try again.
4. cookies.txt and browser cookies are **mutually exclusive** — use one or the other.

## Hitting HTTP 412?

1. Sign in to Bilibili in the chosen browser and confirm the video plays there;
2. Back in the app, pick that same browser as the login source;
3. Never use cookies.txt and browser cookies together;
4. Close incognito windows and make sure the app and the browser share the same network;
5. Re-run `run.bat` to update yt-dlp and curl_cffi;
6. Avoid hammering the same video over and over in a short time.

## "No video formats found"?

Usually means Bilibili changed something and yt-dlp's parser hasn't caught up:

1. Re-run `run.bat` — the launcher updates yt-dlp to the nightly build automatically;
2. Still failing? Pick a logged-in browser as the cookie source (some content requires login or premium membership);
3. Try again later while upstream ships a fix.

## Development

```powershell
python -m pip install -e ".[dev]"
pytest          # unit tests (no network access)
ruff check .    # style checks
```

## Third-party dependencies

Direct dependencies (everything else resolves through pip; each component keeps its own license):

| Component | Role | License |
|---|---|---|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | parsing & download core | Unlicense (public domain) |
| [curl-cffi](https://github.com/lexiforest/curl-cffi) | browser TLS impersonation (optional, off by default) | MIT |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | modern UI toolkit | MIT |

This project ships source code only — dependencies are installed from PyPI on the user's side, and `bootstrap.py` fetches `get-pip.py` from the official PyPA endpoint only when pip is missing. No third-party code is bundled or modified.

**Optional external component**: merging requires FFmpeg — the easiest way is the in-app one-click download, which installs a portable build into the program folder's `ffmpeg\` directory (no admin rights; delete the folder to uninstall). You can also grab it from the [FFmpeg website](https://ffmpeg.org/download.html) or run `winget install Gyan.FFmpeg`. The default separate mode needs none of this.

## Project structure

```
bilibili_downloader/
├── run.bat                  # one-click launcher
├── bootstrap.py             # environment bootstrap (stdlib only)
├── pyproject.toml           # packaging & tooling config
├── src/bili_dl/
│   ├── __main__.py          # python -m bili_dl entry point
│   ├── gui.py               # CustomTkinter interface
│   ├── core.py              # download engine (yt-dlp options, cancel, progress)
│   ├── settings.py          # settings persistence
│   ├── utils.py             # link parsing, error translation, helpers
│   └── constants.py         # constants: headers, quality/cookie options, etc.
└── tests/                   # unit tests
```

## Notes

This project is open source under [GPL-2.0-or-later](LICENSE): any redistributed derivative must likewise be licensed GPL-2.0-or-later with the copyright notice intact. Please follow Bilibili's Terms of Service, and do not use downloaded content for commercial purposes.
