# Y20W SDK 使用说明

## 1. 前提

- 控制器已使用 `config_sim.yaml` 启动仿真，或使用 `config.yaml` 启动实机。
- SDK 与控制器使用相同的 LCM 多播 URL。
- 跨机器通信时网络允许 UDP 多播。

## 2. 编译

```bash
cmake -S yobotics_sdk -B yobotics_sdk/build
cmake --build yobotics_sdk/build -j4
```

当前仓库提供运动控制、状态读取和 HTTP 服务三个示例。

## 3. 运动控制

```bash
yobotics_sdk/build/yobot_sport_client
```

支持 `DAMP`、`RECOVERY_STAND`、`STAND_DOWN`、`RL_WALK` 和 `DEVELOPMENT`。`Move(vx, vy, vyaw)`、`BodyHeight(h)` 与 `Euler(roll, pitch)` 由控制器在对应运动模式下消费。

## 4. 状态读取

```bash
yobotics_sdk/build/yobot_robot_state_client
```

示例订阅 Y20W 高层状态、关节状态与关节命令。腿关节位于 12 维主数组，四个轮关节位于 `supplement[4]`。

## 5. DEVELOPMENT 通道

- 状态：`Y20W_development_state`
- 命令：`Y20W_development_command`
- 机器人 ID：`Y20W`

逐关节算法建议使用项目的 `external_algorithms/` 框架；`SportClient::Development()` 只负责请求进入开发模式。

## 6. 安全

SDK 命令可能驱动真实机器人。先在 MuJoCo 中验证，再在支架环境以保守速度和姿态范围测试。异常时立即切换 `DAMP` 或使用物理急停。
