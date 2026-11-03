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
    return decode_part(read_json(path, label="MAGTEL part"), path)


def read_json(path: Path, *, label: str) -> object:
    with path.open("rb") as file:
        raw = file.read(MAX_PART_FILE_SIZE + 1)
    if len(raw) > MAX_PART_FILE_SIZE:
        raise DesignError(f"{path} is too large to be a {label}.")
    try:
        return json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise DesignError(f"{path} does not contain a readable {label}.") from error


def decode_part(data: object, path: Path) -> ToySpec:
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise DesignError(f"{path} is not a MAGTEL part. Open a .magtel.json file.")
    if type(data.get("version")) is not int or data["version"] != VERSION:
        raise DesignError(f"{path} uses an unsupported MAGTEL file version.")
    if data.get("units") != "mm":
        raise DesignError("MAGTEL part files must use millimeters.")
    return decode_part_parameters(data.get("part"), path)


def decode_part_parameters(parameters: object, path: Path) -> ToySpec:
    if (not isinstance(parameters, dict) or not {"kind", "name"} <= parameters.keys()
            or not parameters.keys() <= FIELDS):
        raise DesignError(f"{path} contains missing or unknown part parameters.")
    if isinstance(parameters.get("studs"), list):
        parameters = {**parameters, "studs": tuple(parameters["studs"])}
    return ToySpec(**parameters).validate()


def save_part(spec: ToySpec, path: Path, *, force: bool = False) -> None:
    data = {"format": FORMAT, "version": VERSION, "units": "mm", "part": part_parameters(spec)}
    write_json(data, path, force=force)


def part_parameters(spec: ToySpec) -> dict[str, object]:
    return {key: value for key, value in asdict(spec.validate()).items() if value is not None}


def write_json(data: dict[str, object], path: Path, *, force: bool = False) -> None:
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
