"""Unit tests for protocol parsing, songs and addon installation (no network, no game needed)."""

import contextlib
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock
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


@contextlib.contextmanager
def fake_bundled_umu(d):
    """An AppDir with opt/umu/umu-run, as inside the AppImage. Yields the umu-run path."""
    umu = Path(d) / "appdir" / "opt" / "umu" / "umu-run"
    umu.parent.mkdir(parents=True, exist_ok=True)
    umu.write_text("#!/usr/bin/env python3\n")
    with mock.patch.dict(os.environ, {"APPDIR": str(Path(d) / "appdir")}):
        yield umu


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
                    runner.windows_command(Settings(runner="wine", wine_binary="/bin/sh", wine_prefix=str(ro)), "g.exe", [])
            finally:
                ro.chmod(0o755)
            self.assertIsNone(config.prefix_problem(home / "newprefix"))
            proton = home / "Faugus" / "default"
            proton.mkdir(parents=True)
            (proton / "config_info").touch()
            self.assertIn("created by Proton", config.wine_prefix_problem(proton))
            with self.assertRaises(runner.RunnerError):
                runner.windows_command(Settings(runner="wine", wine_binary="/bin/sh", wine_prefix=str(proton)), "g.exe", [])

    def test_umu_join(self):
        from mithlond import runner
        with tempfile.TemporaryDirectory() as d, fake_bundled_umu(d) as umu:
            s = Settings(runner="umu", wine_prefix=str(Path(d) / "pfx"), proton_path="/p/GE",
                         extra_env={"DXVK_HUD": "fps"})
            argv, env = runner.windows_command(s, "game.exe", ["-x"])
            self.assertEqual(argv, [sys.executable, "-I", str(umu), "game.exe", "-x"])  # the AppImage's own Python
            argv, _ = runner.windows_command(s, "/home/me/Games/lotro/x64/lotroclient64.exe", [])
            self.assertEqual(argv[3], "Z:\\home\\me\\Games\\lotro\\x64\\lotroclient64.exe")
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
                with fake_bundled_umu(d), self.assertRaises(runner.RunnerError):
                    runner.windows_command(Settings(runner="umu", proton_path=str(arm),
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
            s2 = Settings(documents_dir=str(docs2), wine_prefix=str(pfx), runner="wine", wine_binary="/bin/sh")
            runner.prefs_args(s2)
            self.assertEqual((docs2 / "UserPreferences.ini").read_text(), "[Display]\nFullScreen=False\n")
            self.assertEqual((docs2 / "lotro.keymap").read_text(), "keys")
            (docs2 / "UserPreferences.ini").write_text("mine")
            runner.prefs_args(s2)  # existing settings are never overwritten
            self.assertEqual((docs2 / "UserPreferences.ini").read_text(), "mine")
            s.use_prefs = False
            self.assertEqual(runner.prefs_args(s), [])
            self.assertEqual(runner.prefs_args(Settings()), [])

    def test_skip_intro(self):
        from mithlond import runner
        with tempfile.TemporaryDirectory() as d:
            game, docs = Path(d) / "game", Path(d) / "docs"
            logo = game / "raw/en/logo"
            logo.mkdir(parents=True)
            (logo / "turbine_logo.bik").write_bytes(b"BIK")
            (logo / "lotro_ad_pregame.jpg").write_bytes(b"JPG")
            docs.mkdir()
            prefs = docs / "UserPreferences.ini"
            prefs.write_bytes(b"[Launcher]\r\nAllowMultipleInstances=true\r\n\r\n[Misc]\r\nPlayedIntroMovie=False\r\n"
                              b"Other=1\r\n\r\n[Render]\r\nGraphicsCore=D3D11\r\n")
            s = Settings(game_dir=str(game), documents_dir=str(docs))
            self.assertTrue(s.skip_intro)  # on by default
            notes = runner.apply_intro_skip(s)
            self.assertFalse((logo / "turbine_logo.bik").exists())
            self.assertTrue((logo / "turbine_logo.bik.mithlond-skipped").exists())
            self.assertTrue((logo / "lotro_ad_pregame.jpg").exists())  # only videos
            self.assertEqual(prefs.read_bytes(), b"[Launcher]\r\nAllowMultipleInstances=true\r\n\r\n[Misc]\r\n"
                             b"PlayedIntroMovie=True\r\nOther=1\r\n\r\n[Render]\r\nGraphicsCore=D3D11\r\n")
            self.assertEqual(len(notes), 2)
            self.assertEqual(runner.apply_intro_skip(s), [])  # nothing left to do
            (logo / "turbine_logo.bik").write_bytes(b"BIK2")  # a patch restored it
            runner.apply_intro_skip(s)
            self.assertEqual((logo / "turbine_logo.bik.mithlond-skipped").read_bytes(), b"BIK2")
            s.skip_intro = False
            self.assertEqual(runner.apply_intro_skip(s), ["restored raw/en/logo/turbine_logo.bik"])
            self.assertTrue((logo / "turbine_logo.bik").exists())
            # no [Misc] section yet (e.g. freshly seeded settings): appended
            s.skip_intro = True
            prefs.write_text("[Render]\nGraphicsCore=D3D11\n")
            runner.apply_intro_skip(s)
            self.assertEqual(prefs.read_text(), "[Render]\nGraphicsCore=D3D11\n[Misc]\nPlayedIntroMovie=True\n")

    def test_removed_onelauncher_mode_migrates(self):
        from mithlond import config
        s = Settings(runner="onelauncher")
        config.autodetect(s)
        self.assertEqual(s.runner, "umu")


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
            s = Settings(companion_dir=str(base), runner="wine", wine_binary=str(wine), wine_prefix=str(Path(d) / "pfx"))
            argv, env, cwd = runner.companion_command(s)
            self.assertEqual(argv[:2], [str(wine), java])
            self.assertIn("delta.games.lotro.Main", argv)
            s.companion_skip_updater = False
            argv, env, cwd = runner.companion_command(s)
            self.assertTrue(argv[1].endswith("LotRO Companion.exe"))
            # Proton-EM-style builds (start.exe /unix) can't run javaw.exe directly: official launcher instead
            umu_ctx = fake_bundled_umu(d)
            umu_ctx.__enter__()
            self.addCleanup(umu_ctx.__exit__, None, None, None)
            em = Path(d) / "Proton-EM"
            em.mkdir()
            (em / "proton").write_text('argv = [g_proton.wine64_bin, "c:\\\\windows\\\\system32\\\\start.exe", "/unix"]\n')
            ge = Path(d) / "GE-Proton"
            ge.mkdir()
            (ge / "proton").write_text('log("launching with umu.exe")\n')
            s = Settings(companion_dir=str(base), runner="umu", wine_prefix=str(Path(d) / "pfx"),
                         proton_path=str(em))
            self.assertTrue(runner.proton_uses_start_unix(s))
            argv, env, cwd = runner.companion_command(s)
            self.assertEqual(argv[3], str(base / "LotRO Companion.exe"))  # Linux path, official launcher
            s.proton_path = str(ge)
            self.assertFalse(runner.proton_uses_start_unix(s))
            argv, env, cwd = runner.companion_command(s)
            self.assertEqual(argv[3], java)  # direct launch, Linux path
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
    def test_play_tab_options(self):
        from mithlond import runner
        s = Settings()
        self.assertEqual((s.fps_limit, s.voice_off), (0, False))
        self.assertEqual(runner.client_option_args(s), [])
        argv, env = runner.apply_game_options(s, ["game.exe"], {})
        self.assertNotIn("DXVK_FRAME_RATE", env)
        s.fps_limit, s.voice_off = 60, True
        self.assertEqual(runner.client_option_args(s, safe=True), ["--voiceoff", "--safe"])
        _, env = runner.apply_game_options(s, ["game.exe"], {})
        self.assertEqual(env["DXVK_FRAME_RATE"], "60")
        _, env = runner.apply_game_options(s, ["game.exe"], {"DXVK_FRAME_RATE": "30"})
        self.assertEqual(env["DXVK_FRAME_RATE"], "30")  # the user's own environment variable wins
        with tempfile.TemporaryDirectory() as d:
            s.documents_dir = d
            self.assertIsNone(runner.backup_preferences(s))
            (Path(d) / "UserPreferences.ini").write_text("[Render]\nGraphicsCore=D3D11\n")
            b = runner.backup_preferences(s)
            self.assertTrue(b.name.startswith("UserPreferences.ini.before-safe-mode-"))
            self.assertEqual(b.read_text(), "[Render]\nGraphicsCore=D3D11\n")

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
                s = Settings(opt_gamescope=True, gamescope_args="-W 2560", opt_gamemode=True, opt_mangohud=True,
                             opt_dxvk_hud=True, opt_proton_wayland=True)
                argv, env = runner.apply_game_options(s, ["umu-run", "game.exe"], {})
                self.assertEqual(argv, [f"{d}/gamescope", "-f", "-W", "2560", "--", f"{d}/gamemoderun",
                                        "umu-run", "game.exe"])
                self.assertEqual((env["MANGOHUD"], env["DXVK_HUD"], env["PROTON_ENABLE_WAYLAND"]), ("1", "fps", "1"))
                self.assertEqual(runner.apply_game_options(Settings(), ["x"], {}), (["x"], {}))
                # vkBasalt inside gamescope: gamescope clears ENABLE_VKBASALT, so it's set again after '--'
                with mock.patch("mithlond.effects.vkbasalt_installed", lambda: True), \
                        mock.patch("mithlond.effects.CONFIG_DIR", Path(d)), \
                        mock.patch("mithlond.effects.VKBASALT_CONF", Path(d) / "vkb.conf"):
                    argv, env = runner.apply_game_options(Settings(opt_gamescope=True, vkb_enabled=True),
                                                          ["umu-run", "game.exe"], {})
                i = argv.index("--")
                self.assertEqual(argv[i + 1:i + 3], ["env", "ENABLE_VKBASALT=1"])
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


class SelfUpdateTests(unittest.TestCase):
    def _serve(self, payload: bytes):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_port}/Mithlond-9.9.9-x86_64.AppImage"

    def _release(self, url, payload, sha=None):
        import hashlib
        from mithlond import selfupdate
        return selfupdate.Release("9.9.9", "v9.9.9", "notes", "https://example/rel", "Mithlond-9.9.9-x86_64.AppImage",
                                  url, len(payload), sha if sha is not None else hashlib.sha256(payload).hexdigest())

    def test_parse_and_compare(self):
        from mithlond import selfupdate
        data = {"tag_name": "v1.4.0", "body": "**new**", "html_url": "https://github.com/x/releases/tag/v1.4.0",
                "assets": [{"name": "Mithlond-1.4.0-aarch64.AppImage", "browser_download_url": "a", "size": 1},
                           {"name": f"Mithlond-1.4.0-{selfupdate.arch()}.AppImage", "browser_download_url": "u",
                            "size": 42, "digest": "sha256:abc"}]}
        r = selfupdate.parse_release(data)
        self.assertEqual((r.version, r.asset_url, r.asset_size, r.sha256), ("1.4.0", "u", 42, "abc"))
        self.assertTrue(selfupdate.is_newer("1.4.0", "1.3.0"))
        self.assertTrue(selfupdate.is_newer("1.10.0", "1.9.9"))
        self.assertFalse(selfupdate.is_newer("1.3.0", "1.3.0"))
        self.assertFalse(selfupdate.is_newer("1.2.9", "1.3.0"))
        self.assertIsNone(selfupdate.parse_release({"tag_name": "v2", "assets": []}).asset_url)

    def test_update_replaces_appimage(self):
        from mithlond import selfupdate
        payload = b"\x7fELF" + b"\x02\x01\x01\x00" + b"AI\x02" + b"x" * 5000
        url = self._serve(payload)
        with tempfile.TemporaryDirectory() as d:
            cur = Path(d) / "Mithlond-1.3.0-x86_64.AppImage"
            cur.write_bytes(b"old")
            new = selfupdate.update(self._release(url, payload), current=cur)
            self.assertEqual(new, Path(d) / "Mithlond-9.9.9-x86_64.AppImage")
            self.assertEqual(new.read_bytes(), payload)
            self.assertTrue(os.access(new, os.X_OK))
            self.assertFalse(cur.exists())
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["Mithlond-9.9.9-x86_64.AppImage"])

    def test_update_rejects_bad_downloads(self):
        from mithlond import selfupdate
        good = b"\x7fELF" + b"\x02\x01\x01\x00" + b"AI\x02" + b"x" * 100
        cases = [("checksum", good, "0" * 64), ("not an AppImage", b"<html>error</html>", None)]
        for label, payload, sha in cases:
            with self.subTest(label), tempfile.TemporaryDirectory() as d:
                url = self._serve(payload)
                cur = Path(d) / "Mithlond-1.3.0-x86_64.AppImage"
                cur.write_bytes(b"old")
                with self.assertRaises(selfupdate.UpdateError):
                    selfupdate.update(self._release(url, payload, sha), current=cur)
                self.assertEqual(cur.read_bytes(), b"old")  # current version untouched
                self.assertEqual([p.name for p in Path(d).iterdir()], [cur.name])  # no partial files left
        with tempfile.TemporaryDirectory() as d:  # truncated download
            url = self._serve(good)
            cur = Path(d) / "M.AppImage"
            cur.write_bytes(b"old")
            rel = self._release(url, good)
            rel.asset_size += 10
            with self.assertRaises(selfupdate.UpdateError):
                selfupdate.update(rel, current=cur)
            self.assertTrue(cur.exists())

    def test_can_self_update(self):
        from mithlond import selfupdate
        old = os.environ.pop("APPIMAGE", None)
        try:
            self.assertFalse(selfupdate.can_self_update()[0])
            with tempfile.TemporaryDirectory() as d:
                f = Path(d) / "M.AppImage"
                f.write_bytes(b"x")
                os.environ["APPIMAGE"] = str(f)
                self.assertEqual(selfupdate.running_appimage(), f)
                self.assertTrue(selfupdate.can_self_update()[0])
        finally:
            os.environ.pop("APPIMAGE", None)
            if old:
                os.environ["APPIMAGE"] = old


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


