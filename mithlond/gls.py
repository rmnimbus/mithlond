"""The LOTRO login protocol (Turbine/SSG "GLS" services).

Flow: datacenter info -> launcher config -> LoginAccount -> world status -> login queue -> client args.
Protocol knowledge comes from OneLauncher (GPL-3.0) and the official launcher's config files.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse, urlunparse
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import requests

GLS_NS = "http://www.turbine.com/SE/GLS"
TIMEOUT = 20
USER_AGENT = "Mithlond-LOTRO-Launcher/1.0"


class GLSError(Exception):
    """A login service returned an error or something unexpected."""


class LoginFailed(GLSError):
    """Wrong username/password and similar user-fixable problems."""


class WorldUnavailable(GLSError):
    pass


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


_http = _session()


# ---- tiny namespace-agnostic XML helpers -----------------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _children(el: ET.Element | None, name: str) -> list[ET.Element]:
    return [] if el is None else [c for c in el if _local(c.tag) == name]


def _text(el: ET.Element | None, name: str, default: str = "") -> str:
    if el is None:
        return default
    c = _child(el, name)
    return (c.text or "").strip() if c is not None and c.text else default


def _find_deep(el: ET.Element, name: str) -> ET.Element | None:
    for c in el.iter():
        if _local(c.tag) == name:
            return c
    return None


# ---- data types --------------------------------------------------------------

@dataclass
class LocalLauncherConfig:
    gls_datacenter_url: str
    game_name: str  # datacenter game name, "LOTRO"


@dataclass
class World:
    name: str
    chat_server: str
    status_url: str
    order: int = 0
    language: str = ""


@dataclass
class Datacenter:
    auth_server: str
    patch_server: str
    launcher_config_url: str
    worlds: list[World]


@dataclass
class Subscription:
    game: str
    name: str
    description: str
    product_tokens: set[str] = field(default_factory=set)
    status: str = ""


@dataclass
class LoginResult:
    ticket: str
    subscriptions: list[Subscription]

    def for_game(self, game: str) -> list[Subscription]:
        return [s for s in self.subscriptions if s.game.lower() == game.lower()]


@dataclass
class WorldStatus:
    login_server: str
    queue_url: str
    allowed_roles: set[str] | None
    denied_roles: set[str] | None
    full: bool = False
    wait_hint: float = 0.0

    def allows(self, sub: Subscription) -> bool:
        if not sub.product_tokens:
            return True
        if self.allowed_roles is not None and not (self.allowed_roles & sub.product_tokens):
            return False
        if self.denied_roles and self.denied_roles & sub.product_tokens:
            return False
        return True


# ---- local config -------------------------------------------------------------

def parse_app_settings(xml_bytes: bytes) -> dict[str, str]:
    root = ET.fromstring(xml_bytes)
    out: dict[str, str] = {}
    for add in root.iter():
        if _local(add.tag) == "add" and "key" in add.attrib:
            out[add.attrib["key"]] = add.attrib.get("value", "")
    return out


def read_local_config(game_dir: Path) -> LocalLauncherConfig:
    cfgs = sorted(game_dir.glob("*.launcherconfig"))
    if not cfgs:
        raise GLSError(f"No .launcherconfig file in {game_dir}")
    d = parse_app_settings(cfgs[0].read_bytes())
    try:
        return LocalLauncherConfig(d["Launcher.DataCenterService.GLS"], d.get("DataCenter.GameName", "LOTRO"))
    except KeyError as e:
        raise GLSError(f"{cfgs[0].name} has no {e}") from e


# ---- SOAP -----------------------------------------------------------------------

def soap_call(url: str, action: str, params: dict[str, str]) -> ET.Element:
    body = "".join(f"<{k}>{escape(v)}</{k}>" for k, v in params.items())
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        f'<soap:Body><{action} xmlns="{GLS_NS}">{body}</{action}></soap:Body></soap:Envelope>'
    )
    r = _http.post(
        url,
        data=envelope.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{GLS_NS}/{action}"'},
        timeout=TIMEOUT,
    )
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        r.raise_for_status()
        raise GLSError(f"{action}: unreadable response") from e
    fault = _find_deep(root, "Fault")
    if fault is not None:
        raise GLSError(_text(fault, "faultstring") or f"{action} failed")
    r.raise_for_status()
    resp = _find_deep(root, f"{action}Response")
    if resp is None:
        raise GLSError(f"{action}: response missing")
    return resp


def get_datacenter(local: LocalLauncherConfig) -> Datacenter:
    resp = soap_call(local.gls_datacenter_url, "GetDatacenters", {"game": local.game_name})
    dc = _find_deep(resp, "Datacenter")
    if dc is None:
        raise GLSError("GetDatacenters: no datacenter in response")
    worlds = [
        World(
            name=_text(w, "Name"),
            chat_server=_text(w, "ChatServerUrl"),
            status_url=_text(w, "StatusServerUrl"),
            order=int(_text(w, "Order", "0") or 0),
            language=_text(w, "Language"),
        )
        for w in _children(_child(dc, "Worlds"), "World")
    ]
    auth, patch, cfg = _text(dc, "AuthServer"), _text(dc, "PatchServer"), _text(dc, "LauncherConfigurationServer")
    if not (auth and cfg):
        raise GLSError("GetDatacenters: response missing AuthServer or LauncherConfigurationServer")
    worlds.sort(key=lambda w: (w.order, w.name))
    return Datacenter(auth, patch, cfg, worlds)


def get_launcher_config(url: str) -> dict[str, str]:
    r = _http.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return parse_app_settings(r.content)


def login(auth_server: str, username: str, password: str) -> LoginResult:
    try:
        resp = soap_call(auth_server, "LoginAccount", {"username": username, "password": password, "additionalInfo": ""})
    except GLSError as e:
        msg = str(e).lower()
        if "no subscriber formal entity" in msg:
            raise LoginFailed("Username or password is incorrect") from e
        if "too short" in msg:
            raise LoginFailed(str(e)) from e
        raise
    result = _child(resp, "LoginAccountResult")
    if result is None:
        raise GLSError("LoginAccount: no result")
    subs = []
    for s in _children(_child(result, "Subscriptions"), "GameSubscription"):
        tokens = {(t.text or "").strip() for t in _children(_child(s, "ProductTokens"), "string")}
        subs.append(Subscription(
            game=_text(s, "Game"), name=_text(s, "Name"), description=_text(s, "Description"),
            product_tokens={t for t in tokens if t}, status=_text(s, "Status"),
        ))
    ticket = _text(result, "Ticket")
    if not ticket:
        raise GLSError("LoginAccount: no session ticket")
    return LoginResult(ticket, subs)


# ---- worlds & queue ------------------------------------------------------------

def _split(s: str, sep: str) -> list[str]:
    return [x for x in (p.strip() for p in s.split(sep)) if x]


def parse_world_status(xml_bytes: bytes) -> WorldStatus:
    root = ET.fromstring(xml_bytes)
    queues = _split(_text(root, "queueurls"), ";")
    logins = _split(_text(root, "loginservers"), ";")
    if not queues or not logins:
        raise WorldUnavailable("World is closed")
    allow = _text(root, "allow_billing_role")
    deny = _text(root, "deny_billing_role")
    try:
        wait = float(_text(root, "wait_hint", "0") or 0)
    except ValueError:
        wait = 0.0
    return WorldStatus(
        login_server=logins[0], queue_url=queues[0],
        allowed_roles=set(_split(allow, ",")) if allow else None,
        denied_roles=set(_split(deny, ",")) if deny else None,
        full=_text(root, "world_full").lower() == "true", wait_hint=wait,
    )


def get_world_status(world: World, gls_datacenter_url: str | None = None) -> WorldStatus:
    r = _http.get(world.status_url, timeout=TIMEOUT)
    if (r.status_code == 404 or not r.content.strip()) and gls_datacenter_url:
        # Some status URLs point at an internal host; retry against the GLS host (as OneLauncher does).
        su, gu = urlparse(world.status_url), urlparse(gls_datacenter_url)
        if su.path.lower().endswith("/statusserver.aspx") and su.netloc.lower() != gu.netloc.lower():
            prefix = gu.path.lower().split("/service.asmx", 1)[0]
            fixed = urlunparse(su._replace(netloc=gu.netloc, path=f"{prefix}/StatusServer.aspx"))
            r = _http.get(fixed, timeout=TIMEOUT)
    if r.status_code == 404 or not r.content.strip():
        raise WorldUnavailable(f"{world.name} is unavailable")
    r.raise_for_status()
    try:
        return parse_world_status(r.content)
    except ET.ParseError as e:
        raise GLSError(f"{world.name}: unreadable status") from e


def queue_params(template: str, subscription: str, ticket: str, world_queue_url: str) -> dict[str, str]:
    out = {}
    for part in template.split("&"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k] = v.replace("{0}", subscription).replace("{1}", ticket).replace("{2}", world_queue_url)
    return out


def take_a_number(queue_endpoint: str, params: dict[str, str]) -> tuple[int, int]:
    r = _http.post(queue_endpoint, data=params, timeout=TIMEOUT)
    r.raise_for_status()
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        raise GLSError("Login queue: unreadable response") from e
    hresult = int(_text(root, "HResult", "0x0") or "0", 16)
    if hresult >> 31 & 1:
        if hresult == 0x80004005:
            raise GLSError("Could not join the world login queue. Try again later.")
        raise GLSError(f"Login queue error (HRESULT {hresult:#x})")
    try:
        return int(_text(root, "QueueNumber"), 16), int(_text(root, "NowServingNumber"), 16)
    except ValueError as e:
        raise GLSError("Login queue: response missing queue numbers") from e


def wait_in_queue(
    launcher_cfg: dict[str, str], subscription: str, ticket: str, world_queue_url: str,
    on_position: Callable[[int], None] | None = None, cancelled: Callable[[], bool] | None = None,
) -> None:
    endpoint = launcher_cfg["WorldQueue.LoginQueue.URL"]
    params = queue_params(launcher_cfg["WorldQueue.TakeANumber.Parameters"], subscription, ticket, world_queue_url)
    while True:
        if cancelled and cancelled():
            raise GLSError("Cancelled")
        number, serving = take_a_number(endpoint, params)
        if number <= serving:
            return
        if on_position:
            on_position(number - serving)
        time.sleep(1.0)


# ---- client launch -------------------------------------------------------------

def client_executable(game_dir: Path, launcher_cfg: dict[str, str], prefer: str = "win64") -> Path:
    win64 = launcher_cfg.get("GameClient.WIN64.Filename")
    win32 = launcher_cfg.get("GameClient.WIN32.Filename") or launcher_cfg.get("GameClient.Filename") or "lotroclient.exe"
    if prefer == "win64" and win64 and (game_dir / "x64" / win64).exists():
        return game_dir / "x64" / win64
    if (game_dir / win32).exists():
        return game_dir / win32
    if win64 and (game_dir / "x64" / win64).exists():
        return game_dir / "x64" / win64
    raise GLSError(f"Game client not found in {game_dir}")


def client_arguments(
    launcher_cfg: dict[str, str], subscription: str, login_server: str, ticket: str,
    chat_server: str, language: str, high_res: bool = True,
) -> list[str]:
    template = launcher_cfg.get("GameClient.WIN32.ArgTemplate") or launcher_cfg.get("GameClient.ArgTemplate")
    if not template:
        raise GLSError("Launcher config has no client argument template")
    mapping = {
        "{SUBSCRIPTION}": subscription,
        "{LOGIN}": login_server,
        "{GLS}": ticket,
        "{CHAT}": chat_server,
        "{LANG}": language,
        "{CRASHRECEIVER}": launcher_cfg.get("GameClient.Arg.crashreceiver"),
        "{UPLOADTHROTTLE}": launcher_cfg.get("GameClient.Arg.DefaultUploadThrottleMbps"),
        "{BUGURL}": launcher_cfg.get("GameClient.Arg.bugurl"),
        "{AUTHSERVERURL}": launcher_cfg.get("GameClient.Arg.authserverurl"),
        "{GLSTICKETLIFETIME}": launcher_cfg.get("GameClient.Arg.glsticketlifetime"),
        "{SUPPORTURL}": launcher_cfg.get("GameClient.Arg.supporturl"),
        "{SUPPORTSERVICEURL}": launcher_cfg.get("GameClient.Arg.supportserviceurl"),
    }
    unknown = set(re.findall(r"\{[A-Z_]+\}", template)) - mapping.keys()
    if unknown:
        raise GLSError(f"Unknown placeholder(s) in client arguments: {', '.join(sorted(unknown))}")
    # Substitute per token so values containing spaces can't break the split.
    args = []
    for token in template.split():
        for key, val in mapping.items():
            if key in token:
                if val is None:
                    raise GLSError(f"Launcher config is missing a value for {key}")
                token = token.replace(key, val)
        args.append(token)
    if not high_res:
        args += (launcher_cfg.get("GameClient.HighResPatchArg") or "--HighResOutOfDate").split()
    return args


def redact(args: list[str], *secrets: str) -> list[str]:
    out = []
    for a in args:
        for s in secrets:
            if s:
                a = a.replace(s, "******")
        out.append(a)
    return out
