from pathlib import Path

ROOT = Path.cwd()
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
MANIFESTS = DATA / "manifests"
OUTPUTS = DATA / "outputs"

def ensure_dirs() -> None:
    for path in (RAW / "nse_bhavcopy", RAW / "news", RAW / "disclosures", PROCESSED, MANIFESTS, OUTPUTS):
        path.mkdir(parents=True, exist_ok=True)
