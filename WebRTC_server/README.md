# WebRTC_server User Guide

`WebRTC_server` starts the robot-side WebRTC video/data publishing service. It captures camera video and streams it to a remote client through WebRTC. It also receives JSON control messages through DataChannel, forwards them to the Y20W LCM control channel, and sends robot state from the LCM state channel back to the client.

## Directory Contents

- `control_publisher.py`: recommended entry. Starts `signaling_server.py` and `publisher.py`, monitors `restart.flag`, and restarts automatically.
- `signaling_server.py`: WebSocket signaling server, listening on `0.0.0.0:8765` by default, used to forward WebRTC Offer / Answer / ICE messages.
- `publisher.py`: WebRTC publisher that reads camera frames, establishes the P2P connection, and handles DataChannel plus LCM communication.
- `config.json`: runtime configuration for camera, LCM channels, signaling address, and low-latency bitrate parameters.
- `test.py`: test/debug publisher; normally use `publisher.py` or `control_publisher.py` first.
- `[Yobotics]JSON格式列表.docx`: control/state JSON field reference.

## Prerequisites

### Python Dependencies

Run in the project Conda environment when possible:

```bash
conda activate robot_controller
python -m pip install websockets aiortc opencv-python numpy av
```

For LCM control and state return, also install Python LCM:

```bash
python -m pip install lcm
```

Or use the project script:

```bash
bash scripts/install_python_lcm.sh
```

### LCM Type Files

`publisher.py` imports these files from root `lcm-types/python/`:

- `sport_client_cmd_t.py`
- `sport_client_state_t.py`

If missing, generate them from the project root:

```bash
bash scripts/generate_lcm_types.sh
```

The deployment package should keep `WebRTC_server/` and `lcm-types/` beside `build/`:

```text
robot-software/
├── build/
├── lcm-types/
└── WebRTC_server/
```

## Configuration

Edit `WebRTC_server/config.json`:

```json
{
  "use_camera": true,
  "camera": {
    "device_index": 4,
    "width": 640,
    "height": 360,
    "fps": 15
  },
  "lcm": {
    "url": "udpm://239.255.76.67:7667?ttl=255",
    "control_channel": "QUAD_ROBOT_CONTROL_Y20W",
    "state_channel": "QUAD_ROBOT_STATE_Y20W"
  },
  "signaling": {
    "server": "ws://localhost:8765"
  },
  "webrtc": {
    "low_latency": true,
    "max_fps": 15,
    "min_bitrate_kbps": 300,
    "start_bitrate_kbps": 500,
    "max_bitrate_kbps": 900
  }
}
```

Common fields:

- `use_camera`: whether to enable a real camera; when `false`, a virtual image is used.
- `camera.device_index`: OpenCV camera index, matching `/dev/video*`.
- `camera.width/height/fps`: capture resolution and frame rate.
- `lcm.url`: LCM multicast URL.
- `lcm.control_channel`: LCM channel where DataChannel control JSON is published, currently `QUAD_ROBOT_CONTROL_Y20W`.
- `lcm.state_channel`: LCM channel subscribed for robot state and returned to the client, currently `QUAD_ROBOT_STATE_Y20W`.
- `signaling.server`: WebSocket signaling address used by the publisher.
- `webrtc.*`: low-latency and bitrate-control parameters.

## DataChannel Control JSON

`publisher.py` converts client JSON into `sport_client_cmd_t` and publishes it to `lcm.control_channel`.

Supported fields:

- `mode`: SDK API ID / mode number, converted to `sport_client_cmd_t.api`.
- `v`: 3D velocity array `[vx, vy, vyaw]`.
- `rpy`: posture array `[roll, pitch, yaw]`.
- `h`: body-height array, for example `[0.0]`.

Example:

```json
{
  "mode": 4,
  "v": [0.2, 0.0, 0.0],
  "rpy": [0.0, 0.0, 0.0],
  "h": [0.0]
}
```

Robot state is returned through DataChannel. Main fields include:

- `power`
- `rpy`
- `v`
- `h`
- `state`
- `fault`

## Startup

### Recommended: Unified Entry

From the robot deployment package directory:

```bash
python3 WebRTC_server/control_publisher.py
```

This starts automatically:

- `signaling_server.py`
- `publisher.py`

Current managed mode runs in the foreground and exits with `Ctrl+C`. Older keyboard commands may exist in historical deployments, but the current MkDocs manual documents the managed startup flow.

### Separate Startup for Debugging

Terminal 1, start the signaling server:

```bash
python3 WebRTC_server/signaling_server.py
```

Terminal 2, start the WebRTC publisher:

```bash
python3 WebRTC_server/publisher.py
```

Remote clients should connect to the robot IP at `ws://<robot_ip>:8765` as the signaling address.

## Runtime Checks

### Check Camera

```bash
ls /dev/video*
```

If `camera.device_index` in `config.json` is `4`, it usually maps to `/dev/video4`. Change `device_index` if the camera number differs.

### Check Port

```bash
ss -lntp | grep 8765
```

`0.0.0.0:8765` means the signaling server is listening.

### Check LCM

```bash
bash scripts/monitor_lcm.sh --no-gui
```

If no LCM messages are received, configure multicast first:

```bash
sudo bash scripts/setup_lcm_network.sh
```

## Common Issues

### Camera Cannot Open

- Check whether `/dev/video*` exists.
- Change `camera.device_index` in `config.json`.
- Confirm the current user has camera read permission; use `sudo` temporarily if needed.

### LCM Module Import Fails

- Confirm Python LCM is installed.
- Confirm `lcm-types/python/` exists and contains `sport_client_cmd_t.py` and `sport_client_state_t.py`.
- In the deployment package, confirm `WebRTC_server/` and `lcm-types/` are beside `build/`.

### Client Cannot Connect

- Confirm robot-side port `8765` is listening.
- Confirm the client signaling address uses the robot IP, such as `ws://192.168.1.134:8765`.
- Confirm the robot and client are on the same network or routable.

### Video Latency Is High

- Reduce `camera.width`, `camera.height`, or `camera.fps`.
- Reduce `webrtc.max_bitrate_kbps`.
- Keep `webrtc.low_latency` set to `true`.

### Control Has No Response

- Confirm the LCM URL in `config.json` matches the robot state machine.
- Confirm the control channel is `QUAD_ROBOT_CONTROL_Y20W`.
- Confirm the state channel is `QUAD_ROBOT_STATE_Y20W`.
- Confirm the client sends JSON fields named `mode`, `v`, `rpy`, and `h`.

## Stop Service

Press `Ctrl+C` in the foreground process. When using `control_publisher.py`, wait for publisher and signaling server cleanup before restarting or powering off.
