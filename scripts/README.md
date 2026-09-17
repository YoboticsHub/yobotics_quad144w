# quad144w 二次开发包脚本说明

本目录是 `yobotics_quad144w` 开发包中的 `scripts/` 目录说明。这里的脚本用于启动 quad144w/Y20W 控制器、启动 MuJoCo 仿真、配置 LCM 网络、监控 LCM 消息、准备 Python 环境、查看实机姿态和分析 CSV 日志。

## 使用前准备

建议在开发包根目录执行命令：

```bash
cd yobotics_quad144w
chmod +x scripts/*.sh
```

如果使用仿真或 Python 工具，先准备环境：

```bash
bash scripts/setup_conda_env.sh
```

如果只需要修复 Python LCM 绑定：

```bash
bash scripts/install_python_lcm.sh
```

开发包常见目录如下：

```text
yobotics_quad144w/
├── bin/                  # 控制器入口脚本 ybt_ctrl 与真实二进制 ybt_ctrl.bin
├── bin_rk3588/           # RK3588/aarch64 控制器入口
├── lib/                  # 运行所需动态库
├── lib_rk3588/           # RK3588/aarch64 运行所需动态库
├── log/                  # 运行日志目录
├── lcm-types/            # LCM 类型定义和生成结果
├── mujoco_sim/           # MuJoCo 仿真代码
├── resources/            # 实机机器人资源
├── resources_sim/        # 仿真机器人资源
├── scripts/              # 本说明文档描述的脚本
├── config.yaml           # 实机配置
└── config_sim.yaml       # 仿真配置
```

## 推荐工作流

```bash
# 1. 配置 Python/LCM 环境
bash scripts/setup_conda_env.sh

# 2. 启动仿真
bash scripts/start_mujoco.sh --config config_sim.yaml

# 3. 监控 LCM
bash scripts/monitor_lcm.sh --no-gui

# 4. 实机启动
sudo bash scripts/run_robot_controller.sh --config config.yaml --iface eth0
```

## 运行控制器

### `run_robot_controller.sh`

用于启动实物控制器，并自动设置当前架构对应的动态库路径。

```bash
sudo bash scripts/run_robot_controller.sh --config config.yaml
```

默认 LCM 网卡为 `eth0`。如现场机器使用其他网卡：

```bash
sudo bash scripts/run_robot_controller.sh --config config.yaml --iface <网卡名>
```

也可以通过环境变量指定：

```bash
LCM_IFACE=<网卡名> sudo -E bash scripts/run_robot_controller.sh --config config.yaml
```

该脚本会按当前系统架构选择控制器入口和动态库：

- x86_64：优先使用 `bin/ybt_ctrl` 和 `lib/`。
- RK3588/aarch64：优先使用 `bin_rk3588/ybt_ctrl` 和 `lib_rk3588/`，不存在时回退到 `bin/ybt_ctrl` 和 `lib/`。

直接运行 `ybt_ctrl.bin` 时不会自动设置完整库路径，优先使用该脚本或对应目录下的 `ybt_ctrl` 包装入口。

### `run_controller.sh`

保留原项目开发环境启动入口，主要面向源码树中的 `build/` 或 `build_lib/` 结构。独立开发包中优先使用 `run_robot_controller.sh`。

### `run_human_debug.sh`

保留的旧版调试入口，用于兼容已有调试流程。新开发包实机启动优先使用 `run_robot_controller.sh`。

## MuJoCo 仿真

### `start_mujoco.sh`

用于启动 MuJoCo 仿真器并启动控制器：

```bash
bash scripts/start_mujoco.sh --config config_sim.yaml
bash scripts/start_mujoco.sh --config config_sim.yaml --headless
```

仿真依赖 `config_sim.yaml`、`resources_sim/`、`mujoco_sim/`、`actor_model/` 和 `lcm-types/`。

如果提示找不到控制器，先确认开发包内存在 `bin/ybt_ctrl`，或源码环境中已经编译出 `build/user/YBT_Controller/ybt_ctrl`。

### `start_hardware_viewer.sh` / `hardware_mujoco_viewer.py`

用于把实物机器人发布的 LCM 反馈实时显示到 MuJoCo Viewer 中，只刷新模型姿态，不推进完整仿真闭环。

