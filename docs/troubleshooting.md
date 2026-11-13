# Troubleshooting

The **Log** panel at the bottom of the window shows everything the game, Wine/Proton and LotRO Companion print. The
same log is saved in `~/.cache/mithlond/mithlond.log`, with dates and the full error details.

**Asking for help:** click **Export logs…** (in the Log panel's title bar, or **Settings → About & updates**) and
send the zip it saves. It holds everything needed to find the problem: your system, Wine/Proton setup, Mithlond's
log, the game's log and your settings. Your user name, home folder, account names, login tickets and e-mail
addresses are removed first; `README.txt` in the zip lists what's inside. If the problem is with the game itself,
start it once more before exporting so the newest game log is included.

### Double-clicking the AppImage says "archive type not supported" (or opens an archive tool)
The file isn't marked executable. Browsers remove that permission from every download. Run
`chmod +x Mithlond-*.AppImage`, or right-click → Properties → Permissions → "Allow executing file as program".
Re-downloading the file removes the permission again.

### "xcb-cursor0 or libxcb-cursor0 is needed to load the Qt xcb platform plugin" (Aborted)
Versions before 1.4.2 needed the system's `libxcb-cursor0`, which Linux Mint, Ubuntu and some other
distributions don't install by default. Use 1.4.2 or later, which brings its own copy. Alternatively,
install the package: `sudo apt install libxcb-cursor0`.

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

### "Wine ('wine') isn't installed" / "Wine binary 'wine' was not found"
Mithlond 1.4.2 and older defaulted to system Wine, which many systems don't have (Faugus, for example, only
uses Proton). Pick a Proton runner in **Settings → Runners and Prefix**. 1.4.3 and later switch to Proton
automatically when Wine isn't installed, and bring their own umu-run.

### The game closes a few seconds after starting (openSUSE, Fedora-style SELinux)
With SELinux enforcing and the `selinuxuser_execmod` setting off (openSUSE's default), Wine/Proton can't make
its code executable and the game exits right away. A Wine debug log shows `failed to set … protection on
ntdll.dll … noexec filesystem?`. Mithlond warns about this in Settings and in the log. Fix:
`sudo setsebool -P selinuxuser_execmod 1`.

### The game waits at "Enable DirectX 11 Graphics?"
That's the game's first-run prompt, shown when its documents folder has no settings yet. Mithlond 1.4.4 and
later always pick a documents folder (`~/Documents/The Lord of the Rings Online` if none exists) and seed it with
settings, so the prompt doesn't appear. Otherwise, answer it once, or set a documents folder in Settings.

### "umu-run was not found"
Only happens when running Mithlond from source: the AppImage includes umu-run. Install umu-launcher
(https://github.com/Open-Wine-Components/umu-launcher/releases), or use the AppImage.

### "…was created by Proton… Plain Wine would convert it"
You picked system Wine with a prefix made by Proton (Steam, Faugus, umu). Choose a Proton runner for that
prefix, or a different prefix for Wine.

### My plugins or music don't show up in game
The game reads `Documents/The Lord of the Rings Online` **inside the prefix it runs in**. Each prefix has its own
copy. Check that **Settings → Documents folder** is the one in the prefix you play with. To share one folder
between several prefixes, replace the other prefixes' `The Lord of the Rings Online` folders with symlinks to
it.

### LotRO Companion never opens
Leave **Skip LotRO Companion's built-in updater** ticked on the LotRO Companion tab. LotRO Companion's own updater can stop
partway through a download and wait forever. Mithlond then starts LotRO Companion directly. Update LotRO Companion with
the **Update LotRO Companion** button instead.

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

### "corestrings.dll not found. tried to print stringid 201"
Fixed in 1.2.1. Proton-EM ran the game from its `x64` folder instead of the game folder. Update Mithlond.

### "…is an aarch64 build and can't run on this x86_64 computer"
That Proton folder was built for ARM computers (for example an aarch64 "Proton-GE Latest"). Pick another Proton
in Settings → Runners and Prefix; such builds are greyed out in the list.

### Switching Proton builds on an existing prefix
Running a different Proton build in a prefix makes Proton convert the prefix to its own version, and switching
back can print "Prefix has an invalid version?!". **The first launch after a switch can fail** (the game never
appears) while Proton converts the prefix; the next launch works. It's best to stick to one Proton build per
prefix. If you share a prefix with Faugus or Steam, use the same build there.

### The password isn't remembered
This needs `secret-tool` and a running Secret Service keyring: KWallet (`ksecretd`), GNOME Keyring or
KeePassXC with Secret Service enabled. The line under the password box shows the reason if saving failed.
