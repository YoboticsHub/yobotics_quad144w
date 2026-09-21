# quad144w/Y20W Reinforcement-Learning Control Framework

> A 16D wheel-legged robot RL control package for quad144w/Y20W, including MuJoCo simulation, hardware control, LCM external-algorithm integration, WebRTC remote video/control, and Yobotics SDK examples.

This document is the entry point for the current `yobotics_quad144w` secondary development package. Controller entries and runtime libraries are provided by platform under `bin/`, `bin_rk3588/`, `lib/`, and `lib_rk3588/`.

The full manual is available at [docs/index.md](./docs/index.md) and can be viewed with MkDocs:

```bash
python3 -m pip install -r requirements-docs.txt
mkdocs serve
```

Read by goal:

- First run: [Environment and Quick Start](./docs/part-1-quick-start/1.framework.md)
- Field operation: [Hardware Architecture and Safety](./docs/part-3-hardware/1.overview.md)
- SDK integration: [SDK Overview](./docs/part-4-sdk/1.overview.md)
- Algorithm development: [LCM Communication Architecture](./docs/part-5-lcm-dev/1.structure.md) through [Custom Algorithms and Hardware Integration](./docs/part-5-lcm-dev/6.hardware.md)
- Remote control: [WebRTC Service Architecture](./docs/part-6-webrtc/1.overview.md)

## Capability Overview

Main modes supported by the current configuration and controller:

- `DAMP`
- `RECOVERY_STAND`
- `RL_WALK`
- `RL_HIGHSPEED`
- `RL_CLIMB`
- `RL_STAND`
- `DEVELOPMENT`

Main runtime paths:

1. MuJoCo simulation with [config_sim.yaml](./config_sim.yaml) and [scripts/start_mujoco.sh](./scripts/start_mujoco.sh).
2. Hardware control with [config.yaml](./config.yaml) and [scripts/run_robot_controller.sh](./scripts/run_robot_controller.sh).
3. External algorithms through `Y20W_development_state` / `Y20W_development_command` in `DEVELOPMENT` mode.
4. Remote control/video through [WebRTC_server](./WebRTC_server/), forwarding video and JSON control to Y20W LCM channels.

See [external_algorithms/README.md](./external_algorithms/README.md), [yobotics_sdk/README.md](./yobotics_sdk/README.md), and [WebRTC_server/README.md](./WebRTC_server/README.md) for component-specific notes.

## Quick Start

Run MuJoCo simulation first to confirm the Python environment, LCM, model files, and controller artifacts before using hardware.

### 1. Configure the Environment

```bash
bash scripts/setup_conda_env.sh
```

If one-click setup fails, install manually as needed:

```bash
conda create -n quad_controller python=3.8
conda activate quad_controller

sudo apt-get install -y liblcm-dev libeigen3-dev
pip install numpy==1.24.4 mujoco==3.2.3 pyyaml onnxruntime pillow

bash scripts/install_python_lcm.sh
sudo bash scripts/setup_lcm_network.sh
```

### 2. Check the Controller

The package already includes controller entries. Use `bin/ybt_ctrl` on x86_64 and `bin_rk3588/ybt_ctrl` on RK3588/aarch64.

### 3. Start Simulation

```bash
conda activate quad_controller
bash scripts/start_mujoco.sh --config config_sim.yaml
```

For headless environments:

```bash
bash scripts/start_mujoco.sh --config config_sim.yaml --headless
```

Key simulation settings:

- `simulation.enable_mujoco: true` in `config_sim.yaml`
- `simulation.mujoco.xml_path: resources_sim/robots/quad144w/scene_terrain.xml`
- `safety_checker.urdf_path: resources_sim/robots/quad144w/urdf/sduog144_V2_s.urdf`
- `motor_communication.type: "lcm"`

Press `Ctrl+C` to stop both MuJoCo and the controller processes.

## Hardware Operation

Before hardware operation, complete one simulation validation and confirm the emergency stop, power, IMU, motor communication, gamepad, stand, and safety environment are under control.

### 1. Configuration Checks

The default hardware configuration is [config.yaml](./config.yaml). Before running, check at least:

- `simulation.enable_mujoco: false`
- `motor_communication.type: "spi"`
- `gamepad.device_type: "hybrid"`
- `development.robot_id: "Y20W"`
- `development.state_channel: "Y20W_development_state"`
- `development.command_channel: "Y20W_development_command"`
- `gamepad.lcm_control_channel: "QUAD_ROBOT_CONTROL_Y20W"`
- `gamepad.lcm_state_channel: "QUAD_ROBOT_STATE_Y20W"`
- URDF/XML/mesh files are complete under `resources/robots/quad144w/`
- ONNX model paths under `actor_model/` match the RL policy blocks in `config.yaml`

