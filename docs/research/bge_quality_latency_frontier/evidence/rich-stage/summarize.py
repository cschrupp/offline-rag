import csv
import datetime as dt
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
rows = [json.loads(x) for x in (root/"MEASUREMENTS.log").read_text().splitlines() if x.startswith("{")]
observations = {row["phase"]:row for row in rows if "assembler_total_ms" in row}
scorers = {row["bge_phase"]:row["profile"] for row in rows if "bge_phase" in row}
timestamps = {}
for line in (root/"PHASE_TIMESTAMPS.log").read_text().splitlines():
    stamp, data = line.split(" ",1)
    timestamps[json.loads(data)["phase"]] = dt.datetime.fromisoformat(stamp)
samples = []
for line in (root/"SAMPLES.log").read_text().splitlines()[1:]:
    stamp,*values = line.split()
    samples.append((dt.datetime.fromisoformat(stamp),dict(part.split("=",1) for part in values)))
stages = {
    "Dense + Qwen3":"dense_ms","Lexical":"lexical_ms","RRF":"fusion_ms",
    "Pair construction":"pair_build_ms","BGE scorer":"rerank_infer_ms","Sort":"sort_ms",
    "Expand + pack":"context_expand_ms",
}
summary={}
with (root/"WATERFALL.csv").open("w") as file:
    writer=csv.writer(file, lineterminator="\n")
    writer.writerow(("phase","stage","start_s","end_s"))
    for phase, obs in observations.items():
        measurements = {label:obs[key] for label,key in stages.items()}
        measurements["Rounding / other"] = obs["assembler_total_ms"]-sum(measurements.values())
        assert measurements["Rounding / other"] >= 0
        elapsed=0
        for stage, value in measurements.items():
            writer.writerow((phase,stage,elapsed/1000,(elapsed+value)/1000))
            elapsed+=value
        end=timestamps[phase]
        start=end-dt.timedelta(milliseconds=obs["assembler_total_ms"])
        window=[(stamp,row) for stamp,row in samples if start<=stamp<=end]
        usage=[]
        host=[]
        for (t,a),(u,b) in zip(window,window[1:]):
            usage.append(sum(int(b[k])-int(a[k]) for k in ("user_jiffies","system_jiffies"))/100/(u-t).total_seconds())
            diff=[int(y)-int(x) for x,y in zip(a["host_jiffies"].split(","), b["host_jiffies"].split(","),strict=True)]
            host.append(100*(sum(diff)-sum(diff[3:5]))/sum(diff))
        batches=scorers[phase]["batches"]
        summary[phase]={
            "stage_ms":measurements,"forward_s":sum(b["forward"]["wall_s"] for b in batches),
            "forward_cpu_s":sum(b["forward"]["cpu_s"] for b in batches),
            "bge_load_or_wait_s":scorers[phase]["phases"]["load_or_wait"]["wall_s"],
            "batches":[{k:b[k] for k in ("batch_size","padded_width","lengths","padded_positions","active_positions","padding_fraction")} for b in batches],
            "assembler":obs,"sample_count":len(window),
            "sample_process_peak_cores":max(usage,default=None),"sample_host_peak_busy_pct":max(host,default=None),
            "sample_peak_rss_kib":max((int(r["rss_kib"]) for _,r in window),default=None),
            "sample_min_available_kib":min((int(r["MemAvailable_kib"]) for _,r in window),default=None),
            "sample_swap_free_range_kib":sorted({int(r["SwapFree_kib"]) for _,r in window}),
        }
print(json.dumps(summary,indent=2))
