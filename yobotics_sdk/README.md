# yobotics_sdk_e15_260408_lib_generate

本工程包含 E15 SDK、示例程序，以及基于 HTTP 的运动控制与导航控制示例服务。

## 目录说明
- `include/`：SDK 头文件
- `lib/libyobotics_sdk.a`：静态库
- `example/http_server.cpp`：E15 HTTP 控制服务示例
- `example/sport_client.cpp`：运动控制示例
- `example/robot_state_client.cpp`：状态订阅示例
- `example/nav_control_subscriber_demo.cpp`：`NAV_CONTROL` 订阅打印示例
- `dist/`：打包输出目录
- `tools/`：构建与部署脚本

## 编译示例
```bash
mkdir -p build && cd build
cmake ..
make -j4
```

默认示例可执行文件名：
- `yobot_sport_client`
- `yobot_robot_state_client`
- `yobot_http_server`
- `yobot_nav_control_demo`
- `yobot_nav_control_subscriber_demo`

### NAV_CONTROL 订阅打印示例
```bash
./yobot_nav_control_subscriber_demo
./yobot_nav_control_subscriber_demo "udpm://239.255.76.67:7667?ttl=255"
```

该示例订阅 `NAV_CONTROL`，收到 `navigationtmp` 后打印 `velocity[0..2]`、`yaw_velocity`、`yaw_cmd` 和 `state`。
同时会把相同字段追加写入当前执行命令所在目录下的 `nav_control_subscriber_demo.log`，便于联调后回看数据。

## 安装 SDK
```bash
mkdir -p build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=/opt/yobotics_sdk_e15_260408
make -j4
sudo make install
```

## 业务程序直接链接静态库
```bash
g++ -std=c++11 your_app.cpp \
  -I./include -I./include/common -I./include/robot -I./include/robot/channel \
  ./lib/libyobotics_sdk.a -llcm -lpthread -o your_app
```

## HTTP 控制服务说明
默认配置：
- 服务地址：`http://192.168.1.100:8080`
- 默认 Token：`Y20W_Robot_Secure_Token_123`
- 请求头：`Authorization: Bearer <token>`

可通过环境变量调整：
- `SERVER_HOST`
- `SERVER_PORT`
- `ROBOT_HTTP_TOKEN`
- `YOBOTICS_LCM_URL`

### 通用请求头
```bash
-H "Authorization: Bearer Y20W_Robot_Secure_Token_123" -H "Content-Type: application/json"
```

PowerShell 示例：
```powershell
$headers = @{
  Authorization = "Bearer Y20W_Robot_Secure_Token_123"
  "Content-Type" = "application/json"
}
```

---

## 运动控制接口

### 1. 查询整体状态
```bash
curl -X GET "http://192.168.1.100:8080/control/status" -H "Authorization: Bearer Y20W_Robot_Secure_Token_123"
```

### 2. 更新运动控制命令
接口：`POST /control/motion`

支持字段：
- `mode`：`passive` / `damp` / `recovery_stand` / `stand_down` / `rl_walk` / `development`
- `vx`
- `vy`
- `vyaw`
- `body_height`
- `roll`
- `pitch`

说明：
- 当 `mode` 不是 `rl_walk` 或 `development` 时，速度和姿态相关量会被自动清零。
- 当前限幅规则：
  - `vx`：`[-1.5, 1.5]`
  - `vy`：`[-1.0, 1.0]`
  - `vyaw`：`[-1.5, 1.5]`
  - `body_height`：`[-0.20, 0.20]`
  - `roll`：`[-0.50, 0.50]`
  - `pitch`：`[-0.50, 0.50]`

### 2.1 切换阻尼模式
```bash
curl -X POST "http://192.168.1.100:8080/control/motion" -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" -H "Content-Type: application/json" -d "{\"mode\":\"damp\"}"
```

### 2.2 恢复站立
```bash
curl -X POST "http://192.168.1.100:8080/control/motion" -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" -H "Content-Type: application/json" -d "{\"mode\":\"recovery_stand\"}"
```

