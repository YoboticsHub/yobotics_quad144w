# External Algorithm Development Demos

This directory contains external algorithm demos that connect to the robot development mode through LCM. Each demo lives in its own subdirectory and usually contains `config.yaml` and `run_algorithm.py`. `AlgorithmBase` and `LCMInterface` provide state reception, policy inference or rule computation, and joint-command publishing.

For the full development manual, see MkDocs [Part 5: LCM and External Algorithms](../docs/part-5-lcm-dev/1.structure.md). This README keeps a quick reference for directories, commands, and configuration.

Current demos:

- **`walk_algorithm/`**: Y20W wheel-leg walking policy demo based on ONNX actor / encoder models.
- **`wave_algorithm/`**: Y20W wheel-leg sinusoidal rule-control demo without a policy model.

## Directory Layout

```text
external_algorithms/
├── README.md
├── algorithm_base.py
├── lcm_interface.py
├── walk_algorithm/
│   ├── config.yaml
│   ├── run_algorithm.py
│   ├── HumanActornet.onnx
│   └── HumanEncodernet.onnx
└── wave_algorithm/
    ├── README.md
    ├── config.yaml
    └── run_algorithm.py
```

## Architecture

- `algorithm_base.py`: base class for configuration loading, ONNX model loading, development-mode lifecycle, inference loop, action warmup, and high-frequency LCM command sending.
- `lcm_interface.py`: LCM wrapper that subscribes to `development_state_t` and publishes `development_command_t`.
- `walk_algorithm/`: 16D Y20W DRL locomotion demo loading `HumanActornet.onnx` and `HumanEncodernet.onnx`.
- `wave_algorithm/`: 16D Y20W explicit rule-control demo that generates sinusoidal actions from time without loading ONNX.

## Demo Overview

| Demo | Directory | Development style | Main dependencies | Robot / LCM channels |
| --- | --- | --- | --- | --- |
| Wheel-leg walking policy demo | `walk_algorithm/` | DRL-based | `onnxruntime`, `numpy`, `LCM` | `Y20W`, `Y20W_development_state`, `Y20W_development_command` |
| Body wave demo | `wave_algorithm/` | model/rule-based | `numpy`, `LCM` | `Y20W`, `Y20W_development_state`, `Y20W_development_command` |

## 16D Wheel-Leg Protocol

External algorithms in this project use a 16D action layout with four DOF per leg:

```text
LF: hip, thigh, calf, wheel
RF: hip, thigh, calf, wheel
LR: hip, thigh, calf, wheel
RR: hip, thigh, calf, wheel
```

The lower-level LCM command still contains a 12D main-joint array and a 4D supplement wheel array. `LCMInterface` automatically splits 16D input:

- The first three values of each leg `[hip, thigh, calf]` go to the 12D main joint array.
- The fourth value `wheel` of each leg goes to the 4D supplement array.

## DRL Demo: `walk_algorithm/`

`walk_algorithm` is a Y20W wheel-leg ONNX policy demo. Its configuration uses:

- `policy.type: "onnx"`
- `policy.model_path: "./HumanActornet.onnx"`
- `policy.encoder_path: "./HumanEncodernet.onnx"`

Main flow:

1. Subscribe to `Y20W_development_state` through LCM.
2. Read body angular velocity, posture quaternion, desired velocity, 12D main-joint state, and 4D wheel supplement state.
3. Merge main joints and wheel state into a 16D leg-block layout.
4. Build a 57D observation as `[angVel, projected_gravity, command, dofPos, dofVel, action_buffer]`.
5. Run encoder + actor inference to generate a 16D action.
6. Convert action into target position with `action_scale` and `default_joint_pos`, then publish a 16D wheel-leg command.

This demo is suitable for validating Y20W wheel-leg locomotion policies such as walking, velocity tracking, or wheel-leg motion control.

## Rule Demo: `wave_algorithm/`

`wave_algorithm` is an explicit 16D rule-control demo for Y20W. Its configuration uses `policy.type: "none"` and does not load ONNX or PyTorch policy models.

Main flow:

1. Override `_load_policy()` to skip policy loading.
2. Generate sinusoidal actions in `_run_inference()` according to runtime.
3. Keep hip and wheel at 0 offset for each leg; offset thigh/calf joints with sine waves.
4. Generate 16D target positions, velocities, torques, Kp, and Kd in `process_action()`.
5. Publish development-mode control commands through `LCMInterface` to create periodic body motion.

This demo is useful for validating the development-mode communication path, 16D wheel-leg command format, PD parameters, and simple periodic control logic.

## Running

Start MuJoCo and LCM monitoring first:

```bash
bash scripts/start_mujoco.sh --config config_sim.yaml
```

```bash
bash scripts/monitor_lcm.sh --no-gui
```

After `Y20W_development_state` is updating continuously, start an algorithm.

From the project root:

```bash
python3 external_algorithms/walk_algorithm/run_algorithm.py --config external_algorithms/walk_algorithm/config.yaml
```

```bash
python3 external_algorithms/wave_algorithm/run_algorithm.py --config external_algorithms/wave_algorithm/config.yaml
```

Or from the demo directory:

```bash
cd external_algorithms/walk_algorithm
python3 run_algorithm.py --config config.yaml
```

