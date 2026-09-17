#!/usr/bin/env python3
"""
LCM 通道监控脚本 - 自动检测所有通道并显示频率，支持变量曲线绘制
作者: Han Jiang (jh18954242606@163.com)
日期: 2026-01
功能: 自动检测所有LCM通道，10Hz显示通道名称和频率，支持选择变量绘制曲线
"""

import sys
import os
import time
import threading
import argparse
import numpy as np
from collections import deque, OrderedDict
from datetime import datetime
from queue import Queue
import signal
import atexit

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, 'lcm-types', 'python'))

try:
    import lcm
    LCM_AVAILABLE = True
except ImportError as e:
    print(f"错误: LCM 模块导入失败: {e}")
    sys.exit(1)

try:
    from quad_joint_state_t import quad_joint_state_t
    from quad_joint_command_t import quad_joint_command_t
    from microstrain_lcmt import microstrain_lcmt
    from development_state_t import development_state_t
    from development_command_t import development_command_t
    TYPES_AVAILABLE = True
except ImportError:
    print("警告: LCM类型文件未找到，将使用原始数据处理")
    TYPES_AVAILABLE = False

try:
    import matplotlib
    # 强制使用TkAgg后端（支持交互式GUI）
    import os
    try:
        matplotlib.use('TkAgg')
        # 测试后端是否可用
        import matplotlib.pyplot as plt
        plt.figure()  # 尝试创建图形
        plt.close()
    except Exception:
        try:
            matplotlib.use('Qt5Agg')
        except Exception:
            pass  # 使用默认后端
    
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    import tkinter as tk
    from tkinter import messagebox
    TKINTER_AVAILABLE = True
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    TKINTER_AVAILABLE = False
except Exception:
    MATPLOTLIB_AVAILABLE = False
    TKINTER_AVAILABLE = False

# 频率计算窗口大小
FREQ_WINDOW_SIZE = 100
UPDATE_INTERVAL = 0.1  # 10Hz更新频率
MAX_PLOT_POINTS = 1000  # 最大绘图点数


class VariableMonitor:
    """单个变量监控器"""
    def __init__(self, channel_name, variable_name):
        self.channel_name = channel_name
        self.variable_name = variable_name
        self.values = deque(maxlen=MAX_PLOT_POINTS)
        self.timestamps = deque(maxlen=MAX_PLOT_POINTS)
        self.lock = threading.Lock()
    
    def add_value(self, value, timestamp=None):
        """添加变量值"""
        if timestamp is None:
            timestamp = time.time()
        with self.lock:
            self.values.append(value)
            self.timestamps.append(timestamp)


