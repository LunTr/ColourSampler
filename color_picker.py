# -*- coding: utf-8 -*-
"""
屏幕取色器 - 实时获取鼠标位置的颜色
需要安装: pip install pillow pyautogui
"""

import tkinter as tk
import pyautogui
from PIL import ImageGrab
import threading
import time


class ColorPicker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("屏幕取色器")
        self.root.geometry("560x300")
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)  # 窗口置顶

        self.running = True
        self.locked = False  # 锁定状态
        self.current_color = "#FFFFFF"
        self.current_hex = "#FFFFFF"
        self.current_rgb = "255, 255, 255"
        self.current_text_color = "#000000"
        self.current_shadow_color = "#ffffff"

        self.setup_ui()
        self.bind_keys()
        self.start_color_thread()

    def setup_ui(self):
        # 主画布，用于绘制带阴影的文字
        self.canvas = tk.Canvas(self.root, width=560, height=300,
                                 bg="#FFFFFF", highlightthickness=0)
        self.canvas.place(x=0, y=0)

        # 创建带阴影的文字（阴影在下，白字在上）
        # HEX标签
        self.hex_shadow = self.canvas.create_text(50, 55, text="HEX:",
                                                   font=("Consolas", 14), fill="#333333", anchor="w")
        self.hex_text = self.canvas.create_text(48, 53, text="HEX:",
                                                 font=("Consolas", 14), fill="white", anchor="w")

        # HEX值（大字）
        self.hex_val_shadow = self.canvas.create_text(130, 55, text="#FFFFFF",
                                                       font=("Consolas", 28, "bold"), fill="#333333", anchor="w")
        self.hex_val_text = self.canvas.create_text(128, 53, text="#FFFFFF",
                                                     font=("Consolas", 28, "bold"), fill="white", anchor="w")

        # RGB标签和值（字体调小）
        self.rgb_shadow = self.canvas.create_text(50, 105, text="RGB:",
                                                   font=("Consolas", 12), fill="#333333", anchor="w")
        self.rgb_text = self.canvas.create_text(48, 103, text="RGB:",
                                                 font=("Consolas", 12), fill="white", anchor="w")

        self.rgb_val_shadow = self.canvas.create_text(120, 105, text="255, 255, 255",
                                                       font=("Consolas", 14), fill="#333333", anchor="w")
        self.rgb_val_text = self.canvas.create_text(118, 103, text="255, 255, 255",
                                                     font=("Consolas", 14), fill="white", anchor="w")

        # 位置标签和值（字体调小，改为坐标格式）
        self.pos_shadow = self.canvas.create_text(50, 145, text="POS:",
                                                   font=("Consolas", 12), fill="#333333", anchor="w")
        self.pos_text = self.canvas.create_text(48, 143, text="POS:",
                                                 font=("Consolas", 12), fill="white", anchor="w")

        self.pos_val_shadow = self.canvas.create_text(120, 145, text="(0, 0)",
                                                       font=("Consolas", 14), fill="#333333", anchor="w")
        self.pos_val_text = self.canvas.create_text(118, 143, text="(0, 0)",
                                                     font=("Consolas", 14), fill="white", anchor="w")

        # 提示文字（移到左下角）
        self.tip_shadow = self.canvas.create_text(52, 272, text="移动鼠标实时取色",
                                                   font=("Microsoft YaHei", 10), fill="#333333", anchor="w")
        self.tip_text = self.canvas.create_text(50, 270, text="移动鼠标实时取色",
                                                 font=("Microsoft YaHei", 10), fill="white", anchor="w")

        # 毛玻璃效果的圆角矩形按钮
        # 复制HEX按钮
        self.hex_btn_shadow = self.create_rounded_rect(52, 192, 172, 232, 12, fill="#aaaaaa", outline="")
        self.hex_btn_bg = self.create_rounded_rect(50, 190, 170, 230, 12, fill="#f0f0f0", outline="#ffffff")
        self.hex_btn_text = self.canvas.create_text(110, 210, text="复制 HEX",
                                                     font=("Microsoft YaHei", 10), fill="#333333")
        self.canvas.tag_bind(self.hex_btn_bg, "<Button-1>", lambda _: self.copy_hex())
        self.canvas.tag_bind(self.hex_btn_text, "<Button-1>", lambda _: self.copy_hex())

        # 复制RGB按钮
        self.rgb_btn_shadow = self.create_rounded_rect(192, 192, 312, 232, 12, fill="#aaaaaa", outline="")
        self.rgb_btn_bg = self.create_rounded_rect(190, 190, 310, 230, 12, fill="#f0f0f0", outline="#ffffff")
        self.rgb_btn_text = self.canvas.create_text(250, 210, text="复制 RGB",
                                                     font=("Microsoft YaHei", 10), fill="#333333")
        self.canvas.tag_bind(self.rgb_btn_bg, "<Button-1>", lambda _: self.copy_rgb())
        self.canvas.tag_bind(self.rgb_btn_text, "<Button-1>", lambda _: self.copy_rgb())

        # 锁定状态开关（右上角，毛玻璃圆角矩形）
        self.lock_shadow = self.create_rounded_rect(502, 22, 542, 62, 20, fill="#aaaaaa", outline="")
        self.lock_bg = self.create_rounded_rect(500, 20, 540, 60, 20, fill="#4CAF50", outline="#ffffff")

        # 锁定开关点击事件
        self.canvas.tag_bind(self.lock_bg, "<Button-1>", self.toggle_lock)

    def create_rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        """创建圆角矩形"""
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def bind_keys(self):
        """绑定键盘事件"""
        self.root.bind("<space>", self.toggle_lock)
        self.root.focus_set()

    def toggle_lock(self, _event=None):
        """切换锁定状态"""
        self.locked = not self.locked
        if self.locked:
            # 锁定状态 - 红色指示器
            self.canvas.itemconfig(self.lock_bg, fill="#f44336")
            self.canvas.itemconfig(self.tip_shadow, text="已锁定 | 空格键/点击解锁")
            self.canvas.itemconfig(self.tip_text, text="已锁定 | 空格键/点击解锁", fill="#ff6666")
        else:
            # 取色状态 - 绿色指示器
            self.canvas.itemconfig(self.lock_bg, fill="#4CAF50")
            self.canvas.itemconfig(self.tip_shadow, text="移动鼠标实时取色", fill=self.current_shadow_color)
            self.canvas.itemconfig(self.tip_text, text="移动鼠标实时取色", fill=self.current_text_color)

    def get_pixel_color(self, x, y):
        """获取指定位置的像素颜色"""
        try:
            screenshot = ImageGrab.grab(bbox=(x, y, x + 1, y + 1))
            pixel = screenshot.getpixel((0, 0))
            return pixel[:3]  # 返回RGB
        except Exception:
            return (255, 255, 255)

    def get_contrast_color(self, r, g, b, threshold=128):
        """根据背景亮度返回对比色（黑或白）"""
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        if brightness > threshold:
            return "#000000", "#ffffff"  # 背景亮，用黑字白阴影
        else:
            return "#ffffff", "#333333"  # 背景暗，用白字深灰阴影

    def update_color(self):
        """更新颜色显示"""
        while self.running:
            try:
                if not self.locked:  # 只在未锁定时更新
                    x, y = pyautogui.position()
                    r, g, b = self.get_pixel_color(x, y)

                    hex_color = f"#{r:02X}{g:02X}{b:02X}"
                    self.current_color = hex_color

                    # 更新UI（线程安全）
                    self.root.after(0, lambda: self.update_ui(hex_color, r, g, b, x, y))

            except Exception:
                pass

            time.sleep(0.05)  # 50ms刷新一次

    def update_ui(self, hex_color, r, g, b, x, y):
        """更新界面显示"""
        try:
            # 更新背景色
            self.canvas.config(bg=hex_color)

            # 获取对比色
            text_color, shadow_color = self.get_contrast_color(r, g, b)

            # 更新所有文字颜色
            for text_item in [self.hex_text, self.hex_val_text, self.rgb_text,
                              self.rgb_val_text, self.pos_text, self.pos_val_text]:
                self.canvas.itemconfig(text_item, fill=text_color)

            for shadow_item in [self.hex_shadow, self.hex_val_shadow, self.rgb_shadow,
                                self.rgb_val_shadow, self.pos_shadow, self.pos_val_shadow]:
                self.canvas.itemconfig(shadow_item, fill=shadow_color)

            # 更新提示文字颜色（非锁定状态）
            if not self.locked:
                self.canvas.itemconfig(self.tip_text, fill=text_color)
                self.canvas.itemconfig(self.tip_shadow, fill=shadow_color)

            # 更新锁定指示器边框颜色
            self.canvas.itemconfig(self.lock_bg, outline=text_color)

            # 更新HEX值
            self.canvas.itemconfig(self.hex_val_shadow, text=hex_color)
            self.canvas.itemconfig(self.hex_val_text, text=hex_color)

            # 更新RGB值
            rgb_str = f"{r}, {g}, {b}"
            self.canvas.itemconfig(self.rgb_val_shadow, text=rgb_str)
            self.canvas.itemconfig(self.rgb_val_text, text=rgb_str)

            # 更新位置（坐标格式）
            pos_str = f"({x}, {y})"
            self.canvas.itemconfig(self.pos_val_shadow, text=pos_str)
            self.canvas.itemconfig(self.pos_val_text, text=pos_str)

            # 保存当前值用于复制
            self.current_hex = hex_color
            self.current_rgb = rgb_str
            self.current_text_color = text_color
            self.current_shadow_color = shadow_color
        except Exception:
            pass

    def copy_hex(self):
        """复制HEX值到剪贴板"""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.current_hex)
        self.canvas.itemconfig(self.tip_shadow, text="已复制HEX值!")
        self.canvas.itemconfig(self.tip_text, text="已复制HEX值!")
        self.root.after(1500, self.restore_tip)

    def copy_rgb(self):
        """复制RGB值到剪贴板"""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.current_rgb)
        self.canvas.itemconfig(self.tip_shadow, text="已复制RGB值!")
        self.canvas.itemconfig(self.tip_text, text="已复制RGB值!")
        self.root.after(1500, self.restore_tip)

    def restore_tip(self):
        """恢复提示标签"""
        if self.locked:
            self.canvas.itemconfig(self.tip_shadow, text="已锁定 | 空格键/点击解锁")
            self.canvas.itemconfig(self.tip_text, text="已锁定 | 空格键/点击解锁", fill="#ff6666")
        else:
            self.canvas.itemconfig(self.tip_shadow, text="移动鼠标实时取色", fill=self.current_shadow_color)
            self.canvas.itemconfig(self.tip_text, text="移动鼠标实时取色", fill=self.current_text_color)

    def start_color_thread(self):
        """启动颜色获取线程"""
        self.color_thread = threading.Thread(target=self.update_color, daemon=True)
        self.color_thread.start()

    def on_closing(self):
        """关闭窗口时的处理"""
        self.running = False
        self.root.destroy()

    def run(self):
        """运行程序"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()


if __name__ == "__main__":
    app = ColorPicker()
    app.run()
