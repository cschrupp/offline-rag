#!/usr/bin/env python3
"""Qualify Docling inside an exact CPU release image, optionally with a real PDF."""

import argparse
import json
import subprocess
from pathlib import Path

NATIVE_CHECK = """
import importlib.util
import os
import subprocess
from pathlib import Path

if (os.getuid(), os.getgid()) != (10001, 10001):
    raise SystemExit("Unexpected runtime UID/GID")
for path in ("/app/.env", "/app/.git", "/app/src", "/run/secrets/build_ca"):
    if Path(path).exists():
        raise SystemExit(f"Unexpected image file or directory: {path}")
if any(Path("/data").iterdir()):
    raise SystemExit("Unexpected files in the image data directory")
spec = importlib.util.find_spec("cv2")
if spec is None or not spec.origin:
    raise SystemExit("OpenCV package not found")
package = Path(spec.origin).parent
objects = sorted(set(package.rglob("*.so*")) |
                 set((package.parent / "opencv_python.libs").glob("*.so*")))
objects = [obj for obj in objects if obj.is_file()]
if not any(obj.name.startswith("cv2.") for obj in objects):
    raise SystemExit("OpenCV extension not found")
for obj in objects:
    result = subprocess.run(["ldd", str(obj)], capture_output=True, text=True)
    output = result.stdout + result.stderr
    if result.returncode or "not found" in output or not output.strip():
        raise SystemExit(f"Native linkage failed for {obj.name}: {output}")
print(f"Native linkage PASS ({len(objects)} shared objects)", flush=True)

import cv2
from docling_ibm_models.tableformer.data_management.tf_predictor import TFPredictor

print(f"OpenCV {cv2.__version__} and {TFPredictor.__name__} imports PASS", flush=True)
"""

PDF_CHECK = """
from hashlib import sha256

from offline_rag.config.loader import load_settings
from offline_rag.domain.blocks import ParsedDocument
from offline_rag.ingestion.docling_artifacts import require_docling_artifacts
from offline_rag.ingestion.docling_parser import DoclingPdfParser

settings = load_settings()
if settings.parsing.pdf.ocr_enabled or not settings.project.strict_offline:
    raise SystemExit("Expected strict offline configuration with OCR disabled")
require_docling_artifacts(settings.paths.docling_artifacts)
print("Docling artifacts ready", flush=True)
fixture = Path("/qualification.pdf")
digest = sha256(fixture.read_bytes()).hexdigest()
parsed = DoclingPdfParser(
    artifacts_path=settings.paths.docling_artifacts,
    strict_offline=settings.project.strict_offline,
    ocr_enabled=settings.parsing.pdf.ocr_enabled,
).parse(fixture, document_id=f"doc_{digest}", content_hash=digest)
if not isinstance(parsed, ParsedDocument) or not any(b.text.strip() for b in parsed.blocks):
    raise SystemExit("Expected a valid ParsedDocument with useful content")
print(f"Real Docling conversion PASS ({len(parsed.blocks)} blocks)", flush=True)
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("revision")
    parser.add_argument("--models", type=Path)
    parser.add_argument("--pdf", type=Path)
    args = parser.parse_args()
    if bool(args.models) != bool(args.pdf):
        parser.error("--models and --pdf must be supplied together")

    image = json.loads(
        subprocess.check_output(["docker", "image", "inspect", args.image], text=True)
    )[0]
    config = image["Config"]
    labels = config["Labels"] or {}
    env = dict(entry.split("=", 1) for entry in config["Env"])
    if (
        labels.get("io.seneca.dependency-profile") != "cpu-release"
        or labels.get("org.opencontainers.image.revision") != args.revision
        or config["User"] != "10001:10001"
        or config.get("Entrypoint")
        or config["Cmd"] != ["python", "-m", "offline_rag.api.server"]
        or env.get("OFFLINE_RAG_MODELS_DIR") != "/models"
        or env.get("OFFLINE_RAG_DATA_DIR") != "/data"
    ):
        raise SystemExit("Release image contract mismatch")
    for name, value in env.items():
        if value and any(word in name.upper() for word in ("KEY", "TOKEN", "SECRET")):
            raise SystemExit(f"Unexpected secret-like image variable: {name}")
    print(f"Image contract PASS. ID={image['Id']} Size={image['Size']}", flush=True)

    command = ["docker", "run", "--rm", "--network", "none", "--entrypoint", "python"]
    code = NATIVE_CHECK
    if args.models and args.pdf:
        if not args.models.is_dir() or not args.pdf.is_file():
            parser.error("Expected a provisioned model directory and an existing PDF")
        for path, destination in (
            (args.models, "/models"),
            (args.pdf, "/qualification.pdf"),
        ):
            command.extend(
                [
                    "--mount",
                    f"type=bind,src={path.resolve()},dst={destination},readonly",
                ]
            )
        code += PDF_CHECK
    result = subprocess.run([*command, args.image, "-c", code], check=False)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