### 2.3 进入 RL 行走并给前进速度
```bash
curl -X POST "http://192.168.1.100:8080/control/motion" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"mode\":\"rl_walk\",\"vx\":0.3,\"vy\":0.0,\"vyaw\":0.0}"
```

### 2.4 RL 行走横移 + 转向
```bash
curl -X POST "http://192.168.1.100:8080/control/motion" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"mode\":\"rl_walk\",\"vx\":0.1,\"vy\":0.2,\"vyaw\":0.3}"
```

### 2.5 调整机身高度与姿态
```bash
curl -X POST "http://192.168.1.100:8080/control/motion" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"mode\":\"development\",\"body_height\":0.05,\"roll\":0.05,\"pitch\":-0.05}"
```

### 2.6 更新部分字段
例如只更新角速度：
```bash
curl -X POST "http://192.168.1.100:8080/control/motion" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"vyaw\":0.4}"
```

说明：该接口会基于当前缓存命令做增量更新。

### 3. 停止运动
接口：`POST /control/stop`

```bash
curl -X POST "http://192.168.1.100:8080/control/stop" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123"
```

### 4. 运动控制错误测试示例

#### 4.1 非法模式
```bash
curl -X POST "http://192.168.1.100:8080/control/motion" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"mode\":\"run_fast\"}"
```

#### 4.2 `mode` 类型错误
```bash
curl -X POST "http://192.168.1.100:8080/control/motion" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"mode\":123}"
```

#### 4.3 Token 错误
```bash
curl -X GET "http://192.168.1.100:8080/control/status" 
  -H "Authorization: Bearer wrong_token"
```

---

## 导航控制接口

### 1. 查询导航状态
```bash
curl -X GET "http://192.168.1.100:8080/control/nav/status" -H "Authorization: Bearer Y20W_Robot_Secure_Token_123"
```

重点字段：
- `data.nav_state.code`
- `data.nav_state.code_desc`
- `data.last_command.expected_response_code`
- `data.last_command.matched_expected_response`
- `data.summary.status`
- `data.summary.goal_reached`

### 2. 导航命令接口
接口：`POST /control/nav`

支持命令：
- `start_mapping`
- `end_mapping`
- `start_cutter`
- `end_cutter`
- `start_localization`
- `end_localization`
- `start_nav`
- `end_nav`
- `start_goal_program`
- `end_goal_program`
- `send_goal`
- `clear_goal`
- `start_all`
- `stop_all`

### 2.1 启动定位
```bash
curl -X POST "http://192.168.1.100:8080/control/nav" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"cmd_type\":\"start_localization\"}"
```

预期状态：
- `nav_state.code = 20265`
- `summary.status = "ack_received"`

### 2.2 结束定位
```bash
curl -X POST "http://192.168.1.100:8080/control/nav" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"cmd_type\":\"end_localization\"}"
```

### 2.3 启动导航
```bash
curl -X POST "http://192.168.1.100:8080/control/nav" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"cmd_type\":\"start_nav\"}"
```

预期状态：
- `nav_state.code = 20267`
- `last_command.matched_expected_response = true`

### 2.4 结束导航
```bash
curl -X POST "http://192.168.1.100:8080/control/nav" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"cmd_type\":\"end_nav\"}"
```

### 2.5 启动目标点程序
```bash
curl -X POST "http://192.168.1.100:8080/control/nav" -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" -H "Content-Type: application/json" -d "{\"cmd_type\":\"start_goal_program\"}"
```

### 2.6 发送目标点
`params` 必须为 8 个空格分隔数字：
`goal_index x y z roll pitch yaw w`

```bash
curl -X POST "http://192.168.1.100:8080/control/nav" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"cmd_type\":\"send_goal\",\"params\":\"1 0.5 0.0 0.0 0.0 0.0 0.0 1.0\"}"
```

