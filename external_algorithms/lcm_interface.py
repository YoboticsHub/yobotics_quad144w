#!/usr/bin/env python3
"""
LCM通信接口模块
提供统一的LCM通信接口，供所有外部算法使用
"""

import sys
import os
import threading
import time

# 添加LCM Python模块路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../lcm-types/python'))

try:
    import lcm
    from development_state_t import development_state_t
    from development_command_t import development_command_t
    LCM_AVAILABLE = True
except ImportError as e:
    LCM_AVAILABLE = False
    print(f"Warning: LCM modules not available: {e}")


class LCMInterface:
    """LCM通信接口类"""
    
    def __init__(self, config):
        """
        初始化LCM接口
        
        Args:
            config: 配置字典，包含以下键：
                - lcm.url: LCM URL（可选，空字符串表示使用默认）
                - lcm.state_channel: 状态通道名称
                - lcm.command_channel: 命令通道名称
                - lcm.robot_id: 机器人ID
        """
        if not LCM_AVAILABLE:
            raise RuntimeError("LCM modules not available. Please ensure LCM Python bindings are installed.")
        
        self.config = config
        self.lcm_instance = None
        self.running = False
        
        # 状态缓存
        self.latest_state = None
        self.state_lock = threading.Lock()
        self.last_state_time = None
        
        # 回调函数
        self.state_callback = None
        
        # 初始化LCM
        self._init_lcm()
    
    def _init_lcm(self):
        """初始化LCM实例"""
        # 检查配置中是否有lcm部分
        if 'lcm' not in self.config:
            raise KeyError("Configuration missing 'lcm' section. Please ensure your config.yaml contains an 'lcm' section with 'url', 'state_channel', 'command_channel', and 'robot_id'.")
        
        lcm_config = self.config['lcm']
        lcm_url = lcm_config.get('url', '')
        if lcm_url:
            self.lcm_instance = lcm.LCM(lcm_url)
        else:
            self.lcm_instance = lcm.LCM()
        
        # 订阅状态通道
        if 'state_channel' not in lcm_config:
            raise KeyError("Configuration missing 'lcm.state_channel'. Please specify the state channel name.")
        state_channel = lcm_config['state_channel']
        self.lcm_instance.subscribe(state_channel, self._on_state_received)
        print(f"[LCMInterface] Subscribed to state channel: {state_channel}")

    @staticmethod
    def _flatten_values(value):
        if value is None:
            return None
        if hasattr(value, "tolist"):
            value = value.tolist()
        if isinstance(value, dict):
            return value
        if not isinstance(value, (list, tuple)):
            return [float(value)]
        flat = []
        for item in value:
            if isinstance(item, (list, tuple)):
                flat.extend(LCMInterface._flatten_values(item))
            else:
                flat.append(float(item))
        return flat

    @staticmethod
    def _split_main_and_supplement(value, main_len=12, supplement_len=4):
        """
        支持三种输入：
        - 12维：只填主关节，补充轮子清零
        - 16维：前12维主关节，后4维轮子
        - 16维腿块布局：每条腿 4 个值，第四个是轮子
        - dict: {'LF': [...], 'RF': [...], 'LR': [...], 'RR': [...]}
        """
        if value is None:
            return [0.0] * main_len, [0.0] * supplement_len

        if isinstance(value, dict):
            leg_order = ("LF", "RF", "LR", "RR")
            main = []
            supplement = []
            for leg in leg_order:
                leg_value = value.get(leg, None)
                flat = LCMInterface._flatten_values(leg_value) or []
                if len(flat) >= 4:
                    main.extend(flat[:3])
                    supplement.append(flat[3])
                elif len(flat) == 3:
                    main.extend(flat[:3])
                elif len(flat) == 1:
                    main.append(flat[0])
            if len(main) < main_len:
                main.extend([0.0] * (main_len - len(main)))
            if len(supplement) < supplement_len:
                supplement.extend([0.0] * (supplement_len - len(supplement)))
            return main[:main_len], supplement[:supplement_len]

        flat = LCMInterface._flatten_values(value) or []
        flat = [float(x) for x in flat]
        if len(flat) == 16:
            main = []
            supplement = []
            for leg in range(4):
                base = leg * 4
                main.extend(flat[base:base + 3])
                supplement.append(flat[base + 3])
            return main[:main_len], supplement[:supplement_len]
        if len(flat) >= main_len + supplement_len:
            return flat[:main_len], flat[main_len:main_len + supplement_len]
        if len(flat) >= main_len:
            main = flat[:main_len]
            supplement = [0.0] * supplement_len
            return main, supplement

        main = flat[:]
        main.extend([0.0] * (main_len - len(main)))
        return main[:main_len], [0.0] * supplement_len
    
    def _on_state_received(self, channel, data):
        """LCM状态消息回调（内部使用）"""
        try:
            msg = development_state_t.decode(data)
            
            # 检查机器人ID是否匹配
            lcm_config = self.config.get('lcm', {})
            robot_id = lcm_config.get('robot_id', '')
            if robot_id and msg.robot_id != robot_id:
                return
            
            # 更新状态缓存
            with self.state_lock:
                self.latest_state = msg
                self.last_state_time = time.time()
            
            # 调用用户注册的回调函数
            if self.state_callback:
                try:
                    self.state_callback(msg)
                except Exception as e:
                    print(f"[LCMInterface] Error in state callback: {e}")
                    
        except Exception as e:
            print(f"[LCMInterface] Error processing state message: {e}")
    
    def register_state_callback(self, callback):
        """
        注册状态消息回调函数
        
        Args:
            callback: 回调函数，接收一个 development_state_t 消息作为参数
        """
        self.state_callback = callback
    
    def get_latest_state(self):
        """
        获取最新的状态消息
        
        Returns:
            development_state_t: 最新的状态消息，如果没有则返回None
        """
        with self.state_lock:
            return self.latest_state
    
    def send_command(self, enable_development_mode, 
                     joint_positions=None, joint_velocities=None, 
                     joint_torques=None, joint_kp=None, joint_kd=None,
                     joint_positions_supplement=None, joint_velocities_supplement=None,
                     joint_torques_supplement=None, joint_kp_supplement=None, joint_kd_supplement=None):
        """
        发送四足机器人的控制命令（适配 LCM development_command_t 的 12维数组格式）
        
        Args:
            enable_development_mode: bool, 是否启用开发模式
            joint_positions: dict, 关节位置，格式：
                {
                    'LF': [hip, thigh, calf],   # 左前腿
                    'RF': [hip, thigh, calf],   # 右前腿
                    'LR': [hip, thigh, calf],   # 左后腿
                    'LR': [hip, thigh, calf]    # 右后腿
                }
            joint_velocities: dict, 关节速度，格式同上
            joint_torques: dict, 关节扭矩，格式同上
            joint_kp: dict, Kp 增益，格式同上
            joint_kd: dict, Kd 增益，格式同上
        """
        if self.lcm_instance is None:
            return
        
        try:
            lcm_config = self.config.get('lcm', {})
            if 'robot_id' not in lcm_config:
                raise KeyError("Configuration missing 'lcm.robot_id'. Please specify the robot ID.")
            
            msg = development_command_t()
            msg.robot_id = lcm_config['robot_id']
            msg.enable_development_mode = 1 if enable_development_mode else 0
            if enable_development_mode and joint_positions is not None:
                q_main, q_supp = self._split_main_and_supplement(joint_positions)
                qd_main, qd_supp = self._split_main_and_supplement(joint_velocities)
                tau_main, tau_supp = self._split_main_and_supplement(joint_torques)
                kp_main, kp_supp = self._split_main_and_supplement(joint_kp)
                kd_main, kd_supp = self._split_main_and_supplement(joint_kd)

                if joint_positions_supplement is not None:
                    q_supp = self._flatten_values(joint_positions_supplement)[:4]
                    q_supp = list(q_supp) + [0.0] * (4 - len(q_supp))
                if joint_velocities_supplement is not None:
                    qd_supp = self._flatten_values(joint_velocities_supplement)[:4]
                    qd_supp = list(qd_supp) + [0.0] * (4 - len(qd_supp))
                if joint_torques_supplement is not None:
                    tau_supp = self._flatten_values(joint_torques_supplement)[:4]
                    tau_supp = list(tau_supp) + [0.0] * (4 - len(tau_supp))
                if joint_kp_supplement is not None:
                    kp_supp = self._flatten_values(joint_kp_supplement)[:4]
                    kp_supp = list(kp_supp) + [0.0] * (4 - len(kp_supp))
                if joint_kd_supplement is not None:
                    kd_supp = self._flatten_values(joint_kd_supplement)[:4]
                    kd_supp = list(kd_supp) + [0.0] * (4 - len(kd_supp))

                msg.joint_des_q = q_main
                msg.joint_des_q_supplement = q_supp
                msg.joint_des_qd = qd_main
                msg.joint_des_qd_supplement = qd_supp
                msg.joint_des_tau = tau_main
                msg.joint_des_tau_supplement = tau_supp
                msg.joint_des_kp = kp_main
                msg.joint_des_kp_supplement = kp_supp
                msg.joint_des_kd = kd_main
                msg.joint_des_kd_supplement = kd_supp

            else:
                # 清零所有命令
                zero_12 = [0.0] * 12
                zero_4 = [0.0] * 4
                msg.joint_des_q = zero_12
                msg.joint_des_q_supplement = zero_4
                msg.joint_des_qd = zero_12
                msg.joint_des_qd_supplement = zero_4
                msg.joint_des_tau = zero_12
                msg.joint_des_tau_supplement = zero_4
                msg.joint_des_kp = zero_12
                msg.joint_des_kp_supplement = zero_4
                msg.joint_des_kd = zero_12
                msg.joint_des_kd_supplement = zero_4

            # 发布命令
            if 'command_channel' not in lcm_config:
                raise KeyError("Configuration missing 'lcm.command_channel'. Please specify the command channel name.")
            command_channel = lcm_config['command_channel']
            self.lcm_instance.publish(command_channel, msg.encode())

        except Exception as e:
            print(f"[LCMInterface] Error sending command: {e}")
            import traceback
            traceback.print_exc()

    def start(self):
        """启动LCM处理线程"""
        self.running = True
    
    def stop(self):
        """停止LCM处理"""
        self.running = False
    
    def handle(self, timeout_ms=100):
        """
        处理LCM消息（需要在主循环中调用）
        
        Args:
            timeout_ms: 超时时间（毫秒）
        """
        if self.running and self.lcm_instance:
            self.lcm_instance.handle_timeout(timeout_ms)