SAMPLE_PREFS = (
    "[Launcher]\r\nGameClientType=1\r\n\r\n[User_1]\r\nUserName=someone\r\nWorldName_1=Glamdring\r\n\r\n"
    "[Display]\r\nResolution=1920x1080\r\nScreenMode=FullScreen\r\nSyncToRefresh=False\r\n"
    "WindowedResolution=122029088\r\n\r\n[Render]\r\nTextureDetail=VeryHigh\r\nBrightness=1.00\r\n"
    "ShadowMapQuality=3\r\nMeasuredFillRate=77121.31\r\n\r\n[Sound]\r\nMasterVolume=0.10\r\n"
    "\r\n[Voice]\r\nDeviceCapture=ABC\r\n\r\n[NewSection]\r\nSomethingNew=True\r\nOddValue=x y\r\n")


class GamePrefsTests(unittest.TestCase):
    def test_read_visible_save(self):
        from mithlond import gameprefs as g
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "UserPreferences.ini"
            f.write_bytes(SAMPLE_PREFS.encode())
            values = g.read(f)
            self.assertEqual(values["Display.Resolution"], "1920x1080")
            shown = {p.id: p for p in g.visible(values)}
            for hid in ("Launcher.GameClientType", "User_1.UserName", "User_1.WorldName_1", "Voice.DeviceCapture",
                        "Render.MeasuredFillRate", "Display.WindowedResolution"):
                self.assertNotIn(hid, shown)
            self.assertEqual(shown["Render.TextureDetail"].category, "Detail")
            self.assertEqual(shown["Sound.MasterVolume"].kind, "volume")
            self.assertEqual((shown["NewSection.SomethingNew"].category, shown["NewSection.SomethingNew"].kind),
                             ("Other", "bool"))  # unknown settings still show up
            self.assertEqual(shown["NewSection.OddValue"].kind, "text")
            self.assertEqual(g.format_value(shown["Sound.MasterVolume"], 0.5), "0.50")
            self.assertEqual([g.pretty(v) for v in ("VeryHigh", "FullScreenWindowed", "16x9", "1920x1080", "D3D11")],
                             ["Very High", "Full screen (borderless window)", "16:9", "1920x1080", "DirectX 11"])
            self.assertIsNone(g.save(f, {}))
            b = g.save(f, {"Display.ScreenMode": "Windowed", "Sound.MasterVolume": "0.50"})
            self.assertEqual(b.read_bytes(), SAMPLE_PREFS.encode())  # backup = previous version
            new = f.read_bytes().decode()
            self.assertIn("ScreenMode=Windowed\r\n", new)
            self.assertIn("MasterVolume=0.50\r\n", new)
            self.assertIn("UserName=someone\r\n", new)  # untouched
            self.assertEqual(new.count("\r\n"), SAMPLE_PREFS.count("\r\n"))
            self.assertEqual(g.latest_backup(f), b)

    def test_presets(self):
        from mithlond import gameprefs as g
        for name in g.PRESET_NAMES:
            values = g.preset(name)
            self.assertTrue(all(k in g.BY_ID for k in values))
            self.assertFalse([k for k in values if not k.startswith("Render.")])  # display/sound/UI untouched
            for k, v in values.items():
                p = g.BY_ID[k]
                if p.kind == "choice" and not p.editable:
                    self.assertIn(v, p.choices, k)
        self.assertEqual(g.preset("Very Low")["Render.TextureDetail"], "VeryLow")
        self.assertEqual(g.preset("Very High")["Render.ModelDetail"], "UltraHigh")
        self.assertEqual(g.preset("High", {"Render.TextureDetail": "x"}), {"Render.TextureDetail": "High"})

    def test_tab(self):
        from PySide6.QtWidgets import QApplication
        from mithlond import procs
        from mithlond.ui.context import AppContext
        from mithlond.ui.game_settings_tab import GameSettingsTab
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(procs, "game_clients", lambda: []):
            (Path(d) / "UserPreferences.ini").write_bytes(SAMPLE_PREFS.encode())
            tab = GameSettingsTab(AppContext(Settings(documents_dir=d)))
            titles = [tab.nav.item(i).text() for i in range(tab.nav.count())]
            self.assertEqual(titles, ["Display (4)", "Detail (1)", "Shadows (1)", "Sound (1)", "Other (2)"])
            self.assertEqual(len(tab.groups), 5)
            shown_boxes = lambda: [c for c, (box, _f, _x) in tab.groups.items() if not box.isHidden()]
            self.assertEqual(shown_boxes(), ["Display"])  # only the selected category
            tab.nav.setCurrentRow(3)
            self.assertEqual(shown_boxes(), ["Sound"])
            # live search: every typed word must match the name, file key, category or description
            visible = lambda: [tab.nav.item(i).text() for i in range(tab.nav.count()) if not tab.nav.item(i).isHidden()]
            tab.search.setText("volume")
            self.assertEqual(visible(), ["Sound (1)"])
            self.assertEqual(shown_boxes(), ["Sound"])
            tab.search.setText("screen mode")  # the selected category has no match: the first that does is shown
            self.assertEqual(shown_boxes(), ["Display"])
            tab.search.setText("")
            tab.nav.setCurrentRow(0)
            tab.search.setText("e")  # several categories match: the selection stays, filtered
            self.assertEqual(shown_boxes(), ["Display"])
            tab.search.setText("volume")
            tab.search.setText("screen mode")
            self.assertEqual(visible(), ["Display (1)"])
            tab.search.setText("MasterVolume")  # the name in the file works too
            self.assertEqual(visible(), ["Sound (1)"])
            tab.search.setText("zzz")
            self.assertEqual(visible(), [])
            self.assertFalse(tab.no_match.isHidden())
            tab.search.clear()
            self.assertEqual(len(visible()), 5)
            field = next(f for f in tab.fields if f.pref.id == "Display.ScreenMode")
            self.assertFalse(tab.save_btn.isEnabled())
            self.assertEqual(field.widget.currentText(), "Full screen")  # shown readable
            field.widget.setCurrentIndex(field.widget.findData("Windowed"))
            self.assertTrue(field.label.font().bold())
            self.assertTrue(tab.save_btn.isEnabled())
            vol = next(f for f in tab.fields if f.pref.id == "Sound.MasterVolume")
            self.assertEqual(vol.current(), "0.10")
            tab.save()
            self.assertIn("ScreenMode=Windowed", (Path(d) / "UserPreferences.ini").read_text())
            tab._apply_preset(1)  # Very Low: filled in, not saved yet
            tex = next(f for f in tab.fields if f.pref.id == "Render.TextureDetail")
            self.assertEqual(tex.current(), "VeryLow")
            self.assertTrue(tex.label.font().bold())
            self.assertIn("TextureDetail=VeryHigh", (Path(d) / "UserPreferences.ini").read_text())
            self.assertEqual(next(f for f in tab.fields if f.pref.id == "Render.ShadowMapQuality").current(), "0")
            tab.save()
            self.assertIn("TextureDetail=VeryLow", (Path(d) / "UserPreferences.ini").read_text())
            self.assertTrue(tab.restore_btn.isEnabled())
            self.assertFalse(tab._timer.isActive())  # never shown: no process polling
            tab.show()
            self.assertTrue(tab._timer.isActive())
            tab.hide()
            self.assertFalse(tab._timer.isActive())
            with mock.patch.object(procs, "game_clients", lambda: ["game"]):
                tab._check_game()
                self.assertFalse(tab.save_btn.isEnabled())
                self.assertFalse(tab.restore_btn.isEnabled())
            tab._timer.stop()
            tab.deleteLater()  # destroy the widgets now, not during interpreter shutdown (segfault)
            app.processEvents()


