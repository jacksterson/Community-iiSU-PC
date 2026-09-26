# Community-iiSU-PC (Linux)

Runs iiSU (an Android emulation frontend) inside a hardware-accelerated Android VM on Linux (via KVM), patched so launching a game in iiSU seamlessly hands off to native PC emulators instead of Android ones.

**This does not include iiSU itself.** iiSU is closed-source, third-party software this project has no direct affiliation with. You will need your own copy of its APK. This tool patches *your* copy, the same way any APK-patching/modding tool works; it never bundles or redistributes iiSU's binary.

## Features

- **Seamless Linux Integration:** Auto-launches in borderless fullscreen with 1:1 monitor scaling and automatic window rule configuration (KWin / X11 / Wayland compatibility).
- **Zero-Friction Immersion:** Stock Android launcher and Google boot logos disabled so it feels like a native frontend application rather than an Android VM.
- **Controller Support:** Native Linux joystick bridge for PlayStation (DualSense / DualShock), Xbox, and generic USB gamepads, with automated input filtering for gyros and virtual pointers.
- **Built-in Emulator Downloader:** Integrated Flatpak and native emulator downloader in Settings and Onboarding to get DuckStation, Dolphin, PCSX2, RPCS3, RetroArch, and more in one click.
- **Global Quit Hotkeys:** Graceful shutdown via `Esc`, `Alt+F4`, `Ctrl+Q`, or controller chord (`Select + Start`).

## Requirements

