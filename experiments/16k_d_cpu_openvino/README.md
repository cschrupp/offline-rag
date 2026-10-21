# Isolated OpenVINO feasibility environment

This directory is an **isolated** uv project for 16K-D CPU-OV-01 dependencies.
It must **not** mutate Seneca production `pyproject.toml` / `uv.lock`.

## Create / sync (when authorized to install deps)

```bash
cd experiments/16k_d_cpu_openvino
uv sync
```

Large OpenVINO export artifacts (`.xml` / `.bin`) stay outside Git under a local
work path (for example `data/16k_d_cpu_ov_work/exports/`).

## Execution

Scientific OpenVINO export/screen/parity/full runs remain **NOT AUTHORIZED**
under `S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-AUTH-001`.
Use the repository harness CLI from the main checkout; it refuses while
`EXECUTION_AUTHORIZED=False`.
