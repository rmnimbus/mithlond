"""The game's own settings (UserPreferences.ini in the documents folder): reading, a categorized schema of every
known setting, and saving only what changed.

The setting names and their allowed values come from the game client itself (the client contains every
`Section.Key` it reads and the tables of values it accepts). The game rewrites this file when it exits, so it
must not be edited while the game runs.
"""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

QUALITY = ["VeryLow", "Low", "Medium", "High", "VeryHigh", "UltraHigh"]
COLORS = ["Default", "White", "Red", "Gold", "Blue", "Yellow", "Green", "Orange", "Magenta", "Turquoise"]
RESOLUTIONS = ["1280x720", "1280x800", "1366x768", "1440x900", "1600x900", "1680x1050", "1920x1080", "1920x1200",
               "2560x1080", "2560x1440", "2560x1600", "3440x1440", "3840x1600", "3840x2160", "5120x1440"]


@dataclass(frozen=True)
class Pref:
    section: str
    key: str
    label: str
    kind: str  # bool | choice | float | int | volume | text
    category: str
    tip: str = ""
    choices: tuple[str, ...] = ()
    lo: float = 0.0
    hi: float = 1.0
    step: float = 0.05
    editable: bool = False  # choice list also accepts typed values

    @property
    def id(self) -> str:
        return f"{self.section}.{self.key}"


CATEGORIES = ["Display", "Detail", "Lighting & Effects", "Shadows", "Sound", "Interface", "Controls & Camera",
              "Voice Chat", "Performance", "Other"]


def _p(section, key, label, kind, category, tip="", **kw) -> Pref:
    if "choices" in kw:
        kw["choices"] = tuple(kw["choices"])
    return Pref(section, key, label, kind, category, tip, **kw)


B, C, F, I, V, T = "bool", "choice", "float", "int", "volume", "text"
D, DET, FX, SH, SND, UI_, CTL, VOI, PERF = CATEGORIES[:9]

