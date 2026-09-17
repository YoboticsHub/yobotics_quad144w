# 外部算法开发 Demo

本目录用于存放通过 LCM 接入机器人开发模式的外部算法 demo。每个算法 demo 独立放在一个子目录中，通常包含 `config.yaml` 和 `run_algorithm.py`，通过 `AlgorithmBase` 和 `LCMInterface` 完成状态接收、策略推理或规则计算、关节命令发布等流程。

当前保留两个 demo：

- **`walk_algorithm/`**：基于 ONNX actor / encoder 双模型的 Y20W 轮足行走策略 demo。
- **`wave_algorithm/`**：不依赖策略模型的 Y20W 轮足正弦波规则控制 demo。

## 目录结构

```text
external_algorithms/
├── README.md
├── algorithm_base.py
├── lcm_interface.py
├── walk_algorithm/
│   ├── config.yaml
│   ├── run_algorithm.py
│   ├── HumanActornet.onnx
│   └── HumanEncodernet.onnx
└── wave_algorithm/
    ├── README.md
    ├── config.yaml
    └── run_algorithm.py
```

## 架构说明

- `algorithm_base.py`：算法基类，负责配置加载、ONNX 模型加载、开发模式生命周期、推理循环、动作预热和高频 LCM 命令发送。
- `lcm_interface.py`：LCM 通信封装，负责订阅 `development_state_t` 状态消息并发布 `development_command_t` 控制命令。
- `walk_algorithm/`：16 维 Y20W DRL locomotion demo，加载 `HumanActornet.onnx` 和 `HumanEncodernet.onnx`。
- `wave_algorithm/`：16 维 Y20W 显式规则控制 demo，根据时间生成正弦波动作，不加载 ONNX 策略。

## Demo 分类总览

| Demo | 目录 | 开发模式 | 核心依赖 | 适用机器人 / LCM 通道 |
| --- | --- | --- | --- | --- |
| 轮足行走策略 demo | `walk_algorithm/` | 基于 DRL | `onnxruntime`, `numpy`, `LCM` | `Y20W`, `Y20W_development_state`, `Y20W_development_command` |
| 躯干波动 demo | `wave_algorithm/` | 基于模型 / 规则 | `numpy`, `LCM` | `Y20W`, `Y20W_development_state`, `Y20W_development_command` |

## 16 维轮足协议

本项目的外部算法使用 16 维动作布局，每条腿 4 个自由度：

```text
LF: hip, thigh, calf, wheel
RF: hip, thigh, calf, wheel
LR: hip, thigh, calf, wheel
RR: hip, thigh, calf, wheel
```

LCM 底层命令仍包含 12 维主关节和 4 维 supplement 轮子通道。`LCMInterface` 会将 16 维输入自动拆分：

- 每条腿前三项 `[hip, thigh, calf]` 进入 12 维主关节数组。
- 每条腿第四项 `wheel` 进入 4 维 supplement 数组。

## 基于 DRL 的开发 demo

### `walk_algorithm/`

`walk_algorithm` 是 Y20W 轮足 ONNX 策略 demo，配置文件中使用：

- `policy.type: "onnx"`
- `policy.model_path: "./HumanActornet.onnx"`
- `policy.encoder_path: "./HumanEncodernet.onnx"`

主要流程：

1. 通过 LCM 订阅 `Y20W_development_state`。
2. 读取机身角速度、姿态四元数、期望速度、12 维主关节状态和 4 维轮子 supplement 状态。
3. 将主关节和轮子状态拼成 16 维腿块布局。
4. 按 `[angVel, projected_gravity, command, dofPos, dofVel, action_buffer]` 构造 57 维观测。
5. 通过 encoder + actor 推理生成 16 维动作。
6. 使用 `action_scale` 和 `default_joint_pos` 将动作转换为目标位置，并发布 16 维轮足命令。

该 demo 适合验证 Y20W 轮腿协同 locomotion 策略，例如行走、速度跟踪或轮足运动控制。

## 基于模型的开发 demo

### `wave_algorithm/`

`wave_algorithm` 是 Y20W 16 维显式规则控制 demo，配置文件中使用 `policy.type: "none"`，不会加载 ONNX 或 PyTorch 策略模型。

主要流程：

1. 覆盖 `_load_policy()`，跳过策略模型加载。
2. 在 `_run_inference()` 中根据运行时间生成正弦波动作。
3. 每条腿保持 hip 和 wheel 为 0 偏移，thigh / calf 关节按正弦波偏移。
4. 在 `process_action()` 中生成 16 维目标位置、速度、力矩、Kp 和 Kd。
5. 通过 `LCMInterface` 发布开发模式控制命令，使机器人躯干产生周期波动。

该 demo 适合验证开发模式通信链路、16 维轮足命令格式、PD 参数和简单周期运动控制逻辑。

## 运行方式

在工程根目录下运行：

```bash
python3 external_algorithms/walk_algorithm/run_algorithm.py --config external_algorithms/walk_algorithm/config.yaml
```

