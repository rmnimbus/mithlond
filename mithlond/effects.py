"""Visual effects for the game client: vkBasalt (post-processing Vulkan layer), gamescope (upscaling and display),
and DXVK options (dxvk.conf). They work on what DXVK/Vulkan renders, so the game itself is not modified.

vkBasalt and DXVK read config files that Mithlond writes to its config folder; the game gets their paths through
VKBASALT_CONFIG_FILE / DXVK_CONFIG_FILE, so nothing in the user's own ~/.config/vkBasalt is touched.
"""

from __future__ import annotations

import shlex
import shutil
from pathlib import Path

from .config import CONFIG_DIR, HOME, Settings

VKBASALT_LAYER_DIRS = (Path("/usr/share/vulkan/implicit_layer.d"), Path("/etc/vulkan/implicit_layer.d"),
                       HOME / ".local/share/vulkan/implicit_layer.d")
VKBASALT_CONF = CONFIG_DIR / "vkBasalt.conf"
DXVK_CONF = CONFIG_DIR / "dxvk.conf"

FILTERS = [("linear", "Linear (plain)"), ("fsr", "AMD FSR 1"), ("nis", "NVIDIA Image Scaling"),
           ("sgsr", "Snapdragon SGSR"), ("nearest", "Nearest (pixelated)"), ("pixel", "Pixel art")]
SCALERS = [("auto", "Auto"), ("fit", "Fit (keep aspect)"), ("fill", "Fill (crop)"), ("stretch", "Stretch"),
           ("integer", "Integer")]
RENDER_SCALES = [("native", "Native (no upscaling)", 1.0), ("ultra", "Ultra quality (77%)", 1 / 1.3),
                 ("quality", "Quality (67%)", 1 / 1.5), ("balanced", "Balanced (59%)", 1 / 1.7),
                 ("performance", "Performance (50%)", 1 / 2.0), ("custom", "Custom size", 0.0)]


# ---- vkBasalt -------------------------------------------------------------------------------------------
def vkbasalt_installed() -> bool:
    return any((d / "vkBasalt.json").exists() for d in VKBASALT_LAYER_DIRS) or \
        any(d.is_dir() and any(d.glob("vkBasalt*.json")) for d in VKBASALT_LAYER_DIRS)


def reshade_effects(s: Settings) -> list[tuple[str, Path]]:
    """(name, path) of each ReShade .fx effect named in the settings that exists in the shaders folder."""
    if not s.vkb_reshade_dir:
        return []
    shaders = Path(s.vkb_reshade_dir).expanduser() / "Shaders"
    out = []
    for name in s.vkb_reshade_effects.replace(",", " ").split():
        fx = shaders / (name if name.endswith(".fx") else name + ".fx")
        if fx.is_file():
            out.append((fx.stem, fx))
    return out


def vkbasalt_effects(s: Settings) -> list[str]:
    """Effect order: antialiasing first, then sharpening, then colour (LUT), then ReShade shaders."""
    order = [("smaa", s.vkb_smaa), ("fxaa", s.vkb_fxaa), ("cas", s.vkb_cas), ("dls", s.vkb_dls),
             ("lut", s.vkb_lut and bool(s.vkb_lut_file))]
    return [name for name, on in order if on] + [name for name, _ in reshade_effects(s)]


def vkbasalt_config(s: Settings) -> str:
    effects = vkbasalt_effects(s)
    lines = [
        "# Written by Mithlond (Visual effects tab). Changes here are overwritten.",
        f"effects = {':'.join(effects) if effects else 'cas'}",
        f"toggleKey = {s.vkb_toggle_key or 'Home'}",
        f"enableOnLaunch = {'True' if s.vkb_on_launch else 'False'}",
        f"casSharpness = {s.vkb_cas_sharpness:.2f}",
        f"dlsSharpness = {s.vkb_dls_sharpness:.2f}",
        f"dlsDenoise = {s.vkb_dls_denoise:.2f}",
        f"fxaaQualitySubpix = {s.vkb_fxaa_subpix:.2f}",
        f"fxaaQualityEdgeThreshold = {s.vkb_fxaa_edge:.3f}",
        f"fxaaQualityEdgeThresholdMin = {s.vkb_fxaa_edge_min:.4f}",
        f"smaaEdgeDetection = {s.vkb_smaa_edge}",
        f"smaaThreshold = {s.vkb_smaa_threshold:.2f}",
        f"smaaMaxSearchSteps = {int(s.vkb_smaa_steps)}",
        f"smaaMaxSearchStepsDiag = {int(s.vkb_smaa_steps_diag)}",
        f"smaaCornerRounding = {int(s.vkb_smaa_corner)}",
    ]
    if s.vkb_lut and s.vkb_lut_file:
        lines.append(f'lutFile = "{Path(s.vkb_lut_file).expanduser()}"')
    fx = reshade_effects(s)
    if fx:
        base = Path(s.vkb_reshade_dir).expanduser()
        lines += [f'reshadeTexturePath = "{base / "Textures"}"', f'reshadeIncludePath = "{base / "Shaders"}"']
        lines += [f'{name} = "{path}"' for name, path in fx]
    return "\n".join(lines) + "\n"