```bash
cd external_algorithms/wave_algorithm
python3 run_algorithm.py --config config.yaml
```

## Configuration Reference

### `policy`

- `type`: policy type. `walk_algorithm` uses `"onnx"`; `wave_algorithm` uses `"none"`.
- `model_path`: actor/main policy model path; `walk_algorithm` uses `HumanActornet.onnx`.
- `encoder_path`: encoder model path; `walk_algorithm` uses `HumanEncodernet.onnx`.
- `read_metadata`: whether to read model parameters from ONNX metadata.
- `warmup_count`: policy warmup count used to detect inference or action issues early.
- `action_threshold`: action-abnormality threshold.

### `model_params`

- `num_actions`: action dimension; current Y20W demos use 16D.
- `num_obs`: observation dimension; current Y20W demos use 57D.
- `default_joint_pos`: default joint position in per-leg `[hip, thigh, calf, wheel]` order.
- `joint_stiffness`: joint Kp; wheel items are usually 0.
- `joint_damping`: joint Kd.
- `action_scale`: policy action scaling; wheel items may use larger velocity/position scaling.
- `dof_pos_scale`, `dof_vel_scale`, `lin_vel_scale`, `ang_vel_scale`, `command_scale`: observation scaling parameters for `walk_algorithm`.

### `lcm`

- `url`: LCM URL; an empty string uses default configuration.
- `state_channel`: subscribed development state channel, currently `Y20W_development_state`.
- `command_channel`: published development command channel, currently `Y20W_development_command`.
- `robot_id`: robot ID, currently `Y20W`; it must match the state-machine configuration.

### `execution`

- `frequency`: policy inference or rule-computation frequency.
- `lcm_send_frequency`: cached LCM command sending frequency.
- `auto_start`: whether to enter local development flow automatically after state is received.
- `auto_end`: whether to exit development mode automatically when the algorithm ends.
- `max_execution_time`: maximum runtime; `0` means unlimited.

### `motion`

Used by `wave_algorithm`:

- `frequency`: sine-wave frequency.
- `amplitude`: thigh/calf sine-wave amplitude.

The current wave implementation directly uses `default_joint_pos + action` and does not apply `model_params.action_scale` again. The calf offset is `-2 * amplitude * sin(phase)`, so its peak is twice the configured amplitude.

### `rl_mode`

- `true`: DRL policy demo.
- `false`: explicit model/rule-control demo.

### `debug`

- `print_config`: print configuration on startup.
- `print_metadata`: print ONNX metadata while loading.

## Extending

### Add a DRL Demo

1. Create an independent algorithm directory, such as `your_drl_algorithm/`.
2. Prepare `config.yaml` with `model_path`, `encoder_path`, LCM channels, execution frequency, and model parameters.
3. In `run_algorithm.py`, inherit from `AlgorithmBase`.
4. Implement `compute_observation(state)` to convert robot state into the policy observation vector.
5. Implement `process_action(state, action)` to convert policy output into a 16D wheel-leg command.
6. If the model has a special input/output structure, override `_run_inference()` or `_load_policy()`.

### Add a Rule Demo

1. Set `policy.type: "none"` in the configuration.
2. Override `_load_policy()` and set `self.model` and `self.encoder` to `None`.
3. Generate 16D actions in `_run_inference()` from time, state, trajectory planning, or a control model.
4. Convert action into a development-mode command in `process_action()`.
5. Set `rl_mode.is_rl_mode` according to state-machine expectations, usually `false`.

## Dependencies

- Python 3.6+
- `numpy`
- `pyyaml`
- Python `lcm` bindings
- `onnxruntime`: required for `walk_algorithm`
- `onnx`: required when reading parameters from ONNX metadata

## Safety Notes

- Confirm `robot_id`, `state_channel`, and `command_channel` exactly match the state-machine configuration.
- Before hardware use, validate action amplitude, joint order, wheel supplement order, and PD parameters in simulation or on a safe stand.
- DRL output must be checked for NaN, Inf, and abnormally large actions before publishing.
- After replacing a policy model, confirm `num_actions`, `num_obs`, `default_joint_pos`, and `action_scale` match training.
- 16D wheel-leg policies must keep per-leg `[hip, thigh, calf, wheel]` order. If reusing another model, map explicitly in observation and command sending.
- Control frequency should match the state-machine control period; set LCM send frequency according to link capability.
- Publish a disable command when leaving development mode to avoid leftover control commands.

## Pre-Deployment Quick Check

Proceed in this order without skipping stages:

1. Offline-check model inputs, outputs, dtype, observation order, and action order.
2. Read `Y20W_development_state` only, without publishing valid joint targets.
3. Run wave in MuJoCo first, then validate the custom algorithm.
4. Test state dropout, inference failure, network interruption, and `Ctrl+C`.
5. Validate low-amplitude, low-gain hardware motion on a reliable stand.
6. Move to low-speed ground testing only after stand tests pass.

Full pass and stop conditions are in [Custom Algorithms and Hardware Integration](../docs/part-5-lcm-dev/6.hardware.md). The example framework does not replace controller safety checks and does not fully implement automatic state-timeout shutdown or per-joint limits.
