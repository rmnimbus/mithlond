# Changelog

## 1.4.2

- **Fix: the AppImage didn't start on Linux Mint, Ubuntu and other distributions without `libxcb-cursor0`**
  ("xcb-cursor0 or libxcb-cursor0 is needed to load the Qt xcb platform plugin", then "Aborted"). The
  AppImage now brings that library and the other small xcb-util libraries Qt's X11 support needs, built for
  glibc 2.14 or newer.
- **If you're on 1.4.0 or 1.4.1 and it already runs**, it offers this update automatically. If it doesn't start,
  download 1.4.2 from the releases page.

## 1.4.1

- Fix the Settings section title, which showed "About _updates" instead of "About & updates".
- First release delivered through the built-in updater: 1.4.0 offers it automatically.

## 1.4.0

- **Mithlond updates itself.** At startup it checks GitHub for a newer release (can be turned off), and a banner
  offers **Update now**, **What's new** and **Skip this version**. **Settings → About & updates** has the current
  version and a **Check for updates** button. Updating downloads the new AppImage next to the current one,
  verifies its size, AppImage header and GitHub's SHA-256 checksum, makes it executable, replaces the old file
  and offers to restart. Running from source, it opens the release page instead.

## 1.3.0

- **The game always uses your chosen documents folder.** Mithlond starts the client with
  `--prefs <documents>\UserPreferences.ini`, which makes the game use that folder for settings, plugins, music
  and plugin data, whatever the Wine prefix. Tested: the game read and wrote its settings in the chosen folder
  and left the prefix's own folder alone. Folders without game settings get them copied from the prefix (or
  DirectX 11 defaults), because without them the game stops at a first-run graphics prompt.
- **Choose…** next to the documents folder lists every LOTRO documents folder found on the computer, showing
  where it belongs, when it was last played, its plugin and song counts and whether it's a link. It can also
  create a new one.
- Removed the separate *Plugins folder* setting. The game only loads plugins from its documents folder, so the
  setting could only make Mithlond install plugins where the game never looks.
- Proton builds for another CPU architecture (e.g. an aarch64 "Proton-GE Latest" on an x86-64 PC) are greyed
  out in the runner list, and launching with one gives a clear error instead of "Exec format error".

## 1.2.1

- **Fix: "corestrings.dll not found" with Proton-EM.** Proton-EM starts programs given as Linux paths through
  `start.exe /unix`, which runs them from their own folder (`x64/`). There the 64-bit client can't find
  `corestrings.dll`, which lives in the game folder. Mithlond now passes the game as a Windows path
  (`Z:\…`), so every Proton build keeps the game folder as the working directory, like the official launcher.
- LotRO Companion with Proton-EM-style builds: they can't run Companion's bundled Java directly, so Mithlond
  detects them and uses Companion's own launcher. It's fine as long as Companion is up to date; use the
  Companion tab's Update button.

## 1.2.0

- **The Downloads tab now lists every LOTRO addon on lotrointerface.com** (about 1,180), not just the curated
  lists. lotrointerface has no API for the full catalogue, so Mithlond reads the site's own category pages
  (about 70 pages, politely paced, cached for a day). The curated lists show up instantly; the rest follow
  within about half a minute on the first load of the day.
- Addons that are only in the full catalogue load their version and description when you select them. Ones
  you have installed are checked for updates in the background.
- New **Hide outdated** checkbox, on by default, for the 400+ addons in "Outdated LotRO Interfaces".

## 1.1.2

- **Plugin list now merges both lotrointerface.com lists** (OneLauncher's and LOTRO Plugin Compendium's):
  474 plugins instead of 412. Plugins like Festival Buddy II were missing before.
- **Install from link…** on the Downloads tab installs any lotrointerface.com addon from its page link or
  number, including ones that aren't in either list.

## 1.1.1

Every game option was tested with real game launches (login → character select, 60 s running):

- **Fix: GameMode with gamescope.** The order is now `gamescope -- gamemoderun <game>`. gamescope drops
  GameMode's preload for the game, so Mithlond also registers the game process with `gamemoded` once it starts.
- Settings warns when GameMode is ticked but your user isn't in the `gamemode` group. Without that group,
  GameMode has no effect: polkit refuses its CPU-governor helper. Distributions without systemd-sysusers, such as
  Artix, don't create the group.
- Native Wayland: the tooltip now says that Proton may still keep a game on XWayland. LOTRO stayed on XWayland
  with GE-Proton 11-6, even though Proton turned on its Wayland driver.

## 1.1.0

- The Addons tab is now **Downloads**, and the Songs tab is now **Music**.
- New **Downloads folder** setting. It defaults to `<documents>/Downloads` and is where Mithlond puts
  LotRO Companion, Maestro and WAN Songbook Filler.
- Music tab: **Music tools** section with Download / Start / project-page buttons for Maestro, BruTE and WAN
  Songbook Filler. Each shows its latest release date. The Songbook auto-update option moved here.
- Companion tab: **Download Companion** installs it into the Downloads folder. *Start with the game* is now off
  by default.
- Settings: the section is renamed **Runners and Prefix**. New **game options**: gamescope (with arguments),
  MangoHud, GameMode, DXVK FPS counter, Proton native Wayland, Proton debug log. The Faugus import button is
  removed.

## 1.0.0

- First release: login, world status and queue, launch through Wine or Proton (umu-run). STOP button.
  lotro.com news with the weekly coupon.
- lotrointerface.com plugins, skins and music packs: install, update, uninstall. Existing plugins are picked
  up automatically.
- ABC song import and SongbookData.plugindata generation.
- LotRO Companion: start with or without the game, direct launch (skips its hanging updater), updates.
- Runner dropdown (system Wine, Proton builds), prefix and environment variables. Password in the system
  keyring. Single-file AppImage.
