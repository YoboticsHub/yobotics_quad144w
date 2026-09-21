# Y20W SDK User Guide

## 1. Prerequisites

- The controller has started simulation with `config_sim.yaml` or hardware with `config.yaml`.
- The SDK and controller use the same LCM multicast URL.
- For cross-machine communication, the network allows UDP multicast.

## 2. Build

```bash
cmake -S yobotics_sdk -B yobotics_sdk/build
cmake --build yobotics_sdk/build -j4
```

The repository provides three examples: motion control, state reading, and HTTP service.

## 3. Motion Control

```bash
yobotics_sdk/build/yobot_sport_client
```

Supported modes include `DAMP`, `RECOVERY_STAND`, `STAND_DOWN`, `RL_WALK`, and `DEVELOPMENT`. `Move(vx, vy, vyaw)`, `BodyHeight(h)`, and `Euler(roll, pitch)` are consumed by the controller in the corresponding motion modes.

## 4. State Reading

```bash
yobotics_sdk/build/yobot_robot_state_client
```

The example subscribes to Y20W high-level state, joint state, and joint command. Leg joints are in the 12D main array, and four wheel joints are in `supplement[4]`.

## 5. DEVELOPMENT Channels

- State: `Y20W_development_state`
- Command: `Y20W_development_command`
- Robot ID: `Y20W`

Joint-level algorithms should use the project `external_algorithms/` framework. `SportClient::Development()` only requests entry into development mode.

## 6. Safety

SDK commands may drive a real robot. Validate in MuJoCo first, then test on a stand with conservative speed and posture limits. If anything is abnormal, switch to `DAMP` immediately or use the physical emergency stop.
