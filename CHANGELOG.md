# Changelog

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
