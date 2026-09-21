# quad144w/Y20W Wheel-Legged Robot Control Framework Manual

This manual is for the `yobotics_quad144w` secondary development package. It explains how to configure the environment, run MuJoCo simulation, start the real robot, use the Yobotics SDK, integrate external algorithms, and run the WebRTC service.

| Item | Description |
| --- | --- |
| Document version | 1.0 |
| Applicable software | yobotics_quad144w secondary development package |
| Robot model | quad144w / Y20W, 16-DOF wheel-legged robot |
| Supported platforms | x86_64; RK3588/aarch64 |
| Control protocol | 12 leg joints plus 4 wheel joints |

## Recommended Reading Path

| User | Reading order | Goal |
| --- | --- | --- |
| First-time user | Part 1 -> Part 2 | Set up the environment and run MuJoCo |
| Field deployment user | Part 1 -> Part 2 -> Part 3 | Configure, start, and inspect the real robot |
| SDK integrator | Part 1 -> Part 4 | Send mode/velocity commands and read state |
| Algorithm developer | Part 2 -> Part 5 -> Part 3 | Validate 16D algorithms in simulation before hardware |
| Remote-control developer | Part 1 -> Part 4 -> Part 6 | Connect video, DataChannel, and LCM |

## System Overview

```text
                    High-level control input
        Gamepad ----- SDK -------- WebRTC
          \            |             /
           +---- QUAD_ROBOT_CONTROL_Y20W
                         |
                         v
              +--------------------+
              | Y20W controller    |
              | modes/policies/safety |
              +--------------------+
                 |              ^
      joint cmd  |              | DEVELOPMENT cmd
                 v              |
          MuJoCo / hardware   external algorithm
                 |
          12 leg joints + 4 wheels
```

The controller is the center of every runtime path. SDK and WebRTC send high-level motion intent, external algorithms submit joint-level targets through DEVELOPMENT mode, and MuJoCo or the hardware layer executes the controller output.

## Operating Principles

!!! danger "Hardware safety"
    New models, new parameters, and external algorithms must be validated in MuJoCo first. For initial hardware runs, lift the wheel-legged robot or use a reliable stand, and keep personnel ready to press the emergency stop.

- Use `config_sim.yaml` for simulation and `config.yaml` for hardware. Do not mix them.
- The wheel-leg order is always `LF, RF, LR, RR`; each leg is `[hip, thigh, calf, wheel]`.
- When changing models, check the observation dimension, action dimension, default joint positions, scaling, and PD parameters together.
- For LCM communication across machines, sender and receiver must use the same multicast URL and a reachable network interface.

## Common Commands

```bash
# Prepare Python, MuJoCo, and LCM
bash scripts/setup_conda_env.sh

# Start simulation
bash scripts/start_mujoco.sh --config config_sim.yaml

# Start the hardware controller
sudo bash scripts/run_robot_controller.sh --config config.yaml

# Monitor LCM
bash scripts/monitor_lcm.sh --no-gui

# Visualize hardware state
bash scripts/start_hardware_viewer.sh
```

## First Acceptance Sequence

1. Install the environment and verify Python, LCM, and MuJoCo.
2. Start MuJoCo and confirm the model, joint state, and IMU channels are continuous.
3. Start from `DAMP`, then verify standing and low-speed modes.
4. Use the SDK state example to confirm upper-layer communication.
5. For algorithm development, run wave first, then ONNX walk.
6. Move to stand-supported hardware testing only after all abnormal-exit paths pass in simulation.

Each stage should leave reproducible commands, configuration files, and success indicators. If an exception occurs, return to the most recent passed stage. Do not change the model, gains, channels, and mechanical configuration at the same time.

## Robot Operation Video

Using the Y20W quadruped robot as an example:

![type:video](videos/Y20W.mp4)
