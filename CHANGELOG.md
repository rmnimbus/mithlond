# Changelog

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
