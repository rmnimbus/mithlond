# User guide

## First start

Mithlond looks for a LOTRO install and documents folder. If it finds nothing, it opens on **Settings**. The
Settings tab has a category list on the left (Locations, Runner & Prefix, Game options, Game, About & updates) and
a search box: typing narrows the page to the settings that match. Fill in **Locations** from top to bottom:

| Setting | What to put there |
|---|---|
| LOTRO game folder | The folder that contains `lotroclient.exe` and `lotro.launcherconfig`. No game yet? **Install…** (also on the Play tab while no game folder is set) downloads the official installer (`lotrolive.exe`, linked from lotro.com's download page) and installs the game's launcher silently into your Wine/Proton prefix (about 45 MB, a few seconds), then sets this folder. The game itself then downloads with **Check for game updates** on the Play tab; until then Play and Settings say the game isn't downloaded yet. |
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
- **My LOTRO account** opens the Standing Stone Games account page (myaccount.standingstonegames.com) in your browser.
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

**Effects preset** (top right) sets everything at once; you can adjust it afterwards:

| Preset | For | Sets |
|---|---|---|
| Very Low | weak computers | gamescope renders at 50% and upscales with FSR, CAS sharpening 0.6, frame latency 1 |
| Low | | gamescope 59% + FSR, CAS 0.5, 4× anisotropic filtering, frame latency 1 |
| Medium | | native resolution, CAS 0.4, 8× anisotropic filtering |
| High | | native, SMAA antialiasing + CAS, 16× anisotropic filtering |
| Very High | fast computers | native, SMAA (color edges, more search steps) + CAS 0.5, 16× anisotropic filtering |

Without gamescope installed, the presets leave upscaling off. Without vkBasalt, its effects are skipped at launch.

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

## Layouts

Edits the interface layouts the game saves with **/ui layout save <name>** (files in
`<documents>/ui/layouts/<name>.layout`). The game applies a layout with **/ui layout load <name>**; after
changing one here, type that in game. To capture the layout you have in game right now, `/ui layout save` it
and press **Reload**.

- **Layout** list: **Copy as…** (a new layout from this one), **Rename…**, **Delete** (moved into
  `ui/layouts/.mithlond-backups`, so it can be recovered), **Reload**, **Open folder**. Names may use letters,
  digits, `-` and `_`, because they're typed after `/ui layout load`.
- **Windows:** your screen drawn at the game's resolution, with each interface window as a box. Drag a box to
  move it, drag its bottom-right corner to resize it, or type exact pixel values below the screen. Windows snap
  to the screen edges. The list on the left picks which windows are drawn: by default what you see while
  playing (chat, vitals, target, minimap, quest tracker, quickslot bars, bags, fellowship members); **Show all**
  and **Show none** apply to the windows listed, and the search finds any of the ~160 windows.
- **Move in steps of** 1 px (free), 5 px or 10 px: dragging and resizing with the mouse goes in those steps
  (typed pixel values are used exactly). **Snap to other windows**: while dragging, a window's edges snap to the
  edges of the other windows shown, as they always do to the screen edges. Both are remembered.
- **Interface options:** the layout's ~190 options (accepting duels/trades/invites, per-window UI scales,
  show/hide toggles, toolbar slots, quest guide colors…) in categories with search.
  `/ui layout load` sets these options as well as the window positions (checked in game with
  *Always loot all*), so two layouts can differ only in their options.
- **Chat colors:** color and font size for each chat message type (Say, Tell, Kinship, World, loot, combat…),
  with a preview line.

Saving writes only the changed lines (the rest of the file stays exactly as the game wrote it) and keeps the
previous version in the backup folder; **Restore previous** puts it back. Chat tabs and their filters are not
part of layout files: the game keeps them on its servers.

## Key bindings

Every key binding in `lotro.keymap` (documents folder): the action, its key with modifiers (e.g.
*Ctrl+Shift+Q*, *Mouse 4*, *Mouse wheel up*), and where it works (*General*, *Map*, *Music mode*, *Text
fields*…). Search by action or key (`map`, `quickslot 5`, `ctrl+q`), pick a place, or tick **Keys that do two
things** to see keys that run more than one action in the same place (shown in red).

- **Change key…** (or double-click) waits for the new key or combination; Shift, Ctrl and Alt work as
  modifiers, and the middle and side mouse buttons can be used. **Add another key…** gives an action a second
  key, and **Remove key** removes one.
- **Show blocked keys** shows keys set to do nothing (the game writes these when you clear a default key).
- **Save** writes the file, keeping every unchanged line exactly as the game wrote it, with a backup
  (**Restore backup**). Not while the game runs: it rewrites its key bindings when it closes.
- **Save to file…** saves the whole set of key bindings as a `.keymap` file (default folder
  `~/.config/mithlond/keymaps`) to keep or to use on another computer; **Load from file…** loads one, and
  **Save** then makes it the game's key bindings.

## In game settings

