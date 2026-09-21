# wave_algorithm

A policy-free body up/down wave example for Y20W DEVELOPMENT mode.

```bash
cd external_algorithms/wave_algorithm
python3 run_algorithm.py --config config.yaml
```

This algorithm directly generates 16D `[hip, thigh, calf, wheel]` joint targets. `thigh` / `calf` create the vertical wave, `wheel` remains 0, and `external_algorithms/lcm_interface.py` splits the command into Y20W's 12D main joint array and 4D supplement fields.
