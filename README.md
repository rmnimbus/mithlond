# Mithlond

> **Disclaimer:** this project is entirely vibe coded. I have no idea what I'm doing, I just wanted an
> all-in-one Linux launcher for LOTRO. Use it at your own risk.

A native Linux launcher for **The Lord of the Rings Online**, built with Python and Qt.

It logs you in and starts the game through Wine or Proton. It also installs plugins, skins and music from
lotrointerface.com, manages your ABC song library and the Songbook plugin's song list, and runs LotRO Companion
alongside the game.

## Features

| Tab | What it does |
|---|---|
| **Play** | Logs in with the official login servers and shows each world's status. Waits in the login queue, then starts the game client through Wine or Proton (umu-run). The **STOP** button closes every game client and every helper program. The news panel shows the official lotro.com news, with this week's **coupon code** at the top. |
| **Downloads** | Plugins, skins and music packs from [lotrointerface.com](https://www.lotrointerface.com/). Browse, search, install (dependencies included), update and uninstall. It works alongside LOTRO Plugin Compendium and picks up plugins you installed by hand. |
| **Music** | Import `.abc` songs (files, folders, zips, drag and drop) and browse them by title and part count. Keeps the **Songbook** plugin's song list up to date. Downloads and starts **Maestro** and **WAN Songbook Filler**, and links to **BruTE**. |
| **Companion** | Downloads, updates and starts **LotRO Companion**, and can open and close it along with the game. |
| **Settings** | Game, documents, plugins and downloads folders. Runner (system Wine or any Proton) and prefix, environment variables, and game options (gamescope, MangoHud, GameMode, DXVK HUD…). |

Your password is saved in the desktop keyring (KWallet, GNOME Keyring, KeePassXC… through the Secret Service API).
It never goes into a file.

## Getting started

1. Download `Mithlond-<version>-x86_64.AppImage` and **make it executable**. Browsers always save downloads
   without that permission. If you skip this, double-clicking opens it in an archive program ("archive type not
   supported") instead of running it. Either:
   - in a terminal: `chmod +x ~/Downloads/Mithlond-*.AppImage`, or
   - in your file manager: right-click the file → **Properties** → **Permissions** → tick
     **"Allow executing file as program"** (or "Executable").

   Then double-click it. Everything it needs is bundled, including umu-run for Proton: nothing else has to be
   installed. The first game start with Proton downloads the Steam Runtime and Proton, which takes a few minutes.
2. **Settings → LOTRO game folder:** pick the folder with `lotroclient.exe` (Detect tries the usual places).
3. **Settings → Runners and Prefix:** Proton is the default. Mithlond picks a Proton build you already have, or
   umu's own (UMU-Proton). If you play LOTRO through Faugus (including the Flatpak), it starts with Faugus's
   prefix and Proton. You can also choose system Wine, if it's installed, and any other prefix.
4. **Settings → Game documents folder:** this is where the game keeps plugins, music and settings. Use
   **Choose…** to pick one of the folders found on your computer (or make a new one). Mithlond starts the game
   with that folder, whatever Wine prefix it runs in.
5. **Play:** enter your account, pick a world, press **PLAY**.

More in the **[User guide](docs/user-guide.md)**. If something doesn't work, see
**[Troubleshooting](docs/troubleshooting.md)**.

### Optional programs

| Program | Used for |
|---|---|
| `secret-tool` (libsecret) and a keyring | Saving your password |
| `wine` | The "Wine (system)" runner. Not needed for Proton, the default |
| `bsdtar` (libarchive) or `7z` | Addons packed as `.rar`/`.7z` |
| `java` (17+) | Running Maestro natively, and LotRO Companion's "native" mode |
| `gamescope`, `mangohud`, `gamemoderun` | The matching game options |

## Building from source

```sh
python3 -m mithlond                 # run from the source tree (needs PySide6 + requests)
packaging/build-appimage.sh         # build dist/Mithlond-<version>-x86_64.AppImage
./install.sh                        # or install the source version for your user
```

See **[Development](docs/development.md)** for the code layout, tests and how the AppImage is made.

## Credits and license

GPL-3.0-or-later. The login protocol follows [OneLauncher](https://github.com/JuneStepp/OneLauncher) (GPL-3.0).
Addon handling is compatible with LOTRO Plugin Compendium, and the Songbook data format matches Chiran's
Songbook. Thanks also to [lembas](https://github.com/mawilms/lembas),
[LotRO Companion](https://github.com/LotroCompanion/lotro-companion),
[Maestro](https://github.com/NikolaiVChr/maestro), [BruTE](https://github.com/bruzo/BruTE-) and
[WAN Songbook Filler](https://lotro.hanft.de/wansongbookfiller/).

Not affiliated with Standing Stone Games or Daybreak. The Lord of the Rings Online is a trademark of its owners.
