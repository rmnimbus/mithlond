# Troubleshooting

The **Log** panel at the bottom of the window shows everything the game, Wine/Proton and Companion print. The
same log is saved in `~/.cache/mithlond/mithlond.log`.

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

### The password isn't remembered
This needs `secret-tool` and a running Secret Service keyring: KWallet (`ksecretd`), GNOME Keyring or
KeePassXC with Secret Service enabled. The line under the password box shows the reason if saving failed.
