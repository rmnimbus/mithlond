# Development

Python ≥ 3.11, PySide6 (Qt 6 widgets) and `requests`. There are no other runtime dependencies.

## Layout

```
mithlond/
  app.py          entry point (python -m mithlond)
  config.py       Settings dataclass (~/.config/mithlond/config.json), auto-detection, prefix checks
  gls.py          LOTRO login protocol: datacenter (SOAP), launcher config, LoginAccount, world status,
                  login queue (TakeANumber), client arguments
  runner.py       Wine / umu-run (Proton) commands, game options (gamescope…), ManagedProcess (own session,
                  output forwarding), Companion and tool commands, patcher
  procs.py        /proc scanning: running game clients, programs in a prefix, STOP
  addons.py       lotrointerface feeds, archive extraction (zip natively, rar/7z via bsdtar/7z), install /
                  uninstall with a manifest, .plugincompendium compatibility, adopting existing plugins
  songs.py        ABC parsing, song import, SongbookData.plugindata writer
  catalog.py      lotrointerface.com full catalogue from the site's category pages (no API exists for it)
  news.py         lotro.com launcher feed, HTML sanitizer, weekly coupon extraction
  companion.py    LotRO Companion: version, SourceForge releases, update/install, direct launch
  tools.py        Maestro / BruTE / WAN Songbook Filler: latest release info, download
  effects.py      Visual effects: vkBasalt.conf, dxvk.conf, gamescope arguments, environment for the game
  desktopentry.py application menu entry that follows the AppImage
  uilayout.py     the game's ui/layouts/*.layout: windows, options, chat colors; in-place saving
  gameprefs.py    the game's UserPreferences.ini: schema of every known setting (names and values from the client), read, save
  selfupdate.py   Mithlond's own updates from GitHub releases (rmnimbus/mithlond): check, download, verify, replace
  keystore.py     password storage through secret-tool
  hostenv.py      environment isolation when running from the AppImage
  ui/             one module per tab, plus theme, workers (thread pool) and shared context
packaging/build-appimage.sh
tests/            test_core.py (logic) and test_e2e.py (drives the UI offscreen against a fake login server)
```

## Login flow (gls.py)

1. Read `Launcher.DataCenterService.GLS` and `DataCenter.GameName` from the game's `*.launcherconfig`.
2. `GetDatacenters` (SOAP) returns the auth server, patch server, launcher config URL and worlds.
3. The launcher config (appSettings XML) gives the client file names, argument template, queue URL and
   parameters, and the news feed URL.
4. `LoginAccount` (SOAP) returns a session ticket and the account's subscriptions.
5. The world's status XML gives its login server and queue URL, plus allowed and denied billing roles.
6. POST `TakeANumber` to the login queue until the queue number is ≤ the now-serving number.
7. Fill in the argument template (`{SUBSCRIPTION}`, `{LOGIN}`, `{GLS}`, `{CHAT}`, `{LANG}`, …) and start
   `x64/lotroclient64.exe` with the game folder as working directory.

## Tests

```sh
python3 -m unittest tests.test_core      # needs PySide6 for the runner tests
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_e2e
```

`test_e2e` starts a local HTTP server that mimics the login, world-status and queue services, and uses a fake
`wine` script. It covers: world list, a wrong and a right password, the queue, the exact client arguments,
Companion starting after its delay, Companion closing with the game, news and coupon, and that no ticket or
password reaches the log or config.

## AppImage

`packaging/build-appimage.sh [output-dir]`:

1. Downloads a relocatable Python 3.13 (python-appimage, manylinux_2_28) and appimagetool.
2. Installs `PySide6-Essentials` and `requests` into it.
3. Prunes Qt to the QtCore/QtGui/QtWidgets bindings, the X11/Wayland/offscreen/minimal platforms, and the
   libraries those need, by following `readelf -d` NEEDED entries. No GTK3 theme plugin: it would load the
   host's GTK, which can need a newer GLib than the bundled one.
4. Bundles every other library Qt needs except the ones on `packaging/excludelist` (the standard AppImage
   excludelist: glibc, GPU drivers, libX11/libxcb, fontconfig… which must come from the host).
   `packaging/bundle_libs.py` takes them from Debian 11 (archived, so its package index never changes; pinned by
   SHA-256), gives them RUNPATH `$ORIGIN`, and fails the build if a library can't be reached or needs a newer
   glibc than PySide6 itself (2.34).
5. Adds umu-launcher's `umu-run` (a Python zipapp, pinned release and SHA-256) as `opt/umu/umu-run`. Mithlond
   runs it with the bundled Python (`config.umu_command()`), so Proton works without anything installed.
6. Adds the app, an `AppRun` that runs Python in isolated mode (`-I`), and the desktop file and icon.

The result is about 46 MB. Inside the AppImage, programs that Mithlond starts (wine, umu-run, java,
secret-tool…) get the user's original environment (`hostenv.py`).

## Releasing

`packaging/release.sh` does the whole release in two steps, with the per-build check in between:

1. Write the changes under `## Unreleased` in CHANGELOG.md.
2. `packaging/release.sh build X.Y.Z` sets `__version__`, renames `## Unreleased` to `## X.Y.Z` and builds
   `dist/Mithlond-X.Y.Z-x86_64.AppImage`.
3. Test that AppImage: the test suite and one real launch with saved settings.
4. `packaging/release.sh publish X.Y.Z [-F message-file]` commits (message: the version plus the changelog section,
   or the given file), tags `vX.Y.Z`, pushes to Gitea, creates the Gitea release with the AppImage, waits until
   Gitea's push mirror has brought the tag to GitHub, creates the GitHub release (marked latest) with the
   AppImage, and checks that the updater sees `X.Y.Z` with the same SHA-256 as the local file.

`publish` skips whatever already exists, so after a failure (network, mirror delay) just run it again. It needs
`~/.config/gitea/token` and `~/.config/github/token` (never printed; `packaging/publish_release.py` holds the API
calls). The updater reads GitHub's "latest release" and its asset's `digest`.
