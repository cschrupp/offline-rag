# Review VM qualification

Use the [Docling cutover and rollback procedure](../docling_native_runtime_corrective/REVIEW_VM_DEPLOYMENT_RUNBOOK.md)
after independent review and separate deployment authorization. Use the
candidate below in its build section. Retain the active container and any
existing rollback container and image. Pick an unused rollback name before
cutover if the documented rollback name is occupied.

Inspect capacity before building:

```bash
docker_root=$(docker info --format '{{.DockerRootDir}}')
df -h "$docker_root" /srv/seneca
docker system df
docker ps -a --format '{{.Names}} {{.Image}}'
```

The last CPU image was about 2.64 GB. Allow room for the new image, the
retained images, BuildKit cache, and unpacked build intermediates. If capacity
is tight, expand available storage or build on a separate host and transfer
the verified image. Avoid broad Docker pruning. Keep rollback images tagged
and their stopped containers intact.

```bash
set -e
git fetch origin corrective/18d-r-reranker-initialization
sha=9c92e706c4b9e9d9ac0816a655bdf131cc63fca1
git merge-base --is-ancestor "$sha" FETCH_HEAD
git switch --detach "$sha"
tag="seneca-review:${sha:0:12}"
docker build -f deploy/Dockerfile --build-arg SENECA_DEPENDENCY_PROFILE=cpu-release --build-arg SENECA_SOURCE_SHA="$sha" -t "$tag" .
python3 scripts/verify_docling_runtime.py "$tag" "$sha"
```

Before cutover, run one real reranker load and score using the existing
read-only model mount. Use the inventoried model path if it differs.

```bash
docker run --rm -i --network none \
  --mount type=bind,src=/srv/seneca/models,dst=/models,readonly \
  --entrypoint python "$tag" - <<'PYTHON'
from math import isfinite

from offline_rag.config.loader import load_settings
from offline_rag.rerank.cross_encoder import CrossEncoderReranker
from offline_rag.rerank.protocol import RerankerPair

reranker = CrossEncoderReranker.from_settings(load_settings())
scores = reranker.score_pairs([
    RerankerPair("synthetic", "What grows on trees?", "Apples grow on trees.")
])
assert reranker.device == "cpu"
assert len(scores) == 1 and isfinite(scores[0])
print("CPU BGE raw-logit smoke passed")
PYTHON
```

After authorized cutover, verify readiness, model/data mounts and workspace
visibility per the earlier runbook. In a public-safe workspace containing an
indexed source, submit one new grounded question through the conversation UI.
Confirm the request succeeds, cites the active source and snapshot, and the
trace records successful reranking. Privately confirm the effective provider
and model in Settings. If the request fails, retain its trace and record the
failing stage and exception category before deciding whether to roll back.