- 64-bit Linux distribution with KVM enabled (`/dev/kvm`).
- Python 3.10+ and OpenJDK/Java (`java` and `keytool` on PATH).
- Your own copy of the iiSU APK (drop into `installer/input/` or browse during setup).
- Whichever PC emulators you want to use (or install them automatically via the Manager's downloader).
- Free disk space for the self-contained Android SDK and system image.

## First-time setup

1. Drop your iiSU APK into `installer/input/`, or point Setup at it with Browse.
2. Run **`./Setup.sh`** or **`./Community-iiSU-PC\ Manager.sh`** and click **Run Setup** on the Home page.

Setup checks your APK, downloads and sets up a self-contained portable Android SDK and AVD, patches your APK with the PC launch bridge, installs redirector apps, and creates desktop shortcuts.

Once setup finishes, the onboarding wizard walks you through selecting your ROM directory, scanning emulators, display resolution, and controller quit chords.

## Day to day use

- Launch directly via the **Community-iiSU-PC** desktop shortcut.
- Open the manager anytime with **`./Community-iiSU-PC\ Manager.sh`**.
- To stop or exit: press **`Esc`**, **`Alt+F4`**, **`Ctrl+Q`**, press **`Select+Start`** on your controller, or double-click the **Stop Community-iiSU-PC** shortcut.

Sidebar navigation in the Manager:

- **Home**: AVD/bridge status, Open/Stop, a running status line, and quick buttons to your ROMs folder and logs.
- **Library**: ROM Directory (your host ROM folder), Media Library (check/restore saved media, and browse/install more through iiDB), Android Storage (browse and manage the VM's shared storage over ADB).
- **Games**: Console (every detected ROM, grouped by multi-disc playlist) and PC (native Linux games and Steam URI launches).
- **Emulators**: PC emulator mappings and search folders, test a mapping without starting the AVD, and reinstall iiSU's redirector apps.
- **Settings**: Display (the Android VM's resolution and DPI) and Advanced (hotkeys and debugging options such as "Show console windows").
- **Backup & Diagnostics**: Backup & Restore (back up configuration to a ZIP or restore an earlier one) and Diagnostics (non-destructive checks of the install, Android VM/ADB, bridge, Steam integration, logs; also where you check for and apply updates).
- **Credits**: who built this and how (see below).
- **Uninstall**: below a divider at the bottom of the sidebar.

On startup, Community-iiSU-PC re-syncs your ROM library into the VM automatically. Automatic project updates are opt-in and can be enabled from Backup & Diagnostics; **Check for Updates Now** only checks whether an update is available and does not download or install it. The same page also checks whether a newer iiSU is available (against its official GitHub releases) and can re-patch and reinstall it, with a manual override to point at any APK directly.

A fullscreen overlay covers the AVD boot and the emulator hand-off, showing what's happening ("Booting Community-iiSU-PC...", "Waiting on DuckStation...") instead of raw desktop.

By default, **Escape** controls game quitting and shutdown: tap it while a game is running to force-quit the game and return to iiSU, or tap it while already in iiSU to shut down Community-iiSU-PC. Pressing **Select+Start** together on a controller does the same thing, and the chord is remappable to any combination of buttons.

## PC Games & Steam Integration

The Manager's **Games > PC** page lets iiSU launch native PC games in addition to emulated console games. An entry can launch either an executable binary or a registered URI/protocol such as `steam://rungameid/...`.

Each entry is represented in iiSU by an empty `.pcgame` placeholder under `bridge/windows_stubs/`, kept out of your actual ROM directory so it never shows up when you're browsing your real ROM library. The real launch information stays in `bridge/windows_apps.json`; the launch bridge intercepts iiSU's request for the placeholder and starts the configured target instead. Sync into the AVD merges these placeholders into iiSU's `windows` folder automatically.

Use **Add** for individual programs, or **Import Steam Library** to pick installed Steam games and create URI-based entries automatically.

## Console Games and multi-disc playlists

The Manager's **Games > Console** page lists every game detected in your ROM library, grouped the same way syncing to the AVD does: a multi-disc game backed by an `.m3u`/`.cue` shows up as one entry, not one per disc. Select rows and right-click for two exceptions to that default:

- **Keep Discs Separate** is for a game like Gran Turismo 2, where an `.m3u` actually bundles distinct, separately-launchable modes rather than continuation discs: the individual files show up in iiSU as their own entries instead, and the playlist/sheet itself is hidden from iiSU (still listed on this page, greyed as "hidden", so you can merge it back together later). Only applies to selected playlists/sheets, never to a plain single-file game.
- **Merge Discs Together** undoes that for a previously-excepted playlist/sheet.

Both take effect on your next Start, not while Community-iiSU-PC is already running.

## Uninstalling

Open the Manager's **Uninstall** page for a preview of exactly what will be removed and how much space it frees before you confirm. It removes the Android VM and its portable SDK copy, `bridge/config.json`, the signing keystore, and desktop shortcuts. It does not touch your ROM library, your PC emulators, or the iiSU APK you supplied.

## How it works, briefly

`installer/patch_iisu.py` decompiles your iiSU APK, redirects its ROM-launch code to a small injected class that sends the launch request to `bridge/launch_bridge.py` over a local socket, then rebuilds and signs it. The bridge matches normal ROM requests to a PC emulator (configured in `bridge/config.json`). Native game requests are instead matched against `bridge/windows_apps.json` and launched directly as native executables or registered URI/protocol targets.

iiSU also needs to think a real emulator is installed for each console before it'll treat it as playable. Setup installs a placeholder "redirector" app for each one (`installer/stub_apk.py`) that does nothing itself, since the patched launch never reaches it. The Manager's Emulators page has an "Install Redirector Apps..." button to re-run this any time.

## Project layout

```
Setup.sh, Uninstall.sh     CLI-only entry points; use the Manager instead for normal use
Community-iiSU-PC Manager.sh Manager launcher script
VERSION                    this install's release tag, compared against GitHub Releases on a non-git install

shared/qt_theme.py         the dark/gradient look and fonts shared by every window in this project
shared/emulator_defaults.py  curated console -> PC emulator mappings, and which need a redirector
shared/platform_compat.py   cross-platform POSIX / Linux compatibility layer
shared/qt_avatars.py       fetches+circle-crops a GitHub avatar for the Credits page

installer/
  setup_wizard.py          first-time setup and the iiSU update flow, called by setup_app.py
  patch_iisu.py            decompiles, patches, rebuilds, and signs your iiSU (or an update to it)
  sdk_bootstrap.py         downloads/installs the Android SDK and creates the AVD
  smali_patch/             the injected LaunchBridge classes patch_iisu.py adds to iiSU
  stub_apk.py              builds/installs the placeholder "redirector" apps
  stub_apk_template/       the redirector app project
  uninstall.py             removes everything Setup and day-to-day use create

bridge/
  ui/                      the Manager GUI (PySide6/Qt): app.py is the entry point, pages/ and dialogs/
                            hold each screen, widgets/ shared building blocks like the display-resolution
                            preview and the sidebar's rounded Card
  services/                non-GUI logic behind the GUI pages (diagnostics, backups, PC games,
                            Android storage, media library/iiDB, iiSU update checks)
  bridge_config.py         shared config.json loader
  apply_display.py         applies config.json's display settings to the AVD
  start_iisu_pc.py         checks for updates, boots the AVD, starts launch_bridge.py
  updater.py               checks for (and, on a git checkout, applies) updates
  stop_iisu_pc.py          tears both back down
  launch_bridge.py         handles iiSU launches for PC emulators and native games
  controller_bridge.py     forwards controller input into the AVD
  emulator_downloader.py   Flatpak and native Linux emulator downloader service
  portable_sdk.py          copies the SDK/AVD into a self-contained folder
  sync_library.py          mirrors your ROM library into the AVD as placeholders
  console_names.py         resolves a ROM folder name to one of iiSU's known consoles
  create_shortcut.py       creates desktop shortcuts
  winapi.py                window management and KWin / X11 fullscreen helpers

tests/                    unit tests for the pure routing/mapping logic (no AVD needed)
```

## Running tests

`python3 -m unittest discover -s tests` runs the unit tests covering console/emulator routing logic (`shared/emulator_defaults.py`, `bridge/console_names.py`, `bridge/launch_bridge.py`'s `find_emulator_for_package`, `bridge/emulator_downloader.py`, `bridge/controller_bridge.py`). Stdlib-only, no AVD or adb needed.

## If something breaks

- Run the Manager's **Backup & Diagnostics > Diagnostics** page first for a non-destructive check of the installation, configuration, Android VM/ADB, bridge, Steam integration, and logs.
- `bridge/manager_debug.log` and `bridge/bridge_debug.log` preserve Manager and launch-bridge diagnostics, including uncaught Python exceptions that might otherwise disappear when a console closes.
- `installer/patch_iisu.py`'s patch is anchored on specific log strings in iiSU's code. If iiSU updates and changes them, the patch fails loudly instead of silently producing a broken build.
- `bridge/emulator.log`, `bridge/bridge.log`, and `bridge/stop.log` cover the AVD, the launch bridge, and shutdown respectively. Open the Manager's Home page (Logs button) to check them.
- Re-running setup is safe: it skips anything already done and won't overwrite an existing `config.json`'s settings.
- Community-iiSU-PC uses a quick resume when nothing relevant has changed since the last start, and only cold-boots (a bit slower) when your settings or ROM library have changed since then, or on the very first start.

## Support & Donations

If you find the Linux port helpful and would like to support ongoing development and maintenance:

[![Donate with PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg?logo=paypal)](https://paypal.me/jacksterson)

You can donate directly via PayPal at **[paypal.me/jacksterson](https://paypal.me/jacksterson)**. Any support is greatly appreciated!

## Credits

- **[MAGOOSKEE](https://github.com/MAGOOSKEE)**: project owner, built and maintains Community-iiSU-PC.
- **[Jacksterson](https://github.com/jacksterson)**: Linux port, cross-platform POSIX compatibility, Flatpak and native Linux emulator integration.
- **[Claude](https://github.com/claude)** (Anthropic): AI coding assistant; wrote and refactored most of this codebase in collaboration with MAGOOSKEE.
- **[Gemini](https://github.com/google)** (Google DeepMind): AI coding assistant; engineered the Linux port, POSIX compatibility layer, and platform optimizations in collaboration with Jacksterson.

They are shown with live GitHub avatars on the Manager's Credits page.

**AI disclosure:** a large share of this project's code was written by Claude and Gemini, working under MAGOOSKEE's and Jacksterson's direction and review. If you're evaluating this project for safety or correctness before running it, keep that in mind and read the source.
