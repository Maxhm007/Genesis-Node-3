from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request

PRIMARY_API = "https://api.github.com/repos/Maxhm007/Genesis-AI-Network/contents"
NODE_ID = "genesis-node-3"
NODE_REPOSITORY = "Maxhm007/Genesis-Node-3"
SOURCE_REPO = "Maxhm007/Genesis-AI-Network"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def canonical_bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def fetch_repo_text(path: str) -> str:
    request = urllib.request.Request(
        f"{PRIMARY_API}/{path}?ref=main",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Cache-Control": "no-cache",
            "User-Agent": "genesis-validator-node/1.1",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    encoded = str(payload.get("content", "")).replace("\n", "")
    if not encoded:
        raise RuntimeError(f"GitHub Contents API returned no content for {path}")
    return base64.b64decode(encoded).decode("utf-8")


def sign_ed25519(payload: bytes, private_key_pem: str) -> tuple[str, str, str]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        key_path = root / "node_key.pem"
        payload_path = root / "payload.bin"
        signature_path = root / "signature.bin"
        public_path = root / "public.pem"
        key_path.write_text(private_key_pem, encoding="utf-8")
        key_path.chmod(0o600)
        payload_path.write_bytes(payload)
        subprocess.run(["openssl", "pkey", "-in", str(key_path), "-pubout", "-out", str(public_path)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(key_path), "-rawin", "-in", str(payload_path), "-out", str(signature_path)], check=True, capture_output=True)
        public_pem = public_path.read_text(encoding="utf-8")
        signature = base64.b64encode(signature_path.read_bytes()).decode("ascii")
        return signature, public_pem, sha256_text(public_pem)


def main() -> None:
    genesis_text = fetch_repo_text("GENESIS_BLOCK.json")
    genesis_anchor = sha256_text(genesis_text)
    try:
        published = json.loads(fetch_repo_text("network/blockchain_head.json"))
        head = str(published.get("head") or genesis_anchor)
        height = int(published.get("height", 0))
    except Exception:
        head = genesis_anchor
        height = 0

    core = {
        "peer_id": NODE_ID,
        "repository": NODE_REPOSITORY,
        "source_repo": SOURCE_REPO,
        "network": "gden/0.1",
        "head": head,
        "height": height,
        "genesis_anchor": genesis_anchor,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    attestation = {**core, "attestation_mode": "github-repository-authenticated"}
    private_key_pem = os.environ.get("GENESIS_NODE_PRIVATE_KEY_PEM", "").strip()
    if private_key_pem:
        signature, public_pem, public_key_sha256 = sign_ed25519(canonical_bytes(core), private_key_pem)
        Path("node_public_key.pem").write_text(public_pem, encoding="utf-8")
        attestation.update(
            {
                "attestation_mode": "ed25519-signed",
                "signature_algorithm": "ed25519",
                "signature": signature,
                "signed_payload_sha256": sha256_bytes(canonical_bytes(core)),
                "public_key_sha256": public_key_sha256,
            }
        )

    Path("attestation.json").write_text(json.dumps(attestation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in attestation.items() if k != "signature"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