class EffectsTests(unittest.TestCase):
    def test_gamescope_args(self):
        from mithlond import effects
        s = Settings()
        self.assertEqual(effects.gamescope_args(s), ["-f"])  # defaults: fullscreen only
        s.gs_render, s.gs_filter, s.gs_sharpness = "quality", "fsr", 3
        self.assertEqual(effects.gamescope_args(s, (2560, 1440)),
                         ["-W", "2560", "-H", "1440", "-w", "1706", "-h", "960", "-F", "fsr", "--sharpness", "3", "-f"])
        s.gs_output_w, s.gs_output_h = 3840, 2160
        s.gs_render = "performance"
        self.assertEqual(effects.gamescope_args(s, (1920, 1080))[:8], ["-W", "3840", "-H", "2160", "-w", "1920", "-h", "1080"])
        s = Settings(gs_render="custom", gs_render_w=1280, gs_render_h=720, gs_filter="nis", gs_scaler="fit",
                     gs_refresh=60, gs_unfocused_refresh=15, gs_fullscreen=False, gs_borderless=True,
                     gs_adaptive_sync=True, gs_hdr=True, gs_hdr_itm=True, gs_mangoapp=True, gs_grab_keyboard=True,
                     gs_force_grab_cursor=True, gamescope_args="--rt")
        self.assertEqual(effects.gamescope_args(s), [
            "-w", "1280", "-h", "720", "-F", "nis", "--sharpness", "5", "-S", "fit", "-r", "60", "-o", "15", "-b",
            "-g", "--force-grab-cursor", "--adaptive-sync", "--mangoapp", "--hdr-enabled", "--hdr-itm-enabled", "--rt"])
        s.gs_hdr = False  # inverse tone mapping only with HDR output
        self.assertNotIn("--hdr-itm-enabled", effects.gamescope_args(s))

    def test_vkbasalt_and_dxvk_config(self):
        from mithlond import effects
        with tempfile.TemporaryDirectory() as d:
            shaders = Path(d) / "Shaders"
            shaders.mkdir()
            (shaders / "Vibrance.fx").write_text("")
            s = Settings(vkb_enabled=True, vkb_cas=True, vkb_smaa=True, vkb_cas_sharpness=0.6,
                         vkb_reshade_dir=d, vkb_reshade_effects="Vibrance Missing")
            self.assertEqual(effects.vkbasalt_effects(s), ["smaa", "cas", "Vibrance"])  # AA before sharpening
            conf = effects.vkbasalt_config(s)
            self.assertIn("effects = smaa:cas:Vibrance\n", conf)
            self.assertIn("casSharpness = 0.60\n", conf)
            self.assertIn(f'Vibrance = "{shaders / "Vibrance.fx"}"', conf)
            self.assertIn(f'reshadeIncludePath = "{shaders}"', conf)
        s = Settings()
        self.assertEqual(effects.dxvk_options(s), {})
        s = Settings(dxvk_aniso=16, dxvk_lod_bias=-0.5, dxvk_latency=1, dxvk_vsync="off", dxvk_tearfree="True")
        o = effects.dxvk_options(s)
        self.assertEqual((o["d3d11.samplerAnisotropy"], o["d3d9.samplerAnisotropy"], o["d3d11.samplerLodBias"],
                          o["dxgi.maxFrameLatency"], o["dxgi.syncInterval"], o["d3d9.presentInterval"],
                          o["dxvk.tearFree"]), ("16", "16", "-0.50", "1", "0", "0", "True"))

    def test_apply_env(self):
        from mithlond import effects
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(effects, "CONFIG_DIR", Path(d)), \
                mock.patch.object(effects, "VKBASALT_CONF", Path(d) / "vkBasalt.conf"), \
                mock.patch.object(effects, "DXVK_CONF", Path(d) / "dxvk.conf"):
            env = {}
            self.assertEqual(effects.apply_env(Settings(), env), [])
            self.assertEqual(env, {})  # nothing set: nothing written
            s = Settings(vkb_enabled=True, dxvk_aniso=16)
            with mock.patch.object(effects, "vkbasalt_installed", lambda: False):
                notes = effects.apply_env(s, env)
            self.assertNotIn("ENABLE_VKBASALT", env)
            self.assertIn("not installed", notes[0])
            env = {}
            with mock.patch.object(effects, "vkbasalt_installed", lambda: True):
                effects.apply_env(s, env)
            self.assertEqual((env["ENABLE_VKBASALT"], env["VKBASALT_CONFIG_FILE"], env["DXVK_CONFIG_FILE"]),
                             ("1", f"{d}/vkBasalt.conf", f"{d}/dxvk.conf"))
            self.assertIn("d3d11.samplerAnisotropy = 16", (Path(d) / "dxvk.conf").read_text())

    def test_old_gamescope_f_migrates(self):
        from mithlond import config
        s = Settings(gamescope_args="-f")
        config.autodetect(s)
        self.assertEqual((s.gamescope_args, s.gs_fullscreen), ("", True))

    def test_presets(self):
        from mithlond import effects
        s = Settings()
        v = effects.apply_preset(s, "Very Low", gamescope_installed=True)
        self.assertEqual((s.opt_gamescope, s.gs_render, s.gs_filter, s.vkb_enabled, s.vkb_cas, s.dxvk_latency),
                         (True, "performance", "fsr", True, True, 1))
        self.assertIn("-F", effects.gamescope_args(s, (1920, 1080)))
        s = Settings()
        v = effects.apply_preset(s, "Low", gamescope_installed=False)  # no gamescope: no upscaling part
        self.assertFalse(any(k.startswith("gs_") or k == "opt_gamescope" for k in v))
        self.assertFalse(s.opt_gamescope)
        effects.apply_preset(s, "Very High", gamescope_installed=True)
        self.assertEqual((s.opt_gamescope, s.vkb_smaa, s.vkb_smaa_edge, s.dxvk_aniso), (False, True, "color", 16))
        self.assertEqual(effects.vkbasalt_effects(s), ["smaa", "cas"])

    def test_tab(self):
        from PySide6.QtWidgets import QApplication
        from mithlond.ui.context import AppContext
        from mithlond.ui.effects_tab import VisualEffectsTab
        app = QApplication.instance() or QApplication([])
        ctx = AppContext(Settings())
        tab = VisualEffectsTab(ctx)
        nav = [tab.page.nav.item(i).text() for i in range(tab.page.nav.count())]
        self.assertEqual(nav, ["Sharpening & antialiasing", "Upscaling & display", "DXVK"])
        tab.page.search.setText("fsr")
        self.assertEqual([tab.page.nav.item(i).text() for i in range(tab.page.nav.count())
                          if not tab.page.nav.item(i).isHidden()], ["Upscaling & display"])
        tab.page.search.clear()
        self.assertIn("gamescope -f -- <game>", tab.gs_preview.text())
        tab.page.select("DXVK")
        with mock.patch.object(ctx, "save"):
            tab._apply_preset(4)  # High: applied and saved right away, page rebuilt
        self.assertEqual((ctx.settings.vkb_smaa, ctx.settings.dxvk_aniso), (True, 16))
        self.assertEqual(tab.page.sections[tab.page.nav.currentRow()][0], "DXVK")  # same category still open
        tab.deleteLater()
        app.processEvents()


