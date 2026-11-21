set -euo pipefail
umask 077
container=seneca-review
revision=9c92e706c4b9e9d9ac0816a655bdf131cc63fca1
deadline=$1
check_time() {
    local current
    current=$(date +%s)
    (( deadline - current > 3000 )) || { echo "STOP deadline has insufficient margin"; return 1; }
}
check_time
prefix=$(mktemp -d /var/tmp/seneca-one-shot.XXXXXXXX)
testname="seneca-measure-${prefix##*.}"
stopping=0
verified=0
signature() {
    docker inspect --format '{{.Id}} {{.Image}} {{.HostConfig.RestartPolicy.Name}} {{.Config.User}} {{range .Mounts}}{{println .Source .Destination .RW}}{{end}}' "$container"
}
healthy() {
    for p in live ready; do
        [[ $(curl -sS --max-time 4 -o /dev/null -w "%{http_code}" "http://127.0.0.1/health/$p" 2>/dev/null) == 200 ]] || return 1
    done
}
probe() {
    timeout 180 docker exec -i "$container" python -B - inspect < "$prefix/probe.py"
}
cleanup() {
    rc=$?
    trap - EXIT
    trap '' HUP INT TERM
    set +e
    if (( stopping )); then
        if docker container inspect "$testname" >/dev/null 2>&1; then
            docker rm -f "$testname" >/dev/null || { echo "RESTORATION BLOCKED: isolated container still present"; exit 1; }
        fi
        docker start "$container" >/dev/null || { echo "RESTORATION FAILED: original start"; exit 1; }
        for ((i=0;i<120;i++)); do
            if healthy; then break; fi
            sleep 5
        done
        if healthy && [[ $(signature) == "$before_signature" ]] &&
           probe > "$prefix/after.json" && cmp -s "$prefix/before.json" "$prefix/after.json"; then
            verified=1
            echo "RESTORATION PASS: live=200 ready=200 original image/mounts/restart policy, workspace revision, snapshot and inventory match"
        else
            echo "RESTORATION NOT VERIFIED; temporary evidence retained at $prefix"
            exit 1
        fi
    fi
    if (( !stopping || verified )); then
        sudo -n rm -rf -- "$prefix"
    fi
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
cat > "$prefix/probe.py"
chmod 644 "$prefix/probe.py"
cat > "$prefix/cross_encoder.py" <<'PY_MODULE'
"""Local CrossEncoderReranker with raw logits and passage-only truncation."""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from contextlib import contextmanager, nullcontext
from pathlib import Path
from threading import Lock

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    RAW_LOGIT_SCORE_CONTRACT,
    SEQ_TRUNC_1024_PASSAGE_RIGHT,
)
from offline_rag.rerank.protocol import RerankerPair
from offline_rag.rerank.provision import (
    require_reranker_artifacts,
    resolve_reranker_model_dir,
)


class CrossEncoderRerankerError(RuntimeError):
    pass


def _resolve_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import torch
    except ImportError as exc:
        raise CrossEncoderRerankerError(
            "torch is required for CrossEncoderReranker"
        ) from exc
    return "cuda" if torch.cuda.is_available() else "cpu"


