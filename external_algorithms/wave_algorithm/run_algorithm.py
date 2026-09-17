#!/usr/bin/env python3
"""
Y20W 躯干上下波动算法。
直接生成 16 维 [hip, thigh, calf, wheel] 关节目标，不依赖 ONNX 策略文件。
"""

import os
import sys
import time

import numpy as np

_parent_dir = os.path.join(os.path.dirname(__file__), '..')
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from algorithm_base import AlgorithmBase


class RunAlgorithm(AlgorithmBase):
    """Wave motion algorithm for Y20W DEVELOPMENT mode."""

    def __init__(self, config_path):
        super().__init__(config_path)
        self.execution_complete = False
        self.start_time = time.time()
        self.step_count = 0

    def _load_policy(self):
        """Direct control algorithm: no ONNX policy is required."""
        print(f"[{self.__class__.__name__}] policy.type='none', using direct wave control without ONNX")
        self.model = None
        self.encoder = None
        self.policy_type = 'none'

    def compute_observation(self, state):
        """
        Build a lightweight observation for the base execution loop.
        Wave control itself only needs time, but keeping state fields here helps debug LCM reception.
        """
        obs = np.zeros(self.model_params['num_obs'], dtype=np.float32)

        try:
            main_q = np.array(state.joint_q, dtype=np.float32)
            wheel_q = np.array(state.joint_q_supplement, dtype=np.float32)
            main_qd = np.array(state.joint_qd, dtype=np.float32)
            wheel_qd = np.array(state.joint_qd_supplement, dtype=np.float32)
            dof_q = np.array([
                main_q[0], main_q[1], main_q[2], wheel_q[0],
                main_q[3], main_q[4], main_q[5], wheel_q[1],
                main_q[6], main_q[7], main_q[8], wheel_q[2],
                main_q[9], main_q[10], main_q[11], wheel_q[3],
            ], dtype=np.float32)
            dof_qd = np.array([
                main_qd[0], main_qd[1], main_qd[2], wheel_qd[0],
                main_qd[3], main_qd[4], main_qd[5], wheel_qd[1],
                main_qd[6], main_qd[7], main_qd[8], wheel_qd[2],
                main_qd[9], main_qd[10], main_qd[11], wheel_qd[3],
            ], dtype=np.float32)
            obs[0:16] = dof_q
            obs[16:32] = dof_qd
        except Exception:
            pass

        try:
            obs[32:35] = np.array([state.v_des[0], state.v_des[1], state.v_des[2]], dtype=np.float32)
            obs[35:38] = np.array([state.omega_des[0], state.omega_des[1], state.omega_des[2]], dtype=np.float32)
            obs[38:42] = np.array([state.quat[0], state.quat[1], state.quat[2], state.quat[3]], dtype=np.float32)
        except Exception:
            pass

        return obs

    def _run_inference(self, obs):
        """Generate a sinusoidal 16D action directly."""
        self.step_count += 1
        elapsed = time.time() - self.start_time
        motion_cfg = self.config.get('motion', {})
        frequency = float(motion_cfg.get('frequency', 1.0))
        amplitude = float(motion_cfg.get('amplitude', 0.35))
        phase = 2.0 * np.pi * frequency * elapsed

        thigh_offset = amplitude * np.sin(phase)
        calf_offset = -2.0 * amplitude * np.sin(phase)

        action = np.zeros(self.model_params['num_actions'], dtype=np.float32)
        for leg_id in range(4):
            base = leg_id * 4
            action[base + 0] = 0.0
            action[base + 1] = thigh_offset
            action[base + 2] = calf_offset
            action[base + 3] = 0.0

        return action

    def process_action(self, state, action):
        """Convert the 16D wave action to a DEVELOPMENT command."""
        if self.execution_complete:
            return

        expected_dim = self.model_params.get('num_actions', self.TOTAL_JOINT_DIM)
        if action is None or len(action) != expected_dim:
            print(f"[{self.__class__.__name__}] WARNING: invalid action length {None if action is None else len(action)}")
            return

        default_pos = self.model_params.get('default_joint_pos', np.zeros(expected_dim, dtype=np.float32))
        joint_kp = self.model_params.get('joint_stiffness', np.zeros(expected_dim, dtype=np.float32))
        joint_kd = self.model_params.get('joint_damping', np.zeros(expected_dim, dtype=np.float32))

        default_pos = np.asarray(default_pos, dtype=np.float32)
        joint_kp = np.asarray(joint_kp, dtype=np.float32)
        joint_kd = np.asarray(joint_kd, dtype=np.float32)
        joint_positions = default_pos + np.asarray(action, dtype=np.float32)
        joint_velocities = np.zeros(expected_dim, dtype=np.float32)
        joint_torques = np.zeros(expected_dim, dtype=np.float32)

        with self.latest_command_lock:
            self.latest_command = {
                'enable_development_mode': True,
                'joint_positions': joint_positions,
                'joint_velocities': joint_velocities,
                'joint_torques': joint_torques,
                'joint_kp': joint_kp,
                'joint_kd': joint_kd,
            }

    def on_development_mode_start(self):
        self.execution_complete = False
        self.start_time = time.time()
        self.step_count = 0
        print(f"[{self.__class__.__name__}] Development mode started: Y20W wave motion active")

    def on_development_mode_end(self):
        print(f"[{self.__class__.__name__}] Development mode ended: stopping wave motion")
        with self.latest_command_lock:
            self.latest_command = {
                'enable_development_mode': False,
            }


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Y20W Wave Algorithm Runner')
    parser.add_argument('--config', type=str, default='config.yaml',
                        help='Path to configuration file (default: config.yaml)')
    args = parser.parse_args()

    config_path = args.config
    if not os.path.isabs(config_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        potential_path = os.path.join(script_dir, config_path)
        config_path = potential_path if os.path.exists(potential_path) else os.path.abspath(config_path)

    print(f"[{RunAlgorithm.__name__}] Using config file: {config_path}")

    try:
        algorithm = RunAlgorithm(config_path)
        algorithm.run()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
