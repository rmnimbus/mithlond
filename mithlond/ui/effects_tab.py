"""Visual effects tab: vkBasalt (sharpening, antialiasing, colour, ReShade shaders), gamescope (upscaling and display)
and DXVK options. Everything applies to the game client the next time it starts."""

from __future__ import annotations

import shlex
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)

from .. import effects
from .context import AppContext
from .widgets import PathPicker, SectionedPage, subtle

RESOLUTIONS = ["1280x720", "1600x900", "1920x1080", "2560x1080", "2560x1440", "3440x1440", "3840x2160"]


class VisualEffectsTab(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.preset = QComboBox()
        self.preset.addItem("Effects preset…")
        self.preset.addItems(effects.PRESET_NAMES)
        self.preset.setToolTip("Very Low / Low: render smaller and upscale with FSR (gamescope), sharpen with CAS.\n"
                               "Medium: CAS sharpening, 8× anisotropic filtering.\n"
                               "High / Very High: SMAA antialiasing + CAS sharpening, 16× anisotropic filtering.\n"
                               "Applied right away; adjust anything afterwards.")
        self.preset.activated.connect(self._apply_preset)
        head = QHBoxLayout()
        head.addWidget(subtle("These work on the picture DXVK/Vulkan renders, outside the game itself, and apply the "
                              "next time the game starts."), 1)
        head.addWidget(self.preset)
        self.lay = QVBoxLayout(self)
        self.lay.addLayout(head)
        self.page = None
        self._build_page()

    def _build_page(self) -> None:
        """(Re)create the categories from the current settings, keeping the selected category and the search."""
        keep_sel, keep_search = None, ""
        if self.page is not None:
            row = self.page.nav.currentRow()
            keep_sel = self.page.sections[row][0] if row >= 0 else None
            keep_search = self.page.search.text()
            self.lay.removeWidget(self.page)
            self.page.deleteLater()
        self._loading = True
        self.page = SectionedPage("Search effects, e.g. sharpen, fsr, hdr, anisotropic…")
        self.page.add("Sharpening & antialiasing", self._vkbasalt_box())
        self.page.add("Upscaling & display", self._gamescope_box())
        self.page.add("DXVK", self._dxvk_box())
        self.lay.addWidget(self.page, 1)
        self.page.search.setText(keep_search)
        if keep_sel:
            self.page.select(keep_sel)
        self._loading = False
        self._refresh()

    def _apply_preset(self, index: int) -> None:
        if index <= 0:
            return
        name = effects.PRESET_NAMES[index - 1]
        values = effects.apply_preset(self.ctx.settings, name)
        self.ctx.save()
        self.preset.setCurrentIndex(0)
        self._build_page()
        extra = "" if any(k == "opt_gamescope" for k in values) else " (gamescope isn't installed, so no upscaling)"
        self.ctx.log(f"Visual effects: {name} preset applied{extra}")

    # ---- small builders that load from and save to Settings --------------------------------------------
    def _save(self, *_):
        if not self._loading:
            self.ctx.save()
            self._refresh()

    def check(self, key: str, text: str, tip: str = "") -> QCheckBox:
        w = QCheckBox(text)
        w.setToolTip(tip)
        w.setChecked(bool(getattr(self.ctx.settings, key)))
        w.toggled.connect(lambda v: (setattr(self.ctx.settings, key, v), self._save()))
        return w

    def combo(self, key: str, items: list[tuple[str, str]], tip: str = "") -> QComboBox:
        w = QComboBox()
        w.setToolTip(tip)
        for value, label in items:
            w.addItem(label, value)
        i = w.findData(getattr(self.ctx.settings, key))
        w.setCurrentIndex(max(i, 0))
        w.currentIndexChanged.connect(lambda _i: (setattr(self.ctx.settings, key, w.currentData()), self._save()))
        return w

    def number(self, key: str, lo, hi, step, decimals: int | None = None, tip: str = "", special: str = ""):
        w = QSpinBox() if decimals is None else QDoubleSpinBox()
        if decimals is not None:
            w.setDecimals(decimals)
        w.setRange(lo, hi)
        w.setSingleStep(step)
        if special:
            w.setSpecialValueText(special)
        w.setToolTip(tip)
        w.setValue(getattr(self.ctx.settings, key))
        w.valueChanged.connect(lambda v: (setattr(self.ctx.settings, key, v), self._save()))
        return w

    def slider(self, key: str, lo: float, hi: float, tip: str = "") -> QWidget:
        """0..100 slider mapped onto lo..hi, with the value shown next to it."""
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        s = QSlider(Qt.Horizontal)
        s.setRange(0, 100)
        s.setToolTip(tip)
        lab = QLabel()
        lab.setMinimumWidth(44)
        cur = getattr(self.ctx.settings, key)
        s.setValue(round((cur - lo) / (hi - lo) * 100))
        lab.setText(f"{cur:.2f}")

        def moved(v):
            val = lo + (hi - lo) * v / 100
            setattr(self.ctx.settings, key, round(val, 3))
            lab.setText(f"{val:.2f}")
            self._save()
        s.valueChanged.connect(moved)
        row.addWidget(s, 1)
        row.addWidget(lab)
        return box

    def text(self, key: str, placeholder: str = "", tip: str = "") -> QLineEdit:
        w = QLineEdit(getattr(self.ctx.settings, key))
        w.setPlaceholderText(placeholder)
        w.setToolTip(tip)
        w.editingFinished.connect(lambda: (setattr(self.ctx.settings, key, w.text().strip()), self._save()))
        return w

    def size(self, wkey: str, hkey: str, choices: list[str], auto: str) -> QComboBox:
        """A W x H list with an automatic first entry; typed sizes like 2048x1152 work too."""
        s = self.ctx.settings
        w = QComboBox()
        w.setEditable(True)
        w.addItem(auto)
        w.addItems(choices)
        cur = f"{getattr(s, wkey)}x{getattr(s, hkey)}" if getattr(s, wkey) and getattr(s, hkey) else auto
        w.setCurrentText(cur)

        def done():
            t = w.currentText().lower().replace(" ", "")
            try:
                a, b = (int(x) for x in t.split("x", 1))
            except ValueError:
                a = b = 0
            setattr(s, wkey, a)
            setattr(s, hkey, b)
            if not a:
                w.setCurrentText(auto)
            self._save()
        w.lineEdit().editingFinished.connect(done)
        w.activated.connect(lambda _i: done())
        return w

    # ---- sections ------------------------------------------------------------------------------------
    def _vkbasalt_box(self) -> QGroupBox:
        f = QFormLayout()
        self.vkb_state = QLabel()
        self.vkb_state.setWordWrap(True)
        f.addRow("", self.vkb_state)
        f.addRow("", self.check("vkb_enabled", "Use vkBasalt", "Vulkan post-processing layer (ENABLE_VKBASALT=1)"))
        f.addRow("", self.check("vkb_on_launch", "Effects on when the game starts"))
        f.addRow("Toggle key", self.text("vkb_toggle_key", "Home", "Key that switches the effects on and off in game "
                                         "(X11 key name, e.g. Home, End, F11)"))
        f.addRow("", self.check("vkb_cas", "Sharpening: AMD CAS (contrast adaptive sharpening)",
                                "Sharpens textures and edges; the usual first choice for LOTRO"))
        f.addRow("CAS strength", self.slider("vkb_cas_sharpness", -1.0, 1.0,
                                             "0.4 is a good start; negative values sharpen even less"))
        f.addRow("", self.check("vkb_dls", "Sharpening: DLS (denoised luma sharpening)",
                                "Sharpens without boosting grain/noise"))
        f.addRow("DLS sharpness", self.slider("vkb_dls_sharpness", 0.0, 1.0))
        f.addRow("DLS denoise", self.slider("vkb_dls_denoise", 0.0, 1.0))
        f.addRow("", self.check("vkb_smaa", "Antialiasing: SMAA", "Smooths jagged edges, better than the game's own"))
        f.addRow("SMAA edge detection", self.combo("vkb_smaa_edge", [("luma", "Brightness (luma)"),
                                                                     ("color", "Color (catches more, slower)")]))
        f.addRow("SMAA threshold", self.number("vkb_smaa_threshold", 0.0, 0.5, 0.01, 2,
                                               "Lower finds more edges (slower). 0.05 default"))
        f.addRow("SMAA search steps", self.number("vkb_smaa_steps", 0, 112, 4, None, "Horizontal/vertical, 32 default"))
        f.addRow("SMAA diagonal steps", self.number("vkb_smaa_steps_diag", 0, 20, 1, None, "16 default"))
        f.addRow("SMAA corner rounding", self.number("vkb_smaa_corner", 0, 100, 5, None, "25 default"))
        f.addRow("", self.check("vkb_fxaa", "Antialiasing: FXAA", "Cheaper and blurrier than SMAA"))
        f.addRow("FXAA subpixel quality", self.slider("vkb_fxaa_subpix", 0.0, 1.0, "Lower is sharper"))
        f.addRow("FXAA edge threshold", self.number("vkb_fxaa_edge", 0.063, 0.333, 0.01, 3))
        f.addRow("FXAA dark edge threshold", self.number("vkb_fxaa_edge_min", 0.0, 0.0833, 0.005, 4))
        f.addRow("", self.check("vkb_lut", "Color: LUT (color lookup table)",
                                "A .CUBE file, or a .png whose width = height × height"))
        lut = PathPicker(directory=False, placeholder="LUT file (.cube or .png)", empty_ok=True)
        lut.set_text(self.ctx.settings.vkb_lut_file)
        lut.changed.connect(lambda t: (setattr(self.ctx.settings, "vkb_lut_file", t), self._save()))
        f.addRow("LUT file", lut)
        rs = PathPicker(directory=True, placeholder="Folder with Shaders/ and Textures/ (e.g. reshade-shaders)",
                        empty_ok=True)
        rs.set_text(self.ctx.settings.vkb_reshade_dir)
        rs.changed.connect(lambda t: (setattr(self.ctx.settings, "vkb_reshade_dir", t), self._save()))
        f.addRow("ReShade shaders", rs)
        f.addRow("ReShade effects", self.text("vkb_reshade_effects", "e.g. Vibrance Clarity",
                                              "Names of .fx files in the Shaders folder, run after the effects above"))
        box = QGroupBox("Sharpening && antialiasing (vkBasalt)")
        box.setLayout(f)
        return box

    def _gamescope_box(self) -> QGroupBox:
        f = QFormLayout()
        self.gs_state = QLabel()
        self.gs_state.setWordWrap(True)
        f.addRow("", self.gs_state)
        f.addRow("", self.check("opt_gamescope", "Run the game in gamescope",
                                "Valve's micro-compositor: upscaling, fixed resolution, HDR, frame limits"))
        win = QHBoxLayout()
        win.addWidget(self.check("gs_fullscreen", "Fullscreen (-f)"))
        win.addWidget(self.check("gs_borderless", "Borderless window (-b)"))
        win.addStretch()
        f.addRow("Window", win)
        f.addRow("Output resolution", self.size("gs_output_w", "gs_output_h", RESOLUTIONS, "Auto (monitor size)"))
        f.addRow("Game renders at", self.combo("gs_render", [(k, label) for k, label, _ in effects.RENDER_SCALES],
                                               "Render the game smaller and upscale it: more FPS, a little softer"))
        f.addRow("Custom render size", self.size("gs_render_w", "gs_render_h", RESOLUTIONS, "—"))
        f.addRow("", subtle("LOTRO sizes its own picture inside gamescope from its own resolution setting. For the "
                            "sharpest upscaling, set In game settings → Display → Full-screen resolution to the size "
                            "the game renders at (e.g. 1280x720 for Quality on a 1080p screen)."))
        f.addRow("Upscaler", self.combo("gs_filter", effects.FILTERS,
                                        "FSR/NIS/SGSR sharpen while upscaling; Linear is plain scaling"))
        f.addRow("Upscaler sharpness", self.number("gs_sharpness", 0, 20, 1, None,
                                                   "0 = sharpest, 20 = softest (FSR, NIS, SGSR)"))
        f.addRow("Scaling", self.combo("gs_scaler", effects.SCALERS))
        f.addRow("Game frame rate", self.number("gs_refresh", 0, 360, 5, None, "-r: gamescope's frame rate for the "
                                                "game", "Default"))
        f.addRow("Frame rate in background", self.number("gs_unfocused_refresh", 0, 240, 5, None,
                                                         "-o: lower FPS while the game window isn't focused (saves "
                                                         "power)", "Same"))
        f.addRow("", self.check("gs_adaptive_sync", "Variable refresh rate (VRR / FreeSync / G-Sync)",
                                "--adaptive-sync, if the display supports it"))
        f.addRow("", self.check("gs_hdr", "HDR output", "--hdr-enabled. LOTRO renders SDR; combine with inverse tone "
                                "mapping to stretch it to HDR"))
        f.addRow("", self.check("gs_hdr_itm", "SDR → HDR inverse tone mapping", "--hdr-itm-enabled (needs HDR output)"))
        f.addRow("", self.check("gs_mangoapp", "MangoHud overlay through gamescope",
                                "--mangoapp: the recommended way to use MangoHud with gamescope"))
        f.addRow("", self.check("gs_grab_keyboard", "Grab the keyboard (-g)",
                                "Shortcuts like Alt+Tab go to the game instead of the desktop"))
        f.addRow("", self.check("gs_force_grab_cursor", "Always lock the mouse to the game",
                                "--force-grab-cursor: fixes the camera spinning or the cursor escaping"))
        f.addRow("Extra arguments", self.text("gamescope_args", "Other gamescope options, as typed",
                                              "Added after the options above, before '--'"))
        self.gs_preview = QLabel()
        self.gs_preview.setWordWrap(True)
        self.gs_preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f.addRow("Command", self.gs_preview)
        box = QGroupBox("Upscaling && display (gamescope)")
        box.setLayout(f)
        return box

    def _dxvk_box(self) -> QGroupBox:
        f = QFormLayout()
        f.addRow("", subtle("DXVK turns LOTRO's DirectX into Vulkan in Wine and Proton. These settings go into a "
                            "dxvk.conf that Mithlond passes to the game (DXVK_CONFIG_FILE)."))
        f.addRow("Anisotropic filtering", self.combo("dxvk_aniso", [(0, "Game's setting"), (2, "Force 2×"),
                                                                    (4, "Force 4×"), (8, "Force 8×"),
                                                                    (16, "Force 16×")],
                                                     "Sharper ground and walls at an angle"))
        f.addRow("Texture LOD bias", self.number("dxvk_lod_bias", -2.0, 2.0, 0.25, 2,
                                                 "Negative = sharper (more shimmer), positive = blurrier. 0 = off"))
        f.addRow("Max frame latency", self.combo("dxvk_latency", [(0, "DXVK default"), (1, "1 frame (lowest input lag)"),
                                                                  (2, "2 frames"), (3, "3 frames (smoothest)")]))
        f.addRow("Vertical sync", self.combo("dxvk_vsync", [("game", "Game's setting"), ("on", "Force on"),
                                                            ("off", "Force off")]))
        f.addRow("Tear-free presentation", self.combo("dxvk_tearfree", [("Auto", "Auto"), ("True", "On"),
                                                                       ("False", "Off")],
                                                      "dxvk.tearFree: avoids tearing when VSync is off"))
        box = QGroupBox("DXVK")
        box.setLayout(f)
        return box

    # ---- status ----------------------------------------------------------------------------------------
    def _refresh(self) -> None:
        s = self.ctx.settings
        if effects.vkbasalt_installed():
            self.vkb_state.setText("✔ vkBasalt is installed." + ("" if s.vkb_enabled else " Tick “Use vkBasalt”."))
            self.vkb_state.setObjectName("ok")
        else:
            self.vkb_state.setText("✘ vkBasalt isn't installed (package “vkbasalt”, AUR on Arch). These settings are "
                                   "kept until it is.")
            self.vkb_state.setObjectName("bad")
        gs = shutil.which("gamescope")
        self.gs_state.setText("✔ gamescope is installed." if gs else
                              "✘ gamescope isn't installed (package “gamescope”).")
        self.gs_state.setObjectName("ok" if gs else "bad")
        for w in (self.vkb_state, self.gs_state):
            w.style().unpolish(w)
            w.style().polish(w)
        scr = self.screen()
        size = scr.size() * scr.devicePixelRatio() if scr else None
        args = effects.gamescope_args(s, (size.width(), size.height()) if size else None)
        self.gs_preview.setText("gamescope " + " ".join(shlex.quote(a) for a in args) + " -- <game>"
                                + ("" if s.opt_gamescope else "   (not used: gamescope is off)"))
