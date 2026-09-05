import json
import os
import tempfile
from pathlib import Path

class StorageError(ValueError): pass

def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"invalid JSON input: {path}") from exc

def atomic_json(path, value, force=False):
    target = Path(path)
    if target.exists() and not force: raise StorageError(f"refusing to overwrite: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=".model-guide-", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out: json.dump(value, out, indent=2, sort_keys=True); out.write("\n")
        os.replace(temp, target)
    except Exception:
        try: os.unlink(temp)
        except OSError: pass
        raise

def atomic_text(path, value, force=False):
    target = Path(path)
    if target.exists() and not force: raise StorageError(f"refusing to overwrite: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=".model-guide-", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out: out.write(value)
        os.replace(temp, target)
    except Exception:
        try: os.unlink(temp)
        except OSError: pass
        raise
