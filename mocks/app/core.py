import json
import os
from pathlib import Path

from fastapi import HTTPException

DATA_DIR = Path(os.environ.get("MOCK_DATA_DIR", "data"))
_data_cache: dict[str, tuple[float, dict]] = {}


def load_data(name: str) -> dict:
    path = DATA_DIR / f"{name}.json"
    mtime = path.stat().st_mtime
    cached = _data_cache.get(name)
    if cached and cached[0] == mtime:
        return cached[1]
    data = json.loads(path.read_text(encoding="utf-8"))
    _data_cache[name] = (mtime, data)
    return data


def get_or_404(db: dict, inn: str) -> dict:
    if inn not in db:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "inn": inn})
    return db[inn]