SAMPLE_LAYOUT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\r\n<UI>\r\n\r\n  <Version Value="1.0"/>\r\n\r\n'
    '  <Aliases/>\r\n\r\n  <Layouts>\r\n    <Layout ID="0x22000012">\r\n'
    '      <Element Height="0.307407" ID="NewChatWindow1" Width="0.227604" X="-0.000260" Y="0.692130"/>\r\n'
    '      <Element Height="0.050000" ID="GamePlay_QuestTrackerBox" Width="0.200000" X="0.790000" Y="0.300000"/>\r\n'
    '    </Layout>\r\n    <Layout ID="0x220008A2">\r\n'
    '      <Element Height="0.458333" ID="Vendor_Window" Width="0.335938" X="0.004948" Y="0.106019"/>\r\n'
    '    </Layout>\r\n  </Layouts>\r\n\r\n  <Options>\r\n'
    '    <Option Name="AcceptDuels" Value="True"/>\r\n    <Option Name="ChatUIScale" Value="1.000000"/>\r\n'
    '    <Option Name="QuestGuideColor1" Value="0.816 0.243 0.176 1.000"/>\r\n'
    '    <Option Name="ShowVitalsAsPercentage" Value="CurrentAndMax"/>\r\n  </Options>\r\n\r\n  <ChatColors>\r\n'
    '    <ChatFont Color="1.000 0.322 0.322 1.000" Size="Medium" TextType="Tell"/>\r\n'
    '    <ChatFont Color="1.000 0.000 0.000 1.000" Size="Medium" TextType="CombatEnemy"/>\r\n'
    '  </ChatColors>\r\n\r\n</UI>\r\n')