SCHEMA: list[Pref] = [
    # ---- Display
    _p("Display", "ScreenMode", "Screen mode", C, D, "FullScreenWindowed is a borderless window the size of the screen.",
       choices=["FullScreen", "FullScreenWindowed", "Windowed"]),
    _p("Display", "Resolution", "Full-screen resolution", C, D, "Width x height.", choices=RESOLUTIONS, editable=True),
    _p("Display", "RefreshRate", "Refresh rate", C, D, "Auto, or a rate in Hz.", choices=["Auto", "60", "75", "120",
       "144", "165", "240"], editable=True),
    _p("Display", "SyncToRefresh", "Vertical sync", B, D, "Wait for the screen's refresh (no tearing, adds latency)."),
    _p("Display", "TripleBuffering", "Triple buffering", B, D),
    _p("Display", "Antialiasing", "Antialiasing", C, D, choices=["Disabled", *QUALITY], editable=True),
    _p("Display", "FixedOutputScaling", "Output scaling", C, D, "How a lower resolution fills the screen.",
       choices=["Default", "Centered", "Stretched"]),
    _p("Render", "AspectRatio", "Aspect ratio", C, D, choices=["Auto", "4x3", "5x4", "16x9", "16x10"]),
    _p("Render", "GraphicsCore", "Graphics API", C, D, "DirectX 11 is the normal choice on Linux (DXVK).",
       choices=["D3D11", "D3D10", "D3D9", "OpenGL"]),
    _p("Render", "Brightness", "Brightness", F, D, lo=0.0, hi=2.0, step=0.05),
    _p("Render", "Contrast", "Contrast", F, D, lo=0.0, hi=2.0, step=0.05),
    _p("Render", "Gamma", "Gamma", F, D, lo=0.0, hi=3.0, step=0.05),
    _p("Render", "AllowGammaChanges", "Allow gamma changes", B, D),
    _p("Display", "AllowWindowResizing", "Allow resizing the window", B, D),
    _p("Display", "ConfineFullScreenMouseCursor", "Keep the mouse inside the full-screen window", B, D),
    _p("Display", "AllowFakeFullScreen", "Allow borderless (\"fake\") full screen", B, D),
    _p("Display", "ForceFakeFullScreen", "Always use borderless full screen", B, D),
    _p("Display", "AllowDesktopCompositing", "Allow desktop compositing", B, D),
    _p("Display", "FullScreen", "Full screen (legacy switch)", B, D, "Older setting; Screen mode is what the game uses."),
    _p("Render", "DisplayAdapter", "Display adapter number", I, D, lo=0, hi=8, step=1),
    _p("Render", "DisplayOutput", "Display output number", I, D, lo=0, hi=8, step=1),
    # ---- Detail
    _p("Render", "TextureDetail", "Texture detail", C, DET, choices=QUALITY),
    _p("Render", "MaterialDetail", "Material detail", C, DET, choices=QUALITY),
    _p("Render", "ModelDetail", "Model detail", C, DET, choices=QUALITY),
    _p("Render", "TextureFiltering", "Texture filtering", C, DET,
       choices=["Bilinear", "Trilinear", "Sharp", "VerySharp", "Anisotropic"]),
    _p("Render", "AnisotropicQuality", "Anisotropic filtering level", C, DET, choices=["1", "2", "4", "8", "16"]),
    _p("Render", "ObjectDrawDistance", "Object draw distance", C, DET, choices=QUALITY),
    _p("Render", "LandscapeDrawDistance", "Landscape draw distance", C, DET, choices=QUALITY),
    _p("Render", "LandscapeLightingQuality", "Landscape lighting quality", C, DET, choices=QUALITY),
    _p("Render", "FrillDistance", "Grass and plants distance", C, DET, choices=QUALITY),
    _p("Render", "FrillDensity", "Grass and plants density", F, DET, lo=0.0, hi=1.0),
    _p("Render", "FrillTerrainColor", "Grass takes the terrain's color", B, DET),
    _p("Render", "FarLandscapeNormalMaps", "Detailed distant landscape", B, DET),
    _p("Render", "DistantImposters", "Distant imposters (stand-ins for far objects)", B, DET),
    _p("Render", "StaticEnvironmentalObjects", "Static environmental objects", B, DET),
    _p("Render", "MeshCombining", "Mesh combining", B, DET),
    _p("Render", "PlayerCrowdQuality", "Player crowd quality", F, DET, lo=0.0, hi=1.0),
    _p("Render", "EnablePortraits", "Character portraits", B, DET),
    _p("Graphics", "AvatarTextureCompositing", "Avatar texture compositing", B, DET),
    _p("Graphics", "AvatarUpdateVisible", "Update visible avatars", B, DET),
    # ---- Lighting & Effects
    _p("Render", "AmbientOcclusion", "Ambient occlusion", B, FX),
    _p("Render", "AmbientLightBoost", "Ambient light boost", F, FX, lo=0.0, hi=3.0),
    _p("Render", "AtmosphericsDetail", "Atmospherics detail", C, FX, choices=QUALITY),
    _p("Render", "VolumetricLight", "Volumetric light", B, FX),
    _p("Render", "SpecularLighting", "Specular lighting", B, FX),
    _p("Render", "MultiPassLighting", "Multi-pass lighting", B, FX),
    _p("Render", "PerPixelLightingAttenuation", "Per-pixel lighting attenuation", B, FX),
    _p("Render", "GlowMapping", "Glow mapping", B, FX),
    _p("Render", "OverbrightBloomFilter", "Bloom", B, FX),
    _p("Render", "BloomIntensity", "Bloom intensity", F, FX, lo=0.0, hi=3.0),
    _p("Render", "BlurFilterQuality", "Blur filter quality", C, FX, choices=QUALITY),
    _p("Render", "VideoPostEffects", "Post-processing effects", B, FX),
    _p("Render", "PrecipitationEffects", "Rain and snow", B, FX),
    _p("Render", "DynamicParticles", "Particle effects shown for", C, FX, choices=["All", "Me + Targets", "Me", "None"]),
    _p("Render", "InteractiveWater", "Interactive water", C, FX, choices=QUALITY),
    _p("Render", "LandscapeShoreEffects", "Shore effects", C, FX, choices=QUALITY),
    _p("Render", "SurfaceReflections", "Surface reflections", C, FX, choices=QUALITY),
    _p("Render", "AlphaToCoverage", "Alpha-to-coverage (smoother foliage edges)", B, FX),
    # ---- Shadows
    _p("Render", "StencilShadows", "Character shadows", C, SH, choices=QUALITY),
    _p("Render", "ShadowMapQuality", "Shadow map quality", I, SH, lo=0, hi=4, step=1),
    _p("Render", "LandscapeStaticObjectShadows", "Landscape object shadows", C, SH, choices=QUALITY),
    _p("Render", "EnvironmentStencilShadows", "Environment shadows", B, SH),
    _p("Render", "BlobShadows", "Simple (blob) shadows", B, SH),
    # ---- Sound
    _p("Sound", "MasterVolume", "Master volume", V, SND),
    _p("Sound", "MusicVolume", "Music", V, SND),
    _p("Sound", "SFXVolume", "Sound effects", V, SND),
    _p("Sound", "AmbientVolume", "Ambient sounds", V, SND),
    _p("Sound", "CombatVolume", "Combat", V, SND),
    _p("Sound", "VOVolume", "Voices", V, SND),
    _p("Sound", "UIVolume", "Interface sounds", V, SND),
    _p("Sound", "PlayerMusicVolume", "Player music (instruments)", V, SND),
    _p("Sound", "DefaultVolume", "Default volume", V, SND),
    _p("Sound", "SoundDisabled", "Turn all sound off", B, SND),
    _p("Sound", "MusicDisabled", "Turn music off", B, SND),
    _p("Sound", "FocusBehavior", "When the game is in the background", C, SND,
       choices=["Disable Sound", "Mute Sound", "Persist Sound"]),
    _p("Sound", "PersistentSound", "Keep playing sound in the background", B, SND),
    _p("Sound", "EAXEnabled", "EAX effects", B, SND),
    _p("Sound", "MaxPlayingSounds", "Maximum sounds at once", I, SND, lo=8, hi=256, step=8),
    _p("Sound", "SoundProvider", "Sound system", C, SND, choices=["OpenAL", "DirectMusic"]),
    # ---- Interface
    _p("UI", "UIScale_Global", "Interface scale", F, UI_, lo=0.5, hi=2.0),
    _p("UI", "UIScale_Pregame", "Login and character screen scale", F, UI_, lo=0.5, hi=2.0),
    _p("UI", "UIScale_Cursor", "Mouse cursor scale", F, UI_, lo=0.5, hi=3.0),
    _p("UI", "FloatyTextScale", "Floating combat text size", F, UI_, lo=0.5, hi=2.0),
    _p("UI", "FloatyTextOpacity", "Floating combat text opacity", F, UI_, lo=0.0, hi=1.0),
    _p("UI", "FloatyTextOnTop", "Floating combat text on top", B, UI_),
    _p("Misc", "TooltipEnable", "Tooltips", B, UI_),
    _p("Misc", "TooltipDelay", "Tooltip delay (seconds)", F, UI_, lo=0.0, hi=3.0),
    _p("UI", "HotspotVisualizationColorOverride_Boon", "Helpful ground effect color", C, UI_, choices=COLORS),
    _p("UI", "HotspotVisualizationColorOverride_Harm", "Harmful ground effect color", C, UI_, choices=COLORS),
    _p("UI", "RadarMovementSmoothing", "Smooth radar movement", B, UI_),
    _p("UI", "MountAppearanceShowPlayerMounted", "Show the player on mount appearances", B, UI_),
    _p("UI", "StatTreeShowAllStats", "Character panel: show all stats", B, UI_),
    _p("UI", "WebstoreExternalWindow", "Open the store in a separate window", B, UI_),
    *(_p("UI", f"Bag{n}Columns", f"Bag {n} columns", I, UI_, lo=1, hi=16, step=1) for n in range(1, 7)),
    _p("UI", "BankRepositoryAccountItemDisplayShowText", "Shared storage: show item names", B, UI_),
    _p("UI", "BankRepositoryCharacterItemDisplayShowText", "Vault: show item names", B, UI_),
    _p("UI", "BankRepositorySharedHousingItemDisplayShowText", "Kinship house storage: show item names", B, UI_),
    _p("UI", "BankRepositoryStandardHousingItemDisplayShowText", "House storage: show item names", B, UI_),
    _p("UI", "CharSelectSortType", "Character list sort order", I, UI_, lo=0, hi=5, step=1),
    _p("UI", "MapQuestListXScreenPercentage", "Map quest list position (horizontal)", F, UI_, lo=0.0, hi=1.0, step=0.01),
    _p("UI", "MapQuestListYScreenPercentage", "Map quest list position (vertical)", F, UI_, lo=0.0, hi=1.0, step=0.01),
    _p("International", "UseIME", "Use an input method editor (IME)", B, UI_),
    # ---- Controls & Camera
    _p("Input", "MouseLookSensitivity", "Mouse-look sensitivity", F, CTL, lo=0.01, hi=1.0, step=0.01),
    _p("Input", "MouseLookSmoothingAmount", "Mouse-look smoothing", F, CTL, lo=0.0, hi=1.0),
    _p("Input", "InvertMouseLookYAxis", "Invert mouse-look up/down", B, CTL),
    _p("Input", "TurnKeySpeed", "Turn speed (keys)", F, CTL, lo=10, hi=400, step=5),
    _p("Input", "PitchKeySpeed", "Pitch speed (keys)", F, CTL, lo=10, hi=400, step=5),
    _p("Input", "RollKeySpeed", "Roll speed (keys)", F, CTL, lo=10, hi=400, step=5),
    _p("Input", "XInputDetection", "Detect game controllers (XInput)", B, CTL),
    _p("Input", "JoystickDeadZone", "Controller dead zone", F, CTL, lo=0.0, hi=1.0),
    _p("Camera", "AlignToSlope", "Camera follows the slope", B, CTL),
    _p("Camera", "ResetYawWhenPlayerMoves", "Camera swings behind you when you move", B, CTL),
    # ---- Voice Chat
    _p("Voice", "VoiceVolume", "Voice chat volume", V, VOI),
    _p("Voice", "DefaultGroupVolume", "Group voice volume", V, VOI),
    _p("Voice", "MicVolume", "Microphone volume", V, VOI),
    _p("Voice", "MicCaptureThreshold", "Microphone activation level", F, VOI, lo=0.0, hi=1.0),
    _p("Voice", "HandsFree", "Hands-free (voice activation)", B, VOI),
    _p("Voice", "NetworkLatencyThresh", "Network latency threshold (ms)", I, VOI, lo=0, hi=2000, step=50),
    # ---- Performance
    _p("Troubleshooting", "MaximumFrameRate", "Maximum frame rate (the game's own limit)", I, PERF,
       "The game's built-in frame rate cap. The Play tab's Frame rate box is a separate cap applied by DXVK.",
       lo=10, hi=1000, step=5),
    _p("Troubleshooting", "EngineSpeed", "Engine speed", C, PERF, choices=QUALITY),
    _p("Render", "MemoryUsage", "Graphics memory use", F, PERF, lo=0.0, hi=1.0),
    _p("Graphics", "PVMPPerformanceOverride", "Monster play performance override", B, PERF),
    _p("Net", "ConnectionSpeed", "Connection speed (kbit/s, 0 = detect)", F, PERF, lo=0.0, hi=640.0, step=8),
    _p("Net", "ComputeUniquePort", "Pick a unique network port", B, PERF),
    _p("Net", "UserSpecifiedPort", "Network port (0 = automatic)", I, PERF, lo=0, hi=65535, step=1),
    _p("Net", "BindInterface", "Network interface", T, PERF, "Empty = automatic."),
]

