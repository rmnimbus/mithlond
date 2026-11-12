"""End-to-end: drive the real UI (offscreen) against a fake GLS server and a fake `wine`.

Covers world list, login (wrong + right password), login queue, client arguments, Companion
start-with-game and close-with-game. No real account or game needed.
"""

import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

os.environ["QT_QPA_PLATFORM"] = "offscreen"
_tmp_home = tempfile.mkdtemp(prefix="mithlond-e2e-")
os.environ["XDG_CONFIG_HOME"] = f"{_tmp_home}/config"
os.environ["XDG_CACHE_HOME"] = f"{_tmp_home}/cache"
os.environ["XDG_DATA_HOME"] = f"{_tmp_home}/data"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from mithlond import keystore, news  # noqa: E402
from mithlond.config import CONFIG_FILE, Settings  # noqa: E402
from mithlond.ui.context import AppContext  # noqa: E402
from mithlond.ui.main_window import MainWindow  # noqa: E402

DATA = Path(__file__).parent / "data"
STATE = {"queue_calls": 0, "login_calls": 0}


def soap(body: str) -> bytes:
    return ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/'
            f'envelope/"><soap:Body>{body}</soap:Body></soap:Envelope>').encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, data: bytes, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/xml")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path.startswith("/launcher.config.xml"):
            cfg = (DATA / "launcher.config.xml").read_text()
            cfg = cfg.replace("https://gls.lotro.com/GLS.AuthServer/LoginQueue.aspx", f"{base}/LoginQueue.aspx")
            return self._send(cfg.encode())
        if self.path.startswith("/status"):
            world = parse_qs(urlparse(self.path).query)["w"][0]
            if world == "closed":
                return self._send(b"<Status><loginservers></loginservers><queueurls></queueurls></Status>")
            return self._send(b"<Status><loginservers>10.0.0.1:9004;</loginservers><queueurls>http://q/LoginQueue;"
                              b"</queueurls><allow_billing_role>LOTROStd</allow_billing_role></Status>")
        self._send(b"", 404)

    def do_POST(self):
        base = f"http://127.0.0.1:{self.server.server_port}"
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        if self.path.startswith("/GLS.DataCenterServer"):
            worlds = "".join(
                f"<World><Name>{n}</Name><ChatServerUrl>9.9.9.9:2900</ChatServerUrl>"
                f"<StatusServerUrl>{base}/status?w={k}</StatusServerUrl><Order>{i}</Order></World>"
                for i, (n, k) in enumerate([("Glamdring", "open"), ("Closedworld", "closed")]))
            return self._send(soap(
                '<GetDatacentersResponse xmlns="http://www.turbine.com/SE/GLS"><GetDatacentersResult><Datacenter>'
                f"<Name>LOTRO</Name><Worlds>{worlds}</Worlds><AuthServer>{base}/GLS.AuthServer/Service.asmx"
                f"</AuthServer><PatchServer>patch:6015</PatchServer><LauncherConfigurationServer>{base}/launcher"
                ".config.xml</LauncherConfigurationServer></Datacenter></GetDatacentersResult>"
                "</GetDatacentersResponse>"))
        if self.path.startswith("/GLS.AuthServer"):
            STATE["login_calls"] += 1
            if "<password>right&amp;pw</password>" not in body:
                return self._send(soap("<soap:Fault><faultcode>soap:Server</faultcode><faultstring>No Subscriber "
                                       "Formal Entity was found</faultstring></soap:Fault>"), 500)
            return self._send(soap(
                '<LoginAccountResponse xmlns="http://www.turbine.com/SE/GLS"><LoginAccountResult><Subscriptions>'
                "<GameSubscription><Game>DDO</Game><Name>ddo1</Name><Description>DDO</Description>"
                "</GameSubscription><GameSubscription><Game>LOTRO</Game><Name>SUB42</Name><Description>LOTRO"
                "</Description><ProductTokens><string>LOTROStd</string></ProductTokens></GameSubscription>"
                "</Subscriptions><Ticket>TICKET+/=</Ticket></LoginAccountResult></LoginAccountResponse>"))
        if self.path.startswith("/LoginQueue.aspx"):
            q = parse_qs(body)
            assert q["ticket"] == ["TICKET+/="] and q["subscription"] == ["SUB42"], q
            assert q["queue_url"] == ["http://q/LoginQueue"], q
            STATE["queue_calls"] += 1
            serving = "0x3" if STATE["queue_calls"] == 1 else "0x5"
            return self._send(f"<Result><HResult>0x00000000</HResult><QueueNumber>0x5</QueueNumber>"
                              f"<NowServingNumber>{serving}</NowServingNumber></Result>".encode())
        self._send(b"", 404)