预期过程：
- 刚发送后：`summary.status = "waiting_ack"`
- 收到 ACK 后：`summary.status = "ack_received"`
- 到点后：`summary.status = "goal_reached"`

### 2.7 清空目标点
```bash
curl -X POST "http://192.168.1.100:8080/control/nav" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"cmd_type\":\"clear_goal\"}"
```

### 2.8 结束目标点程序
```bash
curl -X POST "http://192.168.1.100:8080/control/nav" -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" -H "Content-Type: application/json" -d "{\"cmd_type\":\"end_goal_program\"}"
```

### 2.9 一键启动全部导航程序
```bash
curl -X POST "http://192.168.1.100:8080/control/nav" -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" -H "Content-Type: application/json" -d "{\"cmd_type\":\"start_all\"}"
```

### 2.10 一键停止全部导航程序
```bash
curl -X POST "http://192.168.1.100:8080/control/nav" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"cmd_type\":\"stop_all\"}"
```

### 3. 导航错误测试示例

#### 3.1 缺少 `cmd_type`
```bash
curl -X POST "http://192.168.1.100:8080/control/nav" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{}"
```

#### 3.2 `send_goal` 缺少 `params`
```bash
curl -X POST "http://192.168.1.100:8080/control/nav" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"cmd_type\":\"send_goal\"}"
```

#### 3.3 `params` 使用逗号
```bash
curl -X POST "http://192.168.1.100:8080/control/nav" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"cmd_type\":\"send_goal\",\"params\":\"1,0,0,0,0,0,0,1\"}"
```

#### 3.4 `params` 数量错误
```bash
curl -X POST "http://192.168.1.100:8080/control/nav" 
  -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" 
  -H "Content-Type: application/json" 
  -d "{\"cmd_type\":\"send_goal\",\"params\":\"1 0 0\"}"
```

---

## 推荐联调顺序

### 运动控制
1. `POST /control/motion` -> `{"mode":"damp"}`
2. `POST /control/motion` -> `{"mode":"recovery_stand"}`
3. `POST /control/motion` -> `{"mode":"rl_walk","vx":0.2}`
4. `GET /control/status`
5. `POST /control/stop`

### 导航控制
1. `start_localization`
2. 查询 `/control/nav/status`
3. `start_nav`
4. `start_goal_program`
5. `send_goal`
6. 轮询 `/control/nav/status`
7. 观察 `summary.status` 是否变为 `goal_reached`

---

## PowerShell 示例

### 查询导航状态
```powershell
Invoke-RestMethod `
  -Uri "http://192.168.1.100:8080/control/nav/status" `
  -Method Get `
  -Headers @{ Authorization = "Bearer Y20W_Robot_Secure_Token_123" }
```

### 发运动命令
```powershell
Invoke-RestMethod `
  -Uri "http://192.168.1.100:8080/control/motion" `
  -Method Post `
  -Headers @{ Authorization = "Bearer Y20W_Robot_Secure_Token_123" } `
  -ContentType "application/json" `
  -Body '{"mode":"rl_walk","vx":0.3,"vy":0.0,"vyaw":0.0}'
```

### 发导航目标点
```powershell
Invoke-RestMethod `
  -Uri "http://192.168.1.100:8080/control/nav" `
  -Method Post `
  -Headers @{ Authorization = "Bearer Y20W_Robot_Secure_Token_123" } `
  -ContentType "application/json" `
  -Body '{"cmd_type":"send_goal","params":"1 0.5 0.0 0.0 0.0 0.0 0.0 1.0"}'
```

---

## LCM / 导航使能联调步骤

> 适用于 `POST /control/nav/enable` -> `NAV_ENABLE_CTRL` -> `RL_WALK` 的联调确认。

### 1. 前置条件确认
1. 控制程序已经运行，并且 `RL_WALK` 已进入导航订阅逻辑。
2. 控制侧日志已打印：`[RL_Walk][NAV] Subscribed to NAV_CONTROL and NAV_ENABLE_CTRL`
3. HTTP 服务已经启动，且能正常访问 `/control/status` 和 `/control/nav/status`
4. HTTP 服务端与控制侧使用同一个 LCM 组播地址，当前默认都是：`udpm://239.255.76.67:7667?ttl=255`
5. 机器人当前可以切换到 `rl_walk`，因为开启导航使能时服务端要求当前模式必须是 `rl_walk`