# ---- DXVK -----------------------------------------------------------------------------------------------
def dxvk_options(s: Settings) -> dict[str, str]:
    """dxvk.conf entries for the non-default DXVK settings (both the D3D11 and D3D9 renderers of the game)."""
    o: dict[str, str] = {}
    if s.dxvk_aniso:
        o["d3d11.samplerAnisotropy"] = o["d3d9.samplerAnisotropy"] = str(int(s.dxvk_aniso))
    if abs(s.dxvk_lod_bias) > 1e-6:
        o["d3d11.samplerLodBias"] = o["d3d9.samplerLodBias"] = f"{s.dxvk_lod_bias:.2f}"
    if s.dxvk_latency:
        o["dxgi.maxFrameLatency"] = o["d3d9.maxFrameLatency"] = str(int(s.dxvk_latency))
    if s.dxvk_vsync in ("on", "off"):
        o["dxgi.syncInterval"] = o["d3d9.presentInterval"] = "1" if s.dxvk_vsync == "on" else "0"
    if s.dxvk_tearfree in ("True", "False"):
        o["dxvk.tearFree"] = s.dxvk_tearfree
    return o


def dxvk_config(s: Settings) -> str:
    opts = dxvk_options(s)
    return "# Written by Mithlond (Visual effects tab). Changes here are overwritten.\n" + \
        "".join(f"{k} = {v}\n" for k, v in opts.items())