def wait_for(app, cond, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


class EndToEnd(unittest.TestCase):
    def test_full_launch(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_port
        root = Path(_tmp_home)
        game = root / "lotro"
        (game / "x64").mkdir(parents=True)
        (game / "lotroclient.exe").touch()
        (game / "x64" / "lotroclient64.exe").touch()
        (game / "client_local_English.dat").touch()
        (game / "lotro.launcherconfig").write_text(
            '<?xml version="1.0"?><configuration><appSettings><add key="Launcher.DataCenterService.GLS" '
            f'value="http://127.0.0.1:{port}/GLS.DataCenterServer/Service.asmx"/>'
            '<add key="DataCenter.GameName" value="LOTRO"/></appSettings></configuration>')
        comp = root / "LotRO Companion"
        comp.mkdir()
        (comp / "LotRO Companion.exe").touch()
        docs = root / "docs"
        (docs / "PluginData").mkdir(parents=True)
        log = root / "wine.log"
        fake_wine = root / "fakewine"
        fake_wine.write_text(f"#!/bin/sh\necho \"$WINEPREFIX|$*\" >> '{log}'\n"
                             "case \"$1\" in *Companion*) exec sleep 60;; *) echo client-output; sleep 4;; esac\n")
        fake_wine.chmod(0o755)

        s = Settings(game_dir=str(game), documents_dir=str(docs), runner="wine", wine_binary=str(fake_wine),
                     wine_prefix=str(root / "pfx"), companion_dir=str(comp), companion_delay=2,
                     companion_with_game=True, check_updates_on_start=False)
        s.save()
        keystore.available = lambda: False  # never touch the real keyring in tests
        news.fetch = lambda url: (news.parse_feed((DATA / "launcher-feed.xml").read_bytes()), False)
        app = QApplication.instance() or QApplication([])
        ctx = AppContext(Settings.load())
        win = MainWindow(ctx, [])
        play = win.play
        self.assertTrue(wait_for(app, lambda: play.world.count() == 2), "world list did not load")
        self.assertIn("open", play.world.itemText(0))
        self.assertIn("closed", play.world.itemText(1))
        self.assertTrue(wait_for(app, lambda: play.news.coupon is not None), "news/coupon not shown")
        self.assertEqual(play.news.coupon_code.text(), "WARMFEELING")
        self.assertIn("Sales", play.news.browser.toPlainText())

        play.account.setEditText("tester")
        play.password.setText("wrong")
        play.play.click()
        self.assertTrue(wait_for(app, lambda: not play._busy and "incorrect" in play.status.text()), play.status.text())

        play.password.setText("right&pw")
        play.play.click()
        self.assertTrue(wait_for(app, lambda: len(ctx.games) == 1), f"game not started: {play.status.text()}")
        self.assertEqual(STATE["queue_calls"], 2)
        # The timer: not started right away, started once the delay has passed.
        self.assertFalse(ctx.companion_running(), "companion started before its delay")
        self.assertTrue(wait_for(app, lambda: ctx.companion_running(), 6), "companion not started by the timer")
        self.assertTrue(wait_for(app, lambda: log.exists() and log.read_text().count("\n") >= 2))
        lines = log.read_text().splitlines()
        client = next(line for line in lines if "lotroclient64.exe" in line)
        self.assertTrue(client.startswith(f"{root / 'pfx'}|"))
        args = client.split("|", 1)[1].split()
        self.assertEqual(args[args.index("-a") + 1], "SUB42")
        self.assertEqual(args[args.index("-h") + 1], "10.0.0.1:9004")
        self.assertEqual(args[args.index("--glsticketdirect") + 1], "TICKET+/=")
        self.assertEqual(args[args.index("--chatserver") + 1], "9.9.9.9:2900")
        self.assertEqual(args[args.index("--prefs") + 1].rsplit("\\", 1)[-1], "UserPreferences.ini")
        self.assertTrue(args[args.index("--prefs") + 1].startswith("Z:"))
        self.assertTrue(any("LotRO Companion.exe" in line for line in lines))
        logtext = win.log.toPlainText()
        self.assertNotIn("TICKET+/=", logtext)
        self.assertNotIn("right&pw", logtext)
        self.assertNotIn("right&pw", CONFIG_FILE.read_text())

        # Game exits after ~1.5s -> companion is closed too.
        self.assertTrue(wait_for(app, lambda: not ctx.games), "game did not finish")
        self.assertTrue(wait_for(app, lambda: not ctx.companion_running(), 10), "companion not closed")
        self.assertEqual(Settings.load().accounts[0].world, "Glamdring")
        win.close()
        srv.shutdown()


if __name__ == "__main__":
    unittest.main()
