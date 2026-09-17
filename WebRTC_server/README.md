# WebRTC_server 使用说明

`WebRTC_server` 用于在机器人端启动 WebRTC 视频 / 数据发布服务。它通过摄像头采集视频，经 WebRTC 推送给远端客户端；同时通过 DataChannel 接收 JSON 控制消息，并转发到 Y20W 的 LCM 控制通道，也会把机器人状态从 LCM 状态通道回传给客户端。

## 目录内容

- `control_publisher.py`：推荐入口，负责同时启动 `signaling_server.py` 和 `publisher.py`，并监控 `restart.flag` 后自动重启。
- `signaling_server.py`：WebSocket 信令服务器，默认监听 `0.0.0.0:8765`，用于转发 WebRTC Offer / Answer / ICE 消息。
- `publisher.py`：WebRTC 发布端，读取摄像头画面，建立 P2P 连接，处理 DataChannel 和 LCM 通信。
- `config.json`：运行配置，包括摄像头、LCM 通道、信令地址和低时延码率参数。
- `test.py`：测试 / 调试版本发布端，一般优先使用 `publisher.py` 或 `control_publisher.py`。
- `[Yobotics]JSON格式列表.docx`：控制 / 状态 JSON 字段说明文档。

## 前置条件

### Python 依赖

建议在项目 Conda 环境中运行：

```bash
conda activate robot_controller
python -m pip install websockets aiortc opencv-python numpy av
```

如果需要 LCM 控制与状态回传，还需要：

```bash
python -m pip install lcm
```

或使用项目脚本安装：

```bash
bash scripts/install_python_lcm.sh
```

### LCM 类型文件

`publisher.py` 会从项目根目录的 `lcm-types/python/` 导入：

- `sport_client_cmd_t.py`
- `sport_client_state_t.py`

如果缺失，请先在项目根目录生成：

```bash
bash scripts/generate_lcm_types.sh
```

部署包中应保持如下结构，`WebRTC_server/` 和 `lcm-types/` 与 `build/` 同级：

```text
robot-software/
├── build/
├── lcm-types/
└── WebRTC_server/
```

## 配置说明

编辑 `WebRTC_server/config.json`：

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

常用字段：

- `use_camera`：是否启用真实摄像头；设为 `false` 时使用虚拟画面。
- `camera.device_index`：OpenCV 摄像头编号，对应 `/dev/video*`。
- `camera.width/height/fps`：采集分辨率和帧率。
- `lcm.url`：LCM 多播地址。
- `lcm.control_channel`：DataChannel 收到控制 JSON 后发布到的 LCM 通道，当前为 `QUAD_ROBOT_CONTROL_Y20W`。
- `lcm.state_channel`：订阅机器人状态并回传给客户端的 LCM 通道，当前为 `QUAD_ROBOT_STATE_Y20W`。
- `signaling.server`：发布端连接的 WebSocket 信令地址。
- `webrtc.*`：低时延和码率控制参数。

## DataChannel 控制 JSON

`publisher.py` 会将客户端发来的 JSON 转换为 `sport_client_cmd_t` 并发布到 `lcm.control_channel`。

支持字段：

- `mode`：SDK API ID / 模式编号，转换为 `sport_client_cmd_t.api`。
- `v`：三维速度数组 `[vx, vy, vyaw]`。
- `rpy`：姿态数组 `[roll, pitch, yaw]`。
- `h`：机身高度数组，例如 `[0.0]`。

示例：

```json
{
  "mode": 4,
  "v": [0.2, 0.0, 0.0],
  "rpy": [0.0, 0.0, 0.0],
  "h": [0.0]
}
```

机器人状态会通过 DataChannel 回传，主要字段包括：

- `power`
- `rpy`
- `v`
- `h`
- `state`
- `fault`

## 启动方法

### 推荐方式：统一启动

在机器人部署包目录：

```bash
python3 WebRTC_server/control_publisher.py
```

该方式会自动启动：

- `signaling_server.py`
- `publisher.py`

控制脚本按键：

- `s`：启动 / 重启 publisher
- `q`：停止 publisher
- `e`：退出控制脚本并停止全部子进程

### 分开启动：调试用

终端 1：启动信令服务器。

```bash
python3 WebRTC_server/signaling_server.py
```

终端 2：启动 WebRTC 发布端。

```bash
python3 WebRTC_server/publisher.py
```

远端客户端需要连接到机器人 IP 的 `ws://<robot_ip>:8765` 作为信令地址。

## 运行检查

### 检查摄像头

```bash
ls /dev/video*
```

如果 `config.json` 中 `camera.device_index` 为 `4`，通常对应 `/dev/video4`。摄像头编号不匹配时，修改 `device_index`。

### 检查端口

```bash
ss -lntp | grep 8765
```

能看到 `0.0.0.0:8765` 表示信令服务器已监听。

### 检查 LCM

```bash
bash scripts/monitor_lcm.sh --no-gui
```

如果收不到 LCM 消息，先配置多播网络：

```bash
sudo bash scripts/setup_lcm_network.sh
```

## 常见问题

### 摄像头打不开

- 检查 `/dev/video*` 是否存在。
- 修改 `config.json` 的 `camera.device_index`。
- 确认当前用户有摄像头读取权限，必要时临时使用 `sudo` 运行。

### LCM 模块导入失败

- 确认已安装 Python LCM。
- 确认 `lcm-types/python/` 存在并包含 `sport_client_cmd_t.py`、`sport_client_state_t.py`。
- 在部署包中确认 `WebRTC_server/` 和 `lcm-types/` 与 `build/` 同级。

### 客户端无法连接

- 确认机器人端 `8765` 端口已监听。
- 确认客户端信令地址使用机器人 IP，例如 `ws://192.168.1.134:8765`。
- 确认机器人与客户端在同一网络或路由可达。

### 视频延迟较高

- 降低 `camera.width`、`camera.height` 或 `camera.fps`。
- 降低 `webrtc.max_bitrate_kbps`。
- 保持 `webrtc.low_latency` 为 `true`。

### 控制无响应

- 确认 `config.json` 中的 LCM URL 与机器人状态机侧一致。
- 确认控制通道为 `QUAD_ROBOT_CONTROL_Y20W`。
- 确认状态通道为 `QUAD_ROBOT_STATE_Y20W`。
- 确认客户端发送的 JSON 字段名为 `mode`、`v`、`rpy`、`h`。

## 停止服务

前台运行时按 `Ctrl+C` 停止。若使用 `control_publisher.py`，也可以输入 `e` 停止 publisher 和 signaling server 后退出。
