# quad144w/Y20W 强化学习控制框架开发说明

> quad144w/Y20W 16 维轮足机器人 RL 控制开发包，支持 MuJoCo 仿真、实机控制、LCM 外部算法接入、WebRTC 远程视频/控制服务，以及 Yobotics SDK 示例。

本文档作为二次开发入口，适用于当前 `yobotics_quad144w` 开发包。控制器入口和运行库已按平台放在 `bin/`、`bin_rk3588/`、`lib/` 与 `lib_rk3588/` 中；源码构建环境也可使用 `build/` 或 `build_lib/` 下的控制器产物。

## 能力概览

当前配置和控制器支持的主要模式：

- `DAMP`
- `RECOVERY_STAND`
- `RL_WALK`
- `RL_HIGHSPEED`
- `RL_CLIMB`
- `RL_STAND`
- `DEVELOPMENT`

主要运行方式：

1. MuJoCo 仿真：使用 [config_sim.yaml](./config_sim.yaml) 和 [scripts/start_mujoco.sh](./scripts/start_mujoco.sh)。
2. 实机控制：使用 [config.yaml](./config.yaml) 和 [scripts/run_robot_controller.sh](./scripts/run_robot_controller.sh)。
3. 外部算法：在 `DEVELOPMENT` 模式下通过 `Y20W_development_state` / `Y20W_development_command` 接入。
4. 远程控制/视频：通过 [WebRTC_server](./WebRTC_server/) 发布视频并转发 JSON 控制到 Y20W LCM 通道。

外部算法说明见 [external_algorithms/README.md](./external_algorithms/README.md)，SDK 说明见 [yobotics_sdk/README.md](./yobotics_sdk/README.md)，WebRTC 说明见 [WebRTC_server/README.md](./WebRTC_server/README.md)。

## 快速开始

推荐先跑 MuJoCo 仿真，确认 Python 环境、LCM、模型文件和控制器产物可用，再上实机。

### 1. 环境配置

```bash
bash scripts/setup_conda_env.sh
```

若一键配置失败，可按需手动安装：

```bash
conda create -n quad_controller python=3.8
conda activate quad_controller

sudo apt-get install -y liblcm-dev libeigen3-dev
pip install numpy==1.24.4 mujoco==3.2.3 pyyaml onnxruntime pillow

bash scripts/install_python_lcm.sh
sudo bash scripts/setup_lcm_network.sh
```

### 2. 编译控制器

源码仓库首次运行仿真或实机前，需要先生成控制器：

```bash
mkdir -p build
cd build
cmake ..
make -j4
```

控制器产物通常为：

```bash
build/user/YBT_Controller/ybt_ctrl
```

### 3. 启动仿真

```bash
conda activate quad_controller
bash scripts/start_mujoco.sh --config config_sim.yaml
```

无图形环境可使用：

```bash
bash scripts/start_mujoco.sh --config config_sim.yaml --headless
```

仿真关键配置：

- `config_sim.yaml` 中 `simulation.enable_mujoco: true`
- `simulation.mujoco.xml_path: resources_sim/robots/quad144w/scene_terrain.xml`
- `safety_checker.urdf_path: resources_sim/robots/quad144w/urdf/sduog144_V2_s.urdf`
- `motor_communication.type: "lcm"`

按 `Ctrl+C` 可停止 MuJoCo 和控制器进程。

## 实机运行

实机运行前请先完成一次仿真验证，并确认机器人急停、供电、IMU、电机通信、遥控器和支架/安全环境都处于可控状态。

### 1. 配置确认

实机默认配置为 [config.yaml](./config.yaml)。运行前重点确认：

- `simulation.enable_mujoco: false`
- `motor_communication.type: "spi"`
- `gamepad.device_type: "hybrid"`
- `development.robot_id: "Y20W"`
- `development.state_channel: "Y20W_development_state"`
- `development.command_channel: "Y20W_development_command"`
- `gamepad.lcm_control_channel: "QUAD_ROBOT_CONTROL_Y20W"`
- `gamepad.lcm_state_channel: "QUAD_ROBOT_STATE_Y20W"`
- `resources/robots/quad144w/` 下 URDF/XML/mesh 文件完整
- `actor_model/` 下 ONNX 模型路径与 `config.yaml` 中各 RL 策略块一致

### 2. 启动控制器

在项目根目录运行：

```bash
sudo bash scripts/run_robot_controller.sh --config config.yaml
```

脚本默认使用 `eth0` 作为 LCM 网卡参数。若现场网卡不同，使用：

```bash
sudo bash scripts/run_robot_controller.sh --config config.yaml --iface <网卡名>
```

或通过环境变量指定：

```bash
LCM_IFACE=<网卡名> sudo -E bash scripts/run_robot_controller.sh --config config.yaml
```

