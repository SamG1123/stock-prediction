import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .paths import MANIFESTS, ensure_dirs

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def register(path: Path, source_name: str, source_url: str = "", retrieved_at: str | None = None) -> None:
    """Append an immutable provenance record unless this exact file was registered."""
    ensure_dirs()
    manifest = MANIFESTS / "raw_files.csv"
    record = {
        "path": str(path.relative_to(Path.cwd())), "sha256": sha256(path),
        "bytes": path.stat().st_size, "source_name": source_name, "source_url": source_url,
        "retrieved_at_utc": retrieved_at or datetime.now(timezone.utc).isoformat(),
    }
    existing = pd.read_csv(manifest) if manifest.exists() else pd.DataFrame(columns=record)
    if record["sha256"] not in set(existing.get("sha256", [])):
        pd.concat([existing, pd.DataFrame([record])], ignore_index=True).to_csv(manifest, index=False)
