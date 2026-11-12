"""Unit tests for protocol parsing, songs and addon installation (no network, no game needed)."""

import os
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA = Path(__file__).parent / "data"

# Keep tests away from the real config/cache.
_tmp_home = tempfile.mkdtemp(prefix="mithlond-test-")
os.environ["XDG_CONFIG_HOME"] = f"{_tmp_home}/config"
os.environ["XDG_CACHE_HOME"] = f"{_tmp_home}/cache"
os.environ["XDG_DATA_HOME"] = f"{_tmp_home}/data"

from mithlond import addons, gls, songs  # noqa: E402
from mithlond.config import Settings, check_game_dir  # noqa: E402


class GLSTests(unittest.TestCase):
    def test_launcher_config_and_args(self):
        cfg = gls.parse_app_settings((DATA / "launcher.config.xml").read_bytes())
        self.assertEqual(cfg["GameClient.WIN64.Filename"], "lotroclient64.exe")
        args = gls.client_arguments(cfg, "sub123", "1.2.3.4:9000", "TICKET==", "5.6.7.8:2900", "English", True)
        self.assertEqual(args[:2], ["-a", "sub123"])
        self.assertIn("--glsticketdirect", args)
        self.assertEqual(args[args.index("--glsticketdirect") + 1], "TICKET==")
        self.assertEqual(args[args.index("--language") + 1], "English")
        self.assertNotIn("--HighResOutOfDate", args)
        self.assertFalse(any("{" in a for a in args))
        low = gls.client_arguments(cfg, "s", "l", "t", "c", "English", False)
        self.assertIn("--HighResOutOfDate", low)
        q = gls.queue_params(cfg["WorldQueue.TakeANumber.Parameters"], "sub", "tick et", "http://q")
        self.assertEqual(q, {"command": "TakeANumber", "subscription": "sub", "ticket": "tick et",
                             "ticket_type": "GLS", "queue_url": "http://q"})

    def test_unknown_placeholder(self):
        with self.assertRaises(gls.GLSError):
            gls.client_arguments({"GameClient.WIN32.ArgTemplate": "-a {SUBSCRIPTION} {NEWTHING}"},
                                 "s", "l", "t", "c", "English")

    def test_world_status(self):
        xml = (b'<?xml version="1.0"?><Status><loginservers>1.1.1.1:9004;1.1.1.1:9003;</loginservers>'
               b'<queueurls>http://q1/LoginQueue;http://q2/LoginQueue;</queueurls>'
               b'<allow_billing_role>A,B</allow_billing_role><deny_billing_role></deny_billing_role>'
               b'<world_full>false</world_full><wait_hint>3.5</wait_hint></Status>')
        ws = gls.parse_world_status(xml)
        self.assertEqual(ws.login_server, "1.1.1.1:9004")
        self.assertEqual(ws.queue_url, "http://q1/LoginQueue")
        self.assertTrue(ws.allows(gls.Subscription("LOTRO", "x", "", {"B"})))
        self.assertFalse(ws.allows(gls.Subscription("LOTRO", "x", "", {"C"})))
        with self.assertRaises(gls.WorldUnavailable):
            gls.parse_world_status(b"<Status><loginservers></loginservers><queueurls></queueurls></Status>")

    def test_local_config(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "lotro.launcherconfig").write_bytes(
                b'\xef\xbb\xbf<?xml version="1.0" encoding="utf-8" ?><configuration><appSettings>'
                b'<add key="Launcher.DataCenterService.GLS" value="http://x/Service.asmx"/>'
                b'<add key="DataCenter.GameName" value="LOTRO" /></appSettings></configuration>')
            local = gls.read_local_config(p)
            self.assertEqual(local.gls_datacenter_url, "http://x/Service.asmx")
            self.assertFalse(check_game_dir(p)[0])
            (p / "lotroclient.exe").touch()
            self.assertTrue(check_game_dir(p)[0])


