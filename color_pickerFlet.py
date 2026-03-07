# -*- coding: utf-8 -*-
"""Flet 实时取色器：跟随鼠标取色，支持 RGB / HEX 显示与复制。"""

from __future__ import annotations

import asyncio
import ctypes
import sys
import tkinter as tk

import flet as ft
import pyautogui
from PIL import ImageGrab


class ColorPickerApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.running = True
        self.display_mode = "RGB"
        self.enable_dpi_awareness()
        self.display_scale = self.get_display_scale()

        self.current_x = 0
        self.current_y = 0
        self.current_r = 255
        self.current_g = 255
        self.current_b = 255
        self.pause_by_space = False
        self.pause_by_window = False
        self.clipboard_helper: tk.Tk | None = None

        self.main_container: ft.Container | None = None
        self.hex_label_text: ft.Text | None = None
        self.main_code_text: ft.Text | None = None
        self.hex_text: ft.Text | None = None
        self.rgb_text: ft.Text | None = None
        self.pos_text: ft.Text | None = None
        self.tip_text: ft.Text | None = None
        self.copy_btn: ft.Container | None = None
        self.copy_label: ft.Text | None = None
        self.mode_switch: ft.Switch | None = None

    def enable_dpi_awareness(self):
        try:
            if not sys.platform.startswith("win"):
                return

            user32 = ctypes.windll.user32
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                user32.SetProcessDPIAware()
        except Exception:
            pass

    def get_display_scale(self) -> float:
        try:
            if sys.platform.startswith("win"):
                user32 = ctypes.windll.user32
                gdi32 = ctypes.windll.gdi32
                dc = user32.GetDC(0)
                dpi_x = gdi32.GetDeviceCaps(dc, 88)
                user32.ReleaseDC(0, dc)
                return max(1.0, dpi_x / 96.0)
        except Exception:
            pass
        return 1.0

    def rgb_to_hex(self, r: int, g: int, b: int) -> str:
        return f"#{r:02X}{g:02X}{b:02X}"

    def rgb_to_cmyk(self, r: int, g: int, b: int) -> tuple[int, int, int, int]:
        if r == 0 and g == 0 and b == 0:
            return 0, 0, 0, 100

        r_n = r / 255
        g_n = g / 255
        b_n = b / 255
        k = 1 - max(r_n, g_n, b_n)
        c = (1 - r_n - k) / (1 - k)
        m = (1 - g_n - k) / (1 - k)
        y = (1 - b_n - k) / (1 - k)

        return round(c * 100), round(m * 100), round(y * 100), round(k * 100)

    def get_contrast_color(self, r: int, g: int, b: int) -> str:
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        return "#000000" if brightness >= 128 else "#FFFFFF"

    def get_display_code(self) -> str:
        if self.display_mode == "CMYK":
            c, m, y, k = self.rgb_to_cmyk(self.current_r, self.current_g, self.current_b)
            return f"CMYK({c}, {m}, {y}, {k})"
        return f"RGB({self.current_r}, {self.current_g}, {self.current_b})"

    def get_decimal_values(self) -> str:
        if self.display_mode == "CMYK":
            c, m, y, k = self.rgb_to_cmyk(self.current_r, self.current_g, self.current_b)
            return f"({c}, {m}, {y}, {k})"
        return f"({self.current_r}, {self.current_g}, {self.current_b})"

    def get_pixel_color(self, x: int, y: int) -> tuple[int, int, int]:
        try:
            grab_args = {"bbox": (x, y, x + 1, y + 1)}
            if sys.platform.startswith("win"):
                grab_args["all_screens"] = True
            pixel = ImageGrab.grab(**grab_args).getpixel((0, 0))
            return pixel[:3]
        except Exception:
            return 255, 255, 255

    def get_window_bounds_px(self) -> tuple[float, float, float, float] | None:
        try:
            left = self.page.window.left
            top = self.page.window.top
            width = self.page.window.width
            height = self.page.window.height
            if left is None or top is None or width is None or height is None:
                return None

            scale = self.display_scale
            left_px = round(left * scale)
            top_px = round(top * scale)
            width_px = round(width * scale)
            height_px = round(height * scale)
            return left_px, top_px, width_px, height_px
        except Exception:
            return None

    def is_cursor_in_window(self, x: int, y: int) -> bool:
        bounds = self.get_window_bounds_px()
        if bounds is None:
            return False

        left_px, top_px, width_px, height_px = bounds
        margin = max(3, round(self.display_scale * 4))
        right_px = left_px + width_px
        bottom_px = top_px + height_px

        return (
            left_px + margin <= x <= right_px - margin
            and top_px + margin <= y <= bottom_px - margin
        )

    def on_mode_switch_change(self, e):
        self.display_mode = "CMYK" if e.control.value else "RGB"
        self.refresh_ui()
        self.page.update()

    def toggle_space_pause(self):
        self.pause_by_space = not self.pause_by_space
        self.refresh_ui()
        self.page.update()

    def on_keyboard(self, e: ft.KeyboardEvent):
        if e.key == " ":
            self.toggle_space_pause()

    def copy_text_to_clipboard(self, text: str) -> bool:
        try:
            if self.clipboard_helper is None:
                self.clipboard_helper = tk.Tk()
                self.clipboard_helper.withdraw()

            self.clipboard_helper.clipboard_clear()
            self.clipboard_helper.clipboard_append(text)
            self.clipboard_helper.update()
            return True
        except Exception:
            return False

    def copy_code(self, _=None):
        code = self.get_display_code()
        if self.copy_text_to_clipboard(code):
            self.tip_text.value = f"已复制: {code}"
        else:
            self.tip_text.value = "复制失败"
        self.page.update()

    def build_glass_button(self, label: str, width: int, on_click) -> tuple[ft.Container, ft.Text]:
        text = ft.Text(label, size=11, weight=ft.FontWeight.W_500, text_align=ft.TextAlign.CENTER)
        button = ft.Container(
            width=width,
            height=38,
            border_radius=12,
            padding=0,
            bgcolor="#F3F3F380",
            border=ft.border.all(1, "#FFFFFF90"),
            ink=True,
            on_click=on_click,
            content=ft.Row(
                controls=[text],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        return button, text

    def update_button_styles(self, text_color: str):
        inactive_bg = ft.Colors.with_opacity(0.10, text_color)
        border_color = ft.Colors.with_opacity(0.35, text_color)

        self.copy_btn.bgcolor = inactive_bg
        self.copy_btn.border = ft.border.all(1, border_color)
        self.copy_label.color = text_color

    def refresh_ui(self, paused: bool | None = None):
        if paused is None:
            paused = self.pause_by_window or self.pause_by_space

        hex_code = self.rgb_to_hex(self.current_r, self.current_g, self.current_b)
        text_color = self.get_contrast_color(self.current_r, self.current_g, self.current_b)

        self.main_container.bgcolor = hex_code
        self.hex_label_text.color = text_color
        self.main_code_text.value = hex_code
        self.main_code_text.color = text_color
        self.hex_text.value = self.get_display_code()
        self.hex_text.color = text_color
        self.rgb_text.value = f"HEX: {hex_code}"
        self.rgb_text.color = text_color
        self.pos_text.value = f"POS: ({self.current_x}, {self.current_y})"
        self.pos_text.color = text_color
        self.tip_text.color = text_color
        if self.pause_by_space:
            self.tip_text.value = "已暂停取色（空格键恢复）"
        elif self.pause_by_window:
            self.tip_text.value = "已暂停取色（鼠标在窗口内）"
        else:
            self.tip_text.value = "移动鼠标实时取色 | 空格键暂停"

        self.update_button_styles(text_color)

    async def update_color_loop(self):
        pyautogui.FAILSAFE = False

        while self.running:
            try:
                x, y = pyautogui.position()
                self.current_x = x
                self.current_y = y
                self.pause_by_window = self.is_cursor_in_window(x, y)
                paused = self.pause_by_window or self.pause_by_space

                if paused:
                    self.refresh_ui()
                    self.page.update()
                    await asyncio.sleep(0.05)
                    continue

                self.current_r, self.current_g, self.current_b = self.get_pixel_color(x, y)
                self.refresh_ui()
                self.page.update()
            except Exception as exc:
                self.tip_text.value = f"取色失败: {exc}"
                self.page.update()

            await asyncio.sleep(0.05)

    def build(self):
        self.page.title = "Flet 实时取色器"
        self.page.window.width = 300
        self.page.window.height = 220
        self.page.window.resizable = False
        self.page.window.always_on_top = True
        self.page.padding = 0
        self.page.spacing = 0

        def on_window_event(e: ft.WindowEvent):
            if e.data == "close":
                self.running = False
                if self.clipboard_helper is not None:
                    self.clipboard_helper.destroy()
                    self.clipboard_helper = None
                self.page.window.destroy()

        self.page.window.on_event = on_window_event
        self.page.on_keyboard_event = self.on_keyboard

        self.hex_label_text = ft.Text("", size=14, font_family="Consolas")

        self.main_code_text = ft.Text(
            value="#FFFFFF",
            size=32,
            weight=ft.FontWeight.BOLD,
            font_family="Consolas",
        )
        self.hex_text = ft.Text(
            value="RGB(255, 255, 255)",
            size=14,
            font_family="Consolas",
        )
        self.rgb_text = ft.Text(
            value="RGB: 255, 255, 255",
            size=14,
            font_family="Consolas",
        )
        self.pos_text = ft.Text(
            value="POS: (0, 0)",
            size=14,
            font_family="Consolas",
        )
        self.tip_text = ft.Text(
            value="移动鼠标实时取色",
            size=10,
        )

        self.copy_btn, self.copy_label = self.build_glass_button("复制", 56, self.copy_code)
        self.mode_switch = ft.Switch(value=False, scale=0.8, on_change=self.on_mode_switch_change)

        header_row = ft.Row(
            controls=[
                self.hex_label_text,
                self.main_code_text,
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        info_column = ft.Column(
            controls=[
                header_row,
                self.hex_text,
                self.pos_text,
            ],
            spacing=6,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )

        mode_row = ft.Row(
            controls=[self.mode_switch],
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        buttons_row = ft.Row(
            controls=[self.copy_btn, mode_row],
            spacing=8,
            wrap=False,
            alignment=ft.MainAxisAlignment.START,
        )

        self.main_container = ft.Container(
            expand=True,
            bgcolor="#FFFFFF",
            padding=ft.padding.only(left=12, right=12, top=12, bottom=10),
            content=ft.Column(
                controls=[
                    info_column,
                    ft.Container(height=8),
                    buttons_row,
                    ft.Container(expand=True),
                    self.tip_text,
                ],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.START,
            ),
        )

        self.page.add(self.main_container)
        self.refresh_ui()
        self.page.run_task(self.update_color_loop)


def main(page: ft.Page):
    app = ColorPickerApp(page)
    app.build()


if __name__ == "__main__":
    ft.app(target=main)
