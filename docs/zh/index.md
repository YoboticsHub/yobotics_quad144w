# quad144w/Y20W 轮足机器人控制框架使用说明书

本文档面向 `yobotics_quad144w` 二次开发包，说明如何配置环境、运行 MuJoCo 仿真、启动真实机器人、使用 Yobotics SDK、接入外部算法以及启动 WebRTC 服务。

| 项目 | 内容 |
| --- | --- |
| 文档版本 | 1.0 |
| 适用软件 | yobotics_quad144w 二次开发包 |
| 适用机型 | quad144w / Y20W，16 自由度轮足机器人 |
| 支持平台 | x86_64；RK3588/aarch64 |
| 控制协议 | 12 个腿关节加 4 个轮关节 |

## 推荐阅读路径

| 用户 | 阅读顺序 | 完成目标 |
| --- | --- | --- |
| 首次使用人员 | 第一部分 -> 第二部分 | 配好环境并跑通 MuJoCo |
| 现场部署人员 | 第一部分 -> 第二部分 -> 第三部分 | 完成实机配置、启动和检查 |
| SDK 集成人员 | 第一部分 -> 第四部分 | 下发模式/速度命令并读取状态 |
| 算法开发人员 | 第二部分 -> 第五部分 -> 第三部分 | 在仿真验证 16 维算法后上实机 |
| 远程控制开发人员 | 第一部分 -> 第四部分 -> 第六部分 | 接通视频、DataChannel 和 LCM |

## 系统全景

```text
                    高层控制输入
        手柄 -------- SDK -------- WebRTC
          \            |             /
           +---- QUAD_ROBOT_CONTROL_Y20W
                         |
                         v
              +--------------------+
              | Y20W 控制器状态机   |
              | 模式 / 策略 / 安全  |
              +--------------------+
                 |              ^
      关节命令   |              | DEVELOPMENT 命令
                 v              |
          MuJoCo / 实机       外部算法
                 |
          12 腿关节 + 4 wheel
```

控制器是所有运行路径的中心。SDK 和 WebRTC 发送高层运动意图，外部算法通过 DEVELOPMENT 提交关节级目标，MuJoCo 或实机硬件层执行控制器最终输出。

## 使用原则

!!! danger "实机安全"
    新模型、新参数和外部算法必须先在 MuJoCo 中验证。首次实机运行应架空轮足或使用可靠支架，并安排人员随时操作急停。

- 仿真使用 `config_sim.yaml`，实机使用 `config.yaml`，不要混用。
- 轮足顺序始终按 `LF, RF, LR, RR`，每条腿为 `[hip, thigh, calf, wheel]`。
- 修改模型时同时核对观测维度、动作维度、默认关节位置、缩放和 PD 参数。
- LCM 跨机器通信时，发送端和接收端必须使用同一多播 URL 和可达网卡。

## 常用命令

```bash
# 准备 Python、MuJoCo 和 LCM 环境
bash scripts/setup_conda_env.sh

# 启动仿真
bash scripts/start_mujoco.sh --config config_sim.yaml

# 启动实机控制器
sudo bash scripts/run_robot_controller.sh --config config.yaml

# 监控 LCM
bash scripts/monitor_lcm.sh --no-gui

# 实机状态可视化
bash scripts/start_hardware_viewer.sh
```

## 首次验收顺序

1. 安装环境并验证 Python、LCM 和 MuJoCo。
2. 启动 MuJoCo，确认模型、关节状态和 IMU 通道连续。
3. 从 `DAMP` 开始验证站立和低速模式。
4. 使用 SDK 状态示例确认上层通信。
5. 算法开发先运行 wave，再运行 ONNX walk。
6. 所有异常退出路径在仿真通过后，才进入支架实机测试。

每一阶段都应留下可重复的命令、配置文件和成功标志。出现异常时回到最近一个已通过的阶段，不同时修改模型、增益、通道和机械配置。

## 机器人操作视频
以Y20W型号四足机器人为例：

![type:video](videos/Y20W.mp4)

