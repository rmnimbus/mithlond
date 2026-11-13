# Changelog

## Unreleased

- Fix: a prefix set to the `drive_c` folder inside a prefix (or a folder in it) is now taken as the prefix
  itself, at startup and when saving Settings. Before, Proton made a second, empty prefix inside `drive_c`
  ("Prefix has an invalid version", "unable to use parent for game drive"), so Companion and the game kept
  their data in the wrong place.
- Export logs no longer blanks long folder paths as if they were security tokens.
- **Load plugins** lists only installed plugins. Plugins the game's list still auto-loads but that aren't
  installed any more are named in one line under the list, with **Remove them from the list**.
- Plugins tab order: Get plugins, Load plugins, Skins, Plugin errors. Music packs sit above Music tools.
- **Install the game:** with no game folder yet, **Install the game…** (Play tab; also **Install…** in
  Settings → Locations) downloads the official installer from lotro.com and installs the game silently into
  the Wine/Proton prefix, then sets the game folder. **Detect** also looks in the configured prefix.
- **My LOTRO account** button on the Play tab opens the Standing Stone Games account page.
- **Layouts:** move and resize in steps of 1, 5 or 10 px, and optionally **snap to other windows' edges**
  (screen edges always snap). Typed pixel values are used exactly. Both choices are remembered.

## 1.4.14

- **New Key bindings tab:** every key binding in the game, searchable by action or key, with keys that do two
  things in the same place marked in red. Change keys (keyboard with Shift/Ctrl/Alt, middle and side mouse
  buttons), add a second key, remove keys, and **save or load whole key binding files**. Saving keeps every
  unchanged line exactly as the game wrote it, with a backup; not possible while the game runs.
- **Downloads is now the Plugins tab:** **Get plugins** (as before), **Load plugins**, **Plugin errors** and
  **Skins**.
  - **Load plugins** sets which characters auto-load each plugin, per server: click a plugin and tick *All
    characters* or the characters you want. Named **sets** can be saved and loaded. Characters you haven't
    played on this computer can be added by name. Plugins whose authors say not to auto-load them are hidden
    unless asked for.
  - **Plugin errors** lists the Lua errors the game wrote to Script.log, per plugin. Export logs now includes
    Script.log too.
- **Music packs** moved to the Music tab, as a section that's closed by default.
- The user guide notes that `/ui layout load` also applies a layout's interface options (checked in game).

## 1.4.13

- The **Companion** tab is now called **LotRO Companion**, the name its author uses, and its buttons, options and
  messages say "LotRO Companion" too.
- **Export logs:** a button in the Log panel's title bar and in **Settings → About & updates** saves one zip
  (default `~/Downloads/mithlond-logs-<date>.zip`) to send to whoever helps you. It contains a system and
  setup summary (distribution, GPU and driver, Vulkan, Wine/Proton/umu-run, gamescope, vkBasalt, SELinux,
  the prefix, your Mithlond options), Mithlond's log, the game's own `lotroclient.log`, Proton's log, your
  game settings, installed plugins, the effects configs and Companion's log. Your user name, home folder,
  account names, login tickets and e-mail addresses are removed, and `README.txt` inside lists everything.
- **Better log file:** `~/.cache/mithlond/mithlond.log` now has the date on every line, a header for each start
  (version, Python, Qt), and full tracebacks of crashes and failed background tasks. It's moved to
  `mithlond.log.1` when it passes 2 MB instead of growing forever.
- **New Layouts tab** for the interface layouts the game saves with `/ui layout save <name>`: drag and resize
  windows on a screen-sized canvas (or type pixel values), edit the layout's interface options and the chat
  colors and font sizes, and copy, rename or delete layouts. Saving changes only the edited lines and keeps a
  backup; apply a layout in game with `/ui layout load <name>`.

## 1.4.12

- **Lighter in the background:** In game settings checks whether the game is running only while that tab is
  open (it used to scan all processes every 4 seconds the whole time Mithlond ran).
- **Faster settings search:** each setting's search text is collected once instead of on every keystroke.
- In game settings, Settings and Visual effects now share one category/search component.
- Fix: no more "Signal source has been deleted" errors when Mithlond is closed while it's still loading news, the
  world list or the plugin catalogue.
- README credits umu-launcher (bundled, GPL-3.0), PySide6, the bundled Debian libraries, vkBasalt, gamescope and
  DXVK.

## 1.4.11

- **Presets:** In game settings has a **Graphics preset** list (Very Low … Very High) that fills in the game's
  graphics settings as unsaved changes; Visual effects has an **Effects preset** list that sets upscaling,
  sharpening, antialiasing and DXVK options for slower to faster computers. Both were checked with real game
  starts: the game kept every preset value, and the effects loaded.