```bash
bash scripts/start_hardware_viewer.sh
bash scripts/start_hardware_viewer.sh --xml resources/robots/quad144w/scene_terrain.xml
bash scripts/start_hardware_viewer.sh --lcm-url "udpm://239.255.76.67:7667?ttl=255"
bash scripts/start_hardware_viewer.sh --viewer-hz 30
```

默认参数：

- XML：`resources/robots/quad144w/scene_terrain.xml`
- 关节状态通道：`Y20W_QUAD_JOINT_STATE`
- 机器人状态通道：`QUAD_ROBOT_STATE_Y20W`
- Viewer 刷新率：`60 Hz`

如果 Viewer 中模型没有动作，先确认控制器正在发布以上通道，并检查 LCM URL 和网卡配置。

## LCM 工具

### `setup_lcm_network.sh`

配置 LCM 多播网络：

```bash
sudo bash scripts/setup_lcm_network.sh
```

该脚本会修改网络配置，远程调试时请先确认目标网卡，避免影响 SSH 连接。

### `monitor_lcm.sh` / `monitor_lcm.py`

查看 LCM 通道和消息频率：

```bash
bash scripts/monitor_lcm.sh --no-gui
python3 scripts/monitor_lcm.py --no-gui
```

如果 GUI 环境可用，也可以不带 `--no-gui` 运行。没有消息时优先检查 `setup_lcm_network.sh`、控制器进程、仿真进程和通道配置是否一致。

### `launch_lcm_spy.sh`

启动系统中的 `lcm-spy`：

```bash
bash scripts/launch_lcm_spy.sh
```

需要系统已安装 LCM 工具链。

### `generate_lcm_types.sh`

当修改 `.lcm` 文件或生成代码缺失时重新生成类型：

```bash
bash scripts/generate_lcm_types.sh
```

### `make_types_no_java.sh`

生成不包含 Java 输出的 LCM 类型，适用于只需要 C++/Python 类型的开发场景：

```bash
bash scripts/make_types_no_java.sh
```

## 环境和辅助工具

### `setup_conda_env.sh`

创建或配置仿真、LCM 监控和 Python 工具所需环境：

```bash
bash scripts/setup_conda_env.sh
```

### `install_python_lcm.sh`

安装或修复 Python LCM 绑定：

```bash
bash scripts/install_python_lcm.sh
```

### `remove_conda_env.sh`

移除脚本创建的 conda 环境：

```bash
bash scripts/remove_conda_env.sh
```

### `calibrate_gamepad.py`

校准游戏手柄输入：

```bash
python3 scripts/calibrate_gamepad.py
```

### `data_viewer.py`

查看 RL 日志 CSV，支持按腿、关节、变量类型分组，也支持 quad144w 的 `hip/thigh/calf/wheel` 列名。

```bash
python3 scripts/data_viewer.py
python3 scripts/data_viewer.py log/log_RL_walk.csv
```

### `motor_trace_viewer.py`

查看 `motor_trace.csv` 一类电机追踪日志，支持角度、扭矩、IMU 等常用预设。

```bash
python3 scripts/motor_trace_viewer.py
python3 scripts/motor_trace_viewer.py log/motor_trace.csv
```

### `show_network_bandwidth.sh`

查看指定网卡带宽占用：

```bash
bash scripts/show_network_bandwidth.sh
bash scripts/show_network_bandwidth.sh eth0 1
```

## 常见问题

### 控制器提示找不到动态库

确认位于开发包根目录，并优先使用：

```bash
sudo bash scripts/run_robot_controller.sh --config config.yaml
```

同时检查：

```bash
ls -l bin/ybt_ctrl bin/ybt_ctrl.bin
ls -l lib/libonnxruntime.so*
```

### LCM 监控没有消息

建议按顺序检查：

```bash
sudo bash scripts/setup_lcm_network.sh
bash scripts/monitor_lcm.sh --no-gui
```

同时确认控制器或仿真进程已经启动，并且使用同一组 Y20W LCM 通道。

### 图形界面打不开

无头服务器或 SSH 环境可以使用文本模式：

```bash
bash scripts/monitor_lcm.sh --no-gui
bash scripts/start_mujoco.sh --config config_sim.yaml --headless
```