class UILayoutTests(unittest.TestCase):
    def _docs(self, d):
        lay = Path(d) / "ui" / "layouts"
        lay.mkdir(parents=True)
        (lay / "main.layout").write_bytes(SAMPLE_LAYOUT.encode())
        return Path(d), lay / "main.layout"

    def test_read_save_files(self):
        import copy
        from mithlond import uilayout as u
        with tempfile.TemporaryDirectory() as d:
            docs, f = self._docs(d)
            self.assertEqual([p.name for p in u.list_layouts(docs)], ["main.layout"])
            orig = u.read(f)
            self.assertEqual((len(orig.windows), len(orig.options), len(orig.chat)), (3, 4, 2))
            self.assertEqual([w.name for w in orig.windows], ["Chat Window 1", "Quest Tracker", "Vendor"])
            self.assertEqual([w.hud for w in orig.windows], [True, True, False])
            self.assertIsNone(u.save(orig, copy.deepcopy(orig)))  # nothing changed: file untouched
            self.assertEqual(f.read_bytes(), SAMPLE_LAYOUT.encode())
            ed = copy.deepcopy(orig)
            ed.windows[1].x, ed.windows[1].h = 0.5, 0.25
            ed.options["AcceptDuels"] = "False"
            ed.chat[0].color, ed.chat[0].size = (0.0, 0.5, 1.0, 1.0), "Large"
            b = u.save(orig, ed)
            self.assertEqual(b.read_bytes(), SAMPLE_LAYOUT.encode())
            new = f.read_bytes().decode()
            self.assertIn('<Element Height="0.250000" ID="GamePlay_QuestTrackerBox" Width="0.200000" X="0.500000" '
                          'Y="0.300000"/>\r\n', new)
            self.assertIn('<Option Name="AcceptDuels" Value="False"/>', new)
            self.assertIn('<ChatFont Color="0.000 0.500 1.000 1.000" Size="Large" TextType="Tell"/>', new)
            changed = [a for a, b2 in zip(SAMPLE_LAYOUT.split("\r\n"), new.split("\r\n")) if a != b2]
            self.assertEqual(len(changed), 3)
            self.assertEqual(new.count("\r\n"), SAMPLE_LAYOUT.count("\r\n"))
            self.assertEqual(u.latest_backup(f), b)
            self.assertTrue(u.valid_name("raid_ui-2") and not u.valid_name("my layout"))
            c = u.copy_layout(f, "raid")
            r = u.rename_layout(c, "raid2")
            self.assertEqual(sorted(p.stem for p in u.list_layouts(docs)), ["main", "raid2"])
            kept = u.delete_layout(r)
            self.assertTrue(kept.exists() and not r.exists())
            self.assertEqual(u.pretty_chat("Guild"), "Kinship")
            self.assertEqual(u.pretty_chat("UserChat3"), "User channel 3")
            self.assertEqual(u.option_group("AcceptDuels"), "Social")
            self.assertEqual(u.option_group("ChatUIScale"), "Chat")

    def test_tab(self):
        from PySide6.QtWidgets import QApplication
        from mithlond.ui.context import AppContext
        from mithlond.ui.layout_tab import LayoutTab
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as d:
            docs, f = self._docs(d)
            tab = LayoutTab(AppContext(Settings(documents_dir=str(docs))))
            self.assertEqual(tab.files.currentText(), "main")
            self.assertIn("/ui layout load main", tab.hint.text())
            ed = tab.windows
            shown = [i for i in ed.items.values() if i.isVisible()]
            self.assertEqual(sorted(i.win.id for i in shown), ["GamePlay_QuestTrackerBox", "NewChatWindow1"])  # core HUD
            ed._tick_listed(False)
            self.assertFalse(any(i.isVisible() for i in ed.items.values()))
            ed.hud_only.setChecked(False)
            ed._tick_listed(True)
            self.assertTrue(all(i.isVisible() for i in ed.items.values()))
            self.assertFalse(tab.save_btn.isEnabled())
            chat = ed.items["NewChatWindow1"]
            sw, sh = ed.screen_size
            chat.set_pixels(100, 200, 400, 300)  # as if dragged/resized or typed
            self.assertAlmostEqual(chat.win.x, round(100 / sw, 6))
            self.assertAlmostEqual(chat.win.h, round(300 / sh, 6))
            self.assertTrue(tab.save_btn.isEnabled())
            tab.edited.options["AcceptDuels"] = "False"
            tab.edited.chat[1].size = "XLarge"
            tab._changed()
            self.assertIn("3 changes", tab.state.text())
            tab.save()
            text = f.read_text()
            self.assertIn('Value="False"', text)
            self.assertIn('Size="XLarge" TextType="CombatEnemy"', text)
            self.assertIn(f'X="{100 / sw:.6f}"', text)
            self.assertTrue(tab.restore_btn.isEnabled())
            with mock.patch("mithlond.ui.layout_tab.QMessageBox.question", return_value=QMessageBoxYes()):
                tab.restore()
            self.assertEqual(f.read_bytes(), SAMPLE_LAYOUT.encode())
            tab.deleteLater()
            app.processEvents()