# ---- gamescope ------------------------------------------------------------------------------------------
def render_size(s: Settings, output: tuple[int, int] | None) -> tuple[int, int] | None:
    """The game's own resolution (-w/-h): custom, or the output size times the render scale."""
    if s.gs_render == "custom":
        return (s.gs_render_w, s.gs_render_h) if s.gs_render_w and s.gs_render_h else None
    factor = next((f for key, _, f in RENDER_SCALES if key == s.gs_render), 1.0)
    if factor >= 1.0 or not output:
        return None
    w, h = output
    return (round(w * factor) // 2 * 2, round(h * factor) // 2 * 2)


def gamescope_args(s: Settings, screen: tuple[int, int] | None = None) -> list[str]:
    """gamescope's options (everything before '--'). `screen` is the monitor size, used when the output size is
    Auto and a render scale is chosen."""
    a: list[str] = []
    output = (s.gs_output_w, s.gs_output_h) if s.gs_output_w and s.gs_output_h else screen
    if s.gs_output_w and s.gs_output_h:
        a += ["-W", str(s.gs_output_w), "-H", str(s.gs_output_h)]
    elif s.gs_render != "native" and screen:
        a += ["-W", str(screen[0]), "-H", str(screen[1])]
    if size := render_size(s, output):
        a += ["-w", str(size[0]), "-h", str(size[1])]
    if s.gs_filter and s.gs_filter != "linear":
        a += ["-F", s.gs_filter]
        if s.gs_filter in ("fsr", "nis", "sgsr"):
            a += ["--sharpness", str(int(s.gs_sharpness))]
    if s.gs_scaler and s.gs_scaler != "auto":
        a += ["-S", s.gs_scaler]
    if s.gs_refresh:
        a += ["-r", str(int(s.gs_refresh))]
    if s.gs_unfocused_refresh:
        a += ["-o", str(int(s.gs_unfocused_refresh))]
    for on, flag in ((s.gs_fullscreen, "-f"), (s.gs_borderless, "-b"), (s.gs_grab_keyboard, "-g"),
                     (s.gs_force_grab_cursor, "--force-grab-cursor"), (s.gs_adaptive_sync, "--adaptive-sync"),
                     (s.gs_mangoapp, "--mangoapp"), (s.gs_hdr, "--hdr-enabled"),
                     (s.gs_hdr and s.gs_hdr_itm, "--hdr-itm-enabled")):
        if on:
            a.append(flag)
    return a + shlex.split(s.gamescope_args or "")  # "Extra arguments", added as typed


def gamescope_command(s: Settings, screen: tuple[int, int] | None = None) -> list[str]:
    return [shutil.which("gamescope") or "gamescope", *gamescope_args(s, screen), "--"]


# ---- applying them to the game ------------------------------------------------------------------------
def apply_env(s: Settings, env: dict[str, str]) -> list[str]:
    """Write the config files and set the environment for the game client. Returns notes for the log."""
    notes = []
    if s.vkb_enabled:
        if not vkbasalt_installed():
            notes.append("vkBasalt is turned on but not installed; effects skipped")
        else:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            VKBASALT_CONF.write_text(vkbasalt_config(s))
            env["ENABLE_VKBASALT"] = "1"
            env["VKBASALT_CONFIG_FILE"] = str(VKBASALT_CONF)
            notes.append("vkBasalt: " + (":".join(vkbasalt_effects(s)) or "cas"))
    if dxvk_options(s) and "DXVK_CONFIG_FILE" not in env:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        DXVK_CONF.write_text(dxvk_config(s))
        env["DXVK_CONFIG_FILE"] = str(DXVK_CONF)
        shown = {k: v for k, v in dxvk_options(s).items() if not k.startswith("d3d9.")}
        notes.append("DXVK: " + ", ".join(f"{k} = {v}" for k, v in shown.items()))
    return notes


# ---- presets ---------------------------------------------------------------------------------------------
PRESET_NAMES = ["Very Low", "Low", "Medium", "High", "Very High"]

# Slower computers: render smaller and upscale with FSR (gamescope), sharpen the result (CAS), shortest frame queue.
# Faster computers: native resolution, real antialiasing (SMAA) + sharpening, maximum anisotropic filtering.
_PRESETS: dict[str, dict] = {
    "Very Low": dict(opt_gamescope=True, gs_render="performance", gs_filter="fsr", gs_sharpness=3,
                     vkb_enabled=True, vkb_cas=True, vkb_cas_sharpness=0.6, vkb_smaa=False, vkb_fxaa=False,
                     vkb_dls=False, dxvk_aniso=0, dxvk_latency=1),
    "Low": dict(opt_gamescope=True, gs_render="balanced", gs_filter="fsr", gs_sharpness=4,
                vkb_enabled=True, vkb_cas=True, vkb_cas_sharpness=0.5, vkb_smaa=False, vkb_fxaa=False,
                vkb_dls=False, dxvk_aniso=4, dxvk_latency=1),
    "Medium": dict(opt_gamescope=False, gs_render="native", gs_filter="linear",
                   vkb_enabled=True, vkb_cas=True, vkb_cas_sharpness=0.4, vkb_smaa=False, vkb_fxaa=False,
                   vkb_dls=False, dxvk_aniso=8, dxvk_latency=0),
    "High": dict(opt_gamescope=False, gs_render="native", gs_filter="linear",
                 vkb_enabled=True, vkb_cas=True, vkb_cas_sharpness=0.4, vkb_smaa=True, vkb_smaa_edge="luma",
                 vkb_smaa_threshold=0.05, vkb_smaa_steps=32, vkb_fxaa=False, vkb_dls=False,
                 dxvk_aniso=16, dxvk_latency=0),
    "Very High": dict(opt_gamescope=False, gs_render="native", gs_filter="linear",
                      vkb_enabled=True, vkb_cas=True, vkb_cas_sharpness=0.5, vkb_smaa=True, vkb_smaa_edge="color",
                      vkb_smaa_threshold=0.05, vkb_smaa_steps=64, vkb_smaa_steps_diag=16, vkb_fxaa=False,
                      vkb_dls=False, dxvk_aniso=16, dxvk_latency=0),
}


def preset_values(name: str, gamescope_installed: bool | None = None) -> dict:
    """The settings a preset sets. Without gamescope installed, the upscaling part is left out (gamescope stays
    off)."""
    values = dict(_PRESETS[name])
    if gamescope_installed is None:
        gamescope_installed = shutil.which("gamescope") is not None
    if not gamescope_installed:
        for k in [k for k in values if k.startswith("gs_")] + ["opt_gamescope"]:
            values.pop(k, None)
    return values


def apply_preset(s: Settings, name: str, gamescope_installed: bool | None = None) -> dict:
    values = preset_values(name, gamescope_installed)
    for k, v in values.items():
        setattr(s, k, v)
    return values