class SongTests(unittest.TestCase):
    def test_parse_and_songbook(self):
        with tempfile.TemporaryDirectory() as d:
            music = Path(d) / "Music"
            (music / "Band").mkdir(parents=True)
            (music / "solo.abc").write_text("X:1\nT:Solo Tune % comment\nT:Lute\nK:C\nabc|\n")
            (music / "Band" / "trio.abc").write_text(
                "X:1\nT:Trio \"Song\" (1/3)\nK:C\nX:2\nT:Trio (2/3)\nX:3\nT:Trio (3/3)\n")
            (music / "Band" / "notabc.mid").write_bytes(b"MThd")
            s = songs.parse_abc(music / "solo.abc")
            self.assertEqual([(p.id, p.name) for p in s.parts], [("1", "Solo Tune - Lute")])
            dirs, found = songs.scan_music(music)
            self.assertEqual(dirs, ["/", "/Band/"])
            self.assertEqual([f.path.name for f in found], ["solo.abc", "trio.abc"])
            self.assertEqual(found[1].title, 'Trio "Song"')
            text, n, nd = songs.songbook_data(music)
            self.assertEqual((n, nd), (2, 2))
            self.assertIn('["Filepath"] = "/Band/",', text)
            self.assertIn('["Filename"] = "trio",', text)
            self.assertIn('["Name"] ="Trio \\"Song\\" (1/3)"', text)
            self.assertTrue(text.startswith("return\r\n{"))
            pd = Path(d) / "PluginData"
            count, files = songs.write_songbook(music, pd, ["acct"])
            self.assertEqual(files, [pd / "acct" / "AllServers" / "SongbookData.plugindata"])
            self.assertTrue(lua_balanced(files[0].read_text()))

    def test_import(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src = d / "src"
            src.mkdir()
            (src / "a.abc").write_text("X:1\nT:A\n")
            (src / "readme.pdf").write_text("x")
            with zipfile.ZipFile(d / "pack.zip", "w") as z:
                z.writestr("pack/b.abc", "X:1\nT:B\n")
                z.writestr("pack/../../evil.abc", "X:1\n")
                z.writestr("pack/c.mid", "x")
            music = d / "Music"
            added = songs.import_songs([src / "a.abc", d / "pack.zip", src / "readme.pdf"], music)
            rels = sorted(p.relative_to(music).as_posix() for p in added)
            self.assertEqual(rels, ["a.abc", "pack/b.abc", "pack/evil.abc"])
            self.assertFalse((d / "evil.abc").exists())
            again = songs.import_songs([src / "a.abc"], music)
            self.assertEqual(again, [])  # identical file: skipped
            (src / "a.abc").write_text("X:1\nT:A v2\n")
            again = songs.import_songs([src / "a.abc"], music)
            self.assertEqual([p.name for p in again], ["a (2).abc"])


def lua_balanced(text: str) -> bool:
    depth = 0
    for ch in text:
        depth += ch == "{"
        depth -= ch == "}"
        if depth < 0:
            return False
    return depth == 0


def make_plugin_zip(path: Path, top: str = "") -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{top}Garan/Wallet.plugin",
                   "<?xml version='1.0'?><Plugin><Information><Name>Wallet</Name><Author>Garan</Author>"
                   "<Version>1.12</Version></Information><Package>Garan.Wallet.Main</Package></Plugin>")
        z.writestr(f"{top}Garan/Wallet/Main.lua", "-- lua")
        z.writestr(f"{top}Garan/Wallet/Resources/icon.tga", "x")
        z.writestr("__MACOSX/._junk", "x")


