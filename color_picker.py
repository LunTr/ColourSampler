# -*- coding: utf-8 -*-
"""
屏幕取色器 - 实时获取鼠标位置的颜色
需要安装: pip install pillow pyautogui PyQt6
"""

from dataclasses import dataclass
import logging
import sys
import time
from typing import Optional

import pyautogui
from PIL import ImageGrab
from PyQt6.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QKeySequence, QPalette, QShortcut, QCloseEvent
from PyQt6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QLabel, QPushButton, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout


logger = logging.getLogger(__name__)

WINDOW_WIDTH = 320
WINDOW_HEIGHT = 200
REFRESH_INTERVAL = 0.05
DEFAULT_HEX = "#FFFFFF"
DEFAULT_RGB_TEXT = "255, 255, 255"
DEFAULT_POSITION_TEXT = "(0, 0)"
DEFAULT_TEXT_COLOR = "#000000"
DEFAULT_SHADOW_COLOR = "#ffffff"
LIVE_TIP_TEXT = "移动鼠标实时取色 | 空格键锁定"
LOCKED_TIP_TEXT = "已锁定 | 空格键解锁"
WINDOW_PAUSE_TIP_TEXT = "已暂停取色（鼠标在窗口内）"
COPY_FAILED_TEXT = "复制失败"
LOCKED_TIP_COLOR = "#ff6666"
BUTTON_TEXT_COLOR = "#333333"
BUTTON_BG_COLOR = "#f0f0f0"
BUTTON_BORDER_COLOR = "#ffffff"


@dataclass(frozen=True)
class ColorSample:
    x: int
    y: int
    r: int
    g: int
    b: int
    hex_color: str
    rgb_text: str
    pos_text: str
    text_color: str
    shadow_color: str


@dataclass
class PickerState:
    running: bool = True
    locked: bool = False
    paused_by_window: bool = False
    current_hex: str = DEFAULT_HEX
    current_rgb: str = DEFAULT_RGB_TEXT
    current_text_color: str = DEFAULT_TEXT_COLOR
    current_shadow_color: str = DEFAULT_SHADOW_COLOR
    last_sample: Optional[ColorSample] = None


class ScreenColorSampler:
    """负责采样鼠标位置与屏幕像素颜色，不依赖具体 UI。"""

    def get_mouse_position(self) -> Optional[tuple[int, int]]:
        try:
            point = pyautogui.position()
            return point.x, point.y
        except OSError as exc:
            logger.warning("Failed to read mouse position: %s", exc)
            return None
        except Exception:
            logger.exception("Unexpected error while reading mouse position")
            return None

    def get_pixel_color(self, x: int, y: int) -> Optional[tuple[int, int, int]]:
        try:
            screenshot = ImageGrab.grab(bbox=(x, y, x + 1, y + 1))
            pixel = screenshot.getpixel((0, 0))
            return tuple(pixel[:3])
        except OSError as exc:
            logger.warning("Failed to sample screen pixel at (%s, %s): %s", x, y, exc)
            return None
        except Exception:
            logger.exception("Unexpected error while sampling screen pixel at (%s, %s)", x, y)
            return None


def format_hex_color(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def format_rgb_text(r: int, g: int, b: int) -> str:
    return f"{r}, {g}, {b}"


def format_position_text(x: int, y: int) -> str:
    return f"({x}, {y})"


def get_contrast_colors(r: int, g: int, b: int, threshold: int = 128) -> tuple[str, str]:
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    if brightness > threshold:
        return "#000000", "#ffffff"
    return "#ffffff", "#333333"


def build_color_sample(x: int, y: int, rgb: tuple[int, int, int]) -> ColorSample:
    r, g, b = rgb
    text_color, shadow_color = get_contrast_colors(r, g, b)
    return ColorSample(
        x=x,
        y=y,
        r=r,
        g=g,
        b=b,
        hex_color=format_hex_color(r, g, b),
        rgb_text=format_rgb_text(r, g, b),
        pos_text=format_position_text(x, y),
        text_color=text_color,
        shadow_color=shadow_color,
    )


def sample_current_color(sampler: ScreenColorSampler) -> Optional[ColorSample]:
    position = sampler.get_mouse_position()
    if position is None:
        return None

    x, y = position
    rgb = sampler.get_pixel_color(x, y)
    if rgb is None:
        return None

    return build_color_sample(x, y, rgb)


class ColorSamplerWorker(QObject):
    sample_ready = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, state: PickerState, sampler: ScreenColorSampler):
        super().__init__()
        self.state = state
        self.sampler = sampler
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            while self._running and self.state.running:
                if self.state.locked or self.state.paused_by_window:
                    time.sleep(REFRESH_INTERVAL)
                    continue

                try:
                    sample = sample_current_color(self.sampler)
                    if sample is not None:
                        self.sample_ready.emit(sample)
                except Exception:
                    logger.exception("Unexpected error in color sampler worker")

                time.sleep(REFRESH_INTERVAL)
        finally:
            self.finished.emit()


