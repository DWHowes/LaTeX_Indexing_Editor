import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from controllers.app_style_configuration import AppStyleConfiguration
from models.app_paths import get_app_root
from models.app_version import (
    APP_COPYRIGHT,
    APP_LICENCE,
    APP_NAME,
    APP_TAGLINE,
    APP_URL,
    version_string,
)


class AboutDialog(QDialog):
    """
    Help > About. The wordmark, the version, and the handful of facts a
    user needs when reporting a problem.

    The logo comes in a light-ink and a dark-ink variant rather than being
    recoloured at runtime: it is a bitmap, and the alternative -- tinting
    it -- would have to composite over the antialiased edges of Computer
    Modern's very fine serifs, which is exactly where a tint goes wrong.
    apply_theme_configuration swaps between them.
    """

    LOGO_WIDTH = 300

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setModal(True)
        self._build_ui()

    def _build_ui(self) -> None:
        icons = get_app_root() / "icons"
        self._logo_dark_ink = QPixmap(str(icons / "lidx_wordmark.png"))
        self._logo_light_ink = QPixmap(str(icons / "lidx_wordmark_light.png"))

        self._logo_label = QLabel()
        self._logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_logo(self._logo_dark_ink)

        name = QLabel(APP_NAME)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = name.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        name.setFont(font)

        tagline = QLabel(APP_TAGLINE)
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setWordWrap(True)

        version = QLabel(version_string())
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Qt and Python versions are here because they are the first things
        # asked for on a bug report and the last things a user knows how to
        # find. Read at runtime rather than hard-coded so a packaged build
        # reports what it actually shipped with.
        runtime = QLabel(
            f"Python {sys.version_info.major}.{sys.version_info.minor}"
            f".{sys.version_info.micro} · Qt {self._qt_version()}"
        )
        runtime.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Colour is set per theme in apply_theme_configuration: an <a> takes
        # Qt's default link colour, a dark blue that is unreadable against
        # the dark theme's background and immune to the dialog stylesheet.
        self._link_label = QLabel()
        self._link_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._link_label.setOpenExternalLinks(True)
        self._link_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self._set_link_colour(is_dark=False)
        link = self._link_label

        legal = QLabel(f"{APP_COPYRIGHT}\n{APP_LICENCE}")
        legal.setAlignment(Qt.AlignmentFlag.AlignCenter)

        buttons = QDialogButtonBox()
        close_button = buttons.addButton("Close", QDialogButtonBox.ButtonRole.AcceptRole)
        close_button.clicked.connect(self.accept)
        close_button.setDefault(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.addWidget(self._logo_label)
        layout.addSpacing(14)
        layout.addWidget(name)
        layout.addWidget(tagline)
        layout.addSpacing(10)
        layout.addWidget(version)
        layout.addWidget(runtime)
        layout.addSpacing(10)
        layout.addWidget(link)
        layout.addSpacing(10)
        layout.addWidget(legal)
        layout.addSpacing(16)
        layout.addWidget(buttons, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setFixedWidth(self.LOGO_WIDTH + 90)

    @staticmethod
    def _qt_version() -> str:
        from PySide6.QtCore import qVersion

        return qVersion()

    def _set_logo(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            # A missing asset must not take the dialog down with it -- the
            # About box is often the first thing opened when something is
            # already wrong.
            self._logo_label.setText(APP_NAME)
            return
        self._logo_label.setPixmap(
            pixmap.scaledToWidth(
                self.LOGO_WIDTH,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _set_link_colour(self, is_dark: bool) -> None:
        colour = "#8AB4F8" if is_dark else "#1F3864"
        self._link_label.setText(
            f'<a href="{APP_URL}" style="color:{colour};">{APP_URL}</a>'
        )

    def apply_theme_configuration(self, is_dark: bool) -> None:
        self.setStyleSheet(AppStyleConfiguration.get_dialog_stylesheet_for(is_dark))
        self._set_logo(self._logo_light_ink if is_dark else self._logo_dark_ink)
        self._set_link_colour(is_dark)
