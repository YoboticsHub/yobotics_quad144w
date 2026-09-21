# Yobotics Y20W SDK

This directory provides the C++11 SDK, motion-control example, state-reading example, and HTTP service for quad144w/Y20W. The SDK communicates with the controller through LCM and does not access robot SPI devices directly.

## Communication Channels

| Channel | Purpose |
| --- | --- |
| `QUAD_ROBOT_CONTROL_Y20W` | High-level motion command |
| `QUAD_ROBOT_STATE_Y20W` | High-level state |
| `Y20W_QUAD_JOINT_STATE` | 12 leg joints plus 4 wheel joints state |
| `Y20W_QUAD_JOINT_COMMAND` | Joint command mirror |
| `Y20W_development_state` | DEVELOPMENT state |
| `Y20W_development_command` | DEVELOPMENT command |

Wheel joints are stored in each message's `*_supplement[4]` field in `LF, RF, LR, RR` order.

## Build

```bash
cmake -S yobotics_sdk -B yobotics_sdk/build
cmake --build yobotics_sdk/build -j4
```

Generated examples:

- `yobotics_sdk/build/yobot_sport_client`
- `yobotics_sdk/build/yobot_robot_state_client`
- `yobotics_sdk/build/yobot_http_server`

The static library is written to `yobotics_sdk/lib/libyobotics_sdk.a`.

## Run

```bash
export YOBOTICS_LCM_URL='udpm://239.255.76.67:7667?ttl=255'
yobotics_sdk/build/yobot_robot_state_client
yobotics_sdk/build/yobot_sport_client
```

Connect to MuJoCo simulation before hardware. The motion example continuously sends LCM takeover, mode, and velocity commands. Before hardware operation, prepare emergency stop and a reliable stand.

## HTTP Service

```bash
export ROBOT_HTTP_TOKEN='replace-with-a-private-token'
yobotics_sdk/build/yobot_http_server
```

The service listens on `192.168.1.100:8080` by default. Adjust with `SERVER_HOST`, `SERVER_PORT`, `ROBOT_HTTP_TOKEN`, and `YOBOTICS_LCM_URL`. Do not use the source-code default token in production.

See Part 4, "Yobotics SDK", in the root MkDocs manual for the complete flow.
