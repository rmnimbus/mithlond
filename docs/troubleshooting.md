# Troubleshooting

The **Log** panel at the bottom of the window shows everything the game, Wine/Proton and Companion print. The
same log is saved in `~/.cache/mithlond/mithlond.log`.

### Double-clicking the AppImage says "archive type not supported" (or opens an archive tool)
The file isn't marked executable. Browsers remove that permission from every download. Run
`chmod +x Mithlond-*.AppImage`, or right-click → Properties → Permissions → "Allow executing file as program".
Re-downloading the file removes the permission again.

### "Username or password is incorrect"
That's the login server's answer. Check the account name: it's your LOTRO account name, not an email address
or character name.

### The status says "Starting the game…" for a long time and nothing appears
With Proton, the game waits until every other program running in the same prefix has closed. The usual
culprit is a LotRO Companion or launcher started by another tool. Mithlond warns about this before
launching. If it happens anyway, press **STOP**, then **PLAY** again.

### `wine: cannot create …/.wine/dosdevices: Permission denied` (or "Prefix problem")
The prefix folder isn't writable, or isn't a prefix at all. Pick another one in **Settings → Runners and
Prefix**. The ✔/✘ line under the prefix box tells you whether the selected runner can use it.

### "…was created by Proton… Plain Wine would convert it"
You picked system Wine with a prefix made by Proton (Steam, Faugus, umu). Choose a Proton runner for that
prefix, or a different prefix for Wine.

### My plugins or music don't show up in game
The game reads `Documents/The Lord of the Rings Online` **inside the prefix it runs in**. Each prefix has its own
copy. Check that **Settings → Documents folder** is the one in the prefix you play with. To share one folder
between several prefixes, replace the other prefixes' `The Lord of the Rings Online` folders with symlinks to
it.

### LotRO Companion never opens
Leave **Skip Companion's built-in updater** ticked on the Companion tab. Companion's own updater can stop
partway through a download and wait forever. Mithlond then starts Companion directly. Update Companion with
the **Update Companion** button instead.

### Patching fails
**Check for game updates** runs the game's `patchclient.dll` through your runner. If that fails on your setup,
use **Official launcher**, which starts `LotroLauncher.exe` and patches the usual way. Then come back and play
from Mithlond.

### "gamescope / mangohud / gamemoderun is not installed"
Install the program with your package manager, or untick the option in **Settings → Runners and Prefix**.

### GameMode is ticked but nothing changes (the CPU stays on "powersave")
GameMode needs polkit permission to switch the CPU governor, and its rule only allows the `gamemode` group.
Some distributions (Artix and other non-systemd ones) never create that group, and Settings shows a red warning
when that's the case. Fix: `sudo groupadd -r gamemode && sudo usermod -aG gamemode $USER`. While the game runs,
`cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor` should then say `performance`.

### "Native Wayland (Proton)" still shows an XWayland window
Proton gets the setting and turns on its Wayland driver, but some Proton builds keep a game on XWayland as a
fallback. LOTRO did with GE-Proton 11-6. The game runs normally either way.

### The password isn't remembered
This needs `secret-tool` and a running Secret Service keyring: KWallet (`ksecretd`), GNOME Keyring or
KeePassXC with Secret Service enabled. The line under the password box shows the reason if saving failed.
