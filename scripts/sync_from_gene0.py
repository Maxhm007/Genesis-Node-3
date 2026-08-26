#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_URL = "https://raw.githubusercontent.com/Maxhm007/Genesis-AI-Network/main/GENE_CAPABILITY_MANIFEST.json"
EXPECTED_PUBLISHER = "Maxhm007/Genesis-AI-Network"
STATE_PATH = ROOT / "GENE0_INHERITANCE_STATE.json"
MANIFEST_SNAPSHOT = ROOT / "inherited/gene0/GENE_CAPABILITY_MANIFEST.json"
ALLOWED_PREFIX = ("inherited", "gene0")


def fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Genesis-Descendant-Sync/1"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed trusted GitHub hosts
        return response.read()


def load_json_bytes(data: bytes, label: str) -> dict:
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def version_tuple(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"unsupported release_version: {value}")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def safe_relative(value: str, label: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe {label}: {value}")
    return path


def target_path(value: str) -> Path:
    relative = safe_relative(value, "target")
    if relative.parts[:2] != ALLOWED_PREFIX:
        raise ValueError(f"Gene 0 may only write under inherited/gene0/: {value}")
    return ROOT.joinpath(*relative.parts)


def read_state() -> dict:
    if not STATE_PATH.is_file():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - corrupt state is repaired by a verified release
        return {}


def local_release_is_current(manifest: dict, state: dict) -> bool:
    if state.get("release_id") != manifest.get("release_id"):
        return False
    for item in manifest.get("exports", []):
        path = target_path(str(item["target"]))
        if not path.is_file() or sha256(path.read_bytes()) != item.get("sha256"):
            return False
    return MANIFEST_SNAPSHOT.is_file()


def validate_manifest(manifest: dict, node: dict) -> None:
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported capability manifest schema")
    publisher = manifest.get("publisher", {})
    if publisher.get("repository") != EXPECTED_PUBLISHER or publisher.get("ref") != "main":
        raise ValueError("capability manifest publisher is not canonical Gene 0 main")
    compatibility = manifest.get("compatibility", {})
    if node.get("node_id") not in compatibility.get("allowed_nodes", []):
        raise ValueError("this node is not allowed by the Gene 0 capability manifest")
    if node.get("network") != compatibility.get("network"):
        raise ValueError("network version is incompatible with Gene 0 capability release")
    if not manifest.get("release_id") or not manifest.get("release_version"):
        raise ValueError("manifest is missing release identity")
    if not manifest.get("exports"):
        raise ValueError("manifest exports are empty")


def restore(backups: dict[Path, bytes | None]) -> None:
    for path, previous in backups.items():
        if previous is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(previous)


def main() -> int:
    node = json.loads((ROOT / "node.json").read_text(encoding="utf-8"))
    manifest_bytes = fetch_bytes(MANIFEST_URL)
    manifest = load_json_bytes(manifest_bytes, "Gene 0 capability manifest")
    validate_manifest(manifest, node)

    state = read_state()
    if state.get("release_version"):
        if version_tuple(str(manifest["release_version"])) < version_tuple(str(state["release_version"])):
            raise ValueError("refusing Gene 0 capability rollback")

    if local_release_is_current(manifest, state):
        print(f"Gene 0 capability release already current: {manifest['release_version']} {manifest['release_id'][:12]}")
        return 0

    publisher = manifest["publisher"]
    base = f"https://raw.githubusercontent.com/{publisher['repository']}/{publisher['ref']}"
    staged: list[tuple[dict, Path, Path]] = []

    with tempfile.TemporaryDirectory(prefix="gene0-stage-", dir=ROOT) as temp_dir:
        temp_root = Path(temp_dir)
        for index, item in enumerate(manifest["exports"]):
            source = safe_relative(str(item["source"]), "source")
            destination = target_path(str(item["target"]))
            url = f"{base}/{quote(str(source), safe='/')}"
            data = fetch_bytes(url)
            if len(data) != int(item["size"]):
                raise ValueError(f"size mismatch for {source}")
            if sha256(data) != item["sha256"]:
                raise ValueError(f"SHA-256 mismatch for {source}")
            kind = item.get("kind")
            if kind == "json":
                load_json_bytes(data, str(source))
            elif kind == "python":
                compile(data.decode("utf-8"), str(source), "exec")
            else:
                data.decode("utf-8")
            staged_file = temp_root / f"{index:03d}.payload"
            staged_file.write_bytes(data)
            staged.append((item, staged_file, destination))

        new_state = {
            "schema_version": 1,
            "node_id": node["node_id"],
            "publisher_repository": EXPECTED_PUBLISHER,
            "release_version": manifest["release_version"],
            "release_id": manifest["release_id"],
            "source_commit": manifest.get("source_commit"),
            "inherited_files": [
                {"target": item["target"], "sha256": item["sha256"]}
                for item in manifest["exports"]
            ],
        }

        backups: dict[Path, bytes | None] = {}
        affected = [destination for _, _, destination in staged] + [STATE_PATH, MANIFEST_SNAPSHOT]
        for path in affected:
            backups[path] = path.read_bytes() if path.is_file() else None

        try:
            for _, staged_file, destination in staged:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(staged_file, destination)
            STATE_PATH.write_text(json.dumps(new_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            MANIFEST_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
            MANIFEST_SNAPSHOT.write_bytes(manifest_bytes)

            health = ROOT / "inherited/gene0/core/descendant_health.py"
            completed = subprocess.run(
                [sys.executable, str(health), "--repo", str(ROOT)],
                cwd=ROOT,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError("inherited Gene 0 health validation failed")
        except Exception:
            restore(backups)
            raise

    print(f"Installed Gene 0 capability release {manifest['release_version']} {manifest['release_id'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