```bash
python3 external_algorithms/wave_algorithm/run_algorithm.py --config external_algorithms/wave_algorithm/config.yaml
```

也可以进入对应 demo 目录后运行：

```bash
cd external_algorithms/walk_algorithm
python3 run_algorithm.py --config config.yaml
```

```bash
cd external_algorithms/wave_algorithm
python3 run_algorithm.py --config config.yaml
```

## 配置说明

### `policy`

策略配置：

- `type`：策略类型。`walk_algorithm` 使用 `"onnx"`；`wave_algorithm` 使用 `"none"`。
- `model_path`：actor / 主策略模型路径，`walk_algorithm` 使用 `HumanActornet.onnx`。
- `encoder_path`：encoder 模型路径，`walk_algorithm` 使用 `HumanEncodernet.onnx`。
- `read_metadata`：是否从 ONNX metadata 中读取模型参数。
- `warmup_count`：策略预热次数，用于提前发现模型推理或动作异常。
- `action_threshold`：动作异常检测阈值。

### `model_params`

模型和控制参数：

- `num_actions`：动作维度，当前 Y20W demo 使用 16 维。
- `num_obs`：观测维度，当前 Y20W demo 使用 57 维。
- `default_joint_pos`：默认关节位置，按每条腿 `[hip, thigh, calf, wheel]` 排列。
- `joint_stiffness`：关节 Kp，轮子项通常为 0。
- `joint_damping`：关节 Kd。
- `action_scale`：策略动作缩放系数，轮子项可使用更大的速度 / 位移缩放。
- `dof_pos_scale`、`dof_vel_scale`、`lin_vel_scale`、`ang_vel_scale`、`command_scale`：`walk_algorithm` 的观测缩放参数。

### `lcm`

LCM 通信配置：

- `url`：LCM URL，空字符串表示使用默认配置。
- `state_channel`：订阅的开发模式状态通道，当前为 `Y20W_development_state`。
- `command_channel`：发布的开发模式命令通道，当前为 `Y20W_development_command`。
- `robot_id`：机器人 ID，当前为 `Y20W`，必须与状态机配置一致。

### `execution`

执行配置：

- `frequency`：策略推理或规则计算频率。
- `lcm_send_frequency`：LCM 缓存命令发送频率。
- `auto_start`：收到状态消息后是否自动进入开发模式。
- `auto_end`：算法结束后是否自动退出开发模式。
- `max_execution_time`：最大执行时间，`0` 表示不限制。

### `motion`

`wave_algorithm` 的运动配置：

- `frequency`：正弦波频率。
- `amplitude`：thigh / calf 正弦波幅值。

### `rl_mode`

强化学习模式开关：

- `true`：用于 DRL 策略 demo。
- `false`：用于显式模型 / 规则控制 demo。

### `debug`

调试输出配置：

- `print_config`：启动时打印配置文件。
- `print_metadata`：加载 ONNX 时打印 metadata。

## 开发扩展

### 新增基于 DRL 的 demo

1. 新建独立算法目录，例如 `your_drl_algorithm/`。
2. 准备 `config.yaml`，配置 `model_path`、`encoder_path`、LCM 通道、执行频率和模型参数。
3. 在 `run_algorithm.py` 中继承 `AlgorithmBase`。
4. 实现 `compute_observation(state)`，将机器人状态转换为策略需要的观测向量。
5. 实现 `process_action(state, action)`，将策略输出转换为 16 维轮足命令。
6. 如果模型有特殊输入输出结构，可覆盖 `_run_inference()` 或 `_load_policy()`。

### 新增基于模型的 demo

1. 在配置中设置 `policy.type: "none"`。
2. 覆盖 `_load_policy()`，将 `self.model` 和 `self.encoder` 设置为 `None`。
3. 在 `_run_inference()` 中根据时间、状态、轨迹规划或控制模型生成 16 维动作。
4. 在 `process_action()` 中把动作转换为开发模式命令。
5. 将 `rl_mode.is_rl_mode` 设置为符合状态机预期的模式，通常为 `false`。

## 依赖要求

- Python 3.6+
- `numpy`
- `pyyaml`
- `lcm` Python bindings
- `onnxruntime`：运行 `walk_algorithm` 时需要
- `onnx`：从 ONNX metadata 读取参数时需要

## 安全注意事项

- 确认 `robot_id`、`state_channel` 和 `command_channel` 与状态机配置完全一致。
- 上机器人前先在仿真或安全支架环境中验证动作幅值、关节顺序、轮子 supplement 顺序和 PD 参数。
- DRL 模型输出必须检查 NaN、Inf 和异常大动作，避免直接发布危险命令。
- 替换策略模型后，确认 `num_actions`、`num_obs`、`default_joint_pos`、`action_scale` 与训练配置一致。
- 16 维轮足策略必须保持每条腿 `[hip, thigh, calf, wheel]` 的顺序；如需复用其他模型，必须在观测和命令发送处显式映射。
- 控制频率建议与状态机控制周期保持一致；LCM 发送频率按实际链路能力设置。
- 开发模式结束时应发布禁用命令，避免控制命令残留。