The tab is called **In game settings**. It holds the game's own options, read from `UserPreferences.ini` in the documents folder the game is started with. They're
grouped into Display, Detail, Lighting & Effects, Shadows, Sound, Interface, Controls & Camera, Voice Chat and
Performance. Settings the game writes that Mithlond doesn't know yet appear under **Other**, so nothing is left
out. Hidden on purpose: your account's world history, the official launcher's own entries, voice device IDs, and
values the game measures itself.

- **Graphics preset** (next to the search box): Very Low, Low, Medium, High or Very High fills in the
  graphics settings (detail, draw distance, effects, shadows, water, grass) for slower to faster computers. Your
  resolution, window mode, sound, interface and controls are left alone. The values appear as unsaved changes in
  bold; press **Save changes** to keep them. Every preset was checked with the real game: it kept all values (the
  lowest settings use the game's own minimum, e.g. shadows and reflections *Disabled* on Very Low).
- **Search:** type in the box above the settings and the list narrows as you type, across all categories. Every
  word must match the setting's name, its name in the file (e.g. `MasterVolume`), its category or its description.
  The category list on the left only lists categories with a match and shows how many; click one to see its
  matches. Without a search, clicking a category shows just that category.
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

## Plugins

Four pages: **Get plugins**, **Load plugins**, **Skins** and **Plugin errors**.

### Get plugins (and Skins)

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

**Skins** works the same way for interface skins. Music packs are in the Music tab.

### Load plugins

Which plugins the game loads by itself, and for which characters. The game keeps one list per account and
server (`PluginData/<account>/<server>/PluginOptions.xml`), so pick the **Server** first.

- Every installed plugin is listed. **Loads on** says *All characters*, a character's name, *Multiple characters (n)* (hover for the names) or
  *Not loaded*.
- If the game's list still auto-loads plugins that aren't installed any more, a line under the list names
  them (the game skips them); **Remove them from the list** takes them out (then **Save**).
- Click a plugin to open its menu: tick **All characters**, or tick the characters that should load it.
  Ticking a character unticks *All characters* and the other way round. Untick everything for *Not loaded*.
- Characters are known once they've loaded a plugin on this computer (their `PluginData` folder) or appear in
  the list. Others, for example on a server you haven't played on this computer, can be added with
  **Add character…**. The full character list exists only on the game's servers.
- **Show helper plugins** shows plugins whose authors say not to auto-load them (for example MoorMap's
  MMCust); they're hidden otherwise.
- **Sets:** **Save as set…** stores the current choices under a name; pick one from the list and **Load set**
  to use it (then **Save**), or **Delete set**. Sets are kept in `~/.config/mithlond/plugin-sets.json` and work
  on any server.
- **Save** writes only the auto-load part of the file and keeps the rest, with a backup next to it
  (**Restore backup** puts it back). Like the game settings, this can't be saved while the game runs, because
  the game writes the file itself. Changes apply when a character next enters the world.

### Plugin errors

The plugin (Lua) errors the game wrote to `Script.log` in the documents folder, with the plugin each one
belongs to. It isn't a live feed: it shows the file as it was when you opened the page or pressed
**Refresh**. **Export logs** includes this file.

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

### Music packs

Above the music tools, also closed by default: song collections from lotrointerface.com, with the same search,
install, update and uninstall as **Plugins → Get plugins**. The list is loaded the first time you open it.

## LotRO Companion

- **Folder:** empty means `<downloads>/LotRO Companion`. **Download LotRO Companion** installs it there.
  **Update LotRO Companion** replaces it with the latest release and keeps the previous version as
  `LotRO Companion.old-<version>`.
- **Run:** *Through Wine/Proton* (recommended) shares the game's prefix, so LotRO Companion can read character data
  from the running game. *Natively with system Java* runs it as a Linux program.
- **Start LotRO Companion when the game starts:** off by default. When on, it starts after the delay you set.
  *Close LotRO Companion when the last game client exits* closes it again.
- **Skip LotRO Companion's built-in updater:** recommended. LotRO Companion's own updater can hang forever before its
  window appears. Mithlond starts LotRO Companion directly instead, and you update it with the button above.
- LotRO Companion keeps its data (accounts, characters) in `C:\users\<user>\.lotrocompanion` inside the prefix, or in
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

**Export logs…** (here and in the Log panel's title bar) saves a zip with a summary of your system and setup,
Mithlond's, the game's, Proton's and LotRO Companion's logs, and your settings, for whoever helps you with a problem.
Your user name, home folder, account names, login tickets and e-mail addresses are removed. See
[Troubleshooting](troubleshooting.md).

## Files

| What | Where |
|---|---|
| Settings | `~/.config/mithlond/config.json` (no passwords) |
| Log | `~/.cache/mithlond/mithlond.log`, older part in `mithlond.log.1` (also in the Log panel; tickets and passwords are never logged) |
| Addon install records | `~/.local/share/mithlond/installed.json` |
| Download and feed cache | `~/.cache/mithlond/` |
