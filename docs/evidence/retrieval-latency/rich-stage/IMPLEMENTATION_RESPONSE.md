Phase A found that the resolver retrieval hash differed from the original
question hash. The same source/snapshot diagnostic was completed as a
related no-history workload. The runner and probe preserve the two-call
limit, the isolated and network-disabled runtime, model integrity and
snapshot binding, untouched production settings, and restoration on exit.
The analysis reads the existing nested stage metrics once per leaf,
and joins sampled resource data to per-call timestamps. Shell syntax and
Python compilation passed. See REPORT.md for the execution results,
limitations, and ranked performance recommendations.
