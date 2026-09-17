"""
MuJoCo 仿真器主程序
作者: Han Jiang (jh18954242606@163.com)
日期: 2026-01
功能: 运行 MuJoCo 仿真并通过 LCM 与控制器通信
"""

import mujoco
import mujoco.viewer
import numpy as np
import time
import sys
import os
import threading
from typing import Optional

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, 'lcm-types', 'python'))

LCM_AVAILABLE = False
try:
    import lcm
    from quad_joint_state_t import quad_joint_state_t
    from quad_joint_command_t import quad_joint_command_t
    from microstrain_lcmt import microstrain_lcmt
    LCM_AVAILABLE = True
except ImportError as e:
    print(f"警告: LCM 模块导入失败: {e}")
    LCM_AVAILABLE = False

# LCM 通道名称（默认值，将从配置文件读取）
DEFAULT_JOINT_STATE_CHANNEL = "QUAD_JOINT_STATE"
DEFAULT_JOINT_COMMAND_CHANNEL = "QUAD_JOINT_COMMAND"
DEFAULT_IMU_DATA_CHANNEL = "MICROSTRAIN_IMU_DATA"


class MuJoCoSimulator:
    """MuJoCo 仿真器类"""
    
    def __init__(self, xml_path: str, lcm_url: str = "", simulation_dt: float = 0.002,
                 joint_state_channel: str = DEFAULT_JOINT_STATE_CHANNEL,
                 joint_command_channel: str = DEFAULT_JOINT_COMMAND_CHANNEL,
                 imu_data_channel: str = DEFAULT_IMU_DATA_CHANNEL):
        """
        初始化 MuJoCo 仿真器
        
        Args:
            xml_path: MuJoCo XML 文件路径
            lcm_url: LCM URL（空字符串表示使用默认）
            simulation_dt: 仿真时间步长（秒）
            joint_state_channel: 关节状态 LCM 通道名
            joint_command_channel: 关节命令 LCM 通道名
            imu_data_channel: IMU 数据 LCM 通道名
        """
        self.joint_state_channel = joint_state_channel
        self.joint_command_channel = joint_command_channel
        self.imu_data_channel = imu_data_channel
        self.xml_path = xml_path
        self.simulation_dt = simulation_dt
        self.model = None
        self.data = None
        self.viewer = None
        
        # LCM 通信
        self.lcm = None
        self.lcm_thread = None
        self.running = False
        
        # 关节索引映射（根据 MuJoCo 模型定义）
        # 需要根据实际模型调整
        self.joint_indices = {
            'LF': [0, 1, 2],      
            'RF': [4, 5, 6],     
            'LR': [8, 9, 10],                       
            'RR': [12, 13, 14],       
        }

        self.wheel_indices = {
            'LF': 3,      
            'RF': 7,     
            'LR': 11,                       
            'RR': 15,       
        }
        
        # 当前接收到的控制命令
        self.command_lock = threading.Lock()
        self.current_command = None
        
        # 初始化 LCM
        if LCM_AVAILABLE:
            try:
                if lcm_url:
                    self.lcm = lcm.LCM(lcm_url)
                else:
                    self.lcm = lcm.LCM()
                print("[MuJoCoSimulator] LCM initialized successfully")
                print(f"[MuJoCoSimulator] LCM URL: "
                      f"{lcm_url if lcm_url else 'default'}")
                print("[MuJoCoSimulator] Publishing channels:")
                print(f"  - {self.joint_state_channel}")
                print(f"  - {self.imu_data_channel}")
                print("[MuJoCoSimulator] Subscribing channels:")
                print(f"  - {self.joint_command_channel}")
            except Exception as e:
                print(f"[MuJoCoSimulator] LCM initialization failed: {e}")
                import traceback
                traceback.print_exc()
                self.lcm = None
        
        # 加载 MuJoCo 模型
        self._load_model()

    @staticmethod
    def _wrap_to_pm_2pi(angle: float) -> float:
        """Wrap angle to [-2pi, 2pi)."""
        period = 4.0 * np.pi
        return float(((angle + 2.0 * np.pi) % period) - 2.0 * np.pi)
    
    def _load_model(self):
        """加载 MuJoCo 模型"""
        try:
            if not os.path.isabs(self.xml_path):
                # 如果是相对路径，相对于项目根目录
                self.xml_path = os.path.join(project_root, self.xml_path)
            
            if not os.path.exists(self.xml_path):
                raise FileNotFoundError(f"MuJoCo XML file not found: {self.xml_path}")
            
            self.model = mujoco.MjModel.from_xml_path(self.xml_path)
            self.data = mujoco.MjData(self.model)
            print(f"[MuJoCoSimulator] Model loaded from: {self.xml_path}")
            print(f"[MuJoCoSimulator] Model has {self.model.nq} position DOFs, {self.model.nv} velocity DOFs")
            print(f"[MuJoCoSimulator] Model has {self.model.nu} actuators")
            print(f"[MuJoCoSimulator] Model has {self.model.njnt} joints")
            
            # 打印所有关节名称和索引
            print("[MuJoCoSimulator] 关节索引映射:")
            for i in range(self.model.njnt):
                jnt_name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_JOINT, i)
                if jnt_name:
                    print(f"  关节索引 {i}: {jnt_name}")
            
            # 打印执行器信息
            print("[MuJoCoSimulator] 执行器信息:")
            for i in range(self.model.nu):
                act_name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
                if act_name:
                    print(f"  执行器索引 {i}: {act_name}")
                else:
                    print(f"  执行器索引 {i}: (unnamed)")
        except Exception as e:
            print(f"[MuJoCoSimulator] Failed to load model: {e}")
            raise
    
    def _handle_joint_command(self, channel, data):
        """处理接收到的关节控制命令"""
        try:
            msg = quad_joint_command_t.decode(data)
            with self.command_lock:
                self.current_command = msg
        except Exception as e:
            data_len = len(data) if data is not None else 0
            header = data[:8].hex() if data is not None and len(data) >= 8 else ""
            print(f"[MuJoCoSimulator] Failed to decode command: {e} | len={data_len} | header={header}")
    
    def _publish_joint_state(self): 
        """发布关节状态到 LCM"""
        if not LCM_AVAILABLE or not self.lcm:
            return
        
        try:
            msg = quad_joint_state_t()
            # 每条腿顺序：abad, hip, knee, wheel
            for leg in range(4):
                base = leg * 4

                for joint in range(3):
                    flat_idx = base + joint
                    out_idx = leg * 3 + joint
                    joint_q_idx = 7 + flat_idx
                    joint_qd_idx = 6 + flat_idx

                    if joint_q_idx < self.model.nq:
                        msg.joint_q[out_idx] = float(self.data.qpos[joint_q_idx])
                    if joint_qd_idx < self.model.nv:
                        msg.joint_qd[out_idx] = float(self.data.qvel[joint_qd_idx])
                    if flat_idx < self.model.nu:
                        msg.joint_tau[out_idx] = float(self.data.ctrl[flat_idx])

                wheel_idx = base + 3
                joint_q_idx = 7 + wheel_idx
                joint_qd_idx = 6 + wheel_idx
                if joint_q_idx < self.model.nq:
                    msg.joint_q_supplement[leg] = float(self.data.qpos[joint_q_idx])
                    msg.joint_q_supplement[leg] = self._wrap_to_pm_2pi(
                        msg.joint_q_supplement[leg]
                    )
                    # print(f"leg {leg} joint_q_supplement: {msg.joint_q_supplement[leg]}\n")
                if joint_qd_idx < self.model.nv:
                    msg.joint_qd_supplement[leg] = float(self.data.qvel[joint_qd_idx])
                if wheel_idx < self.model.nu:
                    msg.joint_tau_supplement[leg] = float(self.data.ctrl[wheel_idx])
                msg.flags[leg] = 1
            # # 打印发布的关节状态
            # print("=== Published Joint States ===")
            # print(f"Joint angles (q)    : {[f'{x: .3f}' for x in msg.joint_q]}")
            # print(f"Joint velocities (qd): {[f'{x: .3f}' for x in msg.joint_qd]}")
            # print(f"Joint torques (tau) : {[f'{x: .3f}' for x in msg.joint_tau]}")
            # print("===============================")
            try:
                self.lcm.publish(self.joint_state_channel, msg.encode())
            except Exception as pub_error:
                print(f"[MuJoCoSimulator] Failed to publish joint state: {pub_error}")
        except Exception as e:
            print(f"[MuJoCoSimulator] Failed to create/publish joint state: {e}")
            import traceback
            traceback.print_exc()
    
    def _publish_imu_data(self):
        """发布 IMU 数据到 LCM"""
        if not LCM_AVAILABLE or not self.lcm:
            return
        
        try:
            msg = microstrain_lcmt()
            
            # 参考 deploy_mujoco_plot_gamepad.py 的实现
            # MuJoCo 中根身体的姿态和速度存储在 qpos 和 qvel 的前几个元素
            # qpos[0:3] 是位置 (x, y, z)
            # qpos[3:7] 是四元数 (w, x, y, z)
            # qvel[0:3] 是线速度 (vx, vy, vz)
            # qvel[3:6] 是角速度 (wx, wy, wz)
            
            # 获取四元数（从 qpos[3:7]）
            if self.model.nq >= 7:
                quat = self.data.qpos[3:7]
                msg.quat[3] = float(quat[0])  # w
                msg.quat[0] = float(quat[1])  # x
                msg.quat[1] = float(quat[2])  # y
                msg.quat[2] = float(quat[3])  # z
                
                # 计算 RPY（从四元数）
                rpy = self._quat_to_rpy(quat)
                msg.rpy[0] = float(rpy[0])  # roll
                msg.rpy[1] = float(rpy[1])  # pitch
                msg.rpy[2] = float(rpy[2])  # yaw
            else:
                # 如果模型没有足够的自由度，使用默认值
                msg.quat[0] = 1.0
                msg.quat[1] = 0.0
                msg.quat[2] = 0.0
                msg.quat[3] = 0.0
                msg.rpy[0] = 0.0
                msg.rpy[1] = 0.0
                msg.rpy[2] = 0.0
            
            # 获取角速度（从 qvel[3:6]）
            if self.model.nv >= 6:
                omega = self.data.qvel[3:6]
                msg.omega[0] = float(omega[0])  # wx
                msg.omega[1] = float(omega[1])  # wy
                msg.omega[2] = float(omega[2])  # wz
            else:
                msg.omega[0] = 0.0
                msg.omega[1] = 0.0
                msg.omega[2] = 0.0
            
            # 获取加速度（从 qacc 中提取，简化处理）
            # 注意：qacc 是关节加速度，对于根身体可能需要考虑重力
            # 这里简化处理，使用前3个 qacc 作为线加速度
            if self.model.nv >= 3:
                acc = self.data.qacc[:3]
                msg.acc[0] = float(acc[0])
                msg.acc[1] = float(acc[1])
                msg.acc[2] = float(acc[2])
            else:
                msg.acc[0] = 0.0
                msg.acc[1] = 0.0
                msg.acc[2] = 0.0
            
            try:
                self.lcm.publish(self.imu_data_channel, msg.encode())
            except Exception as pub_error:
                print(f"[MuJoCoSimulator] Failed to publish IMU data: {pub_error}")
        except Exception as e:
            print(f"[MuJoCoSimulator] Failed to create/publish IMU data: {e}")
            import traceback
            traceback.print_exc()
    
    def _quat_to_rpy(self, quat):
        """四元数转 RPY"""
        w, x, y, z = quat[0], quat[1], quat[2], quat[3]
        
        # Roll (x-axis rotation)
        sinr_cosp = 2 * (w * x + y * z)
        cosr_cosp = 1 - 2 * (x * x + y * y)
        roll = np.arctan2(sinr_cosp, cosr_cosp)
        
        # Pitch (y-axis rotation)
        sinp = 2 * (w * y - z * x)
        if abs(sinp) >= 1:
            pitch = np.copysign(np.pi / 2, sinp)
        else:
            pitch = np.arcsin(sinp)
        
        # Yaw (z-axis rotation)
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = np.arctan2(siny_cosp, cosy_cosp)
        
        return np.array([roll, pitch, yaw])
    
    def _apply_control(self):
        """应用控制命令到 MuJoCo"""
        with self.command_lock:
            if self.current_command is None:
                return
        
        cmd = self.current_command
        
        # 应用 PD 控制: tau = kp*(qdes - q) + kd*(qddes - qd) + tff
        # 每条腿顺序：abad, hip, knee, wheel
        for leg in range(4):
            base = leg * 4

            # 3 个腿部关节
            for joint in range(3):
                actuator_idx = base + joint
                if actuator_idx >= self.model.nu:
                    continue

                q_des = cmd.joint_des_q[leg * 3 + joint]
                qd_des = cmd.joint_des_qd[leg * 3 + joint]
                kp = cmd.joint_des_kp[leg * 3 + joint]
                kd = cmd.joint_des_kd[leg * 3 + joint]
                tau_ff = cmd.joint_des_tau[leg * 3 + joint]

                if not np.isfinite(q_des):
                    q_des = 0.0
                if not np.isfinite(qd_des):
                    qd_des = 0.0
                if not np.isfinite(kp):
                    kp = 0.0
                if not np.isfinite(kd):
                    kd = 0.0
                if not np.isfinite(tau_ff):
                    tau_ff = 0.0

                joint_q_idx = 7 + actuator_idx
                joint_qd_idx = 6 + actuator_idx
                q = float(self.data.qpos[joint_q_idx]) if joint_q_idx < self.model.nq else 0.0
                qd = float(self.data.qvel[joint_qd_idx]) if joint_qd_idx < self.model.nv else 0.0

                tau = kp*10 * (q_des - q) + kd *10* (qd_des - qd) + tau_ff
                if not np.isfinite(tau) or abs(tau) > 1000.0:
                    tau = 0.0

                self.data.ctrl[actuator_idx] = tau

            # 轮毂电机
            actuator_idx = base + 3
            if actuator_idx >= self.model.nu:
                continue

            q_des = cmd.joint_des_q_supplement[leg]
            qd_des = cmd.joint_des_qd_supplement[leg]
            kp = cmd.joint_des_kp_supplement[leg]
            kd = cmd.joint_des_kd_supplement[leg]
            tau_ff = cmd.joint_des_tau_supplement[leg]

            if not np.isfinite(q_des):
                q_des = 0.0
            if not np.isfinite(qd_des):
                qd_des = 0.0
            if not np.isfinite(kp):
                kp = 0.0
            if not np.isfinite(kd):
                kd = 0.0
            if not np.isfinite(tau_ff):
                tau_ff = 0.0

            wheel_q_idx = 7 + actuator_idx
            wheel_qd_idx = 6 + actuator_idx
            q = float(self.data.qpos[wheel_q_idx]) if wheel_q_idx < self.model.nq else 0.0
            qd = float(self.data.qvel[wheel_qd_idx]) if wheel_qd_idx < self.model.nv else 0.0
            q = self._wrap_to_pm_2pi(q)
            q_des = self._wrap_to_pm_2pi(q_des)

            tau = kp * (q_des - q) + kd * (qd_des - qd) + tau_ff
            if not np.isfinite(tau) or abs(tau) > 1000.0:
                tau = 0.0

            self.data.ctrl[actuator_idx] = tau
            # ctrl_idx += 1




    def _lcm_thread_func(self):
        """LCM 消息处理线程"""
        while self.running:
            if self.lcm:
                try:
                    # Python LCM 库使用 handle_timeout (小写，带下划线)
                    # 参数是超时时间（毫秒）
                    timeout_ms = 10
                    self.lcm.handle_timeout(timeout_ms)
                except AttributeError:
                    # 如果 handle_timeout 不存在，尝试 handle
                    try:
                        self.lcm.handle()
                    except Exception as e:
                        # 忽略超时异常（这是正常的）
                        if "timeout" not in str(e).lower():
                            print(f"[MuJoCoSimulator] LCM handle error: {e}")
                        time.sleep(0.01)
                except Exception as e:
                    # 忽略超时异常（这是正常的）
                    if "timeout" not in str(e).lower():
                        print(f"[MuJoCoSimulator] LCM handle error: {e}")
                    time.sleep(0.01)
            else:
                time.sleep(0.01)
    
    def run(self, headless: bool = False):
        """
        运行仿真
        
        Args:
            headless: 是否无头模式（不显示可视化窗口）
        """
        if not self.model or not self.data:
            raise RuntimeError("Model not loaded")
        
        self.running = True
        
        # 启动 LCM 订阅
        if LCM_AVAILABLE and self.lcm:
            try:
                self.lcm.subscribe(self.joint_command_channel, self._handle_joint_command)
                self.lcm_thread = threading.Thread(target=self._lcm_thread_func, daemon=True)
                self.lcm_thread.start()
                print("[MuJoCoSimulator] LCM subscription started successfully")
                print(f"[MuJoCoSimulator] Listening on channel: {self.joint_command_channel}")
            except Exception as e:
                print(f"[MuJoCoSimulator] Failed to start LCM subscription: {e}")
                import traceback
                traceback.print_exc()
        else:
            if not LCM_AVAILABLE:
                print("[MuJoCoSimulator] WARNING: LCM not available, skipping subscription")
            if not self.lcm:
                print("[MuJoCoSimulator] WARNING: LCM not initialized, skipping subscription")
        
        # 启动仿真循环
        if headless:
            self._run_headless()
        else:
            self._run_with_viewer()
    
    def _run_headless(self):
        """无头模式运行"""
        print("[MuJoCoSimulator] Running in headless mode")
        try:
            while self.running:
                # 应用控制
                self._apply_control()
                
                # 执行一步仿真
                mujoco.mj_step(self.model, self.data)
                
                # 发布状态（只在 LCM 可用时发布）
                if LCM_AVAILABLE and self.lcm:
                    self._publish_joint_state()
                    self._publish_imu_data()
                
                # 等待一个时间步长
                time.sleep(self.simulation_dt)
        except KeyboardInterrupt:
            print("\n[MuJoCoSimulator] Simulation stopped by user")
        finally:
            self.running = False
    
    def _run_with_viewer(self):
        """带可视化窗口运行"""
        print("[MuJoCoSimulator] Running with viewer")
        with mujoco.viewer.launch_passive(self.model, self.data) as viewer:
            # 设置相机跟随根身体（默认视角跟随）
            viewer.cam.lookat[:] = [0, 0, 0.5]  # 看向原点
            viewer.cam.distance = 3.0  # 相机距离
            viewer.cam.azimuth = 90.0  # 方位角
            viewer.cam.elevation = -20.0  # 仰角
            viewer.cam.trackbodyid = -1  # -1 表示跟踪根身体（跟随模式）
            
            while viewer.is_running() and self.running:
                step_start = time.time()
                
                # 应用控制
                self._apply_control()
                
                # 执行一步仿真
                mujoco.mj_step(self.model, self.data)
                
                # 发布状态（只在 LCM 可用时发布）
                if LCM_AVAILABLE and self.lcm:
                    self._publish_joint_state()
                    self._publish_imu_data()
                
                # 同步可视化
                viewer.sync()
                
                # 时间同步
                time_until_next_step = self.simulation_dt - (time.time() - step_start)
                if time_until_next_step > 0:
                    time.sleep(time_until_next_step)
        
        self.running = False
    
    def stop(self):
        """停止仿真"""
        self.running = False
        if self.lcm_thread and self.lcm_thread.is_alive():
            self.lcm_thread.join(timeout=1.0)
        print("[MuJoCoSimulator] Simulation stopped")


