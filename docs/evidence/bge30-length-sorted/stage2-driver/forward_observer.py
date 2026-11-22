"""Diagnostic-only PyTorch hooks. Never replace model inputs or outputs."""

from contextlib import contextmanager
from time import perf_counter


@contextmanager
def observe_forward(
    model, correlation, emit, *, entered=None, release=None, hold_s=180
):
    if hold_s <= 0 or hold_s > 190:
        raise ValueError("forward barrier needs a finite approved bound")
    if (entered is None) != (release is None):
        raise ValueError("forward barrier requires both events")
    active = {}

    def before(_module, _args, kwargs):
        key = correlation()
        if key in active:
            raise RuntimeError("duplicate in-flight forward")
        if entered is not None:
            entered.set()
            if not release.wait(timeout=hold_s):
                raise TimeoutError("diagnostic forward barrier expired")
        active[key] = perf_counter()
        emit(
            {
                "event": "forward_enter",
                "operation": key,
                "shape": list(kwargs["input_ids"].shape),
            }
        )

    def after(_module, _args, output):
        key = correlation()
        if key not in active:
            return
        emit(
            {
                "event": "forward_exit",
                "operation": key,
                "produced_output": output is not None,
                "forward_wall_s": perf_counter() - active.pop(key),
            }
        )

    first = model.register_forward_pre_hook(before, with_kwargs=True)
    last = model.register_forward_hook(after, always_call=True)
    try:
        yield
    finally:
        first.remove()
        last.remove()
