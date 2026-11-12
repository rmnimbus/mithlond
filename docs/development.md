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
3. Prunes Qt to the QtCore/QtGui/QtWidgets bindings and the libraries they and the kept plugins need, by
   following `readelf -d` NEEDED entries. The build fails if a needed library is missing.
4. Adds the xcb-util libraries Qt's X11 plugin needs that not every distribution installs (`libxcb-cursor`,
   `-icccm`, `-image`, `-keysyms`, `-render-util`, `-util`): pinned Debian packages, checked by SHA-256 and
   built for glibc ≤ 2.14. Without `libxcb-cursor`, Qt ≥ 6.5 aborts on X11 (e.g. Linux Mint).
5. Adds the app, an `AppRun` that runs Python in isolated mode (`-I`), and the desktop file and icon.

The result is about 45 MB. Inside the AppImage, programs that Mithlond starts (wine, umu-run, java,
secret-tool…) get the user's original environment (`hostenv.py`).

## Releasing

1. Bump `mithlond/__init__.py`, add a CHANGELOG entry, and commit.
2. Tag `vX.Y.Z` and push to Gitea. Gitea's push mirror copies the commit and tag to GitHub.
3. Build with `packaging/build-appimage.sh` and create the release with `Mithlond-X.Y.Z-x86_64.AppImage`
   attached, on Gitea and on **GitHub**. The updater reads GitHub's "latest release" and its asset's `digest`.
