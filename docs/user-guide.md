# User guide

## First start

Mithlond looks for a LOTRO install and documents folder. If it finds nothing, it opens on **Settings**. The
Settings tab has a category list on the left (Locations, Runner & Prefix, Game options, Game, About & updates) and
a search box: typing narrows the page to the settings that match. Fill in **Locations** from top to bottom:

| Setting | What to put there |
|---|---|
| LOTRO game folder | The folder that contains `lotroclient.exe` and `lotro.launcherconfig`. |
| Game documents folder | Where the game keeps its settings, `Plugins`, `Music`, `PluginData` and `ui/skins`. **Choose…** lists every LOTRO documents folder on the computer (your home Documents and each Wine/Proton prefix) with when it was last played and how many plugins and songs it has, and can also make a new one. With **Start the game with this folder** ticked (the default), Mithlond starts the game with `--prefs <folder>\UserPreferences.ini`, so the game uses this folder whatever the prefix. If the folder has no game settings yet, Mithlond copies them from the prefix (or writes DirectX 11 defaults), so the game doesn't stop at its first-run graphics prompt. |
| Downloads folder | Usually empty, meaning `<documents>/Downloads`. LotRO Companion, Maestro and WAN Songbook Filler get downloaded here. |

### Runner & Prefix, Game options