class ColorPicker(QWidget):
    def __init__(self):
        super().__init__()
        self.state = PickerState()
        self.sampler = ScreenColorSampler()
        self.is_closing = False
        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[ColorSamplerWorker] = None

        self.tip_restore_timer = QTimer(self)
        self.tip_restore_timer.setSingleShot(True)
        self.tip_restore_timer.timeout.connect(self.restore_tip)

        self.cursor_pause_timer = QTimer(self)
        self.cursor_pause_timer.timeout.connect(self._update_pause_by_window)
        self.cursor_pause_timer.start(int(REFRESH_INTERVAL * 1000))

        self.space_shortcut = QShortcut(QKeySequence("Space"), self)
        self.space_shortcut.activated.connect(self.toggle_lock)

        self.setWindowTitle("屏幕取色器")
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAutoFillBackground(True)

        self.setup_ui()
        self._set_background_color(DEFAULT_HEX)
        self.start_color_thread()

    def setup_ui(self):
        title_font = QFont("Consolas", 12, QFont.Weight.Bold)
        large_value_font = QFont("Consolas", 32, QFont.Weight.Bold)
        small_title_font = QFont("Consolas", 10, QFont.Weight.Bold)
        value_font = QFont("Consolas", 12)
        tip_font = QFont("Microsoft YaHei", 8)
        button_font = QFont("Microsoft YaHei", 10, QFont.Weight.Bold)

        self.label_shadow_effects: dict[QLabel, QGraphicsDropShadowEffect] = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 12, 15, 12)
        main_layout.setSpacing(6)

        # HEX Layout
        hex_layout = QHBoxLayout()
        self.hex_text = self._create_label("HEX:", title_font)
        self.hex_val_text = self._create_label(DEFAULT_HEX, large_value_font)
        hex_layout.addWidget(self.hex_text)
        hex_layout.addSpacing(5)
        hex_layout.addWidget(self.hex_val_text)
        hex_layout.addStretch()
        main_layout.addLayout(hex_layout)

        # Middle Grid
        grid_layout = QGridLayout()
        grid_layout.setSpacing(5)
        self.rgb_text = self._create_label("RGB:", small_title_font)
        self.rgb_val_text = self._create_label(DEFAULT_RGB_TEXT, value_font)
        self.pos_text = self._create_label("POS:", small_title_font)
        self.pos_val_text = self._create_label(DEFAULT_POSITION_TEXT, value_font)

        grid_layout.addWidget(self.rgb_text, 0, 0)
        grid_layout.addWidget(self.rgb_val_text, 0, 1)
        grid_layout.addWidget(self.pos_text, 1, 0)
        grid_layout.addWidget(self.pos_val_text, 1, 1)
        grid_layout.setColumnStretch(1, 1)
        
        # Center horizontally wrapper
        mid_layout = QHBoxLayout()
        mid_layout.addLayout(grid_layout)
        mid_layout.addStretch()
        main_layout.addLayout(mid_layout)

        main_layout.addSpacing(5)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.hex_btn = QPushButton("复制 HEX", self)
        self.hex_btn.setFont(button_font)
        self.hex_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hex_btn.clicked.connect(self.copy_hex)
        self._apply_copy_button_style(self.hex_btn)
        self._apply_widget_shadow(self.hex_btn, "#000000", 90, 15, 0, 3)

        self.rgb_btn = QPushButton("复制 RGB", self)
        self.rgb_btn.setFont(button_font)
        self.rgb_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rgb_btn.clicked.connect(self.copy_rgb)
        self._apply_copy_button_style(self.rgb_btn)
        self._apply_widget_shadow(self.rgb_btn, "#000000", 90, 15, 0, 3)

        btn_layout.addWidget(self.hex_btn)
        btn_layout.addWidget(self.rgb_btn)
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        main_layout.addStretch()

        self.tip_text = self._create_label(LIVE_TIP_TEXT, tip_font)
        self.tip_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.tip_text)

        self.content_labels = [
            self.hex_text,
            self.hex_val_text,
            self.rgb_text,
            self.rgb_val_text,
            self.pos_text,
            self.pos_val_text,
        ]

        self._apply_label_colors(self.content_labels, "white", "#333333")
        self._set_tip(LIVE_TIP_TEXT, text_color="white", shadow_color="#333333")

    def _create_label(self, text: str, font: QFont) -> QLabel:
        label = QLabel(text, self)
        label.setFont(font)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet("background-color: transparent;")
        self.label_shadow_effects[label] = self._apply_widget_shadow(label, "#333333", 170, 10, 1, 2)
        return label

    def _with_alpha(self, color: str, alpha: int) -> QColor:
        alpha = max(0, min(255, alpha))
        rgba_color = QColor(color)
        rgba_color.setAlpha(alpha)
        return rgba_color

    def _to_rgba_css(self, color: str, alpha: int) -> str:
        rgba_color = self._with_alpha(color, alpha)
        return f"rgba({rgba_color.red()}, {rgba_color.green()}, {rgba_color.blue()}, {rgba_color.alpha()})"

    def _apply_widget_shadow(
        self,
        widget: QWidget,
        color: str,
        alpha: int,
        blur_radius: float,
        offset_x: int,
        offset_y: int,
    ) -> QGraphicsDropShadowEffect:
        effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(blur_radius)
        effect.setOffset(offset_x, offset_y)
        effect.setColor(self._with_alpha(color, alpha))
        widget.setGraphicsEffect(effect)
        return effect

    def _apply_copy_button_style(self, button: QPushButton):
        button.setStyleSheet(
            "QPushButton {"
            f"background-color: {self._to_rgba_css(BUTTON_BG_COLOR, 190)};"
            f"border: 1px solid {self._to_rgba_css(BUTTON_BORDER_COLOR, 220)};"
            "border-radius: 8px;"
            f"color: {BUTTON_TEXT_COLOR};"
            "padding: 4px 12px;"
            "}"
            "QPushButton:hover {"
            f"background-color: {self._to_rgba_css(BUTTON_BG_COLOR, 220)};"
            "}"
            "QPushButton:pressed {"
            f"background-color: {self._to_rgba_css(BUTTON_BG_COLOR, 255)};"
            "padding-top: 5px;"
            "padding-left: 13px;"
            "padding-bottom: 3px;"
            "padding-right: 11px;"
            "}"
        )

    def _set_background_color(self, color: str):
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(color))
        self.setPalette(palette)

    def _apply_label_colors(self, labels: list[QLabel], text_color: str, shadow_color: str):
        for label in labels:
            label.setStyleSheet(f"color: {text_color}; background-color: transparent;")
            effect = self.label_shadow_effects.get(label)
            if effect is not None:
                effect.setColor(self._with_alpha(shadow_color, 170))

    def _set_label_text(self, label: QLabel, value: str):
        label.setText(value)

    def toggle_lock(self):
        self.state.locked = not self.state.locked
        self.restore_tip()

    def _set_tip(self, text: str, text_color: Optional[str] = None, shadow_color: Optional[str] = None):
        if text_color is None:
            text_color = self.state.current_text_color
        if shadow_color is None:
            shadow_color = self.state.current_shadow_color

        self._set_label_text(self.tip_text, text)
        self._apply_label_colors([self.tip_text], text_color, shadow_color)

    def _show_live_tip(self):
        self._set_tip(
            LIVE_TIP_TEXT,
            text_color=self.state.current_text_color,
            shadow_color=self.state.current_shadow_color,
        )

    def _show_locked_tip(self):
        self._set_tip(
            LOCKED_TIP_TEXT,
            text_color=LOCKED_TIP_COLOR,
            shadow_color=self.state.current_shadow_color,
        )

    def _show_window_pause_tip(self):
        self._set_tip(
            WINDOW_PAUSE_TIP_TEXT,
            text_color=self.state.current_text_color,
            shadow_color=self.state.current_shadow_color,
        )

    def _show_copy_tip(self, message: str):
        self._set_tip(
            message,
            text_color=self.state.current_text_color,
            shadow_color=self.state.current_shadow_color,
        )
        self._schedule_tip_restore()

    def _schedule_tip_restore(self):
        self.tip_restore_timer.stop()
        self.tip_restore_timer.start(1500)

    def _is_cursor_inside_window(self) -> bool:
        # Keep the check in Qt's coordinate space to avoid DPI scaling mismatches.
        margin = 4
        local_point = self.mapFromGlobal(QCursor.pos())
        content_rect = self.rect().adjusted(margin, margin, -margin, -margin)
        return content_rect.contains(local_point)

    def _update_pause_by_window(self):
        if self.is_closing or self.state.locked:
            if self.state.paused_by_window:
                self.state.paused_by_window = False
            return

        paused_by_window = self._is_cursor_inside_window()

        if self.state.paused_by_window == paused_by_window:
            return

        self.state.paused_by_window = paused_by_window
        if paused_by_window:
            self._show_window_pause_tip()
        else:
            self._show_live_tip()

    def start_color_thread(self):
        self.worker_thread = QThread(self)
        self.worker = ColorSamplerWorker(self.state, self.sampler)
        self.worker.moveToThread(self.worker_thread)
        self.worker.sample_ready.connect(self._apply_sample_to_ui)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()

    def _apply_sample_to_ui(self, sample: object):
        if self.is_closing or not isinstance(sample, ColorSample):
            return

        self._set_background_color(sample.hex_color)
        self._apply_label_colors(self.content_labels, sample.text_color, sample.shadow_color)

        self._set_label_text(self.hex_val_text, sample.hex_color)
        self._set_label_text(self.rgb_val_text, sample.rgb_text)
        self._set_label_text(self.pos_val_text, sample.pos_text)

        self.state.current_hex = sample.hex_color
        self.state.current_rgb = sample.rgb_text
        self.state.current_text_color = sample.text_color
        self.state.current_shadow_color = sample.shadow_color
        self.state.last_sample = sample

        if self.state.locked:
            self._show_locked_tip()
        elif self.state.paused_by_window:
            self._show_window_pause_tip()
        else:
            self._show_live_tip()

    def _copy_to_clipboard(self, value: str, value_name: str):
        try:
            QApplication.clipboard().setText(value)
        except Exception:
            logger.exception("Failed to copy %s to clipboard", value_name)
            self._show_copy_tip(COPY_FAILED_TEXT)
            return

        self._show_copy_tip(f"已复制{value_name}值!")

    def copy_hex(self):
        self._copy_to_clipboard(self.state.current_hex, "HEX")

    def copy_rgb(self):
        self._copy_to_clipboard(self.state.current_rgb, "RGB")

    def restore_tip(self):
        if self.state.locked:
            self._show_locked_tip()
        elif self.state.paused_by_window:
            self._show_window_pause_tip()
        else:
            self._show_live_tip()

    def closeEvent(self, event: QCloseEvent):
        self.is_closing = True
        self.state.running = False
        self.tip_restore_timer.stop()
        self.cursor_pause_timer.stop()

        if self.worker is not None:
            self.worker.stop()

        if self.worker_thread is not None and self.worker_thread.isRunning():
            self.worker_thread.quit()
            if not self.worker_thread.wait(2000):
                logger.warning("Color sampler thread did not stop before shutdown.")

        event.accept()
        super().closeEvent(event)


if __name__ == "__main__":
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    app = QApplication(sys.argv)
    window = ColorPicker()
    window.show()
    window.activateWindow()
    window.setFocus()
    sys.exit(app.exec())