class ChannelMonitor:
    """单个通道监控器"""
    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.timestamps = deque(maxlen=FREQ_WINDOW_SIZE)
        self.message_count = 0
        self.last_message_time = None
        self.last_data = None
        self.lock = threading.Lock()
        # 变量监控器字典 {variable_name: VariableMonitor}
        self.variables = {}
        self.variables_lock = threading.Lock()
        # 缓存的变量名称列表（一旦检测到变量，就固定使用这些变量）
        self.cached_variable_names = None
        self.cached_variable_names_lock = threading.Lock()
    
    def add_message(self, data=None, decoded_msg=None):
        """记录消息接收"""
        with self.lock:
            current_time = time.time()
            self.timestamps.append(current_time)
            self.message_count += 1
            self.last_message_time = current_time
            if data is not None:
                self.last_data = data
        
        # 提取变量值
        if decoded_msg is not None:
            self._extract_variables(decoded_msg, current_time)
    
    def _extract_variables(self, msg, timestamp):
        """从消息中提取变量值"""
        with self.variables_lock:
            # 根据消息类型提取变量
            msg_type = type(msg).__name__
            
            if isinstance(msg, quad_joint_state_t):
                # 提取关节位置
                for i, val in enumerate(msg.L_Leg_q):
                    var_name = f"L_Leg_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_q):
                    var_name = f"R_Leg_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.L_Arm_q):
                    var_name = f"L_Arm_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Arm_q):
                    var_name = f"R_Arm_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                var_name = "waist_q"
                if var_name not in self.variables:
                    self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                self.variables[var_name].add_value(msg.waist_q, timestamp)
            
            elif isinstance(msg, quad_joint_command_t):
                # 提取关节命令数据（位置、速度、力矩、kp、kd等）
                # 提取位置
                for i, val in enumerate(msg.L_Leg_q):
                    var_name = f"L_Leg_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_q):
                    var_name = f"R_Leg_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.L_Arm_q):
                    var_name = f"L_Arm_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Arm_q):
                    var_name = f"R_Arm_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                # 提取速度
                for i, val in enumerate(msg.L_Leg_qd):
                    var_name = f"L_Leg_qd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_qd):
                    var_name = f"R_Leg_qd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                # 提取力矩
                for i, val in enumerate(msg.L_Leg_tau):
                    var_name = f"L_Leg_tau[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_tau):
                    var_name = f"R_Leg_tau[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.L_Arm_tau):
                    var_name = f"L_Arm_tau[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Arm_tau):
                    var_name = f"R_Arm_tau[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                # 提取kp（位置增益）
                for i, val in enumerate(msg.L_Leg_kp):
                    var_name = f"L_Leg_kp[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_kp):
                    var_name = f"R_Leg_kp[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.L_Arm_kp):
                    var_name = f"L_Arm_kp[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Arm_kp):
                    var_name = f"R_Arm_kp[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                # 提取kd（速度增益）
                for i, val in enumerate(msg.L_Leg_kd):
                    var_name = f"L_Leg_kd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_kd):
                    var_name = f"R_Leg_kd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.L_Arm_kd):
                    var_name = f"L_Arm_kd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Arm_kd):
                    var_name = f"R_Arm_kd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                # 提取waist相关
                if hasattr(msg, 'waist_q'):
                    var_name = "waist_q"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.waist_q, timestamp)
                
                if hasattr(msg, 'waist_qd'):
                    var_name = "waist_qd"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.waist_qd, timestamp)
                
                if hasattr(msg, 'waist_tau'):
                    var_name = "waist_tau"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.waist_tau, timestamp)
                
                if hasattr(msg, 'waist_kp'):
                    var_name = "waist_kp"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.waist_kp, timestamp)
                
                if hasattr(msg, 'waist_kd'):
                    var_name = "waist_kd"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.waist_kd, timestamp)
                
                # 提取Head相关
                if hasattr(msg, 'Head_q'):
                    var_name = "Head_q"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.Head_q, timestamp)
                
                if hasattr(msg, 'Head_qd'):
                    var_name = "Head_qd"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.Head_qd, timestamp)
                
                if hasattr(msg, 'Head_tau'):
                    var_name = "Head_tau"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.Head_tau, timestamp)
                
                if hasattr(msg, 'Head_kp'):
                    var_name = "Head_kp"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.Head_kp, timestamp)
                
                if hasattr(msg, 'Head_kd'):
                    var_name = "Head_kd"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.Head_kd, timestamp)
            
            elif isinstance(msg, microstrain_lcmt):
                # 提取IMU数据
                for i, val in enumerate(msg.rpy):
                    var_name = f"rpy[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.omega):
                    var_name = f"omega[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
            
            elif isinstance(msg, development_state_t):
                # 提取开发模式状态数据（所有字段）
                # 关节位置
                for i, val in enumerate(msg.L_Leg_q):
                    var_name = f"L_Leg_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_q):
                    var_name = f"R_Leg_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.L_Arm_q):
                    var_name = f"L_Arm_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Arm_q):
                    var_name = f"R_Arm_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                # 关节速度
                for i, val in enumerate(msg.L_Leg_qd):
                    var_name = f"L_Leg_qd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_qd):
                    var_name = f"R_Leg_qd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.L_Arm_qd):
                    var_name = f"L_Arm_qd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Arm_qd):
                    var_name = f"R_Arm_qd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                # 关节力矩
                for i, val in enumerate(msg.L_Leg_tau):
                    var_name = f"L_Leg_tau[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_tau):
                    var_name = f"R_Leg_tau[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.L_Arm_tau):
                    var_name = f"L_Arm_tau[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Arm_tau):
                    var_name = f"R_Arm_tau[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                # Head相关
                if hasattr(msg, 'Head_q'):
                    var_name = "Head_q"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.Head_q, timestamp)
                
                if hasattr(msg, 'Head_qd'):
                    var_name = "Head_qd"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.Head_qd, timestamp)
                
                if hasattr(msg, 'Head_tau'):
                    var_name = "Head_tau"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.Head_tau, timestamp)
                
                # waist相关
                if hasattr(msg, 'waist_q'):
                    var_name = "waist_q"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.waist_q, timestamp)
                
                if hasattr(msg, 'waist_qd'):
                    var_name = "waist_qd"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.waist_qd, timestamp)
                
                if hasattr(msg, 'waist_tau'):
                    var_name = "waist_tau"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.waist_tau, timestamp)
                
                # IMU数据
                for i, val in enumerate(msg.quat):
                    var_name = f"quat[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.rpy):
                    var_name = f"rpy[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.omega):
                    var_name = f"omega[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.acc):
                    var_name = f"acc[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                # 遥控器指令
                for i, val in enumerate(msg.v_des):
                    var_name = f"v_des[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.omega_des):
                    var_name = f"omega_des[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                if hasattr(msg, 'mode'):
                    var_name = "mode"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.mode, timestamp)
            
            elif isinstance(msg, development_command_t):
                # 提取开发模式命令数据（所有字段）
                # 关节位置
                for i, val in enumerate(msg.L_Leg_q):
                    var_name = f"L_Leg_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_q):
                    var_name = f"R_Leg_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.L_Arm_q):
                    var_name = f"L_Arm_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Arm_q):
                    var_name = f"R_Arm_q[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                if hasattr(msg, 'waist_q'):
                    var_name = "waist_q"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.waist_q, timestamp)
                
                # 关节速度
                for i, val in enumerate(msg.L_Leg_qd):
                    var_name = f"L_Leg_qd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_qd):
                    var_name = f"R_Leg_qd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.L_Arm_qd):
                    var_name = f"L_Arm_qd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Arm_qd):
                    var_name = f"R_Arm_qd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                if hasattr(msg, 'waist_qd'):
                    var_name = "waist_qd"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.waist_qd, timestamp)
                
                # 关节力矩
                for i, val in enumerate(msg.L_Leg_tau):
                    var_name = f"L_Leg_tau[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_tau):
                    var_name = f"R_Leg_tau[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.L_Arm_tau):
                    var_name = f"L_Arm_tau[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Arm_tau):
                    var_name = f"R_Arm_tau[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                if hasattr(msg, 'waist_tau'):
                    var_name = "waist_tau"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.waist_tau, timestamp)
                
                # kp
                for i, val in enumerate(msg.L_Leg_kp):
                    var_name = f"L_Leg_kp[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_kp):
                    var_name = f"R_Leg_kp[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.L_Arm_kp):
                    var_name = f"L_Arm_kp[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Arm_kp):
                    var_name = f"R_Arm_kp[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                if hasattr(msg, 'waist_kp'):
                    var_name = "waist_kp"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.waist_kp, timestamp)
                
                # kd
                for i, val in enumerate(msg.L_Leg_kd):
                    var_name = f"L_Leg_kd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Leg_kd):
                    var_name = f"R_Leg_kd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.L_Arm_kd):
                    var_name = f"L_Arm_kd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                for i, val in enumerate(msg.R_Arm_kd):
                    var_name = f"R_Arm_kd[{i}]"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(val, timestamp)
                
                if hasattr(msg, 'waist_kd'):
                    var_name = "waist_kd"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.waist_kd, timestamp)
                
                # 控制标志
                if hasattr(msg, 'enable_development_mode'):
                    var_name = "enable_development_mode"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.enable_development_mode, timestamp)
                
                if hasattr(msg, 'is_rl_mode'):
                    var_name = "is_rl_mode"
                    if var_name not in self.variables:
                        self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                    self.variables[var_name].add_value(msg.is_rl_mode, timestamp)
            else:
                # 对于未知消息类型，尝试提取通用字段
                try:
                    # 尝试使用反射获取消息的所有属性
                    if hasattr(msg, '__dict__'):
                        for attr_name, attr_value in msg.__dict__.items():
                            if not attr_name.startswith('_'):
                                # 如果是数组或列表
                                if isinstance(attr_value, (list, tuple)):
                                    for i, val in enumerate(attr_value):
                                        var_name = f"{attr_name}[{i}]"
                                        if var_name not in self.variables:
                                            self.variables[var_name] = VariableMonitor(self.channel_name, var_name)
                                        self.variables[var_name].add_value(val, timestamp)
                                # 如果是数值类型
                                elif isinstance(attr_value, (int, float)):
                                    if attr_name not in self.variables:
                                        self.variables[attr_name] = VariableMonitor(self.channel_name, attr_name)
                                    self.variables[attr_name].add_value(attr_value, timestamp)
                except Exception:
                    pass  # 忽略提取错误
            
            # 如果变量列表不为空，更新缓存（一旦检测到变量，就固定使用这些变量）
            # 注意：这里已经在variables_lock内，所以直接访问self.variables
            if self.variables:
                var_names = sorted(list(self.variables.keys()))
                with self.cached_variable_names_lock:
                    if self.cached_variable_names is None or len(var_names) > len(self.cached_variable_names):
                        # 如果缓存为空，或者新检测到的变量更多，更新缓存
                        self.cached_variable_names = var_names
    
    def get_frequency(self):
        """计算频率（Hz）"""
        with self.lock:
            if len(self.timestamps) < 2:
                return 0.0
            
            # 计算最近消息的平均间隔
            intervals = []
            for i in range(1, len(self.timestamps)):
                interval = self.timestamps[i] - self.timestamps[i-1]
                if interval > 0:
                    intervals.append(interval)
            
            if len(intervals) == 0:
                return 0.0
            
            avg_interval = sum(intervals) / len(intervals)
            return 1.0 / avg_interval if avg_interval > 0 else 0.0
    
    def is_active(self, timeout=1.0):
        """检查通道是否活跃"""
        with self.lock:
            if self.last_message_time is None:
                return False
            return (time.time() - self.last_message_time) < timeout
    
    def get_variable_names(self):
        """获取所有变量名称（优先返回缓存）"""
        # 优先返回缓存的变量列表
        with self.cached_variable_names_lock:
            if self.cached_variable_names is not None:
                return self.cached_variable_names
        
        # 如果缓存不存在，返回当前的变量列表
        with self.variables_lock:
            var_names = sorted(list(self.variables.keys()))
            # 如果当前有变量，更新缓存
            if var_names:
                with self.cached_variable_names_lock:
                    self.cached_variable_names = var_names
            return var_names


