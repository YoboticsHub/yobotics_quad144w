# Yobotics Y20W SDK

本目录提供 quad144w/Y20W 的 C++11 SDK、运动控制示例、状态读取示例和 HTTP 服务。SDK 通过 LCM 与控制器通信，不直接访问机器人 SPI 设备。

## 通信通道

| 通道 | 用途 |
| --- | --- |
| `QUAD_ROBOT_CONTROL_Y20W` | 高层运动命令 |
| `QUAD_ROBOT_STATE_Y20W` | 高层状态 |
| `Y20W_QUAD_JOINT_STATE` | 12 个腿关节加 4 个轮关节状态 |
| `Y20W_QUAD_JOINT_COMMAND` | 关节命令镜像 |
| `Y20W_development_state` | DEVELOPMENT 状态 |
| `Y20W_development_command` | DEVELOPMENT 命令 |

轮关节保存在各消息的 `*_supplement[4]` 字段中，顺序为 `LF, RF, LR, RR`。

## 编译

```bash
cmake -S yobotics_sdk -B yobotics_sdk/build
cmake --build yobotics_sdk/build -j4
```

生成三个示例：

- `yobotics_sdk/build/yobot_sport_client`
- `yobotics_sdk/build/yobot_robot_state_client`
- `yobotics_sdk/build/yobot_http_server`

静态库输出到 `yobotics_sdk/lib/libyobotics_sdk.a`。

## 运行

```bash
export YOBOTICS_LCM_URL='udpm://239.255.76.67:7667?ttl=255'
yobotics_sdk/build/yobot_robot_state_client
yobotics_sdk/build/yobot_sport_client
```

建议先连接 MuJoCo 仿真，再连接实机。运动示例会持续发送 LCM 接管、模式和速度命令；实机运行前必须准备急停和可靠支架。

## HTTP 服务

```bash
export ROBOT_HTTP_TOKEN='replace-with-a-private-token'
yobotics_sdk/build/yobot_http_server
```

服务默认监听 `192.168.1.100:8080`，可通过 `SERVER_HOST`、`SERVER_PORT`、`ROBOT_HTTP_TOKEN` 和 `YOBOTICS_LCM_URL` 调整。生产环境不要继续使用源码中的默认 Token。

完整流程见项目根目录 MkDocs 说明书的“第四部分 Yobotics SDK”。