### 2. Start the Controller

Run from the project root:

```bash
sudo bash scripts/run_robot_controller.sh --config config.yaml
```

The script uses `eth0` as the default LCM interface. If the onsite interface is different:

```bash
sudo bash scripts/run_robot_controller.sh --config config.yaml --iface <interface-name>
```

Or use an environment variable:

```bash
LCM_IFACE=<interface-name> sudo -E bash scripts/run_robot_controller.sh --config config.yaml
```

The script sets `LD_LIBRARY_PATH` automatically:

- x86_64: prefers packaged `bin/ybt_ctrl` and `lib/`.
- RK3588/aarch64: uses packaged `bin_rk3588/ybt_ctrl` and `lib_rk3588/`; if the onsite package keeps only the target architecture, `bin/ybt_ctrl` and `lib/` may also be used.

### 3. Optional: Start WebRTC

For video and remote control, first confirm [WebRTC_server/config.json](./WebRTC_server/config.json) channels match `config.yaml`:

- `lcm.control_channel: "QUAD_ROBOT_CONTROL_Y20W"`
- `lcm.state_channel: "QUAD_ROBOT_STATE_Y20W"`

Start the service:

```bash
python3 WebRTC_server/control_publisher.py
```

Remote clients connect to the robot IP signaling address:

```text
ws://<robot_ip>:8765
```

### 4. Runtime Checks and Stop

- Controller log path is set by `logging.log_file_path` in `config.yaml`; the current hardware default is `/home/cat/log/robot_log.txt`.
- Check LCM channels and frequencies: `bash scripts/monitor_lcm.sh --no-gui`.
- Launch graphical LCM viewer: `bash scripts/launch_lcm_spy.sh`.
- Visualize hardware state in MuJoCo: `bash scripts/start_hardware_viewer.sh`.
- View RL/motor CSV logs: `python3 scripts/data_viewer.py` or `python3 scripts/motor_trace_viewer.py log/motor_trace.csv`.
- If no state is received, check LCM interface, SPI/IMU/motor connections, `config.yaml` channels, and permissions first.
- Press `Ctrl+C` to stop the foreground controller. For WebRTC via `control_publisher.py`, also use `Ctrl+C` and wait for child-process cleanup.

## Runtime Entries and Directories

- `config.yaml`: default hardware configuration.
- `config_sim.yaml`: default MuJoCo simulation configuration.
- `actor_model/`: ONNX policy models for `RL_WALK`, `RL_HIGHSPEED`, `RL_CLIMB`, and `RL_STAND`.
- `resources/`: quad144w robot resources used by hardware configuration.
- `resources_sim/`: quad144w robot resources used by simulation.
- `mujoco_sim/`: MuJoCo simulation Python module.
- `scripts/`: environment setup, controller startup, LCM monitoring, network setup, hardware Viewer, and log tools.
- `external_algorithms/`: external-algorithm framework for `DEVELOPMENT` mode.
- `WebRTC_server/`: WebRTC video and remote-control service.
- `yobotics_sdk/`: customer SDK, HTTP control service, and examples.
- `lcm-types/`: LCM protocol definitions and generated Python/C++/Java code.
- `bin/`, `lib/`: x86_64 controller entry and runtime libraries.
- `bin_rk3588/`, `lib_rk3588/`: RK3588/aarch64 controller entry and runtime libraries.

## Mode Summary

| Mode | Description |
| --- | --- |
| `DAMP` | Damping/protection mode, commonly used for stopping or safe switching. |
| `RECOVERY_STAND` | Automatically recover to standing posture. |
| `RL_WALK` | Normal RL walking policy with velocity commands. |
| `RL_HIGHSPEED` | High-speed RL policy; config block `rl_highspeed`. |
| `RL_CLIMB` | Climbing/obstacle RL policy; config block `rl_climb`. |
| `RL_STAND` | Standing policy; config block `rl_stand`. |
| `DEVELOPMENT` | External-algorithm development mode receiving joint commands through LCM. |

`gamepad.mode_sequence` in `config.yaml` and `config_sim.yaml` defines the mode order available to the gamepad or host controller.

## Configuration Notes

Key settings are in `config.yaml` / `config_sim.yaml`:

