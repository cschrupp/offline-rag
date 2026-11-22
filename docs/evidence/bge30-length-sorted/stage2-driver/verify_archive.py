"""Verify the exported diagnostic archive and each selected OCI descriptor."""

import hashlib
import json
import sys
import tarfile
from pathlib import Path

ARCHIVE_SHA = "48084b824acd41126f54eb264d6ad63f4414be3239a23ed905edf864c50c3380"
INDEX = "sha256:669932995e62fa53616fbfe0551c442077caa0496f86fba49d5f4a1ba6f48d04"
MANIFEST = "sha256:de19ac0d1ae79dedd6b1fc917716b9d323c8a0fbb937153b7d633a6796f15241"
CONFIG = "sha256:abdabc78de24ede28b5b172a8ceb93bfd9640bd8537bcac9d903fd448139e83a"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def verify(path):
    with path.open("rb") as stream:
        require(
            hashlib.file_digest(stream, "sha256").hexdigest() == ARCHIVE_SHA,
            "archive bytes differ",
        )
    with tarfile.open(path) as archive:

        def blob(digest):
            data = archive.extractfile("blobs/" + digest.replace(":", "/")).read()
            require(
                "sha256:" + hashlib.sha256(data).hexdigest() == digest,
                "OCI blob differs",
            )
            return json.loads(data)

        wrapper = json.load(archive.extractfile("index.json"))
        require(
            [row["digest"] for row in wrapper["manifests"]] == [INDEX],
            "archive index differs",
        )
        manifests = blob(INDEX)["manifests"]
        selected = [
            row["digest"]
            for row in manifests
            if row.get("platform", {}).get("os") == "linux"
            and row.get("platform", {}).get("architecture") == "amd64"
        ]
        require(selected == [MANIFEST], "amd64 descriptor differs")
        require(
            blob(MANIFEST)["config"]["digest"] == CONFIG, "config descriptor differs"
        )
        config = blob(CONFIG)
        require(
            config["config"]["Labels"]["org.opencontainers.image.revision"]
            == "1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e",
            "source label differs",
        )
    print(
        f"Archive SHA-256 {ARCHIVE_SHA}\nOCI index {INDEX}\nAMD64 manifest {MANIFEST}\nImage config {CONFIG}"
    )


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
