"""News panel for the Play tab: lotro.com launcher feed, with this week's coupon code up top."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QStyle, QTextBrowser, QVBoxLayout, QWidget

from .. import news
from .context import AppContext
from .theme import GOLD
from .workers import run_task

REFRESH_MS = 30 * 60 * 1000


class NewsPanel(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.coupon: news.Coupon | None = None

        title = QLabel("News")
        title.setStyleSheet(f"font-size: 14pt; color: {GOLD};")
        self.refresh = QPushButton()
        self.refresh.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.refresh.setToolTip("Reload news from lotro.com")
        head = QHBoxLayout()
        head.addWidget(title)
        head.addStretch()
        head.addWidget(self.refresh)

        # --- weekly coupon
        self.coupon_box = QFrame()
        self.coupon_box.setObjectName("coupon")
        self.coupon_box.setStyleSheet(
            f"QFrame#coupon {{ border: 1px solid {GOLD}; border-radius: 6px; background: #2b261c; }}")
        self.coupon_caption = QLabel("WEEKLY COUPON")
        self.coupon_caption.setStyleSheet("color: #b8a37a; font-size: 8.5pt; letter-spacing: 2px;")
        self.coupon_code = QLabel()
        self.coupon_code.setStyleSheet(f"color: {GOLD}; font-size: 17pt; font-weight: 600; letter-spacing: 1px;")
        self.coupon_code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.coupon_detail = QLabel()
        self.coupon_detail.setWordWrap(True)
        self.coupon_detail.setOpenExternalLinks(True)
        self.copy = QPushButton("Copy code")
        cl = QVBoxLayout(self.coupon_box)
        cl.setContentsMargins(12, 8, 12, 10)
        cl.addWidget(self.coupon_caption)
        row = QHBoxLayout()
        row.addWidget(self.coupon_code, 1)
        row.addWidget(self.copy)
        cl.addLayout(row)
        cl.addWidget(self.coupon_detail)
        self.coupon_box.hide()

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.document().setDefaultStyleSheet(
            f"a {{ color: {GOLD}; text-decoration: none; }} h4 {{ margin: 0; }} "
            ".date { color: #8a8270; } p { margin-top: 2px; margin-bottom: 4px; }")
        self.status = QLabel()
        self.status.setProperty("subtle", True)
        self.status.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(head)
        lay.addWidget(self.coupon_box)
        lay.addWidget(self.browser, 1)
        lay.addWidget(self.status)

        self.refresh.clicked.connect(self.load)
        self.copy.clicked.connect(self._copy)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.load)
        self._timer.start(REFRESH_MS)
        self.load()

    def load(self) -> None:
        url = news.feed_url(None, self.ctx.settings.language)
        self.refresh.setEnabled(False)
        self.status.setText("Loading news…")
        run_task(lambda: news.fetch(url), on_done=self._loaded, on_error=self._failed)

    def _loaded(self, res) -> None:
        items, cached = res
        self.refresh.setEnabled(True)
        self.status.setText("Offline: showing the last news downloaded." if cached else "")
        self.status.setVisible(cached)
        self._show_coupon(news.find_coupon(items))
        parts = []
        for it in items[:25]:
            title = html.escape(it.title)
            head = f'<a href="{html.escape(it.link, quote=True)}">{title}</a>' if it.link else title
            parts.append(f"<h4>{head}</h4><div class='date'><small>{html.escape(it.date)}</small></div>"
                         f"{it.html}<hr>")
        self.browser.setHtml("".join(parts) or "<i>No news.</i>")

    def _failed(self, e: Exception) -> None:
        self.refresh.setEnabled(True)
        self.status.setText(f"Could not load news: {e}")
        self.status.show()

    def _show_coupon(self, c: news.Coupon | None) -> None:
        self.coupon = c
        if c is None:
            self.coupon_box.hide()
            return
        self.coupon_code.setText(c.code)
        detail = " · ".join(html.escape(x) for x in (c.item, c.until) if x)
        if c.link:
            detail += (" · " if detail else "") + f'<a href="{html.escape(c.link, quote=True)}" ' \
                      f'style="color:{GOLD}">{html.escape(c.sale or "details")}</a>'
        self.coupon_detail.setText(detail)
        self.copy.setText("Copy code")
        self.coupon_box.show()

    def _copy(self) -> None:
        if self.coupon:
            QGuiApplication.clipboard().setText(self.coupon.code)
            self.copy.setText("Copied ✔")
            QTimer.singleShot(2000, lambda: self.copy.setText("Copy code"))
