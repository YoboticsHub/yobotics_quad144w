# quad144w Package Scripts

This directory documents the `scripts/` folder in the `yobotics_quad144w` package. The scripts start the quad144w/Y20W controller, start MuJoCo simulation, configure LCM networking, monitor LCM messages, prepare the Python environment, view hardware posture, and analyze CSV logs.

## Before Use

Run commands from the package root:

```bash
cd yobotics_quad144w
chmod +x scripts/*.sh
```

If you use simulation or Python tools, prepare the environment first:

```bash
bash scripts/setup_conda_env.sh
```

To repair only Python LCM bindings:

```bash
bash scripts/install_python_lcm.sh
```

Common package layout:

```text
yobotics_quad144w/
├── bin/                  # controller wrapper ybt_ctrl and real binary ybt_ctrl.bin
├── bin_rk3588/           # RK3588/aarch64 controller entry
├── lib/                  # runtime shared libraries
├── lib_rk3588/           # RK3588/aarch64 runtime shared libraries
├── log/                  # runtime logs
├── lcm-types/            # LCM type definitions and generated results
├── mujoco_sim/           # MuJoCo simulation code
├── resources/            # hardware robot resources
├── resources_sim/        # simulation robot resources
├── scripts/              # scripts described here
├── config.yaml           # hardware configuration
└── config_sim.yaml       # simulation configuration
```

## Recommended Workflow

```bash
# 1. Configure Python/LCM environment
bash scripts/setup_conda_env.sh

# 2. Start simulation
bash scripts/start_mujoco.sh --config config_sim.yaml

# 3. Monitor LCM
bash scripts/monitor_lcm.sh --no-gui

# 4. Start hardware controller
sudo bash scripts/run_robot_controller.sh --config config.yaml --iface eth0
```

## Controller Startup

### `run_robot_controller.sh`

Starts the hardware controller and sets the shared-library path for the current architecture.

```bash
sudo bash scripts/run_robot_controller.sh --config config.yaml
```

The default LCM interface is `eth0`. If the onsite machine uses another interface:

```bash
sudo bash scripts/run_robot_controller.sh --config config.yaml --iface <interface-name>
```

Or use an environment variable:

```bash
LCM_IFACE=<interface-name> sudo -E bash scripts/run_robot_controller.sh --config config.yaml
```

Architecture selection:

- x86_64: prefers `bin/ybt_ctrl` and `lib/`.
- RK3588/aarch64: prefers `bin_rk3588/ybt_ctrl` and `lib_rk3588/`, falling back to `bin/ybt_ctrl` and `lib/` when absent.

Running `ybt_ctrl.bin` directly does not set the full library path. Prefer this script or the `ybt_ctrl` wrapper in the matching directory.

### `run_controller.sh`

Legacy source-tree compatible entry. The current secondary development package does not include controller source; use `run_robot_controller.sh` for normal operation.

### `run_human_debug.sh`

Legacy debug entry retained for existing workflows. New hardware runs should prefer `run_robot_controller.sh`.

## MuJoCo Simulation

### `start_mujoco.sh`

Starts the MuJoCo simulator and controller:

```bash
bash scripts/start_mujoco.sh --config config_sim.yaml
bash scripts/start_mujoco.sh --config config_sim.yaml --headless
```

Simulation depends on `config_sim.yaml`, `resources_sim/`, `mujoco_sim/`, `actor_model/`, and `lcm-types/`.

If the controller is not found, confirm `bin/ybt_ctrl` exists in the package and is executable.

### `start_hardware_viewer.sh` / `hardware_mujoco_viewer.py`

Displays hardware LCM feedback in a MuJoCo Viewer. It only refreshes model posture and does not run a full simulation control loop.

```bash
bash scripts/start_hardware_viewer.sh
bash scripts/start_hardware_viewer.sh --xml resources/robots/quad144w/scene_terrain.xml
bash scripts/start_hardware_viewer.sh --lcm-url "udpm://239.255.76.67:7667?ttl=255"
bash scripts/start_hardware_viewer.sh --viewer-hz 30
```

Defaults:

- XML: `resources/robots/quad144w/scene_terrain.xml`
- Joint state channel: `Y20W_QUAD_JOINT_STATE`
- Robot state channel: `QUAD_ROBOT_STATE_Y20W`
- Viewer refresh rate: `60 Hz`

If the model does not move in the Viewer, confirm the controller is publishing these channels and check LCM URL/interface configuration.

## LCM Tools

### `setup_lcm_network.sh`

Configures LCM multicast networking:

```bash
sudo bash scripts/setup_lcm_network.sh
```

This script changes network configuration. During remote debugging, confirm the target interface first to avoid disrupting SSH.

### `monitor_lcm.sh` / `monitor_lcm.py`

View LCM channels and message frequencies:

```bash
bash scripts/monitor_lcm.sh --no-gui
python3 scripts/monitor_lcm.py --no-gui
```

If GUI is available, run without `--no-gui`. If there are no messages, check `setup_lcm_network.sh`, controller process, simulation process, and channel configuration.

### `launch_lcm_spy.sh`

Starts system `lcm-spy`:

```bash
bash scripts/launch_lcm_spy.sh
```

Requires the LCM toolchain to be installed.

### `generate_lcm_types.sh`

Regenerates types after `.lcm` changes or missing generated code:

```bash
bash scripts/generate_lcm_types.sh
```

### `make_types_no_java.sh`

Generates LCM types without Java output for C++/Python-only development:

```bash
bash scripts/make_types_no_java.sh
```

## Environment and Helper Tools

- `setup_conda_env.sh`: creates/configures the environment for simulation, LCM monitoring, and Python tools.
- `install_python_lcm.sh`: installs or repairs Python LCM bindings.
- `remove_conda_env.sh`: removes the Conda environment created by the scripts.
- `calibrate_gamepad.py`: calibrates gamepad input.
- `data_viewer.py`: views RL CSV logs grouped by leg, joint, or variable type, including quad144w `hip/thigh/calf/wheel` columns.
- `motor_trace_viewer.py`: views motor trace logs such as `motor_trace.csv`, with presets for angle, torque, and IMU.
- `show_network_bandwidth.sh`: displays network-interface bandwidth usage.

Examples:

```bash
python3 scripts/calibrate_gamepad.py
python3 scripts/data_viewer.py log/log_RL_walk.csv
python3 scripts/motor_trace_viewer.py log/motor_trace.csv
bash scripts/show_network_bandwidth.sh eth0 1
```

## Common Issues

### Controller Cannot Find Shared Libraries

Run from the package root and prefer:

```bash
sudo bash scripts/run_robot_controller.sh --config config.yaml
```

Also check:

```bash
ls -l bin/ybt_ctrl bin/ybt_ctrl.bin
ls -l lib/libonnxruntime.so*
```

### LCM Monitor Has No Messages

Check in order:

```bash
sudo bash scripts/setup_lcm_network.sh
bash scripts/monitor_lcm.sh --no-gui
```

Confirm the controller or simulation is running and using the same Y20W LCM channels.

### GUI Cannot Open

On headless servers or SSH sessions, use text/headless mode:

```bash
bash scripts/monitor_lcm.sh --no-gui
bash scripts/start_mujoco.sh --config config_sim.yaml --headless
```