BY_ID = {p.id: p for p in SCHEMA}

PRETTY = {
    "FullScreenWindowed": "Full screen (borderless window)", "FullScreen": "Full screen", "D3D11": "DirectX 11",
    "D3D10": "DirectX 10", "D3D9": "DirectX 9", "Me + Targets": "Me and my targets", "Me": "Only me",
    "Disable Sound": "Stop the sound", "Mute Sound": "Mute", "Persist Sound": "Keep playing", "DirectMusic": "DirectMusic",
}


def pretty(value: str) -> str:
    """How a stored value is shown: 'VeryHigh' -> 'Very High', '16x9' -> '16:9'."""
    if value in PRETTY:
        return PRETTY[value]
    if re.fullmatch(r"\d+x\d+", value) and int(value.split("x")[0]) < 100:
        return value.replace("x", ":")  # aspect ratios (resolutions stay 1920x1080)
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)

# Never shown: account/world history, the launcher's own entries, hardware IDs and values the game measures or uses
# for its first-run prompts, settings Mithlond manages itself.
HIDDEN_SECTIONS = ("Launcher",)
HIDDEN_SECTION_PREFIXES = ("User_",)
HIDDEN = {
    "Voice.DeviceCapture", "Voice.DevicePlayback", "Render.MeasuredFillRate", "Render.MaxHardwareClass",
    "Render.HavePromptedForD3D10AtStartup", "Render.D3DVersionPromptedForAtStartup", "Display.WindowedResolution",
    "Misc.PlayedIntroMovie", "Sound.SoundFeatures", "Sound.QuantizedPlayerMusicVolume",
}


