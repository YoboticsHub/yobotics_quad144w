# wave_algorithm

Y20W DEVELOPMENT 模式下的无策略文件躯干上下波动示例。

```bash
cd external_algorithms/wave_algorithm
python3 run_algorithm.py --config config.yaml
```

本算法直接生成 16 维 `[hip, thigh, calf, wheel]` 关节目标。`thigh` / `calf`
负责上下波动，`wheel` 保持 0，并通过 `external_algorithms/lcm_interface.py`
拆分为 Y20W 的 12 维主关节和 4 维 supplement 字段。
