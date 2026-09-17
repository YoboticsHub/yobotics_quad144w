#!/usr/bin/env python3
"""
电机追踪数据查看器 - GUI调试工具
用于查看和可视化motor_trace.csv数据记录文件

CSV格式说明:
  前4列(元数据，不参与绘图): iteration, time_s, loop_interval_ms, cycle_duration_ms
  电机数据列命名规则: {腿}_{关节}_{变量类型}
    腿: LF(左前), RF(右前), LR(左后), RR(右后)
    关节: hip(髋), thigh(大腿), calf(小腿), wheel(轮)
    变量类型: q_des(期望角度), q(实际角度), tau_des(期望扭矩), tau(实际扭矩)
  IMU数据列: roll, pitch, yaw, gyro_x, gyro_y, gyro_z, acc_x, acc_y, acc_z

作者: 基于 data_viewer.py (Han Jiang) 改编
日期: 2026-06 - 适配motor_trace.csv格式
"""

import os
import sys
import csv
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox
from typing import Dict, List, Optional, Tuple
import re
import random
import platform
import shutil
import subprocess
from collections import defaultdict

CHINESE_FONT_CANDIDATES = [
    'Noto Sans CJK SC',
    'Noto Sans CJK JP',
    'Noto Serif CJK SC',
    'Noto Serif CJK JP',
    'WenQuanYi Micro Hei',
    'WenQuanYi Zen Hei',
    'Source Han Sans CN',
    'AR PL UMing CN',
    'AR PL UKai CN',
    'Microsoft YaHei',
    'SimHei',
    'PingFang SC',
    'DejaVu Sans',
    'Liberation Sans',
    'Ubuntu',
    'FreeSans',
    'Sans',
]

FONTCONFIG_SC_FONT_CANDIDATES = [
    'Noto Sans CJK SC',
    'Noto Sans CJK JP',
    'Noto Serif CJK SC',
    'Noto Serif CJK JP',
    'Source Han Sans CN',
    'WenQuanYi Micro Hei',
    'WenQuanYi Zen Hei',
    'AR PL UMing CN',
    'AR PL UKai CN',
]

TK_CHINESE_FONT_CANDIDATES = [
    # These are the family names Tk actually reports on this X11 setup.
    'song ti',
    'fangsong ti',
    'gothic',
    'mincho',
    'clearlyu',
    'fixed',
    # Keep fontconfig names as fallbacks for other machines where Tk sees them.
    'Microsoft YaHei',
    'SimHei',
    'PingFang SC',
    'Noto Sans CJK SC',
    'Noto Sans CJK JP',
    'Noto Serif CJK SC',
    'Noto Serif CJK JP',
    'Droid Sans Fallback',
    'AR PL UMing CN',
    'AR PL UKai CN',
]

EMOJI_FONT_CANDIDATES = [
    'Noto Color Emoji',
    'Noto Emoji',
    'Symbola',
    'Apple Color Emoji',
    'Segoe UI Emoji',
    'Segoe UI Symbol',
]

FONT_AUTO_INSTALL_ENV = 'MOTOR_TRACE_AUTO_INSTALL_FONTS'
TK_FONT_ENV = 'MOTOR_TRACE_TK_FONT'


