"""Command line and interactive workshop for MAGTEL Toy Factory."""

import argparse
import sys
from pathlib import Path

from . import __version__
from .language import parse
from .mesh import write_stl
from .model import DesignError, ToySpec, mm
from .project import load_part, save_part, write_output

EXAMPLES = (
    "Make a wheel 40 mm across and 10 mm thick with a 6 mm axle hole.",
    "Make it 45 mm across.",
    "Make an axle 5.8 mm in diameter and 24 mm long.",
    "Make a 40 x 20 x 10 mm block with 2 x 3 studs.",
)
SHELL_HELP = """Describe a part or a change in plain language. Try:
  {make}
  {edit}

Workshop commands
  examples      Show requests you can try
  show          Read back your current design and dimensions
  undo          Undo the last design change
  save FILE     Save editable MAGTEL JSON
  save! FILE    Replace an existing part file
  open FILE     Load an editable MAGTEL part
  open! FILE    Open a part and discard unsaved changes
  export FILE   Write a millimeter STL for your slicer
  export! FILE  Replace an existing STL
  quit          Leave the workshop
  help          Show this guide
""".format(make=EXAMPLES[0], edit=EXAMPLES[1])


def _show_examples() -> None:
    for example in EXAMPLES:
        print(f"  {example}")
    print("Start a part with 'make a wheel', 'make an axle', or 'make a block'.")


def _path(text: str, *, workshop: bool = False) -> Path:
    if workshop and text.startswith(('"', "'")):
        if len(text) == 1 or text[-1] != text[0]:
            raise DesignError("Close the quotes around the file name.")
        text = text[1:-1]
    if not text:
        raise DesignError("Include a file name, such as wheel.magtel.json or wheel.stl.")
    try:
        return Path(text).expanduser()
    except RuntimeError as error:
        raise DesignError(f"Could not find a home folder for {text}.") from error


def _part_path(text: str, *, workshop: bool = False) -> Path:
    path = _path(text, workshop=workshop)
    if path.suffix.lower() != ".json":
        raise DesignError("Use a .magtel.json file name for the editable part.")
    return path


def _export(spec: ToySpec, path: Path, *, force: bool = False) -> None:
    if path.suffix.lower() != ".stl":
        raise DesignError("Use a .stl file name for the mesh, such as wheel.stl.")
    write_output(path, lambda temp: write_stl(spec, temp), force=force)
    print(f"Exported {path}. Use millimeters when importing it into your slicer.")


def _save(spec: ToySpec, path: Path, *, force: bool = False) -> None:
    save_part(spec, path, force=force)
    print(f"Saved editable part to {path}.")


def _fit(wheel: ToySpec, axle: ToySpec) -> int:
    if wheel.kind != "wheel" or axle.kind != "axle":
        raise DesignError("Pass a wheel file first and an axle file second.")
    if wheel.hole is None:
        raise DesignError("This wheel is solid. Add an axle hole before checking the fit.")
    gap = wheel.hole - axle.diameter
    if gap > 1e-9:
        print(f"Nominal diametral clearance: {mm(gap)} mm ({mm(gap / 2)} mm per side).")
        if axle.thickness < wheel.thickness:
            print("The axle is shorter than the wheel is thick.")
        print("Check the fit on a test print for your printer and material.")
        return 0
    if gap < -1e-9:
        print(f"Nominal interference: the axle is {mm(-gap)} mm wider than the hole.")
    else:
        print("The hole and axle have the same diameter. Increase the hole or shrink the axle for clearance.")
    return 1


