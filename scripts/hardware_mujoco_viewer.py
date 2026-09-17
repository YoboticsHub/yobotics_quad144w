#!/usr/bin/env python3
"""Realtime quad144w/Y20W hardware-state replay in the MuJoCo viewer."""

import argparse
import math
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import List

import numpy as np


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LCM_PYTHON_DIR = os.path.join(PROJECT_ROOT, "lcm-types", "python")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if LCM_PYTHON_DIR not in sys.path:
    sys.path.insert(0, LCM_PYTHON_DIR)


try:
    import lcm
except ImportError as exc:
    raise SystemExit(
        "Failed to import python lcm module. Install/enable LCM Python bindings "
        "before running this viewer."
    ) from exc

try:
    import mujoco
    import mujoco.viewer
except ImportError as exc:
    raise SystemExit(
        "Failed to import mujoco. Activate the Python environment that provides "
        "the mujoco package before running this viewer."
    ) from exc

from quad_joint_state_t import quad_joint_state_t
from sport_client_state_t import sport_client_state_t


def rpy_to_quat_wxyz(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Convert roll-pitch-yaw radians to MuJoCo's wxyz quaternion order."""
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)

    w = cr * cp * cy + sr * sp * sy
    x = sr * cp * cy - cr * sp * sy
    y = cr * sp * cy + sr * cp * sy
    z = cr * cp * sy - sr * sp * cy
    return np.array([w, x, y, z], dtype=np.float64)


@dataclass
class HardwareReplayState:
    """Thread-safe copy of the newest hardware feedback used by the viewer."""

    joint_q: np.ndarray = field(default_factory=lambda: np.zeros(16, dtype=np.float64))
    rpy: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    height: float = 0.45
    mode: int = 0
    joint_msg_count: int = 0
    robot_state_msg_count: int = 0
    last_joint_time: float = 0.0
    last_robot_state_time: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def update_joint_state(self, msg: quad_joint_state_t) -> None:
        with self.lock:
            joint_q = np.asarray(msg.joint_q, dtype=np.float64)
            copy_count = min(self.joint_q.size, joint_q.size)
            self.joint_q[:] = 0.0
            self.joint_q[:copy_count] = joint_q[:copy_count]
            self.joint_msg_count += 1
            self.last_joint_time = time.monotonic()

    def update_robot_state(self, msg: sport_client_state_t) -> None:
        with self.lock:
            self.rpy[:] = np.asarray(msg.rpy, dtype=np.float64)
            if math.isfinite(float(msg.h)) and float(msg.h) > 0.01:
                self.height = float(msg.h)
            self.mode = int(msg.state)
            self.robot_state_msg_count += 1
            self.last_robot_state_time = time.monotonic()

    def snapshot(self):
        with self.lock:
            return (
                self.joint_q.copy(),
                self.rpy.copy(),
                float(self.height),
                int(self.mode),
                int(self.joint_msg_count),
                int(self.robot_state_msg_count),
                float(self.last_joint_time),
                float(self.last_robot_state_time),
            )


def resolve_project_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(PROJECT_ROOT, path)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay live quad144w/Y20W hardware LCM feedback in a MuJoCo viewer."
    )
    parser.add_argument(
        "--xml",
        default="resources/robots/quad144w/scene_terrain.xml",
        help="MuJoCo XML path, absolute or relative to the project root.",
    )
    parser.add_argument(
        "--lcm-url",
        default="udpm://239.255.76.67:7667?ttl=255",
        help="LCM URL used to receive hardware feedback.",
    )
    parser.add_argument(
        "--joint-channel",
        default="Y20W_QUAD_JOINT_STATE",
        help="LCM channel carrying quad_joint_state_t feedback.",
    )
    parser.add_argument(
        "--robot-state-channel",
        default="QUAD_ROBOT_STATE_Y20W",
        help="LCM channel carrying sport_client_state_t body state.",
    )
    parser.add_argument(
        "--height",
        type=float,
        default=0.45,
        help="Fallback floating-base height when robot state h is absent or zero.",
    )
    parser.add_argument("--x", type=float, default=0.0, help="Fixed world x position.")
    parser.add_argument("--y", type=float, default=0.0, help="Fixed world y position.")
    parser.add_argument(
        "--viewer-hz",
        type=float,
        default=60.0,
        help="Viewer refresh rate. Physics is not stepped; this only limits drawing.",
    )
    parser.add_argument(
        "--stale-timeout",
        type=float,
        default=2.0,
        help="Seconds before printing a warning about missing LCM feedback.",
    )
    return parser