脚本会自动设置 `LD_LIBRARY_PATH`：

- x86_64：优先使用包内 `bin/ybt_ctrl` 和 `lib/`。
- RK3588/aarch64：可使用包内 `bin_rk3588/ybt_ctrl` 和 `lib_rk3588/`；如果现场包只保留目标架构，也可使用 `bin/ybt_ctrl` 和 `lib/`。
- 源码/开发环境：没有包内入口时，使用 `build/` 或 `build_lib/` 下的控制器和库。

### 3. 可选：启动 WebRTC 服务

如需视频和远程控制，先确认 [WebRTC_server/config.json](./WebRTC_server/config.json) 中通道与 `config.yaml` 一致：

- `lcm.control_channel: "QUAD_ROBOT_CONTROL_Y20W"`
- `lcm.state_channel: "QUAD_ROBOT_STATE_Y20W"`

启动服务：

```bash
python3 WebRTC_server/control_publisher.py
```

远端客户端连接机器人 IP 的信令地址：

```text
ws://<robot_ip>:8765
```

### 4. 运行检查与停止

- 控制器日志默认写入 `log/robot_log.txt`。
- 检查 LCM 通道和消息频率：`bash scripts/monitor_lcm.sh --no-gui`。
- 图形化查看 LCM：`bash scripts/launch_lcm_spy.sh`。
- 实机状态 MuJoCo 可视化：`bash scripts/start_hardware_viewer.sh`。
- 查看 RL/电机 CSV 日志：`python3 scripts/data_viewer.py` 或 `python3 scripts/motor_trace_viewer.py log/motor_trace.csv`。
- 如果收不到状态，优先检查 LCM 网卡、SPI/IMU/电机连接、`config.yaml` 通道和权限。
- 前台运行时按 `Ctrl+C` 停止控制器；WebRTC 使用 `control_publisher.py` 时可输入 `e` 停止子进程并退出。

## 运行入口与目录

- `config.yaml`：实机默认配置。
- `config_sim.yaml`：MuJoCo 仿真默认配置。
- `actor_model/`：`RL_WALK`、`RL_HIGHSPEED`、`RL_CLIMB`、`RL_STAND` 使用的 ONNX 策略模型。
- `resources/`：实机配置使用的 quad144w 机器人资源。
- `resources_sim/`：仿真配置使用的 quad144w 机器人资源。
- `mujoco_sim/`：MuJoCo 仿真 Python 模块。
- `scripts/`：环境配置、控制器启动、LCM 监控、网络配置、硬件 Viewer、日志查看等工具脚本。
- `external_algorithms/`：`DEVELOPMENT` 模式外部算法接入框架。
- `WebRTC_server/`：WebRTC 视频与远程控制服务。
- `yobotics_sdk/`：客户侧 SDK、HTTP 控制服务和示例程序。
- `lcm-types/`：LCM 协议定义及 Python/C++/Java 生成代码。
- `build/`：源码构建目录，包含控制器二进制和构建产物。
- `bin/`、`lib/`：x86_64 控制器入口和运行库目录。
- `bin_rk3588/`、`lib_rk3588/`：RK3588/aarch64 控制器入口和运行库目录。

## 各模式说明

| 模式 | 描述 |
| --- | --- |
| `DAMP` | 阻尼/保护模式，常用于停止运动或安全切换。 |
| `RECOVERY_STAND` | 自动恢复到站立姿态。 |
| `RL_WALK` | 常规 RL 行走策略，支持速度命令。 |
| `RL_HIGHSPEED` | 高速 RL 策略，配置块为 `rl_highspeed`。 |
| `RL_CLIMB` | 攀爬/越障相关 RL 策略，配置块为 `rl_climb`。 |
| `RL_STAND` | 站立姿态策略，配置块为 `rl_stand`。 |
| `DEVELOPMENT` | 外部算法开发模式，通过 LCM 接收外部关节命令。 |

`config.yaml` 与 `config_sim.yaml` 的 `gamepad.mode_sequence` 决定遥控器/上位机可切换的模式顺序。

## 配置文件说明

关键配置集中在 `config.yaml` / `config_sim.yaml`：

- `simulation.enable_mujoco`：仿真/硬件模式切换。
- `simulation.mujoco.xml_path`：MuJoCo 场景 XML。
- `motor_communication.type`：通信方式，仿真使用 `lcm`，实机使用 `spi`。
- `motor_communication.board`：SPI 板端协议，填写 `rk3588`（默认）或 `upboard`，且区分大小写。两种板型都使用 Linux SPI `bits_per_word=8`，区别在于帧布局、校验、SPI 频率和 ab/ad 零点偏移。
- `rl_walk` / `rl_highspeed` / `rl_climb` / `rl_stand`：各 RL 策略的 actor、encoder、日志和模型参数配置。
- `development`：外部算法开发模式的 robot_id、状态通道、命令通道和退出自检阈值。
- `gamepad.device_type`：控制输入类型，实机默认 `at9s`，仿真默认 `hybrid`。
- `gamepad.lcm_control_channel` / `gamepad.lcm_state_channel`：上位机/WebRTC/SDK 控制与状态通道。
- `safety_checker.urdf_path`：机器人 URDF 路径。
- `safety_checker`：姿态、关节、硬件丢失等安全检查配置。

