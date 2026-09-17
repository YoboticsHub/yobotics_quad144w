#!/usr/bin/env python3
"""
奔跑算法实现
基于 deploy_mujoco_1Step.py，通过LCM接收机器人状态，执行奔跑动作
"""

import sys
import os
import numpy as np

# 添加父目录到路径
_parent_dir = os.path.join(os.path.dirname(__file__), '..')
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from algorithm_base import AlgorithmBase


class RunAlgorithm(AlgorithmBase):
    """奔跑算法类"""
     
    def __init__(self, config_path):
        """初始化奔跑算法"""
        # 因为 super().__init__ 会调用 _load_policy()，而 _load_onnx_metadata() 需要这些属性
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            temp_config = yaml.safe_load(f)
        
        # 检查是否打印配置信息
        print_config = temp_config.get('debug', {}).get('print_config', False)
        if print_config:
            # 打印读取的配置（在父类打印之前）
            print(f"[RunAlgorithm] Reading config from: {config_path}")
            print("[Runlgorithm] Configuration:")
            print("=" * 80)
            print(yaml.dump(temp_config, default_flow_style=False, allow_unicode=True, sort_keys=False))
            print("=" * 80)
        
        # 调用父类初始化（会加载配置并调用 _load_policy，可能会调用 _warmup_policy）
        super().__init__(config_path)
         
    
    def get_gravity_orientation(self, quaternion):   #得到重力投影，用于观测输入
        qw = quaternion[0]
        qx = quaternion[1]
        qy = quaternion[2]
        qz = quaternion[3]

        gravity_orientation = np.zeros(3)

        gravity_orientation[0] = 2 * (-qz * qx + qw * qy)
        gravity_orientation[1] = -2 * (qz * qy + qw * qx)
        gravity_orientation[2] = 1 - 2 * (qw * qw + qz * qz)

        return gravity_orientation
    
    def compute_observation(self, state):
        """
        计算观测（基于deploy_mujoco_1Step.py的逻辑）
        
        观测结构：
        - angVel 角速度
        - projected_gravity 重力向量
        - command_ 命令向量
        - dofPos 关节位置
        - dofVel 关节速度
        - actionMatrix 历史动作
        """


        dof_pos_scale = self.model_params.get('dof_pos_scale', 1.0)
        dof_vel_scale = self.model_params.get('dof_vel_scale', 1.0)
        lin_vel_scale = self.model_params.get('lin_vel_scale', 1.0)
        ang_vel_scale = self.model_params.get('ang_vel_scale', 1.0)
        command_scale = self.model_params.get('command_scale', 1.0)


        # 构建观测
        obs = np.zeros(self.model_params['num_obs'], dtype=np.float32)
        offset = 0

        # 1. angVel
        omega_body = np.array([state.omega[0], state.omega[1], state.omega[2]], dtype=np.float64)
        obs[offset:offset + 3] = omega_body.astype(np.float32) * ang_vel_scale
        offset += 3
        # 2. projected_gravity
        robot_quat = np.array([
            state.quat[0], state.quat[1], state.quat[2], state.quat[3]
        ])
        gravity_orientation = self.get_gravity_orientation(robot_quat)
        obs[offset:offset + 3] = gravity_orientation.astype(np.float32)
        offset += 3
        # 3. command
        command = np.array([
            state.v_des[0], state.v_des[1], state.omega_des[2]
        ])
        print("command:",command,"\n")
        obs[offset:offset + 3] = command.astype(np.float32) * command_scale
        offset += 3
        # 4. dofPos：按“每条腿前三个关节 + 轮子”交错拼接
        dof_q = np.array([
            state.joint_q[0], state.joint_q[1], state.joint_q[2], state.joint_q_supplement[0],
            state.joint_q[3], state.joint_q[4], state.joint_q[5], state.joint_q_supplement[1],
            state.joint_q[6], state.joint_q[7], state.joint_q[8], state.joint_q_supplement[2],
            state.joint_q[9], state.joint_q[10], state.joint_q[11], state.joint_q_supplement[3],
        ], dtype=np.float32)
        default_q = np.asarray(self.model_params["default_joint_pos"], dtype=np.float32)
        obs[offset:offset + 16] = (dof_q - default_q) * dof_pos_scale
        offset += 16
        # 5. dofVel：和 dofPos 保持相同顺序
        dof_qd = np.array([
            state.joint_qd[0], state.joint_qd[1], state.joint_qd[2], state.joint_qd_supplement[0],
            state.joint_qd[3], state.joint_qd[4], state.joint_qd[5], state.joint_qd_supplement[1],
            state.joint_qd[6], state.joint_qd[7], state.joint_qd[8], state.joint_qd_supplement[2],
            state.joint_qd[9], state.joint_qd[10], state.joint_qd[11], state.joint_qd_supplement[3],
        ], dtype=np.float32)
        obs[offset:offset + 16] = dof_qd * dof_vel_scale
        offset += 16
        # 6. action_buffer (num_actions) - 线程安全地读取
        with self.action_buffer_lock:
            obs[offset:offset + self.model_params['num_actions']] = self.action_buffer.copy()
        offset += self.model_params['num_actions']
        # 裁剪观测数据到合理范围（防止数值溢出）

        obs_clip_range = self.model_params.get('obs_clip_range', 100.0)  # 默认裁剪到 [-10, 10]
        obs = np.clip(obs, -obs_clip_range, obs_clip_range)
        
        return obs
    
    def process_action(self, state, action):
        """
        处理动作并发送控制命令
        
        动作处理流程：
        1. 将动作缩放并加上默认位置
        2. 映射回XML关节顺序
        3. 发送控制命令
        """
        # 如果执行完成，不再处理动作
        if self.execution_complete:
            return
        
        # 检查 action 是否有效
        if action is None or len(action) == 0:
            print("[RunAlgorithm] WARNING: Invalid action received, skipping...")
            return
        
        # 检查 action 中是否包含 NaN 或 Inf
        if np.any(np.isnan(action)) or np.any(np.isinf(action)):
            print(f"[RunAlgorithm] WARNING: Action contains NaN or Inf: {action}")
            print("[RunAlgorithm] Using previous action buffer instead")
            # 使用上一次的 action_buffer 作为备用（线程安全）
            with self.action_buffer_lock:
                action = self.action_buffer.copy()
            if np.any(np.isnan(action)) or np.any(np.isinf(action)):
                print("[RunAlgorithm] ERROR: Action buffer also contains NaN/Inf, cannot proceed")
                return
        
        action_scale = self.model_params.get('action_scale', np.ones(len(action), dtype=np.float32))
        if isinstance(action_scale, list):
            action_scale = np.array(action_scale, dtype=np.float32)
        
        # 确保 action_scale 长度匹配
        if len(action_scale) != len(action):
            print(f"[RunAlgorithm] WARNING: action_scale length ({len(action_scale)}) != action length ({len(action)}), using first {len(action)} elements")
            action_scale = action_scale[:len(action)]
        
        default_pos_seq = self.model_params.get('default_joint_pos', np.zeros(len(action), dtype=np.float32))
        # 确保 default_pos_seq 长度匹配
        if len(default_pos_seq) < len(action):
            print(f"[RunAlgorithm] WARNING: default_pos_seq length ({len(default_pos_seq)}) < action length ({len(action)}), padding with zeros")
            default_pos_seq = np.pad(default_pos_seq, (0, len(action) - len(default_pos_seq)), 'constant')
        #计算期望目标位置
        joint_positions = action * action_scale + default_pos_seq[:len(action)]
        joint_velocities  = action * action_scale 
        
        # 检查计算结果是否包含 NaN
        if np.any(np.isnan(joint_positions)) or np.any(np.isinf(joint_positions)):
            print(f"[RunAlgorithm] ERROR: target_dof_pos_seq contains NaN/Inf after calculation")
            print(f"  action: {action}")
            print(f"  action_scale: {action_scale}")
            print(f"  default_pos_seq[:len(action)]: {default_pos_seq[:len(action)]}")
            print(f"  target_dof_pos_seq: {joint_positions}")
            return
        
        # 确保 target_dof_pos 长度正确
        if len(joint_positions) != 16:
            print(f"[RunAlgorithm] ERROR: target_dof_pos length ({len(joint_positions)}) != 16")
            return

        if len(joint_velocities) != 16:
            print(f"[RunAlgorithm] ERROR: target_dof_vel length ({len(joint_velocities)}) != 16")
            return
        
        # 获取Kp和Kd（模型顺序，确保是numpy数组）
        joint_kp = self.model_params.get('joint_stiffness', np.zeros(16, dtype=np.float32))
        joint_kd = self.model_params.get('joint_damping', np.zeros(16, dtype=np.float32))
        
        # 如果已经是numpy数组，直接使用；如果是列表，转换为numpy数组
        if isinstance(joint_kp, list):
            joint_kp = np.array(joint_kp, dtype=np.float32)
        if isinstance(joint_kd, list):
            joint_kd = np.array(joint_kd, dtype=np.float32) 
        
        # 更新命令缓存（不直接发送，由500Hz发送循环发送）
        with self.latest_command_lock:
            self.latest_command = {
                'enable_development_mode': True,
                'joint_positions': joint_positions,
                'joint_velocities': joint_velocities,
                'joint_kp': joint_kp,
                'joint_kd': joint_kd,
                'joint_torques': [0.0] * 16
            }
        
    
    def on_development_mode_start(self):
        """开发模式开始时的回调"""
        self.execution_complete = False  # 重置完成标志
        
    
    def on_development_mode_end(self):
        """开发模式结束时的回调"""
        print("[RunAlgorithm] Development mode ended. Exiting program...")
        # 确保程序退出（线程安全）
        with self.state_lock:
            self.running = False


def main():
    """主函数"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description='Run Algorithm Runner')
    parser.add_argument('--config', type=str, default='config.yaml',
                       help='Path to configuration file (default: config.yaml)')
    args = parser.parse_args()
    
    # 处理配置文件路径（参考 mujoco_simulator.py）
    config_path = args.config
    if not os.path.isabs(config_path):
        # 如果是相对路径，基于脚本所在目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        potential_path = os.path.join(script_dir, config_path)
        if os.path.exists(potential_path):
            config_path = potential_path
        else:
            # 否则基于当前工作目录
            config_path = os.path.abspath(config_path)
    
    print(f"[RunAlgorithm] Using config file: {config_path}")
    
    # 创建算法实例
    try:
        algorithm = RunAlgorithm(config_path)
        algorithm.run()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
