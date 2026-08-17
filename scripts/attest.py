from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

PRIMARY = "https://raw.githubusercontent.com/Maxhm007/Genesis-AI-Network/main"
NODE_ID = "genesis-node-3"
SOURCE_REPO = "Maxhm007/Genesis-AI-Network"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=20) as response:
        return response.read().decode("utf-8")


def main() -> None:
    genesis_text = fetch_text(f"{PRIMARY}/GENESIS_BLOCK.json")
    genesis_anchor = sha256_text(genesis_text)

    try:
        published = json.loads(fetch_text(f"{PRIMARY}/network/blockchain_head.json"))
        head = str(published.get("head") or genesis_anchor)
        height = int(published.get("height", 0))
    except Exception:
        head = genesis_anchor
        height = 0

    attestation = {
        "peer_id": NODE_ID,
        "repository": "Maxhm007/Genesis-Node-3",
        "source_repo": SOURCE_REPO,
        "network": "gden/0.1",
        "head": head,
        "height": height,
        "genesis_anchor": genesis_anchor,
        "attestation_mode": "github-repository-authenticated",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    Path("attestation.json").write_text(json.dumps(attestation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(attestation, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