class AddonTests(unittest.TestCase):
    def remote(self, version="1.12"):
        return addons.RemoteAddon(id="612", kind="plugin", name="Wallet", author="Garan", version=version,
                                  updated=0, downloads=0, category="Bags", description="", file="w.zip",
                                  size=0, url="http://example/612")

    def test_feed_parse(self):
        xml = (b"<Favorites><Ui><UID>612</UID><UIName>Wallet</UIName><UIAuthorName>Garan</UIAuthorName>"
               b"<UIVersion>1.12</UIVersion><UIUpdated>1700000000</UIUpdated><UIDownloads>5</UIDownloads>"
               b"<UICategory>Bags</UICategory><UIDescription><![CDATA[ hi ]]></UIDescription>"
               b"<UIFile>w.zip</UIFile><UISize>10</UISize><UIFileURL>http://x/download612</UIFileURL></Ui></Favorites>")
        [a] = addons.parse_feed(xml, "plugin")
        self.assertEqual((a.id, a.name, a.version, a.updated, a.url), ("612", "Wallet", "1.12", 1700000000,
                                                                       "http://x/download612"))

    def test_links(self):
        for t in ("https://www.lotrointerface.com/downloads/info1218-.html", "info1218-Festival.html",
                  "http://www.lotrointerface.com/downloads/download1218", "fileinfo.php?id=1218", "1218", " #1218 "):
            self.assertEqual(addons.parse_link(t), "1218", t)
        self.assertIsNone(addons.parse_link("https://example.com/foo"))
        page = ('<html><title>LoTROInterface : Festival Buddy II : Festival Buddy II</title><body>'
                '<td>Version: 2.5.1</td> Category : Other Festival Buddy II Interface Information '
                'Uploaded By: b414213562 [ List b414213562\'s interfaces ] Date: 10-20-2026 02:16 PM</body></html>')
        a = addons.parse_info_page("1218", page, "plugin")
        self.assertEqual((a.name, a.version, a.category, a.author, a.url),
                         ("Festival Buddy II", "2.5.1", "Other", "b414213562",
                          "https://www.lotrointerface.com/downloads/download1218"))
        self.assertEqual(time.strftime("%Y-%m-%d", time.localtime(a.updated)), "2026-10-20")
        with self.assertRaises(addons.AddonError):
            addons.parse_info_page("9", "<html>nothing</html>", "plugin")

    def test_merge_feeds(self):
        def ra(i, v, upd):
            return addons.RemoteAddon(id=i, kind="plugin", name=f"P{i}", author="", version=v, updated=upd,
                                      downloads=0, category="", description="", file="", size=0, url="")
        merged = {a.id: a for a in addons.merge_feeds([[ra("1", "1.0", 10), ra("2", "2.0", 5)],
                                                       [ra("1", "1.1", 20), ra("1218", "2.5.1", 7)]])}
        self.assertEqual(sorted(merged), ["1", "1218", "2"])
        self.assertEqual(merged["1"].version, "1.1")  # newest wins

    def test_versions(self):
        self.assertTrue(addons.is_newer("1.10", "1.9"))
        self.assertFalse(addons.is_newer("1.9", "1.10"))
        self.assertFalse(addons.is_newer("v2.0", "v2.0"))
        self.assertTrue(addons.is_newer("2.0", ""))

    def test_install_update_uninstall(self):
        for top in ("", "Plugins/", "Wallet-1.12/Plugins/"):
            with self.subTest(top=top), tempfile.TemporaryDirectory() as d:
                d = Path(d)
                plugins = d / "Plugins"
                (plugins / "Other").mkdir(parents=True)
                (plugins / "Other" / "Keep.plugin").write_text("<Plugin><Package>Other.Keep.Main</Package></Plugin>")
                z = d / "w.zip"
                make_plugin_zip(z, top)
                files = addons.install_archive("plugin", z, self.remote(), plugins)
                self.assertIn("Garan/Wallet.plugin", files)
                self.assertTrue((plugins / "Garan/Wallet/Main.lua").exists())
                self.assertFalse((plugins / "__MACOSX").exists())
                self.assertTrue((plugins / "Garan/Wallet.plugincompendium").exists())
                inst = addons.scan_plugins(plugins)
                wallet = next(i for i in inst if i.name == "Wallet")
                self.assertEqual((wallet.id, wallet.version, wallet.managed), ("612", "1.12", True))
                self.assertEqual(wallet.descriptors, ["Garan/Wallet.plugin"])
                self.assertTrue(any(i.descriptors == ["Other/Keep.plugin"] for i in inst))
                addons.uninstall(wallet, plugins)
                self.assertFalse((plugins / "Garan").exists())
                self.assertTrue((plugins / "Other/Keep.plugin").exists())

    def test_uninstall_unmanaged(self):
        with tempfile.TemporaryDirectory() as d:
            plugins = Path(d) / "Plugins"
            z = Path(d) / "w.zip"
            make_plugin_zip(z)
            addons.extract_archive(z, plugins)
            (plugins / "Garan" / "Wallet.plugincompendium").write_text(
                "<PluginConfig><Id>612</Id><Name>Wallet</Name><Version>1.0</Version>"
                "<Descriptors><descriptor>Garan\\Wallet.plugin</descriptor></Descriptors></PluginConfig>")
            (plugins / "Garan" / "Other.plugin").write_text("<Plugin><Package>Garan.Other.Main</Package></Plugin>")
            [wallet] = [i for i in addons.scan_plugins(plugins) if i.name == "Wallet"]
            self.assertFalse(wallet.managed)
            addons.uninstall(wallet, plugins)
            self.assertFalse((plugins / "Garan" / "Wallet").exists())
            self.assertFalse((plugins / "Garan" / "Wallet.plugin").exists())
            self.assertFalse((plugins / "Garan" / "Wallet.plugincompendium").exists())
            self.assertTrue((plugins / "Garan" / "Other.plugin").exists())

    def test_unsafe_zip(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "bad.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("../../escape.txt", "x")
            with self.assertRaises(addons.AddonError):
                addons.extract_archive(z, Path(d) / "out")
            self.assertFalse((Path(d).parent / "escape.txt").exists())


class SkinTests(unittest.TestCase):
    def test_compilation(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            z = d / "s.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("Pack/Main Skin/SkinDefinition.xml", "<SkinDefinition name='Main'/>")
                zf.writestr("Pack/Main Skin/a.tga", "x")
                zf.writestr("Pack/Main Skin/inner/SkinDefinition.xml", "<x/>")
                zf.writestr("Pack/Wide bar/SkinDefinition.xml", "<x/>")
            skins = d / "skins"
            (skins / "Mine").mkdir(parents=True)
            a = addons.RemoteAddon(id="9", kind="skin", name="Pack", author="", version="1", updated=0, downloads=0,
                                   category="", description="", file="s.zip", size=0, url="")
            addons.install_archive("skin", z, a, skins)
            self.assertTrue((skins / "Main Skin" / "inner" / "SkinDefinition.xml").exists())
            self.assertTrue((skins / "Wide bar" / "SkinDefinition.xml").exists())
            inst = addons.scan_skins(skins)
            self.assertEqual(sorted((i.name, i.managed) for i in inst), [("Mine", False), ("Pack", True)])
            addons.uninstall(next(i for i in inst if i.managed), skins)
            self.assertEqual([p.name for p in skins.iterdir()], ["Mine"])


class KeystoreTests(unittest.TestCase):
    """Runs keystore against a fake secret-tool that keeps secrets in a temp dir."""

    def setUp(self):
        from mithlond import keystore
        self.ks = keystore
        self.dir = Path(tempfile.mkdtemp())
        tool = self.dir / "secret-tool"
        tool.write_text(f"""#!/bin/sh
store="{self.dir}/store"; mkdir -p "$store"
cmd=$1; shift
[ "$1" = "--label=x" ] || true
case "$cmd" in
  store) shift; cat > "$store/$4" ;;
  lookup) [ -f "$store/$4" ] && cat "$store/$4" || exit 1 ;;
  clear) rm -f "$store/$4" ;;
esac
""")
        tool.chmod(0o755)
        self.old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{self.dir}:{self.old_path}"

    def tearDown(self):
        os.environ["PATH"] = self.old_path

    def test_roundtrip(self):
        self.ks.set_password("Me", "s3cr3t pw")
        self.assertEqual(self.ks.get_password("me"), "s3cr3t pw")
        self.assertNotIn("s3cr3t", (Path(os.environ["XDG_CONFIG_HOME"])).as_posix())
        self.ks.delete_password("ME")
        self.assertIsNone(self.ks.get_password("me"))

    def test_store_failure_is_reported(self):
        (self.dir / "secret-tool").write_text("#!/bin/sh\necho 'Cannot autolaunch D-Bus' >&2\nexit 1\n")
        with self.assertRaises(self.ks.KeyringError) as cm:
            self.ks.set_password("me", "pw")
        self.assertIn("D-Bus", str(cm.exception))


class HostEnvTests(unittest.TestCase):
    def test_appimage_isolation(self):
        from mithlond import hostenv
        old = dict(os.environ)
        try:
            os.environ.update(MITHLOND_APPIMAGE="1", APPIMAGE="/x.AppImage", APPDIR="/tmp/.mount",
                              QT_PLUGIN_PATH="/usr/lib/qt6/plugins", QT_QPA_PLATFORMTHEME="qt6ct")
            hostenv.isolate_bundled_qt()
            self.assertNotIn("QT_PLUGIN_PATH", os.environ)       # our bundled Qt ignores the host's plugins
            env = hostenv.host_env()
            self.assertEqual(env["QT_PLUGIN_PATH"], "/usr/lib/qt6/plugins")  # child programs get them back
            self.assertEqual(env["QT_QPA_PLATFORMTHEME"], "qt6ct")
            self.assertNotIn("APPIMAGE", env)
            self.assertNotIn("APPDIR", env)
        finally:
            os.environ.clear()
            os.environ.update(old)
            hostenv._removed.clear()


class NewsTests(unittest.TestCase):
    def test_real_feed_and_coupon(self):
        from mithlond import news
        items = news.parse_feed((DATA / "launcher-feed.xml").read_bytes())
        self.assertGreater(len(items), 10)
        c = news.find_coupon(items)
        self.assertEqual((c.code, c.item, c.until), ("WARMFEELING", "Battle Potion of Restoration",
                                                     "Now through November 12th!"))
        self.assertTrue(c.sale.startswith("Sales"))

    def test_sanitize(self):
        from mithlond import news
        h, t = news.sanitize('<p onclick="x()">Hi <script>alert(1)</script><img src="http://x/y.png">'
                             '<a href="javascript:evil()">bad</a> <a href="https://ok/">good</a></p>')
        self.assertNotIn("script", h)
        self.assertNotIn("img", h)
        self.assertNotIn("javascript", h)
        self.assertNotIn("onclick", h)
        self.assertIn('<a href="https://ok/">good</a>', h)
        self.assertEqual(t, "Hi bad good")

    def test_no_coupon(self):
        from mithlond import news
        self.assertIsNone(news.find_coupon([news.NewsItem("x", "", "", "Nothing here", "")]))
        self.assertEqual(news.feed_url(None, "English"), "https://www.lotro.com/en/launcher-feed.xml")
        self.assertEqual(news.feed_url({"URL.NewsFeed": "https://a/{lang}/f.xml"}, "DE"), "https://a/de/f.xml")


class RunnerTests(unittest.TestCase):
    def test_prefix_checks(self):
        from mithlond import config, runner
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            ro = home / "ro"
            ro.mkdir()
            ro.chmod(0o555)
            try:
                if os.access(ro, os.W_OK):
                    self.skipTest("running as root")
                self.assertIn("not writable", config.prefix_problem(ro))
                with self.assertRaises(runner.RunnerError):
                    runner.windows_command(Settings(wine_binary="/bin/sh", wine_prefix=str(ro)), "g.exe", [])
            finally:
                ro.chmod(0o755)
            self.assertIsNone(config.prefix_problem(home / "newprefix"))
            proton = home / "Faugus" / "default"
            proton.mkdir(parents=True)
            (proton / "config_info").touch()
            self.assertIn("created by Proton", config.wine_prefix_problem(proton))
            with self.assertRaises(runner.RunnerError):
                runner.windows_command(Settings(wine_binary="/bin/sh", wine_prefix=str(proton)), "g.exe", [])

    def test_umu_join(self):
        from mithlond import runner
        with tempfile.TemporaryDirectory() as d:
            umu = Path(d) / "umu-run"
            umu.write_text("#!/bin/sh\n")
            s = Settings(runner="umu", umu_run=str(umu), wine_prefix=str(Path(d) / "pfx"), proton_path="/p/GE",
                         extra_env={"DXVK_HUD": "fps"})
            argv, env = runner.windows_command(s, "game.exe", ["-x"])
            self.assertEqual(argv, [str(umu), "game.exe", "-x"])
            argv, _ = runner.windows_command(s, "/volumes/games/lotro/x64/lotroclient64.exe", [])
            self.assertEqual(argv[1], "Z:\\volumes\\games\\lotro\\x64\\lotroclient64.exe")
            self.assertEqual(runner.dos_path("C:\\x.exe"), "C:\\x.exe")
            self.assertEqual((env["WINEPREFIX"], env["PROTONPATH"], env["DXVK_HUD"]), (str(Path(d) / "pfx"), "/p/GE", "fps"))
            self.assertNotIn("PROTON_VERB", env)
            _, env = runner.windows_command(s, "game.exe", [], join=True)
            self.assertEqual(env["PROTON_VERB"], "run")

    def test_proton_arch(self):
        from mithlond import config, runner
        with tempfile.TemporaryDirectory() as d:
            def fake(name, machine):
                b = Path(d) / name / "files" / "bin"
                b.mkdir(parents=True)
                (b / "wineserver").write_bytes(b"\x7fELF" + bytes(14) + machine.to_bytes(2, "little") + bytes(40))
                return Path(d) / name
            arm, x86 = fake("Proton-GE Latest", 0xB7), fake("GE-Proton11-6", 0x3E)
            self.assertEqual(config.proton_arch(arm), "aarch64")
            self.assertEqual(config.proton_arch(x86), "x86_64")
            self.assertIsNone(config.proton_arch(Path(d) / "missing"))
            if config.host_arch() == "x86_64":
                self.assertIn("is an aarch64 build", config.proton_problem(arm))
                self.assertIsNone(config.proton_problem(x86))
                umu = Path(d) / "umu-run"
                umu.write_text("#!/bin/sh\n")
                with self.assertRaises(runner.RunnerError):
                    runner.windows_command(Settings(runner="umu", umu_run=str(umu), proton_path=str(arm),
                                                    wine_prefix=str(Path(d) / "pfx")), "g.exe", [])

    def test_prefs_args(self):
        from mithlond import runner
        with tempfile.TemporaryDirectory() as d:
            docs = Path(d) / "My Docs" / "The Lord of the Rings Online"
            s = Settings(documents_dir=str(docs))
            self.assertEqual(runner.prefs_args(s), ["--prefs", runner.dos_path(docs / "UserPreferences.ini")])
            self.assertTrue(docs.is_dir())  # created so the game can write there
            self.assertTrue(runner.prefs_args(s)[1].startswith("Z:\\"))
            self.assertIn("D3DVersionPromptedForAtStartup=11", (docs / "UserPreferences.ini").read_text())
            # seeding copies from the prefix's own documents folder when there is one
            pfx = Path(d) / "pfx"
            src = pfx / "drive_c/users/steamuser/Documents/The Lord of the Rings Online"
            src.mkdir(parents=True)
            (src / "UserPreferences.ini").write_text("[Display]\nFullScreen=False\n")
            (src / "lotro.keymap").write_text("keys")
            docs2 = Path(d) / "new"
            s2 = Settings(documents_dir=str(docs2), wine_prefix=str(pfx), wine_binary="/bin/sh")
            runner.prefs_args(s2)
            self.assertEqual((docs2 / "UserPreferences.ini").read_text(), "[Display]\nFullScreen=False\n")
            self.assertEqual((docs2 / "lotro.keymap").read_text(), "keys")
            (docs2 / "UserPreferences.ini").write_text("mine")
            runner.prefs_args(s2)  # existing settings are never overwritten
            self.assertEqual((docs2 / "UserPreferences.ini").read_text(), "mine")
            s.use_prefs = False
            self.assertEqual(runner.prefs_args(s), [])
            self.assertEqual(runner.prefs_args(Settings()), [])

    def test_removed_onelauncher_mode_migrates(self):
        from mithlond import config
        s = Settings(runner="onelauncher")
        config.autodetect(s)
        self.assertEqual(s.runner, "wine")


class ProcTests(unittest.TestCase):
    def test_find_and_stop_fake_client(self):
        import subprocess
        from mithlond import procs
        with tempfile.TemporaryDirectory() as d:
            pfx = Path(d) / "pfx"
            pfx.mkdir()
            env = dict(os.environ, WINEPREFIX=str(pfx))
            p = subprocess.Popen(["bash", "-c", 'exec -a "S:\\other\\lotro\\x64\\lotroclient64.exe" sleep 60'],
                                 env=env)
            try:
                for _ in range(50):
                    if any(c.pid == p.pid for c in procs.game_clients()):
                        break
                    time.sleep(0.05)
                self.assertIn(p.pid, [c.pid for c in procs.game_clients()])
                self.assertIn(p.pid, [c.pid for c in procs.windows_programs_in_prefix(pfx)])
                self.assertEqual(procs.windows_programs_in_prefix(Path(d) / "other"), [])
                rel = procs.related(Settings())
                self.assertIn(p.pid, [c.pid for c in rel])
                self.assertNotIn(os.getpid(), [c.pid for c in rel])
                procs.terminate([c for c in rel if c.pid == p.pid], grace=2)
                self.assertIsNotNone(p.wait(timeout=5))
            finally:
                if p.poll() is None:
                    p.kill()


class EnvParseTests(unittest.TestCase):
    def test_parse_env(self):
        from mithlond.ui.settings_tab import parse_env
        env = parse_env("DXVK_HUD=fps\n# comment\n\nexport A=1\nB='two words'\nbad line\nC=\"x=y\"\n")
        self.assertEqual(env, {"DXVK_HUD": "fps", "A": "1", "B": "two words", "C": "x=y"})


def make_companion(base: Path, version: str) -> None:
    app = base / "app"
    app.mkdir(parents=True)
    (app / "LotRO Companion.cfg").write_text(f"[Application]\napp.name=LotRO Companion\napp.version={version}\n")
    (app / "launcher.xml").write_text('<launcherConfig mainClass="delta.games.lotro.Main" rootDir="lib"><classpath>'
                                      '<classpathEntry path="patches"/><classpathEntry path="a-1.jar"/>'
                                      '</classpath></launcherConfig>')
    (base / "runtime" / "bin").mkdir(parents=True)
    (base / "runtime" / "bin" / "javaw.exe").touch()
    (base / "LotRO Companion.exe").touch()


class FakeResponse:
    def __init__(self, data: bytes):
        self.content, self.headers = data, {"Content-Length": str(len(data))}

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        for i in range(0, len(self.content), n):
            yield self.content[i:i + n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class CompanionTests(unittest.TestCase):
    def test_versions_and_rss(self):
        from mithlond import companion
        self.assertTrue(companion.is_newer("24.11.0.50.0", "24.9.1"))
        self.assertFalse(companion.is_newer("24.11.0.50.0", "24.11.0.50"))
        self.assertFalse(companion.is_newer("24.10.0.49.6", "24.11.0.50"))
        rss = (b"<rss><channel><item><title><![CDATA[/16/software.xml]]></title></item>"
               b"<item><title><![CDATA[/lotro-companion-24.10.0.49.6.zip]]></title></item>"
               b"<item><title><![CDATA[/lotro-companion-24.11.0.50.0.zip]]></title></item></channel></rss>")
        orig = companion.requests.get
        companion.requests.get = lambda *a, **k: FakeResponse(rss)
        try:
            rel = companion.latest_release()
        finally:
            companion.requests.get = orig
        self.assertEqual((rel.version, rel.name), ("24.11.0.50.0", "lotro-companion-24.11.0.50.0.zip"))
        self.assertIn("lotro-companion-24.11.0.50.0.zip/download", rel.url)

    def test_update_swaps_and_keeps_backup(self):
        import io
        from mithlond import companion
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "LotRO Companion"
            make_companion(base, "24.9.1")
            (Path(d) / "LotRO Companion.old-1.0").mkdir()  # an older Mithlond backup: gets cleaned up
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("LotRO Companion/app/LotRO Companion.cfg", "[Application]\napp.version=24.11.0.50\n")
                z.writestr("LotRO Companion/LotRO Companion.exe", "exe")
            orig = companion.requests.get
            companion.requests.get = lambda *a, **k: FakeResponse(buf.getvalue())
            try:
                backup = companion.update(base, companion.Release("24.11.0.50.0", "x.zip"))
            finally:
                companion.requests.get = orig
            self.assertEqual(companion.installed_version(base), "24.11.0.50")
            self.assertEqual(backup.name, "LotRO Companion.old-24.9.1")
            self.assertEqual(companion.installed_version(backup), "24.9.1")
            self.assertFalse((Path(d) / "LotRO Companion.old-1.0").exists())
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["LotRO Companion", "LotRO Companion.old-24.9.1"])

    def test_direct_launch_and_runner(self):
        from mithlond import companion, runner
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "LotRO Companion"
            make_companion(base, "24.11.0.50")
            java, args, cwd = companion.direct_launch(base, windows=True)
            self.assertTrue(java.endswith("runtime/bin/javaw.exe"))
            self.assertEqual(args[-3:], ["-cp", "lib\\patches;lib\\a-1.jar", "delta.games.lotro.Main"])
            self.assertEqual(cwd, base / "app")
            wine = Path(d) / "wine"
            wine.write_text("#!/bin/sh\n")
            s = Settings(companion_dir=str(base), wine_binary=str(wine), wine_prefix=str(Path(d) / "pfx"))
            argv, env, cwd = runner.companion_command(s)
            self.assertEqual(argv[:2], [str(wine), java])
            self.assertIn("delta.games.lotro.Main", argv)
            s.companion_skip_updater = False
            argv, env, cwd = runner.companion_command(s)
            self.assertTrue(argv[1].endswith("LotRO Companion.exe"))
            # Proton-EM-style builds (start.exe /unix) can't run javaw.exe directly: official launcher instead
            umu = Path(d) / "umu-run"
            umu.write_text("#!/bin/sh\n")
            em = Path(d) / "Proton-EM"
            em.mkdir()
            (em / "proton").write_text('argv = [g_proton.wine64_bin, "c:\\\\windows\\\\system32\\\\start.exe", "/unix"]\n')
            ge = Path(d) / "GE-Proton"
            ge.mkdir()
            (ge / "proton").write_text('log("launching with umu.exe")\n')
            s = Settings(companion_dir=str(base), runner="umu", umu_run=str(umu), wine_prefix=str(Path(d) / "pfx"),
                         proton_path=str(em))
            self.assertTrue(runner.proton_uses_start_unix(s))
            argv, env, cwd = runner.companion_command(s)
            self.assertEqual(argv[1], str(base / "LotRO Companion.exe"))  # Linux path, official launcher
            s.proton_path = str(ge)
            self.assertFalse(runner.proton_uses_start_unix(s))
            argv, env, cwd = runner.companion_command(s)
            self.assertEqual(argv[1], java)  # direct launch, Linux path
            self.assertIn("delta.games.lotro.Main", argv)


class AdoptTests(unittest.TestCase):
    def test_adopt_and_shared_files(self):
        with tempfile.TemporaryDirectory() as d:
            plugins = Path(d) / "Plugins"
            z = Path(d) / "w.zip"
            make_plugin_zip(z)
            addons.extract_archive(z, plugins)
            (plugins / "Garan" / "Wallet.plugincompendium").write_text(
                "<PluginConfig><Id>612</Id><Name>Wallet</Name><Version>1.12</Version>"
                "<Descriptors><descriptor>Garan\\Wallet.plugin</descriptor></Descriptors></PluginConfig>")
            # A second plugin sharing the same package folder
            (plugins / "Garan" / "WalletExtra.plugin").write_text(
                "<Plugin><Information><Name>Extra</Name></Information><Package>Garan.Wallet.Extra</Package></Plugin>")
            (plugins / "Garan" / "WalletExtra.plugincompendium").write_text(
                "<PluginConfig><Id>999</Id><Name>Extra</Name><Version>1</Version>"
                "<Descriptors><descriptor>Garan\\WalletExtra.plugin</descriptor></Descriptors></PluginConfig>")
            adopted = addons.adopt_plugins(plugins)
            self.assertEqual(sorted(adopted), ["Extra", "Wallet"])
            self.assertEqual(addons.adopt_plugins(plugins), [])  # idempotent
            inst = {i.name: i for i in addons.scan_plugins(plugins)}
            self.assertTrue(inst["Wallet"].managed and inst["Extra"].managed)
            addons.uninstall(inst["Extra"], plugins)
            self.assertTrue((plugins / "Garan/Wallet/Main.lua").exists())  # owned by Wallet: kept
            self.assertFalse((plugins / "Garan/WalletExtra.plugin").exists())
            addons.uninstall(inst["Wallet"], plugins)
            self.assertFalse((plugins / "Garan").exists())

    def test_music_folders_listed_and_removable(self):
        with tempfile.TemporaryDirectory() as d:
            music = Path(d) / "Music"
            (music / "FatLute").mkdir(parents=True)
            (music / "FatLute" / "a.abc").write_text("X:1\n")
            (music / "loose.abc").write_text("X:1\n")
            [m] = addons.scan_music(music)
            self.assertEqual((m.name, m.managed), ("FatLute", False))
            addons.uninstall(m, music)
            self.assertFalse((music / "FatLute").exists())
            self.assertTrue((music / "loose.abc").exists())


class GameOptionTests(unittest.TestCase):
    def test_options(self):
        from mithlond import runner
        with tempfile.TemporaryDirectory() as d:
            for tool in ("gamescope", "gamemoderun", "mangohud"):
                t = Path(d) / tool
                t.write_text("#!/bin/sh\n")
                t.chmod(0o755)
            old = os.environ["PATH"]
            os.environ["PATH"] = f"{d}:{old}"
            try:
                s = Settings(opt_gamescope=True, gamescope_args="-f -W 2560", opt_gamemode=True, opt_mangohud=True,
                             opt_dxvk_hud=True, opt_proton_wayland=True)
                argv, env = runner.apply_game_options(s, ["umu-run", "game.exe"], {})
                self.assertEqual(argv, [f"{d}/gamescope", "-f", "-W", "2560", "--", f"{d}/gamemoderun",
                                        "umu-run", "game.exe"])
                self.assertEqual((env["MANGOHUD"], env["DXVK_HUD"], env["PROTON_ENABLE_WAYLAND"]), ("1", "fps", "1"))
                self.assertEqual(runner.apply_game_options(Settings(), ["x"], {}), (["x"], {}))
            finally:
                os.environ["PATH"] = old
            os.environ["PATH"] = d + "/nothing"
            try:
                with self.assertRaises(runner.RunnerError):
                    runner.apply_game_options(Settings(opt_gamescope=True), ["x"], {})
            finally:
                os.environ["PATH"] = old


CAT_INDEX = """
<a href="index.php?s=x&amp;cid=8&amp;dp=0&amp;sh=full"><b>LotRO Stand-Alone Plugins</b></a>
<a href="index.php?s=x&amp;cid=29&amp;dp=0&amp;sh=full">Other</a>
<a href="index.php?s=x&amp;cid=48&amp;dp=0&amp;sh=full"><b>Outdated LotRO Interfaces</b></a>
<a href="index.php?s=x&amp;cid=37&amp;dp=0&amp;sh=full"><b>DDO Complete Sets</b></a>
<a href="index.php?s=x&amp;cid=47&amp;dp=0&amp;sh=full">Other</a>
"""
CAT_PAGE = """<table><tr>
 <td class="alt2" nowrap><a href="info1218-FestivalBuddyII.html"><img src="i.gif" Alt="View file info."></a></td>
 <td class="alt1" align="left"><a href="info1218-FestivalBuddyII.html">Festival Buddy II</a>  &nbsp; </td>
 <td class="alt2"><div class="smallfont">b414213562</div></td>
 <td class="alt1"><div class="smallfont">15.33 MB</div></td>
 <td class="alt2"><div class="smallfont">92616</div></td>
 <td class="alt1"><div class="smallfont" align="left"><div align="left">by <a href="/m">b414213562</a></div>
 <div align="left">10-20-2026 <span class="time">02:22 PM</span></div></div></td>
</tr><tr>
 <td class="alt1" align="left"><a href="fileinfo.php?s=abc&amp;id=1291">Loot Watcher</a></td>
 <td class="alt2"><div class="smallfont">whiterabbit963</div></td>
 <td class="alt1"><div class="smallfont">46.04 Kb</div></td>
 <td class="alt2"><div class="smallfont">1387</div></td>
 <td class="alt1"><div class="smallfont">11-11-2026 <span class="time">01:07 AM</span></div></td>
</tr></table> Page 2 of 5 <a href="cat50.html">Burglar</a>"""


class CatalogTests(unittest.TestCase):
    def test_categories(self):
        from mithlond import catalog
        cats = catalog.parse_categories(CAT_INDEX)
        self.assertEqual(cats, [("8", "LotRO Stand-Alone Plugins"), ("29", "Other"), ("48", "Outdated LotRO Interfaces")])
        self.assertEqual(catalog.parse_categories('<a href="cat50.html">Burglar</a>'), [("50", "Burglar")])

    def test_listing(self):
        from mithlond import catalog
        rows, page, pages = catalog.parse_listing(CAT_PAGE, "Other")
        self.assertEqual((page, pages), (2, 5))
        a, b = rows
        self.assertEqual((a.id, a.name, a.author, a.downloads, a.category), ("1218", "Festival Buddy II", "b414213562",
                                                                            92616, "Other"))
        self.assertEqual(a.size, int(15.33 * 1024 * 1024))
        self.assertEqual(time.strftime("%Y-%m-%d %H:%M", time.localtime(a.updated)), "2026-10-20 14:22")
        self.assertEqual((b.id, b.name, b.size, b.downloads), ("1291", "Loot Watcher", int(46.04 * 1024), 1387))

    def test_fetch_all_merges(self):
        from mithlond import catalog
        listed = [addons.RemoteAddon(id="1291", kind="plugin", name="Loot Watcher", author="w", version="v1.3.1",
                                     updated=1, downloads=1, category="Bags", description="d", file="", size=0, url="")]
        entries = [catalog.Entry("1291", "Loot Watcher", "Other", "w", 1, 1, 1),
                   catalog.Entry("1218", "Festival Buddy II", "Other", "b", 1, 1, 1),
                   catalog.Entry("77", "Some Skin", "Graphical Modifications (Skins)", "s", 1, 1, 1)]
        orig = addons.fetch_feed, catalog.load
        addons.fetch_feed = lambda kind, force=False: list(listed) if kind == "plugin" else []
        catalog.load = lambda force=False, progress=None: entries
        try:
            plugins = {a.id: a for a in addons.fetch_all("plugin")}
            skins = {a.id: a for a in addons.fetch_all("skin")}
        finally:
            addons.fetch_feed, catalog.load = orig
        self.assertEqual(sorted(plugins), ["1218", "1291"])
        self.assertEqual(plugins["1291"].version, "v1.3.1")  # curated entry kept
        self.assertTrue(plugins["1218"].site_only and plugins["1218"].version == "")
        self.assertEqual(plugins["1218"].url, "https://www.lotrointerface.com/downloads/download1218")
        self.assertEqual(sorted(skins), ["77"])


class GameModeTests(unittest.TestCase):
    def test_group_check(self):
        import grp
        import pwd
        from mithlond import runner
        me = pwd.getpwuid(os.getuid())
        orig = grp.getgrnam
        try:
            grp.getgrnam = lambda n: (_ for _ in ()).throw(KeyError(n))
            self.assertIn("doesn't exist", runner.gamemode_problem())
            grp.getgrnam = lambda n: grp.struct_group(("gamemode", "x", 949, []))
            self.assertIn("not in the 'gamemode' group", runner.gamemode_problem())
            grp.getgrnam = lambda n: grp.struct_group(("gamemode", "x", 949, [me.pw_name]))
            self.assertIsNone(runner.gamemode_problem())
        finally:
            grp.getgrnam = orig


class ToolTests(unittest.TestCase):
    def test_defaults_follow_documents(self):
        s = Settings(documents_dir="/docs")
        self.assertEqual(s.downloads_path(), Path("/docs/Downloads"))
        self.assertEqual(s.companion_path(), Path("/docs/Downloads/LotRO Companion"))
        s.downloads_dir = "/dl"
        self.assertEqual(s.companion_path(), Path("/dl/LotRO Companion"))
        self.assertFalse(Settings().companion_with_game)

    def test_install_maestro_and_wan(self):
        import io
        from mithlond import tools
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("Maestro.exe", "exe")
            z.writestr("app/Maestro.jar", "jar")
            z.writestr("app/java.midi.patch.jar", "p")
        orig_latest, orig_get = tools.latest, tools.requests.get
        tools.latest = lambda k: tools.Latest("v9", None, "http://x/" + k)
        tools.requests.get = lambda url, **k: FakeResponse(buf.getvalue() if "maestro" in url else b"MZexe")
        try:
            with tempfile.TemporaryDirectory() as d:
                dl = Path(d) / "Downloads"
                p = tools.install("maestro", dl)
                self.assertIn(p.name, ("Maestro.jar", "Maestro.exe"))
                self.assertTrue((dl / "Maestro" / "app" / "Maestro.jar").exists())
                self.assertEqual(tools.installed_version("maestro", dl), "v9")
                p2 = tools.install("maestro", dl)  # re-download replaces cleanly
                self.assertEqual(p, p2)
                w = tools.install("wan", dl)
                self.assertEqual(w, dl / "WANSongBookFiller" / "WANSongBookFiller.exe")
                self.assertEqual(w.read_bytes(), b"MZexe")
                self.assertEqual(sorted(x.name for x in dl.iterdir()), ["Maestro", "WANSongBookFiller"])
                tools.latest = lambda k: tools.Latest("", None, None, "source only")
                with self.assertRaises(tools.ToolError):
                    tools.install("brute", dl)
        finally:
            tools.latest, tools.requests.get = orig_latest, orig_get

    def test_companion_fresh_install(self):
        import io
        from mithlond import companion
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "Downloads" / "LotRO Companion"
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("LotRO Companion/app/LotRO Companion.cfg", "app.version=24.11.0.50\n")
            orig = companion.requests.get
            companion.requests.get = lambda *a, **k: FakeResponse(buf.getvalue())
            try:
                backup = companion.update(base, companion.Release("24.11.0.50.0", "x.zip"))
            finally:
                companion.requests.get = orig
            self.assertIsNone(backup)
            self.assertEqual(companion.installed_version(base), "24.11.0.50")


class SettingsTests(unittest.TestCase):
    def test_documents_subdirs(self):
        s = Settings(documents_dir="/docs")
        self.assertEqual(s.subdir("Plugins"), Path("/docs/Plugins"))
        self.assertEqual(s.subdir("Music"), Path("/docs/Music"))
        self.assertTrue(s.use_prefs)
    def test_roundtrip(self):
        s = Settings(game_dir="/g", extra_env={"A": "1"})
        s.accounts.append(__import__("mithlond.config", fromlist=["Account"]).Account("me", "Glamdring"))
        s.save()
        t = Settings.load()
        self.assertEqual((t.game_dir, t.extra_env, t.accounts[0].world), ("/g", {"A": "1"}, "Glamdring"))


if __name__ == "__main__":
    unittest.main()