- **Runner:** any Proton build found on the computer (`~/.local/share/Steam/compatibilitytools.d`, Flatpak Steam,
  `/usr/share/steam/compatibilitytools.d`, Steam's own), "umu's default" (downloads UMU-Proton automatically),
  "Wine (system)" when Wine is installed, or "Other…" to pick a Wine binary or Proton folder. Proton runners use
  umu-run, which is built into the AppImage, so they work without installing anything. The first start with
  Proton downloads the Steam Runtime (and UMU-Proton, if chosen); that takes a few minutes. When run from source,
  Mithlond uses an installed umu-run instead (from umu-launcher, or the one Faugus downloads).
- **First start:** Proton is the default. If Faugus (native or Flatpak) has a LOTRO entry, Mithlond starts with that
  entry's prefix and Proton build, so plugins and settings carry over. A config from an older Mithlond that was set
  to system Wine is switched to Proton if Wine isn't installed.
- **Prefix:** the Wine prefix. If you leave it empty, Wine uses `~/.wine` and umu uses its default prefix. The
  list shows prefixes Mithlond found. The line underneath warns about problems, such as a read-only folder or a
  Proton prefix used with plain Wine (Wine would convert it and break it for Proton).
- **Environment variables:** one `KEY=VALUE` per line. They apply to everything Mithlond starts through the
  runner.
- **Game options:** these apply to the game client only.

  | Option | What it does |
  |---|---|
  | Run in gamescope | Wraps the game in `gamescope <arguments> --`. The default argument `-f` means fullscreen. |
  | MangoHud overlay | Sets `MANGOHUD=1`. |
  | Feral GameMode | Wraps the game in `gamemoderun`. With gamescope, Mithlond also registers the game process with GameMode. Your user must be in the `gamemode` group (Settings warns if not). |
  | DXVK FPS counter | Sets `DXVK_HUD=fps`. |
  | Native Wayland (Proton) | Sets `PROTON_ENABLE_WAYLAND=1`. Some Proton builds still keep the game on XWayland. |
  | Proton debug log | Sets `PROTON_LOG=1`. The log goes to `~/steam-*.log`. |

### Game

You can pick the 64- or 32-bit client, the game language (from the installed `client_local_*.dat` files),
high-resolution textures, and whether the launcher minimizes when the game starts.


## Play

- **Account:** type it once and it's remembered. Tick *Save password* to store the password in your keyring.
  The line under the box says whether it was saved. **Forget** removes the account and its saved password.
- **World:** shows each world's status (● open, ○ closed). ⟳ refreshes it.
- **Options:**
  - **Frame rate:** caps the frames per second (less heat, fan noise and power use). It sets `DXVK_FRAME_RATE`,
    which DXVK (Wine/Proton's DirectX layer) applies. "No limit" turns it off. An `DXVK_FRAME_RATE` in your own
    environment variables takes precedence.
  - **Skip intro** (on by default): skips the Turbine logo video that plays at every start and the one-time
    intro cinematic. The game has no setting for the logo video, so Mithlond renames
    `raw/<language>/logo/turbine_logo.bik` to `turbine_logo.bik.mithlond-skipped` before each start (a game
    patch may bring it back; the next start sets it aside again). The cinematic is marked as seen with
    `[Misc] PlayedIntroMovie=True` in the documents folder's `UserPreferences.ini`. Unticking it puts the logo
    video back at the next start.
  - **Voice chat off:** starts the client without its voice chat system (`--voiceoff`).
  - **Safe mode:** for the next start only (`--safe`). The game resets its graphics settings to safe values and
    **keeps them** (tested: 1024×768 windowed, DirectX 9, medium detail). Use it when the game crashes or shows a
    black screen after a graphics change. Mithlond first copies `UserPreferences.ini` to
    `UserPreferences.ini.before-safe-mode-<date>` in the documents folder (the log shows the path); copy it back
    over `UserPreferences.ini` to restore your settings. The box unticks itself after the start.

  The client also lists a `--user <character>` option for logging straight into a character. It's ignored by
  the current client (tested), so Mithlond doesn't offer it.
- **PLAY:** logs in, waits in the queue and starts the client. Pressed while a game is running, it reads
  **PLAY ANOTHER** and starts a second client (for multiboxing or band play).
- **STOP:** closes every LOTRO client, LotRO Companion, the official launcher and patcher, Maestro and WAN
  Songbook Filler. That includes copies started outside Mithlond.
- **Check for game updates:** runs the game's own patcher. **Official launcher:** starts `LotroLauncher.exe`,
  for example if patching here fails.
- **News:** the official launcher feed. This week's coupon code is shown at the top, with a **Copy code**
  button.

If another program is already running in the same Proton prefix, Mithlond asks before launching. Proton
normally waits until those programs close, so the game wouldn't appear. You can close them, start alongside
them, or cancel.

## Visual effects

Effects that work on the picture DXVK/Vulkan renders, outside the game itself. They apply the next time the game
starts. Like the other settings tabs it has a category list and a search box.

- **Sharpening & antialiasing (vkBasalt):** needs the `vkbasalt` package (on Arch-based systems it's in the AUR).
  Tick **Use vkBasalt**, then choose effects: **AMD CAS** sharpening (the usual first choice), **DLS** sharpening,
  **SMAA** or **FXAA** antialiasing, a color **LUT**, and **ReShade shaders** (a folder with `Shaders/` and
  `Textures/`, plus the names of the `.fx` effects to run). Antialiasing runs before sharpening. The **Toggle key**
  (default Home) switches the effects on and off in game. Mithlond writes `~/.config/mithlond/vkBasalt.conf` and
  starts the game with `ENABLE_VKBASALT=1`; your own `~/.config/vkBasalt` is left alone.
- **Upscaling & display (gamescope):** run the game in gamescope with fullscreen or borderless, an output
  resolution, a **render scale** (Quality 67%, Balanced 59%, Performance 50%… or a custom size) with an
  **upscaler** (AMD FSR 1, NVIDIA NIS, Snapdragon SGSR, or plain), upscaler sharpness, scaling mode, the game's
  frame rate and a lower one in the background, variable refresh rate, HDR output with SDR→HDR inverse tone
  mapping, MangoHud through gamescope, keyboard grab and mouse lock, and extra arguments. The **Command** line
  shows the gamescope command it builds. LOTRO sizes its picture from its own resolution setting, so set
  **In game settings → Display → Full-screen resolution** to the render size for the sharpest result.
- **DXVK:** force anisotropic filtering (2×–16×), a texture LOD bias, the maximum frame latency (1 = least input
  lag), vertical sync, and tear-free presentation. Mithlond writes `~/.config/mithlond/dxvk.conf` and passes it
  with `DXVK_CONFIG_FILE`.

Tested with real game starts: vkBasalt loaded into the game with Mithlond's config (SMAA + CAS); gamescope ran the
game at a 1280x720 render size with FSR on a 1920x1080 output; DXVK found the config and applied 16x anisotropic
filtering and a frame latency of 1.

## In game settings

The tab is called **In game settings**. It holds the game's own options, read from `UserPreferences.ini` in the documents folder the game is started with. They're
grouped into Display, Detail, Lighting & Effects, Shadows, Sound, Interface, Controls & Camera, Voice Chat and
Performance. Settings the game writes that Mithlond doesn't know yet appear under **Other**, so nothing is left
out. Hidden on purpose: your account's world history, the official launcher's own entries, voice device IDs, and
values the game measures itself.

- **Search:** type in the box above the settings and the list narrows as you type, across all categories. Every
  word must match the setting's name, its name in the file (e.g. `MasterVolume`), its category or its description.
  The category list on the left shows how many settings match and jumps to that category.
- Values are shown with readable names (e.g. "Very High"), but saved exactly as the game writes them. The setting
  names and allowed values come from the game client itself. Hover over a setting to see its name in the file.
- Changed settings are shown in **bold** until you **Save changes**. Only those lines are written; everything
  else in the file stays as it is. **Discard changes** reloads the file.
- Every save keeps the previous file as `UserPreferences.ini.mithlond-<date>` (the last five).
  **Restore previous** puts the newest one back.
- **The game must be closed.** It rewrites the file when it exits, so changes made while it runs would be lost;
  the tab only allows saving while no game client is running. Changes apply the next time the game starts.
- **Performance → Maximum frame rate** is the game's own frame rate cap. The Play tab's *Frame rate* box is a
  separate cap applied by DXVK.

Tested: settings saved here (texture detail, the game's frame rate cap, interface scale, master volume, ambient
occlusion) were read by the game and kept when it rewrote the file.

## Downloads

Three sub-tabs list **Plugins**, **Skins** and **Music packs** from lotrointerface.com.

The lists combine lotrointerface's curated lists (OneLauncher's and Plugin Compendium's, which include
versions and descriptions) with **the site's full catalogue**, read from its category pages and cached for a
day. The first load of the day takes about half a minute; the status line shows progress. Addons that are only
in the catalogue show "…" as their latest version until you select one, which loads its version and
description. **Hide outdated** (on by default) hides the "Outdated LotRO Interfaces" category.

- Filter with *Installed / Updates available / Not installed*, a category, or search. Installed entries are
  green, and those with updates are gold.
- **Install / Update** downloads and installs, including a plugin's dependencies. **Update all** updates
  everything that has an update.
- **Uninstall** removes exactly the files that addon installed. Files another addon also uses are kept.
  Plugin settings in `PluginData` are kept too.
- **Install from file…** installs a `.zip`, `.rar` or `.7z` you downloaded yourself.
- **Install from link…** installs any addon from its lotrointerface.com page. Paste the link (e.g.
  `https://www.lotrointerface.com/downloads/info1218-.html`) or just the number. The lists come from lotrointerface's
  curated plugin lists (OneLauncher's and Plugin Compendium's, merged), so a few addons on the site aren't in them.

Plugins installed by hand or with LOTRO Plugin Compendium are picked up automatically (through their
`.plugincompendium` files) and can then be updated and uninstalled here as well.

## Music

- **Import songs… / Import folder…** (or drag and drop) copy `.abc` files, folders or `.zip` archives into the
  game's `Music` folder, or a folder inside it. Identical files are skipped. Changed files with the same name
  get a numbered copy.
- The list shows each song's title and number of parts. Hover a file to see its `/play` name. Double-click
  opens it.
- **Update Songbook list** writes `PluginData/<account>/AllServers/SongbookData.plugindata` for each account,
  which is the list the Songbook plugin reads. With *Update the Songbook list automatically* ticked, this
  happens after every change made in Mithlond. Files copied in with a file manager need the button. Reload the
  plugin in game to see changes.

### Music tools

At the bottom of the Music tab, closed by default: click its title to open it.

| Tool | Notes |
|---|---|
| Maestro | MIDI → ABC converter and ABC player. **Download** gets the latest GitHub release. Mithlond runs `Maestro.jar` with your system Java if you have one, otherwise `Maestro.exe` through the runner. |
| BruTE | Another MIDI → ABC converter. Its project currently publishes source code only, with no ready-to-run release, so Download is disabled. |
| WAN Songbook Filler | A Windows program that builds the Songbook list quickly for large or network-shared Music folders. Last release 2017. It runs through your runner. |

The note under each tool shows the latest release and how old it is.

## Companion

- **Folder:** empty means `<downloads>/LotRO Companion`. **Download Companion** installs it there.
  **Update Companion** replaces it with the latest release and keeps the previous version as
  `LotRO Companion.old-<version>`.
- **Run:** *Through Wine/Proton* (recommended) shares the game's prefix, so Companion can read character data
  from the running game. *Natively with system Java* runs it as a Linux program.
- **Start Companion when the game starts:** off by default. When on, it starts after the delay you set.
  *Close Companion when the last game client exits* closes it again.
- **Skip Companion's built-in updater:** recommended. Companion's own updater can hang forever before its
  window appears. Mithlond starts Companion directly instead, and you update it with the button above.
- Companion keeps its data (accounts, characters) in `C:\users\<user>\.lotrocompanion` inside the prefix, or in
  `~/.lotrocompanion` in native mode.

## Updates

Mithlond checks GitHub for a newer release a couple of seconds after it starts. If there is one, a banner above
the tabs offers **Update now**, **What's new** (the release notes) and **Skip this version**. You can turn the
startup check off, or check by hand, in **Settings → About & updates**.

**Update now** downloads the new AppImage into the same folder as the one you're running and checks it: size,
AppImage header and GitHub's SHA-256 checksum. If anything doesn't match, nothing is changed. Otherwise it's made
executable, the old AppImage is removed, and Mithlond offers to restart into the new version. Your settings are
kept, because they live in `~/.config/mithlond`, not in the AppImage. The new file is named after its version
(e.g. `Mithlond-1.4.7-x86_64.AppImage`).

**Application menu:** **Settings → About & updates → Add to application menu** adds Mithlond to your desktop's
app launcher (`~/.local/share/applications/mithlond.desktop` plus its icon). After that, Mithlond keeps the entry
pointing at the AppImage it runs from, right after an update and at every start, so it keeps working when an
update changes the file name or you move the AppImage to another folder. Mithlond only changes an entry it wrote
itself.

## Files

| What | Where |
|---|---|
| Settings | `~/.config/mithlond/config.json` (no passwords) |
| Log | `~/.cache/mithlond/mithlond.log` (also in the Log panel; tickets and passwords are never logged) |
| Addon install records | `~/.local/share/mithlond/installed.json` |
| Download and feed cache | `~/.cache/mithlond/` |