- In game settings: the lists for draw distances, shadows, water, reflections and grass now offer the game's real
  lowest value (*Disabled* or *Low*) instead of a *VeryLow* the game doesn't accept.
- Fix: vkBasalt effects didn't apply when the game ran in gamescope (gamescope clears `ENABLE_VKBASALT`; Mithlond
  now sets it again for the game).

## 1.4.10

- **Settings, Visual effects and In game settings show one category at a time:** clicking a category in the list
  shows only that category instead of one long page. Search still narrows the list to the categories with a match,
  and the selected category shows only its matching settings; if it has none, the first category that does is
  selected.

## 1.4.9

- **New Visual effects tab**, with a category list and search like the other settings tabs:
  - **vkBasalt:** AMD CAS and DLS sharpening, SMAA and FXAA antialiasing, color LUTs, ReShade shaders, a toggle key.
  - **gamescope** (moved here from Settings): fullscreen/borderless, output resolution, render scale with FSR, NIS
    or SGSR upscaling and sharpness, scaling mode, frame rates (also in the background), variable refresh rate,
    HDR with inverse tone mapping, MangoHud through gamescope, keyboard grab, mouse lock, extra arguments, and a
    preview of the command.
  - **DXVK:** forced anisotropic filtering, texture LOD bias, max frame latency, VSync, tear-free presentation.
- The **Game settings** tab is now called **In game settings**.

## 1.4.8

- **Settings is categorized** like Game settings: a category list on the left (Locations, Runner & Prefix, Game
  options, Game, About & updates), one scrolling page, and a search box that narrows it as you type. The old
  "Runners and Prefix" box is split into **Runner & Prefix** and **Game options**.
- **Music tools** on the Music tab is a collapsible section, closed by default.

## 1.4.7

- **Add to application menu** (Settings → About & updates): puts Mithlond in your desktop's app launcher with
  its icon. The entry follows the AppImage: Mithlond updates it after every self-update (new file name) and at
  every start (if you moved the file).

## 1.4.6

- **Game settings search:** a search box narrows the settings live as you type, across all categories (by name,
  name in the file, category or description). The settings are now one scrolling page with a box per category;
  the list on the left jumps to a category and shows how many settings match.
- **Skip intro** moved to the Play tab's options (it was in Settings → Game).

## 1.4.5

- **New Game settings tab:** the game's own options, about 130 of them, in categories (Display, Detail, Lighting &
  Effects, Shadows, Sound, Interface, Controls & Camera, Voice Chat, Performance), with readable names, sliders
  for volumes and lists for quality levels. Saving writes only what changed, keeps a backup, and is only possible
  while the game is closed (it rewrites the file on exit). Unknown settings show up under "Other".

## 1.4.4

- **Play tab options:** a **frame rate limit** (DXVK), **Voice chat off**, and **Safe mode** for one start.
  Safe mode makes the game reset its graphics settings for good, so Mithlond backs up `UserPreferences.ini` first.
- **Skip the intro videos** (Settings → Game, on by default): the Turbine logo video no longer plays at every
  start, and the intro cinematic is marked as seen. Unticking puts the video back.
- Warns when SELinux blocks Wine/Proton (`selinuxuser_execmod` off, e.g. openSUSE): the game would close
  seconds after starting. The warning includes the fix.
- On a computer without any LOTRO documents folder, Mithlond now uses `~/Documents/The Lord of the Rings Online`,
  so the game doesn't stop at its first-run DirectX prompt.

## 1.4.3

- **Proton works out of the box.** The AppImage includes umu-run (umu-launcher 1.4.4), so the Proton runners
  need nothing installed. The *umu-run* path setting is gone. The first game start downloads the Steam Runtime
  (and UMU-Proton, if chosen), which takes a few minutes.
- **Proton is the default runner.** New setups start with Proton. Setups from older versions that were left on
  system Wine switch to Proton if Wine isn't installed. "Wine (system)" stays in the list, greyed out when Wine
  isn't installed.
- **Faugus Flatpak support.** Mithlond now reads the Faugus Flatpak's game list too. On a first start it uses the
  prefix and Proton build of your Faugus LOTRO entry, so plugins and settings carry over. Proton builds are also
  found in Flatpak Steam and `/usr/share/steam/compatibilitytools.d`.
- **The AppImage bundles all its libraries** except the ones every Linux desktop provides and an AppImage must
  take from the system (glibc, graphics drivers, X11/Wayland core, fonts). The others come from Debian 11 and
  are checked by SHA-256. Mithlond needs glibc 2.34 or newer (Linux Mint 21, Ubuntu 22.04, Debian 12, Fedora 35
  and newer). The unused GTK3 theme, framebuffer and VNC plugins are no longer included.

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