def set_preference(path: Path, section: str, key: str, value: str) -> bool:
    """Set `key=value` in `[section]` of a UserPreferences.ini, keeping every other line and the file's line
    endings. Returns True if the file changed."""
    raw = path.read_bytes().decode("utf-8", errors="surrogateescape")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    header = f"[{section}]".lower()
    start = next((i for i, l in enumerate(lines) if l.strip().lower() == header), None)
    if start is None:
        while lines and lines[-1] == "":
            lines.pop()
        lines += [f"[{section}]", f"{key}={value}", ""]
    else:
        end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
        for i in range(start + 1, end):
            if lines[i].split("=", 1)[0].strip().lower() == key.lower():
                if lines[i] == f"{key}={value}":
                    return False
                lines[i] = f"{key}={value}"
                break
        else:
            last = max((i for i in range(start, end) if lines[i].strip()), default=start)
            lines.insert(last + 1, f"{key}={value}")
    path.write_bytes(nl.join(lines).encode("utf-8", errors="surrogateescape"))
    return True


def hidden(section: str, key: str) -> bool:
    return (section in HIDDEN_SECTIONS or section.startswith(HIDDEN_SECTION_PREFIXES)
            or f"{section}.{key}" in HIDDEN or key.startswith("ShaderDebug"))