def QMessageBoxYes():
    from PySide6.QtWidgets import QMessageBox
    return QMessageBox.Yes


class LayoutTests(unittest.TestCase):
    def test_settings_sections_and_music_tools(self):
        from PySide6.QtWidgets import QApplication
        from mithlond.ui.context import AppContext
        from mithlond.ui.settings_tab import SettingsTab
        from mithlond.ui.songs_tab import SongsTab
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as d:
            ctx = AppContext(Settings(documents_dir=d))
            st = SettingsTab(ctx)
            page = st.page
            visible = lambda: [page.nav.item(i).text() for i in range(page.nav.count()) if not page.nav.item(i).isHidden()]
            self.assertEqual(visible(), ["Locations", "Runner & Prefix", "Game options", "Game", "About & updates"])
            boxes = lambda: [t for t, b in page.sections if not b.isHidden()]
            self.assertEqual(boxes(), ["Locations"])  # only the selected category
            page.select("Game")
            self.assertEqual(boxes(), ["Game"])
            page.search.setText("gamescope")
            self.assertEqual(visible(), ["Game options"])
            self.assertEqual(boxes(), ["Game options"])
            page.search.setText("language")
            self.assertEqual(visible(), ["Game"])
            page.search.setText("check for updates")
            self.assertEqual(visible(), ["About & updates"])
            page.search.setText("zzzz")
            self.assertEqual(visible(), [])
            self.assertFalse(page.no_match.isHidden())
            page.search.clear()
            self.assertEqual(len(visible()), 5)
            mt = SongsTab(ctx)
            self.assertFalse(mt.tools_section.toggle.isChecked())  # collapsed by default
            self.assertTrue(mt.tools_section.content.isHidden())
            mt.tools_section.toggle.click()
            self.assertFalse(mt.tools_section.content.isHidden())
            for w in (st, mt):
                w.deleteLater()
            app.processEvents()


