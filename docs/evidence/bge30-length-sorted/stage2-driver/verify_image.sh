#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
base=docs/evidence/bge30-length-sorted/stage2-integration
image=seneca-rich2-local:1f79eca0
digest=sha256:59252d0655267001c4c9ac42e5a2045131b4086bb1ab84e10dbfd98f2e831dee
docker image inspect "$image" | python3 -c '
import json, sys
image=json.load(sys.stdin)[0]
assert image["Descriptor"]["digest"] == sys.argv[1]
print("Image ID=",image["Id"],"OCI descriptor=",image["Descriptor"]["digest"],
      "RepoDigests=",image["RepoDigests"],sep="")
' "$digest"
scratch=$(mktemp -d)
trap 'python3 -c "import shutil,sys;shutil.rmtree(sys.argv[1])" "$scratch"' EXIT
docker run --rm --network none --entrypoint python "$digest" -B -c '
import hashlib, importlib.metadata as md, json, pathlib, sys, torch
import offline_rag
from offline_rag.config.loader import load_settings
from offline_rag.rerank.config_hash import build_reranker_config_hash
classes = ("torch","transformers","tokenizers","tiktoken","onnxruntime","sentence-transformers")
root=pathlib.Path("/diagnostic-src/offline_rag")
assert pathlib.Path(offline_rag.__file__).is_relative_to(root)
assert torch.version.cuda is None and not torch.cuda.is_available()
default=load_settings(yaml_paths=[],environ={}).reranker
opt=load_settings(yaml_paths=[],environ={"OFFLINE_RAG_RERANKER_BATCHING_STRATEGY":"length_sorted_8"}).reranker
assert default.batching_strategy=="consecutive" and opt.batching_strategy=="length_sorted_8"
assert default.input_k==opt.input_k==30
assert build_reranker_config_hash(default)==build_reranker_config_hash(opt)
fixture=pathlib.Path("/diagnostic/provider_fixture.py")
print(json.dumps({"python":sys.version.split()[0],"versions":{n:md.version(n) for n in classes},
    "reranker_fingerprint":build_reranker_config_hash(default),
    "fixture_sha256":hashlib.sha256(fixture.read_bytes()).hexdigest(),
    "files":{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob("*") if p.is_file()}}))
' > "$scratch/observed.json"
python3 - "$scratch/observed.json" "$base/IMAGE_RUNTIME.json" <<'PY'
import hashlib,json,subprocess,sys
from pathlib import Path
observed, expected = (json.loads(Path(p).read_text()) for p in sys.argv[1:])
files=observed.pop("files")
assert all(expected[k]==v for k,v in observed.items())
sha="1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e"
prefix="src/offline_rag/"
paths=subprocess.check_output(["git","ls-tree","-r","--name-only",sha,prefix],text=True).splitlines()
assert files=={p.removeprefix(prefix):hashlib.sha256(
    subprocess.check_output(["git","show",f"{sha}:{p}"])).hexdigest() for p in paths}
print(f"{len(paths)} source digests, fixture, Python/dependencies and scientific fingerprint verified")
PY
