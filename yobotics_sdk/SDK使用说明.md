# E15 SDK 使用说明

## 1. 运行前提
- 控制框架必须使用 **LCM 控制方式**，否则 SDK 无法建立通信链路。
- 当前对接框架：`quad48-rl-control-framework-rk3588`

## 2. 通信频道（与 quad48 当前实现对齐）
- 控制下发：`QUAD_ROBOT_CONTROL`（`sport_client_cmd_t`）
- 状态回读：`QUAD_ROBOT_STATE`（`sport_client_state_t`）
- 关节状态：`leg_control_data`（`quad_joint_state_t`）
- 关节命令镜像：`leg_control_command`（`quad_joint_command_t`）
- 开发态命令：`Y15_development_command`
- 开发态状态：`Y15_development_state`

## 3. API 编号（与 rt_lcm.cpp 对齐）
- `1000`：PASSIVE
- `1001`：DAMP
- `1002`：RL_WALK
- `1003`：RL_RUN
- `1005`：DEVELOPMENT
- `1006`：RECOVERY_STAND
- `1007`：STAND_DOWN

## 4. SDK 包内容
- `include/`：头文件
- `lib/libyobotics_sdk.a`：静态库
- `example/E15/E15_sport_client.cpp`：键盘控制示例
- `example/E15/E15_robot_state_client.cpp`：状态读取示例

## 5. 编译与运行
```bash
mkdir -p build && cd build
cmake ..
make -j4
```

可选环境变量：
- `YOBOTICS_LCM_URL`：LCM 地址（例如 `udpm://239.255.76.67:7667?ttl=255`）

示例运行：
```bash
./E15_sport_client
./E15_robot_state_client
```

## 6. 控制字段说明
- `Move(vx, vy, vyaw)`：设置速度指令
- `BodyHeight(h)`：设置机身高度，映射到 `v_des[2]`
- `Euler(roll, pitch)`：设置姿态命令，映射到 `omega_des[0/1]`
- 以上字段仅在 `RL_WALK`、`RL_RUN` 和 `DEVELOPMENT` 模式下由控制框架消费

## 7. 异机部署与控制方式切换
- 当 SDK 与狗端不在同一台电脑时，双方必须配置一致的 LCM 多播 URL，且网络允许 UDP 组播。
- 狗端是否启用 LCM 控制，仍以控制框架本地配置为准。

## 8. Ubuntu 16/20/22/24 兼容说明
- SDK 代码按 `C++11` 约束，适配 Ubuntu 16/20/22/24 的常见编译环境。
- 若你从其他系统拷贝了预编译 `libyobotics_sdk.a`，建议在 Ubuntu 16/20/22/24 本机重新编译该库再链接。