def start_lcm_thread(lcm_instance, replay_state: HardwareReplayState, args):
    def handle_joint(channel, data):
        try:
            replay_state.update_joint_state(quad_joint_state_t.decode(data))
        except Exception as exc:
            print(f"[hardware_mujoco_viewer] Failed to decode {channel}: {exc}")

    def handle_robot_state(channel, data):
        try:
            replay_state.update_robot_state(sport_client_state_t.decode(data))
        except Exception as exc:
            print(f"[hardware_mujoco_viewer] Failed to decode {channel}: {exc}")

    lcm_instance.subscribe(args.joint_channel, handle_joint)
    lcm_instance.subscribe(args.robot_state_channel, handle_robot_state)

    running = threading.Event()
    running.set()

    def loop():
        while running.is_set():
            try:
                lcm_instance.handle_timeout(50)
            except AttributeError:
                lcm_instance.handle()
            except Exception as exc:
                print(f"[hardware_mujoco_viewer] LCM receive error: {exc}")
                time.sleep(0.05)

    thread = threading.Thread(target=loop, name="hardware-viewer-lcm", daemon=True)
    thread.start()
    return running, thread


def run_viewer(args) -> int:
    xml_path = resolve_project_path(args.xml)
    if not os.path.exists(xml_path):
        print(f"[hardware_mujoco_viewer] MuJoCo XML not found: {xml_path}")
        return 1

    replay_state = HardwareReplayState(height=args.height)
    lcm_instance = lcm.LCM(args.lcm_url)
    running, lcm_thread = start_lcm_thread(lcm_instance, replay_state, args)

    model = mujoco.MjModel.from_xml_path(xml_path)
    data = mujoco.MjData(model)
    expected_nq = 7 + replay_state.joint_q.size
    if model.nq < expected_nq:
        running.clear()
        lcm_thread.join(timeout=1.0)
        print(
            "[hardware_mujoco_viewer] Expected a free joint plus 16 robot joints "
            f"(nq >= {expected_nq}), but model.nq={model.nq}."
        )
        return 1

    period = 1.0 / max(args.viewer_hz, 1.0)
    next_status_time = 0.0

    print("[hardware_mujoco_viewer] Listening for hardware feedback")
    print(f"  xml: {xml_path}")
    print(f"  lcm_url: {args.lcm_url}")
    print(f"  joint_channel: {args.joint_channel}")
    print(f"  robot_state_channel: {args.robot_state_channel}")

    try:
        with mujoco.viewer.launch_passive(model, data) as viewer:
            viewer.cam.distance = 3.0
            viewer.cam.azimuth = 90.0
            viewer.cam.elevation = -20.0
            viewer.cam.lookat[:] = [args.x, args.y, args.height]

            while viewer.is_running():
                frame_start = time.monotonic()
                (
                    joint_q,
                    rpy,
                    height,
                    mode,
                    joint_count,
                    state_count,
                    last_joint_time,
                    last_state_time,
                ) = replay_state.snapshot()

                data.qpos[0] = args.x
                data.qpos[1] = args.y
                data.qpos[2] = height
                data.qpos[3:7] = rpy_to_quat_wxyz(float(rpy[0]), float(rpy[1]), float(rpy[2]))
                data.qpos[7:expected_nq] = joint_q[: replay_state.joint_q.size]
                mujoco.mj_forward(model, data)

                viewer.cam.lookat[:] = data.qpos[0:3]
                viewer.sync()

                now = time.monotonic()
                if now >= next_status_time:
                    if joint_count == 0:
                        print(
                            f"[hardware_mujoco_viewer] Waiting for {args.joint_channel} "
                            "joint feedback..."
                        )
                    elif now - last_joint_time > args.stale_timeout:
                        print(
                            "[hardware_mujoco_viewer] Warning: joint feedback is stale "
                            f"({now - last_joint_time:.1f}s old)."
                        )
                    if state_count == 0:
                        print(
                            f"[hardware_mujoco_viewer] Waiting for {args.robot_state_channel} "
                            "body pose feedback; using fallback height/RPY for now."
                        )
                    elif now - last_state_time > args.stale_timeout:
                        print(
                            "[hardware_mujoco_viewer] Warning: robot state is stale "
                            f"({now - last_state_time:.1f}s old)."
                        )
                    print(
                        "[hardware_mujoco_viewer] "
                        f"joint_msgs={joint_count} state_msgs={state_count} mode={mode}"
                    )
                    next_status_time = now + args.stale_timeout

                sleep_time = period - (time.monotonic() - frame_start)
                if sleep_time > 0.0:
                    time.sleep(sleep_time)
    finally:
        running.clear()
        lcm_thread.join(timeout=1.0)

    return 0


def main() -> int:
    args = build_arg_parser().parse_args()
    return run_viewer(args)


if __name__ == "__main__":
    raise SystemExit(main())