class LCMChannelMonitor:
    """LCM通道监控主类"""
    
    def __init__(self, lcm_url="", use_gui=True):
        self.lcm_url = lcm_url
        # 检查matplotlib是否可用且支持GUI
        if use_gui and MATPLOTLIB_AVAILABLE:
            try:
                import matplotlib
                backend = matplotlib.get_backend()
                # 如果后端是Agg（非交互式），尝试切换到交互式后端
                if backend == 'Agg':
                    try:
                        matplotlib.use('TkAgg')
                        backend = matplotlib.get_backend()
                    except Exception:
                        self.use_gui = False
                        return
                
                # 检查后端是否支持交互
                if backend.lower() in ['agg', 'pdf', 'svg', 'ps']:
                    self.use_gui = False
                else:
                    self.use_gui = True
            except Exception:
                self.use_gui = False
        else:
            self.use_gui = False
        self.running = False
        
        # 通道监控器字典（使用OrderedDict保持顺序）
        self.channels = OrderedDict()
        self.channels_lock = threading.Lock()
        
        # 选中的变量用于绘图 {channel_name: [variable_names]}
        self.selected_variables = {}
        self.selected_variables_lock = threading.Lock()
        
        # 对话框请求队列（用于在主线程中处理tkinter对话框）
        self.dialog_queue = Queue()
        
        # 当前打开的对话框列表（用于清理）
        self.open_dialogs = []
        self.dialogs_lock = threading.Lock()
        
        # 按钮Rectangle存储（用于点击检测）
        self.plus_button_rects = {}
        self.plus_button_positions = {}
        self.clear_all_button_rect = None
        
        # 通用消息处理器
        self.generic_handlers = {}
        
    def _generic_handler(self, channel_name):
        """创建通用消息处理器"""
        def handler(channel, data):
            # 记录消息
            if channel_name not in self.channels:
                with self.channels_lock:
                    if channel_name not in self.channels:
                        self.channels[channel_name] = ChannelMonitor(channel_name)
            
            monitor = self.channels[channel_name]
            
            # 尝试解码已知的消息类型
            decoded_msg = None
            if TYPES_AVAILABLE:
                try:
                    if channel_name == "quad_JOINT_STATE":
                        decoded_msg = quad_joint_state_t.decode(data)
                    elif channel_name == "quad_JOINT_COMMAND":
                        # COMMAND 使用不同的消息类型
                        decoded_msg = quad_joint_command_t.decode(data)
                    elif channel_name == "MICROSTRAIN_IMU_DATA":
                        decoded_msg = microstrain_lcmt.decode(data)
                    elif "Y20W_development_state" in channel_name.lower():
                        decoded_msg = development_state_t.decode(data)
                    elif "Y20W_development_command" in channel_name.lower():
                        decoded_msg = development_command_t.decode(data)
                    elif channel_name == "state_estimator":
                        # state_estimator 只使用 development_state_t 类型，不要尝试其他类型
                        decoded_msg = development_state_t.decode(data)
                except Exception:
                    # 解码失败是正常的（消息类型可能不匹配），静默处理
                    pass
            
            monitor.add_message(data, decoded_msg)
        
        return handler
    
    def start(self):
        """启动监控"""
        try:
            if self.lcm_url:
                self.lcm = lcm.LCM(self.lcm_url)
            else:
                self.lcm = lcm.LCM()
            
            # 订阅所有已知的通道
            known_channels = [
                "quad_JOINT_STATE",
                "quad_JOINT_COMMAND",
                "MICROSTRAIN_IMU_DATA",
                "state_estimator",
                "Y20W_development_state",
                "Y20W_development_command",
            ]
            
            for channel in known_channels:
                handler = self._generic_handler(channel)
                self.lcm.subscribe(channel, handler)
                self.generic_handlers[channel] = handler
            
            self.running = True
            
            # 启动LCM处理线程
            lcm_thread = threading.Thread(target=self._run_lcm, daemon=True)
            lcm_thread.start()
            
            # GUI或文本模式（GUI模式会在_run_gui中阻塞）
            if self.use_gui:
                # GUI模式会在_run_gui中阻塞，直到窗口关闭
                self._run_gui()
            else:
                print("=" * 60)
                print("  LCM Channel Monitor")
                print("=" * 60)
                print(f"LCM URL: {self.lcm_url if self.lcm_url else 'default'}")
                print(f"Update Frequency: {1.0/UPDATE_INTERVAL:.1f} Hz")
                print(f"GUI: disabled (text mode)")
                print("=" * 60)
                print("\n等待LCM消息...")
                print("通道将按名称排序显示（顺序稳定）\n")
                self._run_text_mode()
            
            return True
        except Exception as e:
            if not self.use_gui:
                print(f"错误: 启动失败: {e}")
                import traceback
                traceback.print_exc()
            return False
    
    def _run_lcm(self):
        """LCM处理线程"""
        while self.running:
            try:
                timeout_ms = 100
                self.lcm.handle_timeout(timeout_ms)
            except AttributeError:
                try:
                    self.lcm.handle()
                except Exception:
                    time.sleep(0.1)
            except Exception as e:
                if "timeout" not in str(e).lower():
                    pass
                time.sleep(0.01)
    
    def _run_text_mode(self):
        """文本模式运行"""
        try:
            while self.running:
                time.sleep(UPDATE_INTERVAL)
                self._print_text_status()
        except KeyboardInterrupt:
            print("\n正在退出...")
    
    def _print_text_status(self):
        """打印文本状态（10Hz更新）"""
        os.system('clear' if os.name != 'nt' else 'cls')
        
        print("=" * 80)
        print(f"  LCM Channel Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        print(f"{'Channel Name':<40} {'Frequency (Hz)':<20} {'Messages':<15}")
        print("-" * 80)
        
        with self.channels_lock:
            # 按通道名称排序（保持顺序稳定）
            active_channels = [
                (name, monitor) 
                for name, monitor in self.channels.items()
                if monitor.is_active()
            ]
            active_channels.sort(key=lambda x: x[0])  # 按名称排序
        
        if not active_channels:
            print("  (No active channels detected)")
        else:
            for channel_name, monitor in active_channels:
                freq = monitor.get_frequency()
                count = monitor.message_count
                print(f"{channel_name:<40} {freq:>15.2f} Hz    {count:>10}")
        
        print("=" * 80)
        print("\nPress Ctrl+C to exit")
    
    def _run_gui(self):
        """GUI模式运行"""
        if not self.use_gui:
            return
        
        # 检查matplotlib是否可用
        if not MATPLOTLIB_AVAILABLE:
            self.use_gui = False
            self._run_text_mode()
            return
        
        try:
            # 尝试创建图形
            fig = plt.figure(figsize=(16, 10))
            fig.suptitle('LCM Channel Monitor', fontsize=16, fontweight='bold')
        except Exception:
            self.use_gui = False
            self._run_text_mode()
            return
        
        # 创建布局：状态信息、通道列表、变量曲线
        # 增加通道列表和变量曲线区域的高度，避免重叠
        gs = plt.GridSpec(3, 1, figure=fig, height_ratios=[0.3, 1.5, 2.0], hspace=0.35)
        
        # 最上方：状态信息
        ax_status = fig.add_subplot(gs[0, 0])
        ax_status.axis('off')
        
        # 中间：通道列表
        ax_channels = fig.add_subplot(gs[1, 0])
        ax_channels.axis('off')
        
        # 下方：变量曲线
        ax_plot = fig.add_subplot(gs[2, 0])
        ax_plot.set_xlabel('Time (s)', fontsize=10)
        ax_plot.set_ylabel('Value', fontsize=10)
        ax_plot.grid(True, alpha=0.3)
        ax_plot.set_title('Selected Variables Plot', fontsize=12, fontweight='bold')
        
        # 交互式选择
        self._setup_interactive_selection(fig, ax_channels, ax_plot)
        
        def update(frame):
            """更新GUI"""
            # 处理对话框队列（在主线程中处理tkinter对话框）
            # 使用after方法确保在主线程中执行
            try:
                while not self.dialog_queue.empty():
                    channel_name = self.dialog_queue.get_nowait()
                    # 使用after方法延迟执行，确保在主线程中
                    # 注意：使用lambda时需要用默认参数来正确捕获channel_name
                    root = fig.canvas.get_tk_widget().master
                    root.after(0, lambda ch=channel_name: self._select_variables(ch, fig))
            except Exception:
                pass
            
            # 更新状态信息
            ax_status.clear()
            ax_status.axis('off')
            
            status_y = 0.9
            ax_status.text(0.05, status_y, 'LCM Channel Monitor', 
                          fontsize=16, fontweight='bold', transform=ax_status.transAxes)
            status_y -= 0.3
            
            lcm_url_str = self.lcm_url if self.lcm_url else 'default'
            ax_status.text(0.05, status_y, f'LCM URL: {lcm_url_str}', 
                          fontsize=10, transform=ax_status.transAxes, family='monospace')
            status_y -= 0.3
            
            import matplotlib
            backend = matplotlib.get_backend()
            ax_status.text(0.05, status_y, f'Backend: {backend} | Update Rate: {1.0/UPDATE_INTERVAL:.1f} Hz', 
                          fontsize=9, transform=ax_status.transAxes, family='monospace')
            status_y -= 0.3
            
            current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ax_status.text(0.05, status_y, f'Time: {current_time_str}', 
                          fontsize=9, transform=ax_status.transAxes, family='monospace')
            
            # 更新通道列表
            ax_channels.clear()
            ax_channels.axis('off')
            
            with self.channels_lock:
                # 按通道名称排序（保持顺序稳定）
                active_channels = [
                    (name, monitor) 
                    for name, monitor in self.channels.items()
                    if monitor.is_active()
                ]
                active_channels.sort(key=lambda x: x[0])
            
            # 显示通道信息
            y_pos = 0.95
            ax_channels.text(0.05, y_pos, 'Active LCM Channels', 
                           fontsize=14, fontweight='bold', transform=ax_channels.transAxes)
            y_pos -= 0.05
            
            ax_channels.text(0.05, y_pos, '-' * 50, 
                           fontsize=10, transform=ax_channels.transAxes)
            y_pos -= 0.03
            
            ax_channels.text(0.05, y_pos, f"{'Channel':<35} {'Freq (Hz)':<15} {'Count':<10}", 
                           fontsize=10, fontweight='bold', transform=ax_channels.transAxes,
                           family='monospace')
            y_pos -= 0.1  # 增加表头和通道行之间的间距
            
            # 初始化或清除旧的"+"按钮位置和Rectangle，准备存储新的
            if not hasattr(self, 'plus_button_positions'):
                self.plus_button_positions = {}
            else:
                self.plus_button_positions.clear()
            
            # 清除旧的Rectangle
            if hasattr(self, 'plus_button_rects'):
                for rect in self.plus_button_rects.values():
                    try:
                        rect.remove()
                    except Exception:
                        pass
                self.plus_button_rects.clear()
            else:
                self.plus_button_rects = {}
            
            if not active_channels:
                ax_channels.text(0.05, y_pos, '  (No active channels)', 
                               fontsize=10, transform=ax_channels.transAxes, style='italic')
            else:
                for channel_name, monitor in active_channels:
                    freq = monitor.get_frequency()
                    count = monitor.message_count
                    
                    # 检查是否有选中的变量
                    with self.selected_variables_lock:
                        is_selected = channel_name in self.selected_variables and \
                                     len(self.selected_variables[channel_name]) > 0
                    
                    # 选中通道用不同颜色和粗体显示
                    color = 'green' if is_selected else 'black'
                    weight = 'bold' if is_selected else 'normal'
                    text = f"{channel_name:<35} {freq:>8.2f} Hz    {count:>8}"
                    if is_selected:
                        text = "► " + text  # 添加选中标记
                    ax_channels.text(0.05, y_pos, text, 
                                   fontsize=11, transform=ax_channels.transAxes,
                                   family='monospace', color=color, weight=weight)
                    
                    # 在每个通道后面添加"+"按钮（使用Rectangle作为可点击区域）
                    plus_x = 0.92  # "+"按钮的x位置
                    plus_color = 'blue' if not is_selected else 'green'
                    
                    # 创建可点击的Rectangle
                    from matplotlib.patches import Rectangle
                    button_width = 0.06
                    button_height = 0.04
                    plus_rect = Rectangle((plus_x - button_width/2, y_pos - button_height/2), 
                                         button_width, button_height,
                                         transform=ax_channels.transAxes,
                                         facecolor='lightgray', 
                                         edgecolor=plus_color, 
                                         linewidth=2.0,
                                         alpha=0.8,
                                         zorder=5)  # 设置zorder，确保可以被点击检测
                    ax_channels.add_patch(plus_rect)
                    
                    # 添加"+"文本（zorder高于Rectangle，但点击检测会检测Rectangle）
                    ax_channels.text(plus_x, y_pos, '+', 
                                   fontsize=16, transform=ax_channels.transAxes,
                                   color=plus_color, weight='bold',
                                   ha='center', va='center',
                                   zorder=6)  # 文本在Rectangle之上，但不影响点击检测
                    
                    # 存储"+"按钮的Rectangle和位置用于点击检测
                    if not hasattr(self, 'plus_button_rects'):
                        self.plus_button_rects = {}
                    self.plus_button_rects[channel_name] = plus_rect
                    self.plus_button_positions[channel_name] = (plus_x, y_pos)
                    
                    y_pos -= 0.16  # 增加间距，避免重叠（从0.07增加到0.12）
                    
                    if y_pos < 0.2:
                        break
            
            # 显示选择提示
            y_pos = 0.02
            ax_channels.text(0.05, y_pos, 
                           'Click the "+" button next to a channel to select variables for plotting',
                           fontsize=9, transform=ax_channels.transAxes, style='italic',
                           color='blue', weight='bold')
            
            # 更新变量曲线
            ax_plot.clear()
            ax_plot.set_xlabel('Time (s)', fontsize=10)
            ax_plot.set_ylabel('Value', fontsize=10)
            ax_plot.grid(True, alpha=0.3)
            ax_plot.set_title('Selected Variables Plot', fontsize=12, fontweight='bold')
            
            # 在曲线图右上角添加清除按钮
            # 先清除旧的清除按钮Rectangle
            if hasattr(self, 'clear_all_button_rect') and self.clear_all_button_rect is not None:
                try:
                    self.clear_all_button_rect.remove()
                except Exception:
                    pass
            
            clear_button_x = 0.98
            clear_button_y = 0.98
            clear_button_width = 0.10
            clear_button_height = 0.05
            from matplotlib.patches import Rectangle
            clear_rect = Rectangle((clear_button_x - clear_button_width, clear_button_y - clear_button_height), 
                                   clear_button_width, clear_button_height,
                                   transform=ax_plot.transAxes,
                                   facecolor='lightcoral', 
                                   edgecolor='red', 
                                   linewidth=2.0,
                                   alpha=0.9,
                                   zorder=5)  # 设置zorder
            ax_plot.add_patch(clear_rect)
            # 文字居中显示在按钮中心，确保zorder高于Rectangle
            ax_plot.text(clear_button_x - clear_button_width/2, clear_button_y - clear_button_height/2, 
                        'Clear All', 
                        fontsize=11, transform=ax_plot.transAxes,
                        color='white', weight='bold',
                        ha='center', va='center',
                        zorder=10)  # zorder高于Rectangle，确保文字显示在上方
            
            # 存储清除按钮的Rectangle用于点击检测（统一使用clear_all_button_rect）
            self.clear_all_button_rect = clear_rect
            
            with self.selected_variables_lock:
                if self.selected_variables:
                    current_time = time.time()
                    colors = plt.cm.tab10(np.linspace(0, 1, 10))
                    color_idx = 0
                    
                    for channel_name, var_names in self.selected_variables.items():
                        if channel_name not in self.channels:
                            continue
                        
                        monitor = self.channels[channel_name]
                        with monitor.variables_lock:
                            for var_name in var_names:
                                if var_name not in monitor.variables:
                                    continue
                                
                                var_monitor = monitor.variables[var_name]
                                with var_monitor.lock:
                                    if len(var_monitor.values) > 0:
                                        # 转换为相对时间
                                        # 转换为相对时间（秒）
                                        times = np.array(var_monitor.timestamps) - current_time
                                        values = np.array(var_monitor.values)
                                        
                                        # 只绘制最近的数据点
                                        if len(times) > MAX_PLOT_POINTS:
                                            times = times[-MAX_PLOT_POINTS:]
                                            values = values[-MAX_PLOT_POINTS:]
                                        
                                        color = colors[color_idx % len(colors)]
                                        label = f"{channel_name}:{var_name}"
                                        ax_plot.plot(times, values, label=label, 
                                                   color=color, linewidth=1.5, alpha=0.8)
                                        color_idx += 1
                    
                    if color_idx > 0:
                        ax_plot.legend(loc='upper right', fontsize=8, ncol=2)
                else:
                    ax_plot.text(0.5, 0.5, 
                               'No variables selected.\nLeft-click on channel name above to select variables.',
                               transform=ax_plot.transAxes, ha='center', va='center',
                               fontsize=12, style='italic', color='gray')
            
            # 标题已经在状态区域显示，这里不需要更新suptitle
        
        # 启动动画
        try:
            # 先调用一次update来初始化显示
            update(0)
            # 手动调整布局，避免tight_layout警告
            fig.subplots_adjust(left=0.05, right=0.95, top=0.95, bottom=0.05, hspace=0.25)
            
            # 检查后端是否支持交互式显示
            import matplotlib
            backend = matplotlib.get_backend()
            if backend.lower() in ['agg', 'pdf', 'svg', 'ps']:
                plt.close(fig)
                self.use_gui = False
                self._run_text_mode()
                return
            
            # 启动动画更新（保存引用以便清理）
            self.animation = FuncAnimation(fig, update, interval=int(UPDATE_INTERVAL * 1000), 
                                           blit=False, cache_frame_data=False)
            
            # 设置窗口关闭回调，确保正确清理
            def on_close(event):
                self.running = False
                # 停止动画
                try:
                    if hasattr(self, 'animation'):
                        self.animation.event_source.stop()
                        self.animation = None
                except Exception:
                    pass
                
                # 关闭所有打开的对话框
                with self.dialogs_lock:
                    dialogs_to_close = list(self.open_dialogs)
                    self.open_dialogs.clear()
                
                for dialog in dialogs_to_close:
                    try:
                        if dialog.winfo_exists():
                            dialog.destroy()
                    except Exception:
                        pass
                
                # 清理 matplotlib 资源
                try:
                    plt.close(fig)
                except Exception:
                    pass
            
            fig.canvas.mpl_connect('close_event', on_close)
            
            # 确保使用交互式模式并立即显示窗口
            # 注意：TkAgg后端需要ioff()模式，然后show(block=True)会阻塞
            plt.ioff()  # 关闭交互式模式（TkAgg需要这样）
            plt.show(block=True)  # 阻塞直到窗口关闭，立即显示GUI
            
            # 窗口关闭后停止运行
            self.running = False
        except KeyboardInterrupt:
            self.running = False
            # 停止动画
            try:
                if hasattr(self, 'animation'):
                    self.animation.event_source.stop()
                    self.animation = None
            except Exception:
                pass
            try:
                plt.close(fig)
            except Exception:
                pass
        except Exception:
            self.running = False
            # 停止动画
            try:
                if hasattr(self, 'animation'):
                    self.animation.event_source.stop()
                    self.animation = None
            except Exception:
                pass
            try:
                plt.close(fig)
            except Exception:
                pass
            self.use_gui = False
            self._run_text_mode()
    
    def _setup_interactive_selection(self, fig, ax_channels, ax_plot):
        """设置交互式选择（左键点击选择变量）"""
        def on_click(event):
            # 响应左键点击
            if event.button != 1:  # 1 = 左键
                return
            
            # 检查是否点击了清除按钮（在曲线图区域）
            if event.inaxes == ax_plot:
                try:
                    if hasattr(self, 'clear_all_button_rect') and self.clear_all_button_rect:
                        # 使用Rectangle的contains方法，这是最可靠的方式
                        if self.clear_all_button_rect.contains(event)[0]:
                            # 清除所有已选择的变量
                            with self.selected_variables_lock:
                                self.selected_variables.clear()
                            pass
                        return
                except Exception:
                    pass
                return
            
            # 检查是否点击了通道列表区域
            if event.inaxes != ax_channels:
                return
            
            # 使用Rectangle的contains方法检测点击，这是最可靠的方式
            clicked_channel = None
            
            if hasattr(self, 'plus_button_rects') and self.plus_button_rects:
                # 遍历所有按钮，检查哪个被点击
                for channel_name, rect in self.plus_button_rects.items():
                    try:
                        # 使用Rectangle的contains方法，返回(inside, path)
                        result = rect.contains(event)
                        if isinstance(result, tuple):
                            inside, path = result
                        else:
                            inside = result
                        
                        if inside:
                            clicked_channel = channel_name
                            break
                    except Exception:
                        # 如果contains方法失败，继续检查其他按钮
                        continue
                        continue
            
            if clicked_channel:
                # 检查是否已经有对话框打开，避免重复点击
                with self.dialogs_lock:
                    if len(self.open_dialogs) > 0:
                        return
                
                # 将请求放入队列，在主线程中处理（避免tkinter线程问题）
                self.dialog_queue.put(clicked_channel)
        
        fig.canvas.mpl_connect('button_press_event', on_click)
    
    def _select_variables(self, channel_name, fig=None):
        """选择通道的变量用于绘图（使用GUI对话框）"""
        if not self.running:
            return  # 如果程序正在退出，不创建新对话框
        
        if channel_name not in self.channels:
            return
        
        monitor = self.channels[channel_name]
        
        # 优先使用缓存的变量列表（一旦检测到变量，就固定使用这些变量）
        var_names = None
        with monitor.cached_variable_names_lock:
            if monitor.cached_variable_names is not None and len(monitor.cached_variable_names) > 0:
                # 如果缓存存在且不为空，直接使用缓存
                var_names = monitor.cached_variable_names
        
        # 如果缓存不存在或为空，等待直到有变量
        if not var_names:
            import time
            max_wait = 5.0  # 最多等待5秒
            wait_interval = 0.1
            waited = 0
            
            # 等待直到有变量或超时
            while not var_names and waited < max_wait:
                var_names = monitor.get_variable_names()
                if var_names:
                    break  # 如果变量已经提取，立即退出
                
                # 检查是否收到了消息
                if monitor.message_count == 0:
                    # 如果还没有收到消息，继续等待
                    time.sleep(wait_interval)
                    waited += wait_interval
                else:
                    # 如果已经收到消息但变量列表为空，可能是解码失败
                    # 再等待一小段时间让变量被提取
                    time.sleep(wait_interval)
                    waited += wait_interval
        
        # 如果变量列表为空，不弹出对话框，直接返回
        if not var_names:
            return
        
        if not TKINTER_AVAILABLE or fig is None:
            return
        
        try:
            # 使用matplotlib的tkinter窗口作为父窗口
            root = fig.canvas.get_tk_widget().master
            if not root.winfo_exists():
                return  # 如果窗口已经关闭，不创建对话框
            
            # 创建选择对话框
            dialog = tk.Toplevel(root)
            dialog.title(f"选择变量 - {channel_name}")
            dialog.geometry("500x400")
            dialog.transient(root)
            dialog.grab_set()
            
            # 将对话框添加到列表中以便清理
            with self.dialogs_lock:
                self.open_dialogs.append(dialog)
            
            # 确保对话框在窗口关闭时正确清理
            def on_close():
                with self.dialogs_lock:
                    if dialog in self.open_dialogs:
                        self.open_dialogs.remove(dialog)
                dialog.destroy()
            dialog.protocol("WM_DELETE_WINDOW", on_close)
            
            # 创建变量列表
            tk.Label(dialog, text=f"通道: {channel_name}", 
                    font=('Arial', 10, 'bold')).pack(pady=5)
            tk.Label(dialog, text="可用变量（可多选）:", 
                    font=('Arial', 9)).pack(pady=5)
            
            # 创建滚动列表
            listbox_frame = tk.Frame(dialog)
            listbox_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            scrollbar = tk.Scrollbar(listbox_frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            listbox = tk.Listbox(listbox_frame, selectmode=tk.EXTENDED, 
                                yscrollcommand=scrollbar.set, font=('Courier', 9))
            listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.config(command=listbox.yview)
            
            if var_names:
                for var_name in var_names:
                    listbox.insert(tk.END, var_name)
            else:
                # 如果变量列表为空，显示提示信息
                listbox.insert(tk.END, "（暂无可用变量）")
                listbox.config(state=tk.DISABLED)  # 禁用列表，因为无法选择
            
            # 全选按钮
            def select_all():
                listbox.selection_set(0, tk.END)
            
            def select_none():
                listbox.selection_clear(0, tk.END)
            
            button_frame = tk.Frame(dialog)
            button_frame.pack(pady=5)
            
            tk.Button(button_frame, text="全选", command=select_all, 
                     width=10).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="清除", command=select_none, 
                     width=10).pack(side=tk.LEFT, padx=5)
            
            selected_vars = []
            
            def confirm():
                nonlocal selected_vars
                selected_indices = listbox.curselection()
                selected_vars = [var_names[i] for i in selected_indices]
                with self.dialogs_lock:
                    if dialog in self.open_dialogs:
                        self.open_dialogs.remove(dialog)
                dialog.destroy()
            
            def cancel():
                with self.dialogs_lock:
                    if dialog in self.open_dialogs:
                        self.open_dialogs.remove(dialog)
                dialog.destroy()
            
            # 清除该通道的所有已选择变量
            def clear_channel():
                with self.selected_variables_lock:
                    if channel_name in self.selected_variables:
                        del self.selected_variables[channel_name]
                with self.dialogs_lock:
                    if dialog in self.open_dialogs:
                        self.open_dialogs.remove(dialog)
                dialog.destroy()
            
            # 确认和取消按钮
            confirm_frame = tk.Frame(dialog)
            confirm_frame.pack(pady=10)
            
            tk.Button(confirm_frame, text="确认", command=confirm, 
                     width=10, bg='lightgreen').pack(side=tk.LEFT, padx=5)
            tk.Button(confirm_frame, text="取消", command=cancel, 
                     width=10, bg='lightcoral').pack(side=tk.LEFT, padx=5)
            tk.Button(confirm_frame, text="清除选择", command=clear_channel, 
                     width=12, bg='lightyellow').pack(side=tk.LEFT, padx=5)
            
            # 等待对话框关闭
            dialog.wait_window()
            
            # 应用选择
            if selected_vars:
                with self.selected_variables_lock:
                    self.selected_variables[channel_name] = selected_vars
        except Exception:
            # 如果GUI失败，静默处理
            pass
    
    def stop(self):
        """停止监控"""
        self.running = False
        
        # 停止动画
        try:
            if hasattr(self, 'animation') and self.animation is not None:
                self.animation.event_source.stop()
                self.animation = None
        except Exception:
            pass
        
        # 关闭所有打开的对话框
        with self.dialogs_lock:
            dialogs_to_close = list(self.open_dialogs)
            self.open_dialogs.clear()
        
        for dialog in dialogs_to_close:
            try:
                if dialog.winfo_exists():
                    dialog.destroy()
            except Exception:
                pass


def main():
    # 抑制 tkinter Image 清理时的警告（这是已知的 Python/tkinter 问题，不影响功能）
    import sys
    
    # 创建一个自定义的 stderr 包装器来过滤 tkinter Image 清理警告
    class FilteredStderr:
        def __init__(self, original_stderr):
            self.original_stderr = original_stderr
            self.buffer = []
            self.filtering = False
        
        def write(self, text):
            # 检测是否开始过滤（Exception ignored 消息）
            if 'Exception ignored' in text and 'Image.__del__' in text:
                self.filtering = True
                self.buffer = [text]
                return
            
            # 如果正在过滤，继续缓冲
            if self.filtering:
                self.buffer.append(text)
                # 检查是否包含我们要过滤的错误
                full_text = ''.join(self.buffer)
                if 'main thread is not in main loop' in full_text:
                    # 这是我们要过滤的错误，清空缓冲区并返回
                    self.buffer = []
                    self.filtering = False
                    return
                # 如果缓冲区太长或遇到其他异常，停止过滤
                if len(self.buffer) > 10 or ('Traceback' in text and len(self.buffer) > 1):
                    # 输出缓冲的内容
                    for line in self.buffer:
                        self.original_stderr.write(line)
                    self.buffer = []
                    self.filtering = False
                return
            
            # 过滤掉单独的 RuntimeError 行
            if 'RuntimeError: main thread is not in main loop' in text:
                return
            
            # 其他输出正常显示
            self.original_stderr.write(text)
        
        def flush(self):
            # 如果还有缓冲的内容，输出它们
            if self.buffer:
                for line in self.buffer:
                    self.original_stderr.write(line)
                self.buffer = []
                self.filtering = False
            self.original_stderr.flush()
    
    parser = argparse.ArgumentParser(description='LCM Channel Monitor')
    parser.add_argument('--lcm-url', type=str, default='', 
                       help='LCM URL (默认: 使用默认 URL)')
    parser.add_argument('--no-gui', action='store_true', 
                       help='禁用 GUI，使用文本模式')
    
    args = parser.parse_args()
    
    if not args.no_gui:
        # 重定向 stderr 来过滤 tkinter 清理警告
        filtered_stderr = FilteredStderr(sys.stderr)
        sys.stderr = filtered_stderr
    
    monitor = LCMChannelMonitor(lcm_url=args.lcm_url, use_gui=not args.no_gui)
    
    # 注册清理函数
    def cleanup():
        monitor.stop()
    
    atexit.register(cleanup)
    
    # 注册信号处理器
    def signal_handler(signum, frame):
        monitor.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if not monitor.start():
        if not monitor.use_gui:
            print("启动失败")
        return 1
    
    try:
        # start()方法中已经启动了GUI或文本模式，这里只需要等待
        if monitor.use_gui:
            # GUI模式会在_run_gui中阻塞，start()已经调用了_run_gui()
            while monitor.running:
                time.sleep(0.1)
        else:
            while monitor.running:
                time.sleep(0.1)
    except KeyboardInterrupt:
        if not monitor.use_gui:
            print("\n正在退出...")
    finally:
        monitor.stop()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
