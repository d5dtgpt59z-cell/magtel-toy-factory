"""Read and write versioned MAGTEL part files."""

import errno
import json
import os
import shutil
import tempfile
from dataclasses import asdict, fields
from pathlib import Path
from typing import Callable

from .model import DesignError, ToySpec

FORMAT = "magtel-part"
VERSION = 1
MAX_PART_FILE_SIZE = 64 * 1024
FIELDS = {field.name for field in fields(ToySpec)}


def load_part(path: Path) -> ToySpec:
    with path.open("rb") as file:
        raw = file.read(MAX_PART_FILE_SIZE + 1)
    if len(raw) > MAX_PART_FILE_SIZE:
        raise DesignError(f"{path} is too large to be a MAGTEL part.")
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise DesignError(f"{path} does not contain a readable MAGTEL part.") from error
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise DesignError(f"{path} is not a MAGTEL part. Open a .magtel.json file.")
    if type(data.get("version")) is not int or data["version"] != VERSION:
        raise DesignError(f"{path} uses an unsupported MAGTEL file version.")
    if data.get("units") != "mm":
        raise DesignError("MAGTEL part files must use millimeters.")
    parameters = data.get("part")
    if (not isinstance(parameters, dict) or not {"kind", "name"} <= parameters.keys()
            or not parameters.keys() <= FIELDS):
        raise DesignError(f"{path} contains missing or unknown part parameters.")
    if isinstance(parameters.get("studs"), list):
        parameters["studs"] = tuple(parameters["studs"])
    return ToySpec(**parameters).validate()


def save_part(spec: ToySpec, path: Path, *, force: bool = False) -> None:
    values = {key: value for key, value in asdict(spec.validate()).items() if value is not None}
    data = {"format": FORMAT, "version": VERSION, "units": "mm", "part": values}
    contents = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    write_output(path, lambda temp: temp.write_text(contents, encoding="utf-8"), force=force)


def write_output(path: Path, writer: Callable[[Path], object], *, force: bool = False) -> None:
    """Publish a complete file and leave existing files alone unless requested."""
    if not path.parent.is_dir():
        raise DesignError(f"Folder {path.parent} does not exist. Create it or choose another folder.")
    handle, temp_name = tempfile.mkstemp(prefix=".magtel-", dir=path.parent)
    os.close(handle)
    temp = Path(temp_name)
    try:
        writer(temp)
        if force:
            temp.replace(path)
        else:
            try:
                os.link(temp, path)
            except FileExistsError as error:
                raise FileExistsError(error.errno, error.strerror, path) from error
            except OSError as error:
                if error.errno not in (errno.EPERM, errno.ENOTSUP, errno.ENOSYS):
                    raise
                # Some removable volumes don't support hard links.
                with temp.open("rb") as source:
                    output = path.open("xb")
                    try:
                        with output:
                            shutil.copyfileobj(source, output)
                    except BaseException:
                        path.unlink(missing_ok=True)
                        raise
    finally:
        temp.unlink(missing_ok=True)