def main():
    """主函数"""
    import argparse
    import yaml
    
    parser = argparse.ArgumentParser(description="MuJoCo 仿真器")
    parser.add_argument("--config", type=str, default="config.yaml",
                       help="配置文件路径（默认: config.yaml）")
    parser.add_argument("--headless", action="store_true",
                       help="无头模式（不显示可视化窗口）")
    args = parser.parse_args()
    
    # 加载配置
    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(project_root, config_path)
    
    if not os.path.exists(config_path):
        print(f"错误: 配置文件不存在: {config_path}")
        return 1
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 检查是否启用 MuJoCo
    if not config.get('simulation', {}).get('enable_mujoco', False):
        print("MuJoCo 仿真未启用，请在配置文件中设置 simulation.enable_mujoco: true")
        return 0
    
    # 获取 MuJoCo 配置
    mujoco_config = config.get('simulation', {}).get('mujoco', {})
    xml_path = mujoco_config.get('xml_path', '')
    simulation_dt = mujoco_config.get('simulation_dt', 0.002)
    lcm_url = mujoco_config.get('lcm_url', '')
    
    # 读取 LCM 通道名
    lcm_channels = config.get('motor_communication', {}).get('lcm_channels', {})
    joint_state_channel = lcm_channels.get('joint_state', DEFAULT_JOINT_STATE_CHANNEL)
    joint_command_channel = lcm_channels.get('joint_command', DEFAULT_JOINT_COMMAND_CHANNEL)
    imu_data_channel = lcm_channels.get('imu_data', DEFAULT_IMU_DATA_CHANNEL)
    
    if not xml_path:
        print("错误: 配置文件中未指定 MuJoCo XML 文件路径")
        return 1
    
    # 创建并运行仿真器
    try:
        simulator = MuJoCoSimulator(xml_path, lcm_url, simulation_dt,
                                    joint_state_channel, joint_command_channel, imu_data_channel)
        simulator.run(headless=args.headless)
    except KeyboardInterrupt:
        print("\n[MuJoCoSimulator] Interrupted by user")
    except Exception as e:
        print(f"[MuJoCoSimulator] Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