SPI 板型示例：

```yaml
motor_communication:
  type: "spi"
  board: "upboard"
  spi_device0: "/dev/spidev2.0"
  spi_device1: "/dev/spidev2.1"
```

## DEVELOPMENT 外部算法

外部算法只在 `DEVELOPMENT` 模式下生效，当前保留两个 demo：

```bash
python3 external_algorithms/walk_algorithm/run_algorithm.py --config external_algorithms/walk_algorithm/config.yaml
```

```bash
python3 external_algorithms/wave_algorithm/run_algorithm.py --config external_algorithms/wave_algorithm/config.yaml
```

默认 DEVELOPMENT 通道：

- `robot_id: "Y20W"`
- `state_channel: "Y20W_development_state"`
- `command_channel: "Y20W_development_command"`

更多 16 维轮足动作布局、ONNX actor/encoder 和正弦波规则控制说明见 [external_algorithms/README.md](./external_algorithms/README.md)。

## 开发包校验

当前仓库已包含常用 x86_64 与 RK3588/aarch64 入口和运行库。部署到机器人前可先在目标目录做快速校验：

```bash
file bin/ybt_ctrl.bin
LD_LIBRARY_PATH=$PWD/lib ldd bin/ybt_ctrl.bin
```

如果使用 RK3588/aarch64 目录，将命令中的 `bin/` 和 `lib/` 替换为 `bin_rk3588/` 与 `lib_rk3588/`。如果 `ldd` 中项目内部库（如 `librobot.so`、`libbiomimetics.so`、`libonnxruntime.so.1`）没有 `not found`，说明包内依赖基本完整。

## 开发入口

- [external_algorithms/README.md](./external_algorithms/README.md)：开发模式外部算法接入说明。
- [WebRTC_server/README.md](./WebRTC_server/README.md)：远程视频、DataChannel 控制和 LCM 转发说明。
- [yobotics_sdk/README.md](./yobotics_sdk/README.md)：SDK、HTTP 控制接口和示例程序说明。
- [scripts/README.md](./scripts/README.md)：脚本入口、参数和排查说明。
- `lcm-types/`：查看控制协议和消息字段。
- `user/YBT_Controller/FSM_States/`：控制状态机和各模式实现。

## 常见问题

### 控制器提示找不到动态库

源码环境先检查构建产物：

```bash
ls build/user/YBT_Controller/ybt_ctrl
```

独立开发包中检查：

```bash
ls -l lib/libonnxruntime.so*
LD_LIBRARY_PATH=$PWD/lib ldd bin/ybt_ctrl.bin
```

直接运行真实二进制时需要手动设置 `LD_LIBRARY_PATH`；推荐使用脚本入口启动。

### 仿真启动失败

优先检查：

- `config_sim.yaml` 是否设置 `simulation.enable_mujoco: true`。
- `resources_sim/robots/quad144w/scene_terrain.xml` 是否存在。
- Python 环境是否安装 `mujoco`、`pyyaml`、`numpy`、`onnxruntime`。
- LCM Python 绑定是否可用。
- 控制器是否已编译到 `build/user/YBT_Controller/ybt_ctrl`。

### LCM 收不到消息

先运行：

```bash
sudo bash scripts/setup_lcm_network.sh
bash scripts/monitor_lcm.sh --no-gui
```

如果机器有多网卡，确认 `scripts/setup_lcm_network.sh`、`scripts/run_robot_controller.sh --iface` 和 WebRTC/SDK 进程使用的是同一块网卡与同一组通道。

### WebRTC 控制无响应

- 确认 `WebRTC_server/config.json` 的控制通道为 `QUAD_ROBOT_CONTROL_Y20W`。
- 确认状态通道为 `QUAD_ROBOT_STATE_Y20W`。
- 确认机器人端 `8765` 端口已监听。
- 确认控制器配置的 `gamepad.device_type` 支持 LCM 或混合输入。

## 安全注意事项

- 实机上保持安全检查开启，不建议关闭 `safety_checker`。
- 上机器人前先在支架或安全环境中验证模式切换、速度限幅和急停。
- 替换 ONNX 策略后，确认模型输入输出维度、关节顺序、默认关节位置和动作缩放一致。
- 调试结束时切回 `DAMP` 或停止控制器/WebRTC 服务，避免命令残留。