class DiagnosticsTests(unittest.TestCase):
    def test_redaction(self):
        from mithlond import diagnostics
        from mithlond.config import Account
        s = Settings(accounts=[Account("FrodoBaggins")], last_account="FrodoBaggins")
        r = diagnostics.Redactor(s)
        home = str(diagnostics.HOME)
        text = (f"Logging in as FrodoBaggins to Sting\n{home}/Games/x\n"
                "lotroclient64.exe -a 3AB9CD -h 1.2.3.4:9004 --glsticketdirect wOjh5eij3m7HQ2AES0bw/x+== --chatserver x\n"
                "Command: ['Z:\\x\\lotroclient64.exe', '-a', 'M4YX', '--glsticketdirect', 'abc']\n"
                "mail me at someone@example.com\n" + "Z" * 60 + "\nticket=secret123\n")
        out = r(text)
        for secret in ("FrodoBaggins", home, "3AB9CD", "wOjh5eij3m7HQ2AES0bw", "M4YX", "someone@example.com",
                       "Z" * 60, "secret123"):
            self.assertNotIn(secret, out)
        self.assertIn("Logging in as <account> to Sting", out)
        self.assertIn("~/Games/x", out)
        self.assertIn("Command: <removed", out)

    def test_export_zip(self):
        import zipfile
        from mithlond import diagnostics, logfile
        from mithlond.config import Account
        with tempfile.TemporaryDirectory() as d:
            docs = Path(d) / "docs"
            docs.mkdir()
            (docs / "UserPreferences.ini").write_text("[User_1]\nUserName=FrodoBaggins\n[Display]\nResolution=1920x1080\n")
            s = Settings(accounts=[Account("FrodoBaggins")], last_account="FrodoBaggins", documents_dir=str(docs))
            s.save()
            logfile.write("Logging in as FrodoBaggins with --glsticketdirect ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl0123")
            with mock.patch.object(diagnostics, "_run", lambda argv, timeout=10: "tool 1.0"):
                z = diagnostics.export(s, Path(d) / "out.zip")
            names = zipfile.ZipFile(z).namelist()
            for n in ("README.txt", "summary.txt", "mithlond.log", "settings.json", "game/UserPreferences.txt",
                      "plugins.txt"):
                self.assertIn(n, names)
            everything = "".join(zipfile.ZipFile(z).read(n).decode() for n in names)
            self.assertNotIn("FrodoBaggins", everything)
            self.assertNotIn("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl0123", everything)
            self.assertIn("Display.Resolution = 1920x1080", everything)
            self.assertNotIn("User_1", zipfile.ZipFile(z).read("game/UserPreferences.txt").decode())
            self.assertIn("Mithlond", zipfile.ZipFile(z).read("summary.txt").decode())

    def test_logfile(self):
        import sys
        from mithlond import logfile
        logfile.write("hello")
        logfile.detail("Background task failed: X", "Traceback\n  line 1")
        text = logfile.LOG.read_text()
        self.assertRegex(text, r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d hello")
        self.assertIn("    Traceback\n      line 1", text)
        old_hook = sys.excepthook
        logfile.install_crash_hooks()
        try:
            with mock.patch("sys.__excepthook__"):
                try:
                    raise ValueError("boom")
                except ValueError:
                    with mock.patch.object(sys, "stderr"):
                        sys.excepthook(*sys.exc_info())
        finally:
            sys.excepthook = old_hook
        self.assertIn("CRASH: ValueError: boom", logfile.LOG.read_text())
        # rotation when the file is too big at the next start
        logfile._fh.close()
        logfile._fh = None
        with mock.patch.object(logfile, "MAX_BYTES", 10):
            logfile.write("after rotation")
        self.assertTrue(logfile.LOG.with_name("mithlond.log.1").exists())
        self.assertIn("after rotation", logfile.LOG.read_text())


class DesktopEntryTests(unittest.TestCase):
    def test_finished_task_after_window_closed(self):
        from mithlond.ui import workers
        gone = mock.Mock(emit=mock.Mock(side_effect=RuntimeError("Signal source has been deleted")))
        sig = mock.Mock(done=gone, error=gone, progress=gone)
        workers._Task(lambda: 42, sig, False).run()  # must not raise
        workers._Task(lambda: 1 / 0, sig, False).run()
        self.assertEqual(gone.emit.call_count, 2)

    def test_entry_follows_the_appimage(self):
        from mithlond import desktopentry as de
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"XDG_DATA_HOME": d}):
            old = Path(d) / "My Games" / "Mithlond-1.4.6-x86_64.AppImage"
            new = Path(d) / "My Games" / "Mithlond-1.4.7-x86_64.AppImage"
            self.assertIsNone(de.target())
            self.assertFalse(de.refresh(new))  # no entry yet: nothing is created behind the user's back
            entry = de.install(old)
            self.assertEqual(entry, Path(d) / "applications/mithlond.desktop")
            text = entry.read_text()
            self.assertIn(f'Exec="{old}"', text)
            self.assertIn("Icon=mithlond", text)
            self.assertTrue(de.icon_path().read_bytes().startswith(b"<"))
            self.assertEqual(de.target(), old)
            self.assertFalse(de.refresh(old))  # already right
            self.assertTrue(de.refresh(new))   # after an update / a move
            self.assertEqual(de.target(), new)
            self.assertEqual(de._quote(Path('/a b/$x"y`z\\w')), '"/a b/\\$x\\"y\\`z\\\\w"')
            entry.write_text("[Desktop Entry]\nExec=/somewhere/else\n")  # someone else's entry
            self.assertIsNone(de.target())
            self.assertFalse(de.refresh(new))
            self.assertEqual(entry.read_text(), "[Desktop Entry]\nExec=/somewhere/else\n")


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

    def test_selinux_execmod(self):
        from mithlond import config
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertIsNone(config.selinux_problem(root / "missing"))  # no SELinux
            (root / "booleans").mkdir()
            (root / "enforce").write_text("1")
            (root / "booleans/selinuxuser_execmod").write_text("0 0")
            self.assertIn("setsebool -P selinuxuser_execmod 1", config.selinux_problem(root))
            (root / "booleans/selinuxuser_execmod").write_text("1 1")
            self.assertIsNone(config.selinux_problem(root))
            (root / "booleans/selinuxuser_execmod").write_text("0 0")
            (root / "enforce").write_text("0")  # permissive: Wine works
            self.assertIsNone(config.selinux_problem(root))

    def test_faugus_flatpak_without_wine(self):
        """A Faugus Flatpak user with no system Wine: Proton via the bundled umu, in Faugus's LOTRO prefix."""
        from mithlond import config
        with tempfile.TemporaryDirectory() as d, fake_bundled_umu(d) as umu:
            home = Path(d) / "home"
            flat = home / ".var/app/io.github.Faugus.faugus-launcher/data/faugus-launcher"
            flat.mkdir(parents=True)
            (flat / "umu-run").write_text("#!/usr/bin/env python3\n")
            pfx = home / "Faugus" / "lotro"
            pfx.mkdir(parents=True)
            compat = home / ".local/share/Steam/compatibilitytools.d"
            for name in ("GE-Proton10-1", "Proton-CachyOS Latest"):
                (compat / name).mkdir(parents=True)
                (compat / name / "proton").write_text("")
            (flat / "games.json").write_text(json.dumps([
                {"title": "Other", "path": "/x/other.exe", "prefix": str(home / "Faugus/default"), "runner": ""},
                {"title": "LOTRO", "path": "/games/lotro/LotroLauncher.exe", "prefix": str(pfx),
                 "runner": "Proton-CachyOS Latest", "last_played": "2026-11-10"},
            ]))
            dirs = (home / ".local/share/faugus-launcher", flat)
            with mock.patch.object(config, "FAUGUS_DATA_DIRS", dirs), \
                    mock.patch.object(config, "COMPAT_DIRS", (compat,)), \
                    mock.patch.object(config, "HOME", home), \
                    mock.patch.object(config.shutil, "which", lambda *_: None):
                self.assertEqual(config.detect_umu_run(), str(flat / "umu-run"))  # Faugus Flatpak's own
                self.assertEqual(config.umu_command(), [sys.executable, "-I", str(umu)])  # bundled wins
                s = Settings(runner="wine")  # saved by Mithlond <= 1.4.2, whose default was system Wine
                notes = config.autodetect(s)
                self.assertEqual((s.runner, s.wine_prefix), ("umu", str(pfx)))
                self.assertEqual(s.proton_path, str(compat / "Proton-CachyOS Latest"))  # Faugus's choice
                self.assertIn("Runner: Proton (Wine isn't installed)", notes)
                # no LOTRO documents folder anywhere yet: the usual place, so --prefs + seeding apply
                self.assertEqual(s.documents_dir, str(home / "Documents/The Lord of the Rings Online"))
                # a deliberate "umu's default" choice in an existing config is left alone
                s = Settings(runner="umu")
                Settings().save()
                config.autodetect(s)
                self.assertEqual((s.proton_path, s.wine_prefix), ("", ""))


if __name__ == "__main__":
    unittest.main()