def read(path: Path) -> dict[str, str]:
    """All `Section.Key` → value pairs, in file order."""
    values: dict[str, str] = {}
    section = ""
    for line in path.read_bytes().decode("utf-8", errors="surrogateescape").splitlines():
        s = line.strip()
        if m := re.fullmatch(r"\[(.+)\]", s):
            section = m.group(1)
        elif "=" in s and section:
            k, v = s.split("=", 1)
            values[f"{section}.{k.strip()}"] = v.strip()
    return values


def visible(values: dict[str, str]) -> list[Pref]:
    """The settings to show: every schema setting present in the file, then any other non-hidden setting found in
    the file (under 'Other', as text), so nothing the game writes is left out."""
    shown = [p for p in SCHEMA if p.id in values]
    for ident, v in values.items():
        section, key = ident.split(".", 1)
        if ident in BY_ID or hidden(section, key):
            continue
        kind = "bool" if v in ("True", "False") else "text"
        shown.append(Pref(section, key, key, kind, "Other", f"[{section}] {key}"))
    return shown


def format_value(p: Pref, value) -> str:
    if p.kind == "bool":
        return "True" if value else "False"
    if p.kind in ("float", "volume"):
        return f"{float(value):.2f}"
    if p.kind == "int":
        return str(int(value))
    return str(value)


def backup(path: Path) -> Path:
    b = path.with_name(f"{path.name}.mithlond-{time.strftime('%Y-%m-%d-%H%M%S')}")
    shutil.copy2(path, b)
    for old in sorted(path.parent.glob(f"{path.name}.mithlond-*"))[:-5]:  # keep the last five
        old.unlink(missing_ok=True)
    return b


def latest_backup(path: Path) -> Path | None:
    found = sorted(path.parent.glob(f"{path.name}.mithlond-*"))
    return found[-1] if found else None


def save(path: Path, changes: dict[str, str]) -> Path | None:
    """Write `Section.Key` → value changes (backup first). Every other line stays as it is."""
    if not changes:
        return None
    b = backup(path)
    for ident, value in changes.items():
        section, key = ident.split(".", 1)
        set_preference(path, section, key, value)
    return b
