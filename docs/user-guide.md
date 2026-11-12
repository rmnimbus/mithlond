# User guide

## First start

Mithlond looks for a LOTRO install and documents folder. If it finds nothing, it opens on **Settings**. Fill in
**Locations** from top to bottom:

| Setting | What to put there |
|---|---|
| LOTRO game folder | The folder that contains `lotroclient.exe` and `lotro.launcherconfig`. |
| Documents folder | `…/Documents/The Lord of the Rings Online` *inside the prefix the game runs in*. Detect picks the one with the most recently used `UserPreferences.ini`. |
| Plugins folder | Usually empty, meaning `<documents>/Plugins`. The game only loads plugins from there. |
| Downloads folder | Usually empty, meaning `<documents>/Downloads`. LotRO Companion, Maestro and WAN Songbook Filler get downloaded here. |

### Runners and Prefix

- **Runner:** "Wine (system)", any Proton build found in `~/.local/share/Steam/compatibilitytools.d` or Steam,
  "umu's default" (downloads UMU-Proton automatically), or "Other…" to pick a Wine binary or Proton folder.
  Proton runners use `umu-run`.
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

## Downloads

Three sub-tabs list **Plugins**, **Skins** and **Music packs** from lotrointerface.com.

- Filter with *Installed / Updates available / Not installed*, a category, or search. Installed entries are
  green, and those with updates are gold.
- **Install / Update** downloads and installs, including a plugin's dependencies. **Update all** updates
  everything that has an update.
- **Uninstall** removes exactly the files that addon installed. Files another addon also uses are kept.
  Plugin settings in `PluginData` are kept too.
- **Install from file…** installs a `.zip`, `.rar` or `.7z` you downloaded yourself.

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

## Files

| What | Where |
|---|---|
| Settings | `~/.config/mithlond/config.json` (no passwords) |
| Log | `~/.cache/mithlond/mithlond.log` (also in the Log panel; tickets and passwords are never logged) |
| Addon install records | `~/.local/share/mithlond/installed.json` |
| Download and feed cache | `~/.cache/mithlond/` |