### 2. 先确认 HTTP 服务正常
```bash
curl -X GET "http://192.168.1.100:8080/control/status" -H "Authorization: Bearer Y20W_Robot_Secure_Token_123"
```

如果这里不通，先不要继续查 LCM。

### 3. 切换到 `rl_walk`
```bash
curl -X POST "http://192.168.1.100:8080/control/motion" -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" -H "Content-Type: application/json" -d "{\"mode\":\"rl_walk\"}"
```

如果不是 `rl_walk`，开启导航使能时会返回类似：

```json
{"code":400,"msg":"nav enable requires rl_walk mode"}
```

### 4. 开启导航使能
```bash
curl -X POST "http://192.168.1.100:8080/control/nav/enable" -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" -H "Content-Type: application/json" -d "{\"nav_enabled\":true}"
```

期望 HTTP 返回：

```json
{"code":0,"msg":"nav enable updated", ...}
```

### 5. 观察控制侧日志
执行第 4 步后，控制侧应看到类似日志：

```text
[RL_Walk][NAV] NAV_ENABLE_CTRL received: 1
```

如果关闭导航使能：

```bash
curl -X POST "http://192.168.1.100:8080/control/nav/enable" -H "Authorization: Bearer Y20W_Robot_Secure_Token_123" -H "Content-Type: application/json" -d "{\"nav_enabled\":false}"
```

控制侧应看到：

```text
[RL_Walk][NAV] NAV_ENABLE_CTRL received: 0
```

### 6. 再发送导航速度源验证是否叠加生效
开启导航使能后，再确认导航侧 `NAV_CONTROL` 有持续输入，并观察 `RL_WALK` 是否开始叠加：
- `nav_lcm_xvel_`
- `nav_lcm_yvel_`
- `nav_control_steering_angle_`

当前逻辑下，只要以下任一条件成立，就会启用导航叠加：
1. 遥控侧 `rcCommand->variable[0] == 1`
2. LCM 下发的 `NAV_ENABLE_CTRL == 1`

### 7. 推荐联调顺序
1. `GET /control/status`
2. `GET /control/nav/status`
3. `POST /control/motion` -> `{"mode":"rl_walk"}`
4. `POST /control/nav/enable` -> `{"nav_enabled":true}`
5. 查看控制侧日志是否打印 `NAV_ENABLE_CTRL received: 1`
6. 发送 `start_nav` / `start_goal_program` / `send_goal`
7. 轮询 `/control/nav/status`
8. 如需关闭导航接管，发送 `{"nav_enabled":false}`

### 8. 常见问题排查

#### 8.1 `curl` 没报错，但控制侧没日志
优先检查：
- HTTP 服务和控制程序是否真的在同一网络环境
- 双方是否使用同一个 LCM URL
- 控制程序是否已经重新编译并重启到最新版本
- 是否真的进入了 `RL_WALK`

#### 8.2 `/control/nav/enable` 返回 400
通常是因为当前不是 `rl_walk` 模式，先执行第 3 步。

#### 8.3 `/control/nav/status` 正常，但导航使能没效果
这通常说明：
- 导航状态链路是通的
- 但 `NAV_ENABLE_CTRL` 这条链路未打通，或者控制侧未真正启用导航叠加

应重点看控制侧是否打印：

```text
[RL_Walk][NAV] NAV_ENABLE_CTRL received: 1
```

#### 8.4 开启后还是没有运动效果
说明“使能开关”已通，但还要继续确认：
- `NAV_CONTROL` 是否真的在持续发速度/转向命令
- 机器人当前姿态与状态机是否允许输出
- 自检是否触发了 `setAllMotorsToZero()`