- `simulation.enable_mujoco`: simulation/hardware switch.
- `simulation.mujoco.xml_path`: MuJoCo scene XML.
- `motor_communication.type`: communication type; simulation uses `lcm`, hardware uses `spi`.
- `motor_communication.board`: SPI board protocol, `rk3588` by default or `upboard`; case-sensitive. Both use Linux SPI `bits_per_word=8`, with different frame layout, checksums, SPI frequency, and ab/ad zero offsets.
- `rl_walk` / `rl_highspeed` / `rl_climb` / `rl_stand`: actor, encoder, logs, and model parameters for each RL policy.
- `development`: robot_id, state channel, command channel, and exit self-check thresholds for external algorithms.
- `gamepad.device_type`: control input type; current hardware and simulation configs use `hybrid`.
- `gamepad.lcm_control_channel` / `gamepad.lcm_state_channel`: host/WebRTC/SDK control and state channels.
- `safety_checker.urdf_path`: robot URDF path.
- `safety_checker`: posture, joint, hardware-loss, and related safety checks.

SPI board example:

```yaml
motor_communication:
  type: "spi"
  board: "upboard"
  spi_device0: "/dev/spidev2.0"
  spi_device1: "/dev/spidev2.1"
```

## DEVELOPMENT External Algorithms

External algorithms only take effect in `DEVELOPMENT` mode. Two demos are included:

```bash
python3 external_algorithms/walk_algorithm/run_algorithm.py --config external_algorithms/walk_algorithm/config.yaml
```

```bash
python3 external_algorithms/wave_algorithm/run_algorithm.py --config external_algorithms/wave_algorithm/config.yaml
```

Default DEVELOPMENT channels:

- `robot_id: "Y20W"`
- `state_channel: "Y20W_development_state"`
- `command_channel: "Y20W_development_command"`

For the complete 16D protocol, 57D observation, framework threads, model replacement, and six-stage hardware acceptance, see [Part 5: LCM and External Algorithms](./docs/part-5-lcm-dev/1.structure.md). Command quick reference is in [external_algorithms/README.md](./external_algorithms/README.md).

## Development Entry Points

- [external_algorithms/README.md](./external_algorithms/README.md): external-algorithm integration notes.
- [WebRTC_server/README.md](./WebRTC_server/README.md): remote video, DataChannel control, and LCM forwarding.
- [yobotics_sdk/README.md](./yobotics_sdk/README.md): SDK, HTTP control API, and examples.
- [scripts/README.md](./scripts/README.md): script entries, parameters, and troubleshooting.
- `lcm-types/`: control protocol and message fields.

## Common Issues

### Controller Cannot Find Shared Libraries

Check in the package:

```bash
ls -l lib/libonnxruntime.so*
LD_LIBRARY_PATH=$PWD/lib ldd bin/ybt_ctrl.bin
```

Running the real binary directly requires manually setting `LD_LIBRARY_PATH`; the script entry is recommended.

### Simulation Startup Fails

Check first:

- Whether `simulation.enable_mujoco: true` is set in `config_sim.yaml`.
- Whether `resources_sim/robots/quad144w/scene_terrain.xml` exists.
- Whether Python has `mujoco`, `pyyaml`, `numpy`, and `onnxruntime`.
- Whether Python LCM bindings are available.
- Whether `bin/ybt_ctrl` exists and is executable.

### No LCM Messages

Run:

```bash
sudo bash scripts/setup_lcm_network.sh
bash scripts/monitor_lcm.sh --no-gui
```

On multi-interface machines, confirm `scripts/setup_lcm_network.sh`, `scripts/run_robot_controller.sh --iface`, and WebRTC/SDK processes use the same network interface and channel set.

### WebRTC Control Does Not Respond

- Confirm `WebRTC_server/config.json` control channel is `QUAD_ROBOT_CONTROL_Y20W`.
- Confirm state channel is `QUAD_ROBOT_STATE_Y20W`.
- Confirm robot-side port `8765` is listening.
- Confirm controller `gamepad.device_type` supports LCM or hybrid input.

## Safety Notes

- Keep safety checks enabled on hardware; disabling `safety_checker` is not recommended.
- Before hardware operation, validate mode switching, velocity limits, and emergency stop on a stand or in a safe environment.
- After replacing ONNX policies, confirm model input/output dimensions, joint order, default joint positions, and action scaling.
- At the end of debugging, switch back to `DAMP` or stop the controller/WebRTC service to avoid command leftovers.