class CrossEncoderReranker:
    """Load a provisioned local sequence-classification reranker (raw logits)."""

    def __init__(
        self,
        *,
        model_path: Path,
        model_id: str,
        model_revision: str,
        adapter_contract: str,
        max_length: int = 1024,
        sequence_contract: str = SEQ_TRUNC_1024_PASSAGE_RIGHT,
        score_transform: str = RAW_LOGIT_SCORE_CONTRACT,
        device: str = "auto",
        batch_size: int = 16,
        local_files_only: bool = True,
        trust_remote_code: bool = False,
    ) -> None:
        if not local_files_only:
            raise CrossEncoderRerankerError("local_files_only must be true")
        if trust_remote_code:
            raise CrossEncoderRerankerError("trust_remote_code must be false")
        if sequence_contract == SEQ_TRUNC_1024_PASSAGE_RIGHT and max_length != 1024:
            raise CrossEncoderRerankerError(
                f"{SEQ_TRUNC_1024_PASSAGE_RIGHT} requires max_length=1024 (got {max_length})"
            )
        if score_transform != RAW_LOGIT_SCORE_CONTRACT:
            raise CrossEncoderRerankerError(
                f"unsupported score_transform: {score_transform} "
                f"(expected {RAW_LOGIT_SCORE_CONTRACT})"
            )
        if batch_size < 1:
            raise CrossEncoderRerankerError("batch_size must be >= 1")

        self.model_path = Path(model_path).expanduser().resolve()
        self.model_id = model_id
        self.model_revision = model_revision
        self.adapter_contract = adapter_contract
        self.max_length = int(max_length)
        self.sequence_contract = sequence_contract
        self.score_transform = score_transform
        self.device = _resolve_device(device)
        self.batch_size = int(batch_size)
        self.local_files_only = True
        self.trust_remote_code = False
        self.cpu_diagnostic_samples: list[dict[str, object]] | None = None
        self._load_lock = Lock()
        self._loaded: tuple[object, object] | None = None

        require_reranker_artifacts(
            self.model_path,
            expected_model_id=model_id,
            expected_revision=model_revision,
            expected_adapter_contract=adapter_contract,
        )

    @classmethod
    def from_settings(cls, settings: AppSettings) -> CrossEncoderReranker:
        rrk = settings.reranker
        model_dir = resolve_reranker_model_dir(
            reranker_artifacts_root=settings.paths.reranker_artifacts,
            model_path=rrk.model.model_path,
        )
        return cls(
            model_path=model_dir,
            model_id=rrk.model.model_id,
            model_revision=rrk.model.revision,
            adapter_contract=rrk.model.adapter_contract,
            max_length=rrk.max_length,
            sequence_contract=rrk.sequence_contract,
            score_transform=rrk.score_transform,
            device=rrk.device,
            batch_size=rrk.batch_size,
            local_files_only=rrk.model.local_files_only,
            trust_remote_code=rrk.model.trust_remote_code,
        )

    def _load(self) -> tuple[object, object]:
        loaded = self._loaded
        if loaded is not None:
            return loaded

        with self._load_lock:
            if self._loaded is None:
                # Publish the pair only after initialization succeeds. A failed
                # attempt leaves the next caller free to retry.
                self._loaded = self._initialize()
            return self._loaded

    def _initialize(self) -> tuple[object, object]:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            str(self.model_path),
            local_files_only=True,
            trust_remote_code=False,
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            str(self.model_path),
            local_files_only=True,
            trust_remote_code=False,
        )
        self._require_materialized(model)
        model.eval()
        model.to(self.device)
        self._require_materialized(model)
        return tokenizer, model

    @staticmethod
    def _require_materialized(model) -> None:
        if any(tensor.is_meta for tensor in model.parameters()) or any(
            tensor.is_meta for tensor in model.buffers()
        ):
            raise CrossEncoderRerankerError(
                "reranker checkpoint contains unmaterialized meta parameters or buffers"
            )

    def _assert_query_fits(self, tokenizer: object, query_text: str) -> None:
        """Fail if query + pair specials cannot fit within max_length."""
        encode = getattr(tokenizer, "encode", None)
        if encode is None:
            raise CrossEncoderRerankerError("tokenizer missing encode()")
        query_ids = encode(query_text, add_special_tokens=False)
        specials = 3
        num_special = getattr(tokenizer, "num_special_tokens_to_add", None)
        if callable(num_special):
            specials = int(num_special(pair=True))
        if len(query_ids) + specials > self.max_length:
            raise CrossEncoderRerankerError(
                "query alone cannot fit within max_length under "
                f"{self.sequence_contract}: "
                f"query_tokens={len(query_ids)} specials={specials} "
                f"max_length={self.max_length}"
            )

    def score_pairs(self, pairs: Sequence[RerankerPair]) -> list[float]:
        if not pairs:
            return []

        import torch

        diagnostic = self.cpu_diagnostic_samples if self.device == "cpu" else None
        if diagnostic is not None:
            from offline_rag.evaluation.performance_14.timing import monotonic_now

            def measure(target, name):
                return _measure_cpu_phase(target, name, monotonic_now)
        else:

            def measure(target, name):
                return nullcontext()

        phases = {}
        batches = []
        cold = self._loaded is None
        with measure(phases, "total"):
            with measure(phases, "load_or_wait"):
                tokenizer, model = self._load()
            with measure(phases, "query_validation"):
                seen_queries: set[str] = set()
                for pair in pairs:
                    if pair.query_text not in seen_queries:
                        self._assert_query_fits(tokenizer, pair.query_text)
                        seen_queries.add(pair.query_text)

            scores: list[float] = []
            for start in range(0, len(pairs), self.batch_size):
                batch = pairs[start : start + self.batch_size]
                queries = [pair.query_text for pair in batch]
                passages = [pair.passage_text for pair in batch]
                batch_sample = {}
                with measure(batch_sample, "tokenization"):
                    encoded = tokenizer(
                        text=queries,
                        text_pair=passages,
                        truncation="only_second",
                        max_length=self.max_length,
                        padding=True,
                        return_tensors="pt",
                    )
                with measure(batch_sample, "transfer"):
                    encoded = {
                        key: value.to(self.device) for key, value in encoded.items()
                    }
                with torch.inference_mode():
                    with measure(batch_sample, "forward"):
                        logits = model(**encoded).logits
                    with measure(batch_sample, "output_conversion"):
                        if logits.shape != (len(batch), 1) or logits.dtype != torch.float32:
                            raise CrossEncoderRerankerError(
                                "expected single raw logit per pair "
                                f"(got logits shape {tuple(logits.shape)})"
                            )
                        values = logits.view(-1).detach().cpu().tolist()

                with measure(batch_sample, "output_validation"):
                    for value in values:
                        score = float(value)
                        if not math.isfinite(score):
                            raise CrossEncoderRerankerError(
                                f"non-finite reranker logit: {score!r}"
                            )
                        scores.append(score)
                if diagnostic is not None:
                    mask = encoded["attention_mask"]
                    widths = mask.sum(dim=1).tolist()
                    width = int(mask.shape[1])
                    active = int(sum(widths))
                    slots = len(batch) * width
                    batch_sample.update(
                        batch_size=len(batch),
                        lengths=widths,
                        padded_width=width,
                        active_positions=active,
                        padded_positions=slots - active,
                        padding_fraction=(slots - active) / slots,
                        attention_work_proxy=len(batch) * width**2,
                    )
                    batches.append(batch_sample)

            with measure(phases, "score_count_validation"):
                if len(scores) != len(pairs):
                    raise CrossEncoderRerankerError(
                        f"score count mismatch: got {len(scores)} for {len(pairs)} pairs"
                    )

        if diagnostic is not None:
            diagnostic.append(
                {"cold_at_entry": int(cold), "phases": phases, "batches": batches}
            )
        return scores