def _workshop(start: Path | None = None) -> int:
    current = load_part(start) if start else None
    saved = current
    history: list[ToySpec | None] = []
    print(f"MAGTEL Toy Factory {__version__}. Describe a part to get started, or type help.")
    if current:
        print(current.describe())
    else:
        print(f"Try: {EXAMPLES[0]}")
    prompt = "magtel> " if sys.stdin.isatty() else ""
    while True:
        try:
            request = input(prompt).strip()
        except EOFError:
            if current != saved and current is not None:
                print("Workshop closed with an unsaved design.", file=sys.stderr)
            return 0
        except KeyboardInterrupt:
            print()
            continue
        if not request:
            continue
        command, *tail = request.split(maxsplit=1)
        command = command.lower()
        filename = tail[0] if tail else ""
        try:
            if command in ("quit", "exit", "quit!", "exit!") and not tail:
                if current != saved and current is not None and not command.endswith("!"):
                    print("You have unsaved changes. Use save FILE, or quit! to discard them.")
                    continue
                return 0
            if command in ("help", "?") and not tail:
                print(SHELL_HELP)
            elif command == "examples" and not tail:
                _show_examples()
            elif command == "undo" and not tail:
                if not history:
                    raise DesignError("There is no design change to undo yet.")
                current = history.pop()
                print(current.describe() if current else "Workshop cleared.")
            elif command in ("open", "open!"):
                if current != saved and current is not None and command == "open":
                    raise DesignError("Save your current design first, or use open! FILE to discard it.")
                current = load_part(_part_path(filename, workshop=True))
                saved = current
                history.clear()
                print(current.describe())
            elif command in ("show", "save", "save!", "export", "export!"):
                if current is None:
                    raise DesignError("Make or open a part first. Type examples for ideas.")
                if command == "show" and not tail:
                    print(current.describe())
                elif command in ("save", "save!"):
                    _save(current, _part_path(filename, workshop=True), force=command.endswith("!"))
                    saved = current
                elif command in ("export", "export!"):
                    _export(current, _path(filename, workshop=True), force=command.endswith("!"))
                else:
                    raise DesignError("Type show by itself to read back the current design.")
            else:
                updated = parse(request, current)
                if updated != current:
                    history.append(current)
                    current = updated
                print(updated.describe())
        except FileExistsError as error:
            print(f"Try again: {error.filename} already exists. Use {command}! FILE to replace it.",
                  file=sys.stderr)
        except (DesignError, OSError) as error:
            print(f"Try again: {error}", file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="magtel",
        description="MAGTEL Toy Factory. Build toy parts in plain language.",
        epilog='Try magtel "Make a wheel 40 mm across with a 6 mm hole." Or run magtel to start a workshop.',
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    make = commands.add_parser("make", help="describe a new part")
    make.add_argument("request", nargs="+")
    edit = commands.add_parser("edit", help="describe changes to a saved part")
    edit.add_argument("file")
    edit.add_argument("request", nargs="+")
    for command in (make, edit):
        command.add_argument("-o", "--output", metavar="FILE", help="save editable .magtel.json")
        command.add_argument("--force", action="store_true", help="replace an existing output file")
    show = commands.add_parser("show", help="read back a saved design")
    show.add_argument("file")
    export = commands.add_parser("export", help="export a saved design to STL")
    export.add_argument("file")
    export.add_argument("-o", "--output", required=True, metavar="FILE", help="write a .stl file")
    export.add_argument("--force", action="store_true", help="replace an existing output file")
    fit = commands.add_parser("fit", help="check nominal wheel and axle clearance")
    fit.add_argument("wheel")
    fit.add_argument("axle")
    workshop = commands.add_parser("workshop", help="start a conversation about a part")
    workshop.add_argument("file", nargs="?", help="start with an editable .magtel.json part")
    commands.add_parser("examples", help="show example language")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"make", "edit", "show", "export", "fit", "workshop", "examples"}
    if argv and argv[0] not in commands and not argv[0].startswith("-"):
        argv.insert(0, "make")
    args = _parser().parse_args(argv)
    try:
        if args.command in (None, "workshop"):
            start = _part_path(args.file) if args.command and args.file else None
            return _workshop(start)
        if args.command == "examples":
            _show_examples()
        elif args.command in ("make", "edit"):
            current = load_part(_part_path(args.file)) if args.command == "edit" else None
            part = parse(" ".join(args.request), current)
            print(part.describe())
            if args.output:
                _save(part, _part_path(args.output), force=args.force)
        elif args.command == "show":
            print(load_part(_part_path(args.file)).describe())
        elif args.command == "export":
            _export(load_part(_part_path(args.file)), _path(args.output), force=args.force)
        elif args.command == "fit":
            return _fit(load_part(_part_path(args.wheel)), load_part(_part_path(args.axle)))
    except FileExistsError as error:
        print(f"magtel: {error.filename} already exists. Choose another name or use --force.", file=sys.stderr)
        return 2
    except (DesignError, OSError) as error:
        print(f"magtel: {error}", file=sys.stderr)
        return 2
    return 0
