import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

class StorageError(ValueError): pass

def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        raise StorageError(f"invalid JSON input: {path}") from exc


class OutputReservation:
    def __init__(self, target, temporary):
        self.target, self.temporary = target, temporary

    def write_text(self, text):
        with open(self.temporary, "w", encoding="utf-8") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(self.temporary, self.target)
        self.temporary = None

    def write_json(self, value):
        self.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


@contextmanager
def reserve_output(path, force=False):
    """Check/reserve output before requests; failed runs preserve prior reports."""
    target = Path(path)
    owned = False
    reservation = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not force:
            try:
                with target.open("x", encoding="utf-8"): pass
                owned = True
            except FileExistsError:
                raise StorageError(f"refusing to overwrite: {target}") from None
        elif target.is_dir() or target.is_symlink():
            raise StorageError("output must be a regular file")
        fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=".model-captain-")
        os.close(fd)
        reservation = OutputReservation(target, temporary)
        yield reservation
    except OSError as exc:
        raise StorageError(f"cannot write output: {target}") from exc
    finally:
        if reservation is not None and reservation.temporary is not None:
            Path(reservation.temporary).unlink(missing_ok=True)
        if owned and (reservation is None or reservation.temporary is not None):
            target.unlink(missing_ok=True)


def atomic_json(path, value, force=False):
    with reserve_output(path, force) as output:
        output.write_json(value)


def atomic_text(path, value, force=False):
    with reserve_output(path, force) as output:
        output.write_text(value)