@contextmanager
def _measure_cpu_phase(target, name, clock):
    wall_start = clock()
    cpu_start = time.process_time()
    try:
        yield
    finally:
        target[name] = {
            "wall_s": clock() - wall_start,
            "cpu_s": time.process_time() - cpu_start,
        }
PY_MODULE
chmod 644 "$prefix/cross_encoder.py"
[[ $(nproc) == 4 ]]
healthy || { echo "PREFLIGHT FAIL: not healthy"; exit 1; }
before_signature=$(signature)
image=$(docker inspect --format '{{.Image}}' "$container")
[[ $(docker inspect --format '{{.Id}}' "$container") == e006597fd6e4e40939e49c1dd73da7c6d85f33d87d44929c15dc5f0f38bb7cac ]]
[[ $image == sha256:3bc83208a7526a49abed1b9bd9586b5ae4fd041771732e03030c3ac20419e692 ]]
[[ $(docker inspect --format '{{.Config.Image}}' "$container") == seneca-review:9c92e706c4b9 ]]
[[ $(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}} {{index .Config.Labels "io.seneca.dependency-profile"}}' "$image") == "$revision cpu-release" ]]
[[ $(docker inspect --format '{{json .Mounts}}' "$container" | jq -c 'map([.Type,.Source,.Destination,.RW]) | sort') == '[["bind","/srv/seneca/data","/data",true],["bind","/srv/seneca/models","/models",false]]' ]]
[[ $(docker ps -q --filter ancestor="$image" | wc -l) == 1 ]]
[[ $(docker inspect --format '{{.Config.User}} {{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}' "$container") == '10001:10001 0 0' ]]
sudo -n true
data_kib=$(sudo -n du -sk /srv/seneca/data | awk '{print $1}')
disk_kib=$(df -Pk "$prefix" | awk 'NR==2 {print $4}')
ram_kib=$(awk '$1=="MemAvailable:" {print $2}' /proc/meminfo)
total_kib=$(awk '$1=="MemTotal:" {print $2}' /proc/meminfo)
(( disk_kib > 3*data_kib+2*1024*1024 && ram_kib > 8*1024*1024 && total_kib > 15*1024*1024 ))
printf 'Host preflight: data KiB=%s free disk KiB=%s available RAM KiB=%s\n' "$data_kib" "$disk_kib" "$ram_kib"
python3 - "$prefix/runtime.env" <<'PY'
import json, subprocess, sys
from pathlib import Path
c=json.loads(subprocess.check_output(["docker","inspect","seneca-review"]))[0]
env=c["Config"]["Env"]
if any("\r" in line or "\n" in line for line in env):
    raise SystemExit("Unsupported multiline container environment")
Path(sys.argv[1]).write_text("\n".join(env)+"\n")
PY
probe > "$prefix/before.json" || { cat "$prefix/before.json"; exit 1; }
chmod 644 "$prefix/before.json"
cat "$prefix/before.json"
pid=$(docker inspect -f '{{.State.Pid}}' "$container")
for i in 1 2 3; do
    [[ -z $(sudo -n nsenter -t "$pid" -n ss -Htn state established '( sport = :8080 )') ]] ||
        { echo "PREFLIGHT FAIL: active application connection"; exit 1; }
    cpu=$(docker stats --no-stream --format '{{.CPUPerc}}' "$container")
    awk -v v="${cpu%%%}" 'BEGIN {exit !(v+0 < 5)}' || { echo "PREFLIGHT FAIL: application CPU not idle ($cpu)"; exit 1; }
    sleep 2
done
check_time
stopping=1
docker stop -t 45 "$container" >/dev/null
[[ $(docker inspect --format '{{.State.ExitCode}} {{.State.Running}}' "$container") =~ ^(0|143)\ false$ ]] ||
    { echo "Original container did not exit gracefully"; exit 1; }
mkdir "$prefix/data"
sudo -n cp -a --reflink=auto /srv/seneca/data/. "$prefix/data/"
check_time
printf 'Isolated Rich Workspace 20-call batching diagnostic starting\n'
started=$(date +%s)
set +e
timeout --kill-after=15s 1800 docker run --rm --name "$testname" --network none \
    --env-file "$prefix/runtime.env" \
    --mount "type=bind,src=$prefix/data,dst=/data" \
    --mount type=bind,src=/srv/seneca/models,dst=/models,readonly \
    --mount "type=bind,src=$prefix/probe.py,dst=/diagnostic/probe.py,readonly" \
    --mount "type=bind,src=$prefix/before.json,dst=/diagnostic/before.json,readonly" \
    --mount "type=bind,src=$prefix/cross_encoder.py,dst=/app/.venv/lib/python3.14/site-packages/offline_rag/rerank/cross_encoder.py,readonly" \
    --entrypoint python "$image" -B /diagnostic/probe.py measure \
    2> "$prefix/diagnostic.stderr"
rc=$?
set -e
printf 'Diagnostic container elapsed seconds=%s exit=%s\n' "$(( $(date +%s)-started ))" "$rc"
(( rc == 0 )) || exit "$rc"
if docker container inspect "$testname" >/dev/null 2>&1; then
    echo "Previous isolated container still exists"
    exit 1
fi
exit 0