def _fontconfig_families() -> List[str]:
    if not shutil.which('fc-list'):
        return []
    try:
        result = subprocess.run(
            ['fc-list', ':', 'family'],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []

    families = []
    for line in result.stdout.splitlines():
        for family in line.split(','):
            family = family.strip()
            if family:
                families.append(family)
    return families


def _has_font_family(candidates: List[str]) -> bool:
    families_lower = [family.lower() for family in _fontconfig_families()]
    for candidate in candidates:
        candidate_lower = candidate.lower()
        if any(candidate_lower in family for family in families_lower):
            return True
    return False


def _fontconfig_match(candidates: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return a fontconfig-matched family/file pair for preferred fonts."""
    if not shutil.which('fc-match'):
        return (None, None)

    for candidate in candidates:
        try:
            result = subprocess.run(
                ['fc-match', candidate, '-f', '%{family}\n%{file}\n'],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
            )
        except Exception:
            continue

        if result.returncode != 0:
            continue

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        family = lines[0].split(',')[0].strip() if lines else ''
        font_file = lines[1].strip() if len(lines) > 1 else ''
        family_lower = family.lower()

        # Avoid JP/TC/HK/KR variants for Simplified Chinese UI text.
        if any(tag in family_lower for tag in (' cjk jp', ' cjk tc', ' cjk hk', ' cjk kr')):
            continue

        if font_file and os.path.exists(font_file):
            return (candidate, font_file)
        if family:
            return (candidate, None)

    return (None, None)


def _fontconfig_family_candidates(candidates: List[str]) -> List[str]:
    """Return requested and fontconfig-resolved family names in preference order."""
    families = []
    for candidate in candidates:
        families.append(candidate)

    if shutil.which('fc-match'):
        for candidate in candidates:
            try:
                result = subprocess.run(
                    ['fc-match', candidate, '-f', '%{family}\n'],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=5,
                )
            except Exception:
                continue

            if result.returncode != 0:
                continue

            for family in result.stdout.split(','):
                family = family.strip()
                if family:
                    families.append(family)

    return list(dict.fromkeys(families))


def _print_font_install_hint(packages: List[str]):
    if not packages:
        return
    print("[字体配置] 自动安装字体失败或未启用，可手动执行：")
    print(f"  sudo apt-get update && sudo apt-get install -y {' '.join(packages)}")
    print(f"  或禁用自动安装: {FONT_AUTO_INSTALL_ENV}=0 python scripts/motor_trace_viewer.py")


def ensure_runtime_fonts():
    """Install common CJK/emoji fonts on Linux when they are missing."""
    if platform.system() != 'Linux':
        return

    packages = []
    if not _has_font_family(FONTCONFIG_SC_FONT_CANDIDATES):
        packages.append('fonts-noto-cjk')
    if not _has_font_family(EMOJI_FONT_CANDIDATES):
        packages.append('fonts-noto-color-emoji')
    if not packages:
        return

    auto_install = os.environ.get(FONT_AUTO_INSTALL_ENV, '1').lower()
    if auto_install in ('0', 'false', 'no', 'off'):
        _print_font_install_hint(packages)
        return

    apt_get = shutil.which('apt-get')
    if not apt_get:
        _print_font_install_hint(packages)
        return

    if os.geteuid() == 0:
        prefix = []
    elif shutil.which('sudo') and sys.stdin.isatty():
        prefix = ['sudo']
    else:
        _print_font_install_hint(packages)
        return

    try:
        print(f"[字体配置] 缺少字体，尝试自动安装: {' '.join(packages)}")
        subprocess.run(prefix + [apt_get, 'update'], check=True)
        subprocess.run(prefix + [apt_get, 'install', '-y'] + packages, check=True)
        if shutil.which('fc-cache'):
            subprocess.run(['fc-cache', '-f'], check=False)
    except Exception as exc:
        print(f"[字体配置] 自动安装字体失败: {exc}")
        _print_font_install_hint(packages)


ensure_runtime_fonts()
EMOJI_AVAILABLE = _has_font_family(EMOJI_FONT_CANDIDATES)
os.environ.setdefault('MPLCONFIGDIR', os.path.join('/tmp', f'motor_trace_matplotlib_{os.getuid()}'))
os.makedirs(os.environ['MPLCONFIGDIR'], exist_ok=True)

# 尝试导入matplotlib用于绘图
try:
    import matplotlib
    matplotlib.use('TkAgg')
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from matplotlib.figure import Figure
    from matplotlib import pyplot as plt
    import numpy as np

    class TextNavigationToolbar2Tk(NavigationToolbar2Tk):
        """Text-only toolbar to avoid unreadable icon glyphs on some Linux Tk setups."""
        toolitems = (
            ('Home', 'Reset original view', 'home', 'home'),
            ('Back', 'Back to previous view', 'back', 'back'),
            ('Forward', 'Forward to next view', 'forward', 'forward'),
            (None, None, None, None),
            ('Pan', 'Left button pans, right button zooms', 'move', 'pan'),
            ('Zoom', 'Zoom to rectangle', 'zoom_to_rect', 'zoom'),
            ('Subplots', 'Configure subplots', 'subplots', 'configure_subplots'),
            (None, None, None, None),
            ('Save', 'Save the figure', 'filesave', 'save_figure'),
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            try:
                default_font = tkfont.nametofont('TkDefaultFont')
                family = default_font.actual('family')
                self._label_font.configure(family=family, size=10)
                for child in self.winfo_children():
                    try:
                        child.configure(font=self._label_font)
                    except Exception:
                        pass
            except Exception:
                pass

        def _Button(self, text, image_file, toggle, command):
            try:
                button_font = tkfont.nametofont('TkDefaultFont')
            except Exception:
                button_font = ('Sans', 10)
            if not toggle:
                button = tk.Button(
                    master=self, text=text, command=command,
                    font=button_font, relief='flat', overrelief='groove',
                    borderwidth=1, padx=6, pady=2,
                )
            else:
                var = tk.IntVar(master=self)
                button = tk.Checkbutton(
                    master=self, text=text, command=command,
                    font=button_font, indicatoron=False, variable=var,
                    offrelief='flat', overrelief='groove', borderwidth=1,
                    padx=6, pady=2,
                )
                button.var = var
            button.pack(side=tk.LEFT)
            return button

    # 配置中文字体
    try:
        from matplotlib import font_manager

        system = platform.system()

        if system == 'Windows':
            font_candidates = ['SimHei', 'Microsoft YaHei', 'Microsoft YaHei UI',
                              'Arial Unicode MS', 'SimSun', 'KaiTi']
        elif system == 'Darwin':
            font_candidates = ['Arial Unicode MS', 'STHeiti', 'STSong',
                              'PingFang SC', 'Hiragino Sans GB']
        else:
            font_candidates = CHINESE_FONT_CANDIDATES

        selected_font, selected_font_file = _fontconfig_match(FONTCONFIG_SC_FONT_CANDIDATES)
        if selected_font_file:
            try:
                related_font_files = [selected_font_file]
                font_dir = os.path.dirname(selected_font_file)
                for font_file_name in (
                    'NotoSansCJK-Regular.ttc',
                    'NotoSansCJK-Bold.ttc',
                    'NotoSerifCJK-Regular.ttc',
                    'NotoSerifCJK-Bold.ttc',
                ):
                    font_file = os.path.join(font_dir, font_file_name)
                    if os.path.exists(font_file):
                        related_font_files.append(font_file)
                for font_file in dict.fromkeys(related_font_files):
                    font_manager.fontManager.addfont(font_file)
                selected_font = font_manager.FontProperties(fname=selected_font_file).get_name()
            except Exception:
                pass

        available_font_names = [f.name for f in font_manager.fontManager.ttflist]

        if not selected_font:
            for font_candidate in font_candidates:
                if font_candidate in available_font_names:
                    selected_font = font_candidate
                    break
                for avail_font in available_font_names:
                    avail_lower = avail_font.lower()
                    if font_candidate.lower() in avail_lower:
                        if any(tag in avail_lower for tag in (' cjk jp', ' cjk tc', ' cjk hk', ' cjk kr')):
                            continue
                        selected_font = avail_font
                        break
                if selected_font:
                    break

        if selected_font:
            matplotlib_fonts = [
                selected_font,
                'Noto Sans CJK SC',
                'Noto Serif CJK SC',
                'Source Han Sans CN',
                'WenQuanYi Micro Hei',
                'WenQuanYi Zen Hei',
                'Noto Sans CJK JP',
                'Noto Serif CJK JP',
                'DejaVu Sans',
                'sans-serif',
            ]
            plt.rcParams['font.sans-serif'] = list(dict.fromkeys(matplotlib_fonts))
            plt.rcParams['font.family'] = 'sans-serif'
            print(f"[字体配置] 使用字体: {selected_font}")
        else:
            if font_candidates:
                plt.rcParams['font.sans-serif'] = font_candidates + ['DejaVu Sans', 'sans-serif']
            else:
                plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'sans-serif']
            print(f"[字体配置] 未找到精确匹配的中文字体，使用候选列表")

        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['legend.fontsize'] = 8
        plt.rcParams['axes.labelsize'] = 10
        plt.rcParams['axes.titlesize'] = 12

    except Exception as e:
        try:
            system = platform.system()
            if system == 'Windows':
                plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'sans-serif']
            elif system == 'Darwin':
                plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'STHeiti', 'sans-serif']
            else:
                plt.rcParams['font.sans-serif'] = CHINESE_FONT_CANDIDATES
            plt.rcParams['axes.unicode_minus'] = False
            plt.rcParams['font.family'] = 'sans-serif'
        except:
            pass
        print(f"[警告] 配置中文字体失败: {e}")

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("[警告] matplotlib未安装，绘图功能将不可用")


# ============================================================================
# motor_trace.csv 列名解析常量
# ============================================================================

# 元数据列（前4列，跳过不参与绘图）
METADATA_COLUMNS = {
    'iteration': '迭代序号',
    'time_s': '时间(s)',
    'loop_interval_ms': '循环间隔(ms)',
    'cycle_duration_ms': '循环耗时(ms)',
}

# IMU数据列（末尾9列）
IMU_COLUMNS = {
    'roll': 'Roll',
    'pitch': 'Pitch',
    'yaw': 'Yaw',
    'gyro_x': '陀螺仪X',
    'gyro_y': '陀螺仪Y',
    'gyro_z': '陀螺仪Z',
    'acc_x': '加速度X',
    'acc_y': '加速度Y',
    'acc_z': '加速度Z',
}

# 腿名称映射
LEG_NAMES = {
    'LF': '左前腿(LF)',
    'RF': '右前腿(RF)',
    'LR': '左后腿(LR)',
    'RR': '右后腿(RR)',
}

# 关节名称映射
JOINT_NAMES = {
    'hip': '髋关节(hip)',
    'thigh': '大腿(thigh)',
    'calf': '小腿(calf)',
    'wheel': '轮子(wheel)',
}

# 变量类型名称映射（motor_trace.csv格式: q_des, q, tau_des, tau）
VARIABLE_TYPE_NAMES = {
    'q_des': '期望角度 q_des',
    'q': '实际角度 q',
    'tau_des': '期望扭矩 tau_des',
    'tau': '实际扭矩 tau',
}

# 变量类型简称
VARIABLE_TYPE_SHORT = {
    'q_des': 'q_des',
    'q': 'q',
    'tau_des': 'tau_des',
    'tau': 'tau',
}

PIN_PREFIX = '[固定] '

# 变量类型分组（用于对比期望vs实际）
VARIABLE_PAIRS = {
    'q_des': 'q',           # 期望角度 vs 实际角度
    'tau_des': 'tau',       # 期望扭矩 vs 实际扭矩
}

# 反向配对映射
VARIABLE_PAIRS_REVERSE = {v: k for k, v in VARIABLE_PAIRS.items()}


def is_metadata_column(col_name: str) -> bool:
    """判断列名是否为元数据列（前4列）"""
    return col_name in METADATA_COLUMNS


def is_imu_column(col_name: str) -> bool:
    """判断列名是否为IMU数据列"""
    return col_name in IMU_COLUMNS


def parse_motor_column_name(col_name: str) -> Optional[Tuple[str, str, str]]:
    """
    解析motor_trace.csv的电机数据列名格式: {Leg}_{Joint}_{Variable}

    参数:
        col_name: 列名，如 "LF_hip_q_des", "RF_thigh_tau"

    返回:
        (leg, joint, variable_type) 元组，如果无法解析则返回None
    """
    # 跳过元数据和IMU列
    if is_metadata_column(col_name) or is_imu_column(col_name):
        return None

    parts = col_name.split('_')

    if len(parts) < 3:
        return None

    leg = parts[0]
    if leg not in LEG_NAMES:
        return None

    joint = parts[1]
    if joint not in JOINT_NAMES:
        return None

    # 剩余部分组合成变量类型
    remaining = '_'.join(parts[2:])

    # 标准化变量类型名称
    if remaining in VARIABLE_TYPE_NAMES:
        var_type = remaining
    elif remaining == 'tau_des':
        var_type = 'tau_des'
    elif remaining == 'q_des':
        var_type = 'q_des'
    elif remaining == 'tau':
        var_type = 'tau'
    elif remaining == 'q':
        var_type = 'q'
    else:
        var_type = remaining

    return (leg, joint, var_type)


class MotorTraceViewer:
    def __init__(self, root, csv_file: Optional[str] = None):
        self.root = root
        self.root.title("电机追踪数据查看器 - MotorTrace")
        self.root.geometry("1400x900")

        self.csv_file = csv_file
        self.column_names: List[str] = []
        self.data: Dict[str, List[float]] = {}

        # 元数据列名列表（前4列）
        self.metadata_columns: List[str] = []
        # IMU列名列表
        self.imu_columns: List[str] = []
        # 电机数据列名列表（参与分组和绘图的列）
        self.motor_columns: List[str] = []

        # 变量分组结构
        self.variable_groups: Dict[str, List[str]] = {}
        self.leg_groups: Dict[str, Dict[str, List[str]]] = {}
        self.joint_groups: Dict[str, Dict[str, List[str]]] = {}
        self.compare_groups: Dict[str, List[str]] = {}

        self.selected_variables: List[str] = []
        self.pinned_variables: set = set()
        self.plot_lines: List[Dict] = []
        self.click_annotation = None
        self.click_marker = None
        self.use_multiple_y_axes = tk.BooleanVar(value=False)
        self.use_smart_y_scales = tk.BooleanVar(value=False)

        self.group_view_mode = tk.StringVar(value="by_type")

        self.setup_styles()
        self.create_ui()

        if csv_file and os.path.exists(csv_file):
            self.load_csv_file(csv_file)

    def update_encouraging_message(self):
        if hasattr(self, 'encouraging_messages') and self.encouraging_messages:
            emoji, message = random.choice(self.encouraging_messages)
            if hasattr(self, 'encouragement_icon_label'):
                self.encouragement_icon_label.config(text=emoji if self.use_emoji else "")
            if hasattr(self, 'encouragement_text_label'):
                self.encouragement_text_label.config(text=message)

    def start_encouragement_timer(self):
        self.root.after(2000, self.auto_refresh_encouragement)

    def auto_refresh_encouragement(self):
        self.update_encouraging_message()
        self.start_encouragement_timer()

    def get_available_font(self, size, weight='normal'):
        try:
            available_fonts_list = list(tkfont.families())
            available_fonts_lower = [f.lower() for f in available_fonts_list]
        except Exception:
            available_fonts_list = []
            available_fonts_lower = []

        font_candidates = []
        override_font = os.environ.get(TK_FONT_ENV, '').strip()
        if override_font:
            font_candidates.append(override_font)
        font_candidates.extend(_fontconfig_family_candidates(TK_CHINESE_FONT_CANDIDATES))
        font_candidates = list(dict.fromkeys(font_candidates))
        if not font_candidates:
            font_candidates = TK_CHINESE_FONT_CANDIDATES

        for family in font_candidates:
            if family in available_fonts_list:
                try:
                    tkfont.Font(family=family, size=size, weight=weight)
                    return (family, size, weight)
                except Exception:
                    continue

        for family in font_candidates:
            family_lower = family.lower()
            for avail_font in available_fonts_list:
                if avail_font.lower() == family_lower:
                    try:
                        tkfont.Font(family=avail_font, size=size, weight=weight)
                        return (avail_font, size, weight)
                    except Exception:
                        continue

        fallback_family = 'song ti' if 'song ti' in available_fonts_lower else 'fixed'
        return (fallback_family, size, weight)

    def apply_tk_font_defaults(self, font_family: str):
        """Apply a readable font to Tk's named fonts and common widgets."""
        named_fonts = {
            'TkDefaultFont': {'size': 10},
            'TkTextFont': {'size': 10},
            'TkFixedFont': {'size': 10},
            'TkMenuFont': {'size': 10},
            'TkHeadingFont': {'size': 10},
            'TkCaptionFont': {'size': 10},
            'TkSmallCaptionFont': {'size': 9},
            'TkIconFont': {'size': 10},
            'TkTooltipFont': {'size': 9},
        }
        for font_name, options in named_fonts.items():
            try:
                tkfont.nametofont(font_name).configure(family=font_family, **options)
            except Exception:
                continue

        option_patterns = [
            '*Font', '*Menu*Font', '*Button*Font', '*Label*Font', '*Entry*Font',
            '*Text*Font', '*Checkbutton*Font', '*Radiobutton*Font', '*Listbox*Font',
            '*TCombobox*Listbox.font', '*Treeview*Font', '*Treeview*Heading*Font',
        ]
        for pattern in option_patterns:
            try:
                self.root.option_add(pattern, self.font_normal, 80)
            except Exception:
                pass

    def setup_styles(self):
        font_normal_family = self.get_available_font(11, 'normal')[0]
        font_small_family = self.get_available_font(10, 'normal')[0]

        self.font_title = (font_normal_family, 14, 'normal')
        self.font_large = (font_normal_family, 12, 'normal')
        self.font_normal = (font_normal_family, 11, 'normal')
        self.font_small = (font_small_family, 10, 'normal')
        self.font_bold = (font_normal_family, 11, 'normal')
        self.use_emoji = False
        print(f"[字体配置] Tk界面字体: {font_normal_family}")

        self.apply_tk_font_defaults(font_normal_family)

        self.ttk_style = ttk.Style()
        try:
            self.ttk_style.theme_use('clam')
        except Exception:
            pass
        self.ttk_style.configure(
            'Treeview',
            font=(font_small_family, 10, 'normal'),
            rowheight=22,
        )
        self.ttk_style.configure(
            'Treeview.Heading',
            font=(font_small_family, 10, 'normal'),
        )

        self.colors = {
            'bg_main': '#F5F5F5',
            'bg_section': '#FFFFFF',
            'bg_button': '#4A90E2',
            'fg_text': '#2C3E50',
            'fg_label': '#34495E',
            'border': '#BDC3C7',
            'accent': '#3498DB',
        }

    def create_ui(self):
        self.root.configure(bg=self.colors['bg_main'])

        # 顶部菜单栏
        menubar = tk.Menu(self.root, font=self.font_normal)
        self.root.config(menu=menubar, bg=self.colors['bg_main'])

        file_menu = tk.Menu(menubar, tearoff=0, font=self.font_normal)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="打开CSV文件...", command=self.load_csv_file_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)

        help_menu = tk.Menu(menubar, tearoff=0, font=self.font_normal)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="关于", command=self.show_about)

        # 主容器
        main_frame = tk.Frame(self.root, bg=self.colors['bg_main'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 顶部标题栏
        title_frame = tk.Frame(main_frame, bg=self.colors['accent'], height=60)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        title_frame.pack_propagate(False)

        title_text = "电机追踪数据查看器"
        title_label = tk.Label(title_frame, text=title_text,
                              font=self.font_title, bg=self.colors['accent'],
                              fg='white', padx=20, pady=15)
        title_label.pack(side=tk.LEFT)

        fmt_label = tk.Label(title_frame,
                            text="列格式: {腿}_{关节}_{变量}  |  腿: LF/RF/LR/RR  |  关节: hip/thigh/calf/wheel  |  变量: q_des/q/tau_des/tau  |  前4列为元数据，已跳过",
                            font=self.font_small, bg=self.colors['accent'],
                            fg='#E8F4FD', padx=20)
        fmt_label.pack(side=tk.RIGHT)

        # 工具栏
        toolbar_frame = tk.Frame(main_frame, bg=self.colors['bg_section'],
                                relief='flat', bd=1, highlightbackground=self.colors['border'],
                                highlightthickness=1)
        toolbar_frame.pack(fill=tk.X, pady=(0, 10))

        button_frame = tk.Frame(toolbar_frame, bg=self.colors['bg_section'])
        button_frame.pack(side=tk.LEFT, padx=15, pady=10)

        load_text = "打开CSV文件"
        btn_load = tk.Button(button_frame, text=load_text,
                            font=self.font_normal, bg='#4A90E2', fg='white',
                            relief='flat', bd=0, padx=16, pady=8,
                            cursor='hand2', activebackground='#357ABD',
                            activeforeground='white',
                            command=self.load_csv_file_dialog)
        btn_load.pack(side=tk.LEFT, padx=(0, 8))

        # 鼓励话语显示
        self.encouraging_messages = [
            ("", "观测电机数据，精准调试控制参数"),
            ("", "数据不会说谎，但需要正确的解读方式"),
            ("", "观察数据趋势比单个数值更有价值"),
            ("", "对比期望与实际，发现跟踪误差"),
            ("", "先看整体趋势，再深入细节分析"),
            ("", "异常值往往蕴含着关键信息"),
            ("", "多角度观察数据，全面理解系统行为"),
            ("", "下降趋势和上升趋势同样重要"),
            ("", "快速识别数据模式，提高分析效率"),
            ("", "数据可视化让复杂信息一目了然"),
            ("", "选择合适的比例尺，让数据更清晰"),
            ("", "记录分析过程，便于后续回顾"),
            ("", "从数据中发现规律，指导系统优化"),
            ("", "加油优宝特，一定能上市！"),
            ("", "优宝特机器人，引领未来智能时代"),
            ("", "行者泰山，登峰造极，勇攀高峰"),
            ("", "行者泰山，稳健前行，走向世界舞台"),
            ("", "优宝特机器人，让中国智造闪耀全球"),
            ("", "优宝特团队，技术精湛，追求卓越"),
            ("", "优宝特机器人，服务全球，创造价值"),
            ("", "优宝特品质，精益求精，匠心独运"),
            ("", "优宝特机器人，为人类进步贡献力量"),
            ("", "优宝特加速前行，迈向更广阔的未来"),
            ("", "优宝特技术领先，产品卓越，团队优秀"),
            ("", "优宝特机器人，让科技温暖世界"),
        ]

        encouraging_frame = tk.Frame(toolbar_frame, bg=self.colors['bg_main'])
        encouraging_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=15, pady=10)

        encouragement_card = tk.Frame(encouraging_frame,
                                     bg='#FFF9E6',
                                     relief='flat', bd=1,
                                     highlightbackground='#FFD700',
                                     highlightthickness=2)
        encouragement_card.pack(fill=tk.X, padx=0, pady=0)

        encouragement_content = tk.Frame(encouragement_card, bg='#FFF9E6')
        encouragement_content.pack(fill=tk.X, padx=20, pady=12)

        center_container = tk.Frame(encouragement_content, bg='#FFF9E6')
        center_container.pack(expand=True, fill=tk.BOTH)

        emoji_font_name = self.get_available_font(16, 'normal')[0]
        text_font = self.get_available_font(13, 'normal')

        self.encouragement_icon_label = tk.Label(
            center_container, text="",
            font=(emoji_font_name, 28), bg='#FFF9E6', fg='#FF6B35'
        )
        self.encouragement_icon_label.pack(side=tk.LEFT, padx=(0, 15))

        self.encouragement_text_label = tk.Label(
            center_container, text="",
            font=text_font, bg='#FFF9E6', fg='#2C3E50', anchor='center'
        )
        self.encouragement_text_label.pack(side=tk.LEFT, expand=True)

        refresh_btn = tk.Label(
            center_container, text=("" if self.use_emoji else "刷新"),
            font=(emoji_font_name, 16 if self.use_emoji else 11),
            bg='#FFF9E6', fg='#666666', cursor='hand2'
        )
        refresh_btn.pack(side=tk.LEFT, padx=(15, 0))
        refresh_btn.bind('<Button-1>', lambda e: self.update_encouraging_message())
        refresh_btn.bind('<Enter>', lambda e: refresh_btn.config(fg='#3498DB'))
        refresh_btn.bind('<Leave>', lambda e: refresh_btn.config(fg='#666666'))

        self.encouragement_card = encouragement_card
        self.encouragement_content = encouragement_content

        self.update_encouraging_message()
        self.start_encouragement_timer()

        # 文件路径显示
        file_info_frame = tk.Frame(toolbar_frame, bg=self.colors['bg_section'])
        file_info_frame.pack(side=tk.RIGHT, padx=15, pady=10)

        file_label_title = tk.Label(file_info_frame, text="当前文件:",
                                   font=self.font_small, bg=self.colors['bg_section'],
                                   fg=self.colors['fg_label'])
        file_label_title.pack(side=tk.LEFT, padx=(0, 5))

        self.file_label = tk.Label(file_info_frame, text="未打开文件",
                                   font=self.font_small, bg=self.colors['bg_section'],
                                   fg=self.colors['fg_label'], anchor='w')
        self.file_label.pack(side=tk.LEFT)

        # 主要内容区域（左右分割）
        content_frame = tk.Frame(main_frame, bg=self.colors['bg_main'])
        content_frame.pack(fill=tk.BOTH, expand=True)

        # 左侧：变量选择面板
        left_panel = tk.Frame(content_frame, bg=self.colors['bg_section'],
                             relief='flat', bd=1, highlightbackground=self.colors['border'],
                             highlightthickness=1)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))
        left_panel.config(width=380)
        left_panel.pack_propagate(False)

        # 左侧标题
        left_header = tk.Frame(left_panel, bg=self.colors['bg_section'])
        left_header.pack(fill=tk.X, padx=10, pady=(10, 5))

        left_title = tk.Label(left_header, text="变量选择 (已跳过前4列元数据)",
                             font=self.font_large, bg=self.colors['bg_section'],
                             fg=self.colors['fg_label'])
        left_title.pack(side=tk.LEFT)

        btn_clear = tk.Button(left_header, text="清除固定",
                             font=self.font_small, bg='#E74C3C', fg='white',
                             relief='flat', bd=0, padx=8, pady=3,
                             cursor='hand2', activebackground='#C0392B',
                             activeforeground='white',
                             command=self.clear_pinned_variables)
        btn_clear.pack(side=tk.RIGHT, padx=(5, 0))

        # 分组视图切换按钮
        view_frame = tk.Frame(left_panel, bg=self.colors['bg_section'])
        view_frame.pack(fill=tk.X, padx=10, pady=(0, 8))

        view_label = tk.Label(view_frame, text="分组视图:",
                             font=self.font_small, bg=self.colors['bg_section'],
                             fg=self.colors['fg_label'])
        view_label.pack(side=tk.LEFT, padx=(0, 5))

        views = [
            ("按变量类型", "by_type"),
            ("按腿", "by_leg"),
            ("按关节", "by_joint"),
            ("对比视图", "by_compare"),
        ]

        for text, mode in views:
            rb = tk.Radiobutton(view_frame, text=text, value=mode,
                               variable=self.group_view_mode,
                               font=self.font_small, bg=self.colors['bg_section'],
                               fg=self.colors['fg_label'], activebackground=self.colors['bg_section'],
                               activeforeground=self.colors['accent'],
                               selectcolor=self.colors['bg_section'],
                               indicatoron=True, relief='flat', bd=0,
                               command=self.on_view_mode_changed)
            rb.pack(side=tk.LEFT, padx=2)

        # 快速调试预设按钮
        preset_frame = tk.Frame(left_panel, bg=self.colors['bg_section'])
        preset_frame.pack(fill=tk.X, padx=10, pady=(0, 8))

        preset_label = tk.Label(preset_frame, text="快速预设:",
                               font=self.font_small, bg=self.colors['bg_section'],
                               fg=self.colors['fg_label'])
        preset_label.pack(side=tk.LEFT, padx=(0, 5))

        # 预设按钮行1
        preset_btn_frame1 = tk.Frame(left_panel, bg=self.colors['bg_section'])
        preset_btn_frame1.pack(fill=tk.X, padx=10, pady=(0, 3))

        btn_q_compare = tk.Button(preset_btn_frame1, text="角度对比(期望vs实际)",
                                 font=self.font_small, bg='#3498DB', fg='white',
                                 relief='flat', bd=0, padx=4, pady=4,
                                 cursor='hand2', activebackground='#2980B9',
                                 activeforeground='white',
                                 command=lambda: self.apply_preset('q_compare'))
        btn_q_compare.pack(side=tk.LEFT, padx=(0, 3), fill=tk.X, expand=True)

        btn_tau_compare = tk.Button(preset_btn_frame1, text="扭矩对比(期望vs实际)",
                                   font=self.font_small, bg='#2ECC71', fg='white',
                                   relief='flat', bd=0, padx=4, pady=4,
                                   cursor='hand2', activebackground='#27AE60',
                                   activeforeground='white',
                                   command=lambda: self.apply_preset('tau_compare'))
        btn_tau_compare.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 预设按钮行2
        preset_btn_frame2 = tk.Frame(left_panel, bg=self.colors['bg_section'])
        preset_btn_frame2.pack(fill=tk.X, padx=10, pady=(0, 3))

        btn_all_q = tk.Button(preset_btn_frame2, text="全部实际角度",
                             font=self.font_small, bg='#E67E22', fg='white',
                             relief='flat', bd=0, padx=4, pady=4,
                             cursor='hand2', activebackground='#D35400',
                             activeforeground='white',
                             command=lambda: self.apply_preset('all_q'))
        btn_all_q.pack(side=tk.LEFT, padx=(0, 3), fill=tk.X, expand=True)

        btn_all_q_des = tk.Button(preset_btn_frame2, text="全部期望角度",
                                 font=self.font_small, bg='#9B59B6', fg='white',
                                 relief='flat', bd=0, padx=4, pady=4,
                                 cursor='hand2', activebackground='#8E44AD',
                                 activeforeground='white',
                                 command=lambda: self.apply_preset('all_q_des'))
        btn_all_q_des.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 预设按钮行3
        preset_btn_frame3 = tk.Frame(left_panel, bg=self.colors['bg_section'])
        preset_btn_frame3.pack(fill=tk.X, padx=10, pady=(0, 3))

        btn_all_tau = tk.Button(preset_btn_frame3, text="全部实际扭矩",
                               font=self.font_small, bg='#1ABC9C', fg='white',
                               relief='flat', bd=0, padx=4, pady=4,
                               cursor='hand2', activebackground='#16A085',
                               activeforeground='white',
                               command=lambda: self.apply_preset('all_tau'))
        btn_all_tau.pack(side=tk.LEFT, padx=(0, 3), fill=tk.X, expand=True)

        btn_all_tau_des = tk.Button(preset_btn_frame3, text="全部期望扭矩",
                                   font=self.font_small, bg='#E91E63', fg='white',
                                   relief='flat', bd=0, padx=4, pady=4,
                                   cursor='hand2', activebackground='#C2185B',
                                   activeforeground='white',
                                   command=lambda: self.apply_preset('all_tau_des'))
        btn_all_tau_des.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 预设按钮行4: IMU数据
        preset_btn_frame4 = tk.Frame(left_panel, bg=self.colors['bg_section'])
        preset_btn_frame4.pack(fill=tk.X, padx=10, pady=(0, 3))

        btn_imu_rpy = tk.Button(preset_btn_frame4, text="IMU姿态(Roll/Pitch/Yaw)",
                               font=self.font_small, bg='#FF6B35', fg='white',
                               relief='flat', bd=0, padx=4, pady=4,
                               cursor='hand2', activebackground='#E55A2B',
                               activeforeground='white',
                               command=lambda: self.apply_preset('imu_rpy'))
        btn_imu_rpy.pack(side=tk.LEFT, padx=(0, 3), fill=tk.X, expand=True)

        btn_imu_acc = tk.Button(preset_btn_frame4, text="IMU加速度(X/Y/Z)",
                               font=self.font_small, bg='#00BCD4', fg='white',
                               relief='flat', bd=0, padx=4, pady=4,
                               cursor='hand2', activebackground='#0097A7',
                               activeforeground='white',
                               command=lambda: self.apply_preset('imu_acc'))
        btn_imu_acc.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 变量树
        tree_frame = tk.Frame(left_panel, bg=self.colors['bg_section'])
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        tree_scrollbar = ttk.Scrollbar(tree_frame)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.variable_tree = ttk.Treeview(tree_frame, yscrollcommand=tree_scrollbar.set,
                                          selectmode='extended')
        self.variable_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scrollbar.config(command=self.variable_tree.yview)

        self.variable_tree.bind('<Double-1>', self.on_variable_double_click)

        # 右侧：绘图区域
        right_panel = tk.Frame(content_frame, bg=self.colors['bg_section'],
                              relief='flat', bd=1, highlightbackground=self.colors['border'],
                              highlightthickness=1)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # 右侧标题和控制栏
        right_header = tk.Frame(right_panel, bg=self.colors['bg_section'])
        right_header.pack(fill=tk.X, padx=10, pady=(10, 5))

        right_title = tk.Label(right_header, text="数据曲线",
                              font=self.font_large, bg=self.colors['bg_section'],
                              fg=self.colors['fg_label'])
        right_title.pack(side=tk.LEFT)

        # 多y轴控制复选框
        checkbox_frame = tk.Frame(right_header, bg=self.colors['bg_section'])
        checkbox_frame.pack(side=tk.RIGHT, padx=(10, 0))

        self.smart_y_checkbox = tk.Checkbutton(
            checkbox_frame,
            text="智能Y轴分组",
            variable=self.use_smart_y_scales,
            font=self.font_small, bg=self.colors['bg_section'],
            fg=self.colors['fg_label'], activebackground=self.colors['bg_section'],
            activeforeground=self.colors['accent'],
            selectcolor=self.colors['bg_section'],
            relief='flat',
            command=self.on_multi_y_toggle
        )
        self.smart_y_checkbox.pack(side=tk.RIGHT, padx=(0, 10))

        self.multi_y_checkbox = tk.Checkbutton(
            checkbox_frame,
            text="独立Y轴",
            variable=self.use_multiple_y_axes,
            font=self.font_small, bg=self.colors['bg_section'],
            fg=self.colors['fg_label'], activebackground=self.colors['bg_section'],
            activeforeground=self.colors['accent'],
            selectcolor=self.colors['bg_section'],
            relief='flat',
            command=self.on_multi_y_toggle
        )
        self.multi_y_checkbox.pack(side=tk.RIGHT)

        # 绘图区域
        if MATPLOTLIB_AVAILABLE:
            self.plot_frame = tk.Frame(right_panel, bg=self.colors['bg_section'])
            self.plot_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

            self.fig = Figure(figsize=(12, 7), dpi=100)
            self.ax = self.fig.add_subplot(111)
            self.ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
            self.ax.set_xlabel('采样序号', fontsize=12, fontweight='bold')
            self.ax.set_ylabel('数值', fontsize=12, fontweight='bold')
            self.ax.set_title('电机追踪数据曲线图（请在左侧双击变量固定显示，或使用预设按钮）',
                            fontsize=14, fontweight='bold', pad=15)

            self.canvas = FigureCanvasTkAgg(self.fig, self.plot_frame)
            self.canvas.mpl_connect('button_press_event', self.on_plot_click)
            self.canvas.draw()
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            toolbar_frame = tk.Frame(self.plot_frame, bg=self.colors['bg_section'])
            toolbar_frame.pack(fill=tk.X)
            self.toolbar = TextNavigationToolbar2Tk(self.canvas, toolbar_frame)
            self.toolbar.update()
        else:
            no_plot_label = tk.Label(right_panel,
                                    text="matplotlib未安装，无法显示曲线图\n请安装: pip install matplotlib numpy",
                                    font=self.font_normal, bg=self.colors['bg_section'],
                                    fg=self.colors['fg_label'], justify=tk.CENTER)
            no_plot_label.pack(expand=True)

    def load_csv_file_dialog(self):
        """打开文件选择对话框"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        default_dir = script_dir if os.path.exists(script_dir) else os.getcwd()

        file_path = filedialog.askopenfilename(
            title="选择CSV数据文件",
            initialdir=default_dir,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file_path:
            self.load_csv_file(file_path)

    def load_csv_file(self, file_path: str):
        """加载CSV文件"""
        try:
            if not os.path.exists(file_path):
                messagebox.showerror("错误", f"文件不存在: {file_path}")
                return

            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)

            self.csv_file = file_path
            self.data.clear()
            self.variable_groups.clear()
            self.leg_groups.clear()
            self.joint_groups.clear()
            self.compare_groups.clear()
            self.selected_variables.clear()
            self.pinned_variables.clear()
            self.metadata_columns.clear()
            self.imu_columns.clear()
            self.motor_columns.clear()

            # 更新文件路径显示
            display_path = os.path.basename(file_path)
            if len(display_path) > 50:
                display_path = "..." + display_path[-47:]
            size_text = f"{display_path} ({file_size_mb:.1f} MB)"
            self.file_label.config(text=size_text)
            self.root.update()

            # 读取CSV文件（处理可能的NUL字符）
            with open(file_path, 'rb') as f:
                content = f.read()
                content_clean = content.replace(b'\x00', b'')
                content_text = content_clean.decode('utf-8', errors='replace')

            from io import StringIO
            f_clean = StringIO(content_text)
            reader = csv.reader(f_clean)

            # 读取表头
            try:
                header_row = next(reader)
                self.column_names = [col.strip().strip('\ufeff') for col in header_row]
            except StopIteration:
                messagebox.showerror("错误", "CSV文件为空或格式错误")
                return

            if not self.column_names:
                messagebox.showerror("错误", "CSV文件没有列名")
                return

            # 分类列：元数据列 / 电机数据列 / IMU列
            for col_name in self.column_names:
                if is_metadata_column(col_name):
                    self.metadata_columns.append(col_name)
                elif is_imu_column(col_name):
                    self.imu_columns.append(col_name)
                else:
                    self.motor_columns.append(col_name)

            # 初始化数据字典（仅非元数据列参与绘图）
            columns_to_load = self.motor_columns + self.imu_columns
            for col_name in columns_to_load:
                self.data[col_name] = []

            last_valid_values = {}
            rows_processed = 0
            rows_skipped = 0
            null_values_handled = 0

            # 读取数据行
            for row_num, row in enumerate(reader, start=2):
                if len(row) != len(self.column_names):
                    if len(row) < len(self.column_names):
                        row.extend([''] * (len(self.column_names) - len(row)))
                    else:
                        row = row[:len(self.column_names)]
                    rows_skipped += 1

                if not any(cell.strip() for cell in row):
                    continue

                for i, col_name in enumerate(self.column_names):
                    # 跳过元数据列
                    if col_name in self.metadata_columns:
                        continue

                    try:
                        cell_value = row[i].strip() if i < len(row) else ''
                        value = None
                        is_valid = False

                        if cell_value and cell_value.lower() not in ('null', 'none', 'nan', 'n/a', 'na', ''):
                            try:
                                value = float(cell_value)
                                is_valid = True
                                last_valid_values[col_name] = value
                            except (ValueError, OverflowError):
                                is_valid = False

                        if not is_valid:
                            null_values_handled += 1
                            if col_name in last_valid_values:
                                value = last_valid_values[col_name]
                            else:
                                value = 0.0
                                last_valid_values[col_name] = value

                        self.data[col_name].append(value)
                    except (IndexError, Exception) as e:
                        null_values_handled += 1
                        if col_name in last_valid_values:
                            value = last_valid_values[col_name]
                        else:
                            value = 0.0
                            last_valid_values[col_name] = value
                        self.data[col_name].append(value)

                rows_processed += 1

                if rows_processed > 0 and rows_processed % 10000 == 0:
                    self.file_label.config(text=f"{size_text} (加载中: {rows_processed} 行...)")
                    self.root.update_idletasks()

            if not self.data or not any(len(values) > 0 for values in self.data.values()):
                messagebox.showerror("错误", "CSV文件中没有有效数据")
                return

            num_rows = len(list(self.data.values())[0]) if self.data else 0
            self.file_label.config(text=f"{display_path} ({file_size_mb:.1f} MB, {num_rows} 行)")

            # 分类变量
            self.classify_motor_variables()

            # 更新变量树
            self.update_variable_tree()

            # 显示加载结果
            result_msg = f"已加载 {len(self.data)} 个变量，{num_rows} 行数据"
            result_msg += f"\n已跳过 {len(self.metadata_columns)} 个元数据列: {', '.join(self.metadata_columns)}"
            if rows_skipped > 0:
                result_msg += f"\n跳过了 {rows_skipped} 行格式不正确的数据"
            if null_values_handled > 0:
                result_msg += f"\n处理了 {null_values_handled} 个空值/null值"

            motor_count = len(self.motor_columns)
            imu_count = len(self.imu_columns)
            result_msg += f"\n电机数据: {motor_count} 列  |  IMU数据: {imu_count} 列"
            result_msg += "\n可使用「快速预设」按钮进行调试分析"

            messagebox.showinfo("成功", result_msg)

        except UnicodeDecodeError as e:
            messagebox.showerror("错误", f"文件编码错误: {str(e)}\n请检查文件是否为UTF-8编码")
            import traceback
            traceback.print_exc()
        except Exception as e:
            messagebox.showerror("错误", f"加载CSV文件失败: {str(e)}")
            import traceback
            traceback.print_exc()

    def classify_motor_variables(self):
        """
        按motor_trace.csv的{Leg}_{Joint}_{Variable}格式分类变量

        建立多维度分组:
        1. 按变量类型分组: q_des, q, tau_des, tau, IMU数据
        2. 按腿分组: LF, RF, LR, RR -> 各自的变量类型
        3. 按关节分组: hip, thigh, calf, wheel -> 各自的变量类型
        4. 对比视图分组: q_des vs q, tau_des vs tau
        """
        self.variable_groups.clear()
        self.leg_groups.clear()
        self.joint_groups.clear()
        self.compare_groups.clear()

        # 处理电机数据列
        for col_name in self.motor_columns:
            parsed = parse_motor_column_name(col_name)
            if parsed is None:
                # 无法解析的列归入"其他变量"
                if '其他变量' not in self.variable_groups:
                    self.variable_groups['其他变量'] = []
                self.variable_groups['其他变量'].append(col_name)
                continue

            leg, joint, var_type = parsed

            # 1. 按变量类型分组
            type_display = VARIABLE_TYPE_NAMES.get(var_type, var_type)
            if type_display not in self.variable_groups:
                self.variable_groups[type_display] = []
            self.variable_groups[type_display].append(col_name)

            # 2. 按腿分组
            leg_display = LEG_NAMES.get(leg, leg)
            if leg_display not in self.leg_groups:
                self.leg_groups[leg_display] = {}
            if var_type not in self.leg_groups[leg_display]:
                self.leg_groups[leg_display][var_type] = []
            self.leg_groups[leg_display][var_type].append(col_name)

            # 3. 按关节分组
            joint_display = JOINT_NAMES.get(joint, joint)
            if joint_display not in self.joint_groups:
                self.joint_groups[joint_display] = {}
            if var_type not in self.joint_groups[joint_display]:
                self.joint_groups[joint_display][var_type] = []
            self.joint_groups[joint_display][var_type].append(col_name)

            # 4. 对比视图分组
            pair_key = None
            if var_type in VARIABLE_PAIRS:
                pair_key = f"{var_type}_vs_{VARIABLE_PAIRS[var_type]}"
            elif var_type in VARIABLE_PAIRS_REVERSE:
                pair_key = f"{VARIABLE_PAIRS_REVERSE[var_type]}_vs_{var_type}"

            if pair_key:
                if pair_key not in self.compare_groups:
                    self.compare_groups[pair_key] = []
                self.compare_groups[pair_key].append(col_name)

        # 处理IMU数据列 -> 归类到单独的IMU分组
        if self.imu_columns:
            # IMU姿态
            rpy_cols = [c for c in self.imu_columns if c in ('roll', 'pitch', 'yaw')]
            if rpy_cols:
                self.variable_groups['IMU姿态 (roll/pitch/yaw)'] = rpy_cols

            # IMU陀螺仪
            gyro_cols = [c for c in self.imu_columns if c.startswith('gyro_')]
            if gyro_cols:
                self.variable_groups['IMU角速度 (gyro)'] = gyro_cols

            # IMU加速度
            acc_cols = [c for c in self.imu_columns if c.startswith('acc_')]
            if acc_cols:
                self.variable_groups['IMU加速度 (acc)'] = acc_cols

        # 对每个组内的变量排序
        leg_order = {'LF': 0, 'RF': 1, 'LR': 2, 'RR': 3}
        joint_order = {'hip': 0, 'thigh': 1, 'calf': 2, 'wheel': 3}

        def sort_key(var_name):
            parsed = parse_motor_column_name(var_name)
            if parsed:
                leg, joint, var_type = parsed
                return (leg_order.get(leg, 99), joint_order.get(joint, 99))
            # IMU列和其他列保持原顺序
            return (50, 50)

        for group in self.variable_groups:
            self.variable_groups[group].sort(key=sort_key)

        for leg in self.leg_groups:
            for var_type in self.leg_groups[leg]:
                self.leg_groups[leg][var_type].sort(key=sort_key)

        for joint in self.joint_groups:
            for var_type in self.joint_groups[joint]:
                self.joint_groups[joint][var_type].sort(key=sort_key)

        for pair_key in self.compare_groups:
            self.compare_groups[pair_key].sort(key=sort_key)

    def on_view_mode_changed(self):
        """分组视图切换事件"""
        self.update_variable_tree()

    def update_variable_tree(self):
        """根据当前视图模式更新变量树"""
        for item in self.variable_tree.get_children():
            self.variable_tree.delete(item)

        mode = self.group_view_mode.get()

        if mode == "by_type":
            self._build_tree_by_type()
        elif mode == "by_leg":
            self._build_tree_by_leg()
        elif mode == "by_joint":
            self._build_tree_by_joint()
        elif mode == "by_compare":
            self._build_tree_by_compare()

        self.variable_tree.tag_configure('variable', foreground='#2C3E50')
        self.variable_tree.tag_configure('header', foreground='#3498DB', font=self.font_small)

    def _build_tree_by_type(self):
        """按变量类型分组构建树"""
        # 电机数据先显示，IMU数据后显示
        motor_categories = []
        imu_categories = []
        other_categories = []

        for category in sorted(self.variable_groups.keys()):
            if category.startswith('IMU'):
                imu_categories.append(category)
            elif category == '其他变量':
                other_categories.append(category)
            else:
                motor_categories.append(category)

        for category in motor_categories + imu_categories + other_categories:
            category_id = self.variable_tree.insert('', 'end', text=category, open=True)
            for var_name in self.variable_groups[category]:
                display_name = self._format_var_display(var_name)
                if var_name in self.pinned_variables:
                    display_name = PIN_PREFIX + display_name
                self.variable_tree.insert(category_id, 'end', text=display_name, tags=('variable',))

    def _build_tree_by_leg(self):
        """按腿分组构建树"""
        leg_order = ['左前腿(LF)', '右前腿(RF)', '左后腿(LR)', '右后腿(RR)']
        for leg_display in leg_order:
            if leg_display not in self.leg_groups:
                continue
            leg_id = self.variable_tree.insert('', 'end', text=leg_display, open=True)
            var_types_in_leg = self.leg_groups[leg_display]
            for var_type in sorted(var_types_in_leg.keys()):
                type_display = VARIABLE_TYPE_NAMES.get(var_type, var_type)
                type_id = self.variable_tree.insert(leg_id, 'end', text=type_display, open=False)
                for var_name in var_types_in_leg[var_type]:
                    display_name = self._format_var_display(var_name)
                    if var_name in self.pinned_variables:
                        display_name = PIN_PREFIX + display_name
                    self.variable_tree.insert(type_id, 'end', text=display_name, tags=('variable',))

    def _build_tree_by_joint(self):
        """按关节分组构建树"""
        joint_order = ['髋关节(hip)', '大腿(thigh)', '小腿(calf)', '轮子(wheel)']
        for joint_display in joint_order:
            if joint_display not in self.joint_groups:
                continue
            joint_id = self.variable_tree.insert('', 'end', text=joint_display, open=True)
            var_types_in_joint = self.joint_groups[joint_display]
            for var_type in sorted(var_types_in_joint.keys()):
                type_display = VARIABLE_TYPE_NAMES.get(var_type, var_type)
                type_id = self.variable_tree.insert(joint_id, 'end', text=type_display, open=False)
                for var_name in var_types_in_joint[var_type]:
                    display_name = self._format_var_display(var_name)
                    if var_name in self.pinned_variables:
                        display_name = PIN_PREFIX + display_name
                    self.variable_tree.insert(type_id, 'end', text=display_name, tags=('variable',))

    def _build_tree_by_compare(self):
        """按对比视图分组构建树（期望 vs 实际）"""
        compare_order = [
            ('q_des_vs_q', '角度对比 (q_des vs q)'),
            ('tau_des_vs_tau', '扭矩对比 (tau_des vs tau)'),
        ]

        for pair_key, pair_display in compare_order:
            if pair_key in self.compare_groups and self.compare_groups[pair_key]:
                pair_id = self.variable_tree.insert('', 'end', text=pair_display, open=True)
                for var_name in self.compare_groups[pair_key]:
                    display_name = self._format_var_display(var_name)
                    if var_name in self.pinned_variables:
                        display_name = PIN_PREFIX + display_name
                    self.variable_tree.insert(pair_id, 'end', text=display_name, tags=('variable',))

        # 处理其他对比组
        for pair_key in sorted(self.compare_groups.keys()):
            if pair_key not in [p[0] for p in compare_order] and self.compare_groups[pair_key]:
                pair_id = self.variable_tree.insert('', 'end', text=f'对比: {pair_key}', open=False)
                for var_name in self.compare_groups[pair_key]:
                    display_name = self._format_var_display(var_name)
                    if var_name in self.pinned_variables:
                        display_name = PIN_PREFIX + display_name
                    self.variable_tree.insert(pair_id, 'end', text=display_name, tags=('variable',))

    def _format_var_display(self, var_name: str) -> str:
        """格式化变量显示名称（简化显示）"""
        # IMU列
        if var_name in IMU_COLUMNS:
            return f"IMU_{IMU_COLUMNS[var_name]}"

        # 电机数据列
        parsed = parse_motor_column_name(var_name)
        if parsed:
            leg, joint, var_type = parsed
            leg_short = leg
            joint_short = {'hip': '髋', 'thigh': '大腿', 'calf': '小腿', 'wheel': '轮'}.get(joint, joint)
            type_short = VARIABLE_TYPE_SHORT.get(var_type, var_type)
            return f"{leg_short}_{joint_short}_{type_short}"
        return var_name

    def on_variable_double_click(self, event):
        """变量双击事件 - 切换固定显示状态"""
        item_id = self.variable_tree.identify_row(event.y)
        if not item_id:
            return

        text = self.variable_tree.item(item_id, 'text')

        tags = self.variable_tree.item(item_id, 'tags')
        if 'variable' not in tags:
            return

        display_text = text.replace(PIN_PREFIX, '', 1) if text.startswith(PIN_PREFIX) else text

        var_name = self._display_to_column_name(display_text)
        if var_name is None:
            return

        if var_name in self.pinned_variables:
            self.pinned_variables.discard(var_name)
            self.variable_tree.item(item_id, text=display_text)
        else:
            self.pinned_variables.add(var_name)
            self.variable_tree.item(item_id, text=PIN_PREFIX + display_text)

        self.update_plot()

    def _display_to_column_name(self, display_text: str) -> Optional[str]:
        """将显示文本转换回原始列名"""
        # IMU列
        for imu_col, imu_label in IMU_COLUMNS.items():
            if display_text == f"IMU_{imu_label}":
                return imu_col

        # 直接匹配
        if display_text in self.data:
            return display_text

        # 尝试解析简化格式: LF_髋_q_des -> LF_hip_q_des
        parts = display_text.split('_')
        if len(parts) >= 3:
            leg = parts[0]
            if leg not in LEG_NAMES:
                return None

            joint_short = parts[1]
            joint_map = {'髋': 'hip', '大腿': 'thigh', '小腿': 'calf', '轮': 'wheel', '轮子': 'wheel'}
            joint = joint_map.get(joint_short, joint_short.lower())
            if joint not in JOINT_NAMES:
                return None

            type_str = '_'.join(parts[2:])
            type_short_to_full = {v: k for k, v in VARIABLE_TYPE_SHORT.items()}
            var_type = type_short_to_full.get(type_str, type_str)

            candidate = f"{leg}_{joint}_{var_type}"
            if candidate in self.data:
                return candidate

        return None

    def clear_pinned_variables(self):
        """清除所有固定显示的变量"""
        self.pinned_variables.clear()
        self.update_variable_tree()
        self.update_plot()

    def apply_preset(self, preset_name: str):
        """
        应用调试预设

        预设类型:
        - 'q_compare': 对比期望角度 vs 实际角度
        - 'tau_compare': 对比期望扭矩 vs 实际扭矩
        - 'all_q': 显示所有实际角度
        - 'all_q_des': 显示所有期望角度
        - 'all_tau': 显示所有实际扭矩
        - 'all_tau_des': 显示所有期望扭矩
        - 'imu_rpy': 显示IMU姿态角
        - 'imu_acc': 显示IMU加速度
        """
        self.pinned_variables.clear()

        if preset_name == 'q_compare':
            self.pinned_variables.update(self._get_vars_by_types(['q_des', 'q']))
            self.use_multiple_y_axes.set(True)
        elif preset_name == 'tau_compare':
            self.pinned_variables.update(self._get_vars_by_types(['tau_des', 'tau']))
            self.use_multiple_y_axes.set(True)
        elif preset_name == 'all_q':
            self.pinned_variables.update(self._get_vars_by_types(['q']))
            self.use_multiple_y_axes.set(False)
        elif preset_name == 'all_q_des':
            self.pinned_variables.update(self._get_vars_by_types(['q_des']))
            self.use_multiple_y_axes.set(False)
        elif preset_name == 'all_tau':
            self.pinned_variables.update(self._get_vars_by_types(['tau']))
            self.use_multiple_y_axes.set(False)
        elif preset_name == 'all_tau_des':
            self.pinned_variables.update(self._get_vars_by_types(['tau_des']))
            self.use_multiple_y_axes.set(False)
        elif preset_name == 'imu_rpy':
            for col in self.imu_columns:
                if col in ('roll', 'pitch', 'yaw') and col in self.data:
                    self.pinned_variables.add(col)
            self.use_multiple_y_axes.set(False)
        elif preset_name == 'imu_acc':
            for col in self.imu_columns:
                if col.startswith('acc_') and col in self.data:
                    self.pinned_variables.add(col)
            self.use_multiple_y_axes.set(False)

        self.update_variable_tree()
        self.update_plot()

    def _get_vars_by_types(self, var_types: List[str]) -> List[str]:
        """获取指定变量类型的所有列名"""
        result = []
        for col_name in self.motor_columns:
            parsed = parse_motor_column_name(col_name)
            if parsed and parsed[2] in var_types:
                result.append(col_name)
        return result

    def on_multi_y_toggle(self):
        """多y轴切换事件"""
        if self.use_smart_y_scales.get():
            self.use_multiple_y_axes.set(False)
        elif self.use_multiple_y_axes.get():
            self.use_smart_y_scales.set(False)
        self.update_plot()

    def get_variable_type(self, var_name: str) -> str:
        """
        根据变量名称识别变量类型，用于y轴分组
        """
        # IMU列
        if var_name in IMU_COLUMNS:
            if var_name in ('roll', 'pitch', 'yaw'):
                return 'imu_rpy'
            elif var_name.startswith('gyro_'):
                return 'imu_gyro'
            elif var_name.startswith('acc_'):
                return 'imu_acc'

        # 电机数据列
        parsed = parse_motor_column_name(var_name)
        if parsed:
            leg, joint, var_type = parsed
            return var_type

        return f'other_{var_name}'

    def register_plot_line(self, line, var_name: str, label: str):
        """记录已绘制曲线，用于点击后查找最近数据点。"""
        self.plot_lines.append({
            'line': line,
            'var_name': var_name,
            'label': label,
        })

    def clear_click_annotation(self):
        """清除上一次点击坐标标注。"""
        for artist in (self.click_annotation, self.click_marker):
            if artist is None:
                continue
            try:
                artist.remove()
            except Exception:
                pass
        self.click_annotation = None
        self.click_marker = None

    def on_plot_click(self, event):
        """点击图中曲线附近时显示最近数据点的横纵坐标。"""
        if not MATPLOTLIB_AVAILABLE or event.button != 1 or event.inaxes is None:
            return

        toolbar = getattr(self, 'toolbar', None)
        if toolbar is not None and getattr(toolbar, 'mode', ''):
            return

        if not self.plot_lines:
            return

        best = None
        best_distance = None

        for item in self.plot_lines:
            line = item['line']
            axis = line.axes
            try:
                x_data = np.asarray(line.get_xdata(), dtype=float)
                y_data = np.asarray(line.get_ydata(), dtype=float)
            except Exception:
                continue

            if x_data.size == 0 or y_data.size == 0:
                continue

            valid_mask = np.isfinite(x_data) & np.isfinite(y_data)
            if not np.any(valid_mask):
                continue

            x_valid = x_data[valid_mask]
            y_valid = y_data[valid_mask]
            display_points = axis.transData.transform(np.column_stack([x_valid, y_valid]))
            distances = ((display_points[:, 0] - event.x) ** 2 +
                         (display_points[:, 1] - event.y) ** 2)
            point_index = int(np.argmin(distances))
            distance = float(np.sqrt(distances[point_index]))

            if best_distance is None or distance < best_distance:
                best_distance = distance
                best = (item, axis, x_valid[point_index], y_valid[point_index], distance)

        if best is None or best_distance is None or best_distance > 30:
            return

        item, axis, x_value, y_value, _ = best
        self.clear_click_annotation()

        color = item['line'].get_color()
        x_display = f"{int(x_value)}" if float(x_value).is_integer() else f"{x_value:.3f}"
        text = f"{item['label']}\nX: {x_display}\nY: {y_value:.6g}"

        self.click_marker = axis.plot(
            [x_value], [y_value], marker='o', markersize=8,
            markerfacecolor='#FFF176', markeredgecolor=color,
            markeredgewidth=2, linestyle='None', zorder=10,
            label='_nolegend_'
        )[0]
        self.click_annotation = axis.annotate(
            text, xy=(x_value, y_value), xytext=(12, 12),
            textcoords='offset points', fontsize=9, color='#2C3E50',
            bbox=dict(boxstyle='round,pad=0.35', fc='#FFFDE7', ec=color, alpha=0.95),
            arrowprops=dict(arrowstyle='->', color=color, lw=1.2),
        )
        self.canvas.draw_idle()

    def update_plot(self):
        """更新图表"""
        if not MATPLOTLIB_AVAILABLE or not self.data:
            return

        self.clear_click_annotation()
        self.plot_lines = []
        self.fig.clear()
        self.ax = self.fig.add_subplot(111)

        self.ax.grid(True, alpha=0.3)
        self.ax.set_xlabel('采样序号', fontsize=10)

        all_variables = list(self.pinned_variables)

        if not all_variables:
            self.ax.set_ylabel('数值', fontsize=10)
            self.ax.set_title('电机追踪数据曲线图（请双击变量固定显示，或使用预设按钮）', fontsize=12)
            self.ax.text(0.5, 0.5, '请在左侧双击变量以固定显示曲线\n或点击「快速预设」按钮进行调试分析\n（前4列元数据已自动跳过）',
                        ha='center', va='center', transform=self.ax.transAxes,
                        fontsize=12, color='gray')
        else:
            self.selected_variables = all_variables

            # 获取x轴数据
            if self.data:
                first_var = list(self.data.keys())[0]
                iteration_data = np.arange(len(self.data[first_var]))

            colors = ['#3498DB', '#E74C3C', '#2ECC71', '#F39C12', '#9B59B6',
                     '#1ABC9C', '#E67E22', '#34495E', '#E91E63', '#00BCD4',
                     '#8E44AD', '#27AE60', '#D35400', '#2980B9', '#C0392B',
                     '#16A085', '#F1C40F', '#7F8C8D', '#2C3E50', '#E74C3C',
                     '#1ABC9C', '#3498DB', '#9B59B6', '#E67E22']

            use_smart_y = self.use_smart_y_scales.get() and len(self.selected_variables) > 1
            use_multi_y = self.use_multiple_y_axes.get() and len(self.selected_variables) > 1

            if use_smart_y:
                self._plot_with_smart_y_scales(iteration_data, colors)
            elif use_multi_y:
                lines_list = []
                vars_to_plot = self.selected_variables[:8]

                for i, var_name in enumerate(vars_to_plot):
                    if var_name not in self.data:
                        continue

                    color = colors[i % len(colors)]
                    data_array = np.array(self.data[var_name])

                    label = self._format_var_display(var_name)
                    if len(label) > 25:
                        label = label[:22] + '...'

                    if i == 0:
                        line = self.ax.plot(iteration_data, data_array,
                                          label=label, color=color, linewidth=2.0, alpha=0.85)
                        lines_list.append(line[0])
                        self.register_plot_line(line[0], var_name, label)
                        self.ax.set_ylabel(label, fontsize=11, color=color, fontweight='bold')
                        self.ax.tick_params(axis='y', labelcolor=color, labelsize=10)
                        self.ax.spines['left'].set_color(color)
                        self.ax.spines['left'].set_linewidth(2)
                    else:
                        ax_new = self.ax.twinx()
                        offset = min(i - 1, 3) * 50
                        if offset > 0:
                            ax_new.spines['right'].set_position(('outward', offset))
                        line = ax_new.plot(iteration_data, data_array,
                                         label=label, color=color, linewidth=2.0, alpha=0.85)
                        lines_list.append(line[0])
                        self.register_plot_line(line[0], var_name, label)
                        ax_new.set_ylabel(label, fontsize=11, color=color, fontweight='bold')
                        ax_new.tick_params(axis='y', labelcolor=color, labelsize=10)
                        ax_new.spines['right'].set_color(color)
                        ax_new.spines['right'].set_linewidth(2)

                all_labels = [line.get_label() for line in lines_list]
                self.ax.legend(lines_list, all_labels, loc='best', fontsize=10, framealpha=0.95,
                             ncol=1, fancybox=True, shadow=True)

                title = f'电机追踪数据曲线图（{len(vars_to_plot)}个变量，多Y轴）'
                if len(self.selected_variables) > 8:
                    title += f'（仅显示前8个）'
                self.ax.set_title(title, fontsize=14, fontweight='bold', pad=15)

            else:
                # 单y轴模式
                for i, var_name in enumerate(self.selected_variables[:10]):
                    if var_name in self.data:
                        color = colors[i % len(colors)]
                        label = self._format_var_display(var_name)
                        if len(label) > 30:
                            label = label[:27] + '...'
                        line = self.ax.plot(iteration_data, np.array(self.data[var_name]),
                                          label=label, color=color, linewidth=2.0, alpha=0.85)
                        self.register_plot_line(line[0], var_name, label)

                self.ax.set_ylabel('数值', fontsize=12, fontweight='bold')
                self.ax.tick_params(axis='both', labelsize=10)
                self.ax.legend(loc='best', fontsize=10, framealpha=0.95, ncol=1,
                             fancybox=True, shadow=True)
                title = f'电机追踪数据曲线图（{len(self.selected_variables)}个变量）'
                if len(self.selected_variables) > 10:
                    title += f'（仅显示前10个）'
                self.ax.set_title(title, fontsize=14, fontweight='bold', pad=15)

        self.canvas.draw()

    def _plot_with_smart_y_scales(self, iteration_data, colors):
        """使用智能y轴分组绘制图表（适配motor_trace数据格式）"""
        from collections import defaultdict

        # 按变量类型分组
        var_groups = defaultdict(list)
        for var_name in self.selected_variables:
            if var_name in self.data:
                var_type = self.get_variable_type(var_name)
                var_groups[var_type].append(var_name)

        # 类型显示名称映射
        type_names = {
            'q_des': '期望角度 q_des',
            'q': '实际角度 q',
            'tau_des': '期望扭矩 tau_des',
            'tau': '实际扭矩 tau',
            'imu_rpy': 'IMU姿态角',
            'imu_gyro': 'IMU角速度',
            'imu_acc': 'IMU加速度',
        }

        sorted_groups = sorted(var_groups.items(), key=lambda x: len(x[1]), reverse=True)[:8]

        axes_dict = {}
        lines_list = []

        for group_idx, (var_type, var_list) in enumerate(sorted_groups):
            type_display_name = type_names.get(var_type, var_type)

            if group_idx == 0:
                current_ax = self.ax
            else:
                current_ax = self.ax.twinx()
                offset = min(group_idx - 1, 3) * 50
                if offset > 0:
                    current_ax.spines['right'].set_position(('outward', offset))

            axes_dict[var_type] = current_ax

            group_colors = colors[group_idx % len(colors):] + colors[:group_idx % len(colors)]

            for var_idx, var_name in enumerate(var_list[:10]):
                if var_name not in self.data:
                    continue

                color = group_colors[var_idx % len(group_colors)]
                data_array = np.array(self.data[var_name])

                label = self._format_var_display(var_name)
                if len(label) > 25:
                    label = label[:22] + '...'

                line = current_ax.plot(iteration_data, data_array,
                                     label=label, color=color, linewidth=2.0, alpha=0.85)
                lines_list.append(line[0])
                self.register_plot_line(line[0], var_name, label)

            if group_idx == 0:
                current_ax.set_ylabel(type_display_name, fontsize=11, color=group_colors[0], fontweight='bold')
                current_ax.tick_params(axis='y', labelcolor=group_colors[0], labelsize=10)
                current_ax.spines['left'].set_color(group_colors[0])
                current_ax.spines['left'].set_linewidth(2)
            else:
                current_ax.set_ylabel(type_display_name, fontsize=11, color=group_colors[0], fontweight='bold')
                current_ax.tick_params(axis='y', labelcolor=group_colors[0], labelsize=10)
                current_ax.spines['right'].set_color(group_colors[0])
                current_ax.spines['right'].set_linewidth(2)

        if lines_list:
            all_labels = [line.get_label() for line in lines_list]
            self.ax.legend(lines_list, all_labels, loc='best', fontsize=10, framealpha=0.95,
                         ncol=1, fancybox=True, shadow=True)

        self.ax.tick_params(axis='x', labelsize=10)

        title = f'电机追踪数据曲线图（{len(self.selected_variables)}个变量，智能Y轴分组）'
        if len(self.selected_variables) > 10:
            title += f'（仅显示前10个）'
        self.ax.set_title(title, fontsize=14, fontweight='bold', pad=15)

    def show_about(self):
        """显示关于对话框"""
        about_window = tk.Toplevel(self.root)
        about_window.title("关于")
        about_window.geometry("550x400")
        about_window.configure(bg=self.colors['bg_section'])
        about_window.resizable(False, False)
        about_window.transient(self.root)
        about_window.grab_set()

        main_container = tk.Frame(about_window, bg=self.colors['bg_section'], padx=30, pady=25)
        main_container.pack(fill=tk.BOTH, expand=True)

        title_label = tk.Label(main_container, text="电机追踪数据查看器",
                              font=self.font_title, bg=self.colors['bg_section'],
                              fg=self.colors['fg_text'])
        title_label.pack(pady=(0, 5))

        subtitle_label = tk.Label(main_container, text="四足机器人电机数据 - MotorTrace",
                                 font=self.font_large, bg=self.colors['bg_section'],
                                 fg=self.colors['fg_label'])
        subtitle_label.pack(pady=(0, 20))

        separator = tk.Frame(main_container, height=1, bg=self.colors['border'])
        separator.pack(fill=tk.X, pady=(0, 20))

        version_frame = tk.Frame(main_container, bg=self.colors['bg_section'])
        version_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Label(version_frame, text="版本: 1.0 (motor_trace.csv格式适配)",
                font=self.font_normal, bg=self.colors['bg_section'],
                fg=self.colors['fg_text'], anchor='w').pack(fill=tk.X, pady=(0, 10))

        tk.Label(version_frame, text="基于: data_viewer.py (Han Jiang)",
                font=self.font_normal, bg=self.colors['bg_section'],
                fg=self.colors['fg_text'], anchor='w').pack(fill=tk.X, pady=(0, 15))

        tk.Label(main_container, text="CSV格式: 前4列为元数据(iteration/time_s/loop_interval_ms/cycle_duration_ms)",
                font=self.font_normal, bg=self.colors['bg_section'],
                fg=self.colors['fg_label'], anchor='w').pack(fill=tk.X, pady=(0, 5))

        tk.Label(main_container, text="电机数据: {腿}_{关节}_{变量}",
                font=self.font_normal, bg=self.colors['bg_section'],
                fg=self.colors['fg_label'], anchor='w').pack(fill=tk.X, pady=(0, 5))

        tk.Label(main_container, text="  腿: LF/RF/LR/RR  |  关节: hip/thigh/calf/wheel",
                font=self.font_small, bg=self.colors['bg_section'],
                fg=self.colors['fg_text'], anchor='w').pack(fill=tk.X, pady=(0, 5))

        tk.Label(main_container, text="  变量: q_des/q/tau_des/tau",
                font=self.font_small, bg=self.colors['bg_section'],
                fg=self.colors['fg_text'], anchor='w').pack(fill=tk.X, pady=(0, 5))

        tk.Label(main_container, text="IMU数据: roll/pitch/yaw/gyro_x/y/z/acc_x/y/z",
                font=self.font_small, bg=self.colors['bg_section'],
                fg=self.colors['fg_text'], anchor='w').pack(fill=tk.X, pady=(0, 15))

        tk.Label(main_container, text="功能：",
                font=self.font_normal, bg=self.colors['bg_section'],
                fg=self.colors['fg_label'], anchor='w').pack(fill=tk.X, pady=(0, 8))

        features = [
            "  - 自动跳过前4列元数据(iteration, time_s, loop_interval_ms, cycle_duration_ms)",
            "  - 支持按变量类型/腿/关节/对比视图分组浏览电机数据",
            "  - 一键预设：角度对比(q_des vs q)、扭矩对比(tau_des vs tau)",
            "  - 单独查看IMU姿态、加速度数据",
            "  - 智能Y轴分组、独立Y轴显示",
            "  - 支持缩放和平移",
        ]

        for feature in features:
            tk.Label(main_container, text=feature,
                    font=self.font_normal, bg=self.colors['bg_section'],
                    fg=self.colors['fg_text'], anchor='w').pack(fill=tk.X, pady=(0, 5))

        button_frame = tk.Frame(main_container, bg=self.colors['bg_section'])
        button_frame.pack(fill=tk.X, pady=(20, 0))

        close_button = tk.Button(button_frame, text="确定",
                                font=self.font_normal, bg='#4A90E2', fg='white',
                                relief='flat', bd=0, padx=30, pady=8,
                                cursor='hand2', activebackground='#357ABD',
                                activeforeground='white',
                                command=about_window.destroy)
        close_button.pack()

        about_window.bind('<Escape>', lambda e: about_window.destroy())
        about_window.bind('<Return>', lambda e: about_window.destroy())
        close_button.focus_set()


def main():
    """主函数"""
    csv_file = None
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        # 默认尝试打开motor_trace.csv
        script_dir = os.path.dirname(os.path.abspath(__file__))
        default_csv = os.path.join(script_dir, "motor_trace.csv")
        if os.path.exists(default_csv):
            csv_file = default_csv

    root = tk.Tk()
    app = MotorTraceViewer(root, csv_file)
    root.mainloop()


if __name__ == "__main__":
    main()
