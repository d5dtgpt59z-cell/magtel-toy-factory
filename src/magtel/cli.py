"""Command line and interactive workshop for MAGTEL Toy Factory."""

import argparse
import sys
from pathlib import Path

from . import __version__
from .assembly import CarSpec
from .assembly_io import export_car, export_parts, load_design, save_car
from .assembly_language import parse_car, starts_car
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
CAR_EXAMPLES = (
    "Build a toy car.",
    "Use an 80 x 30 x 12 mm chassis.",
    "Mount two 5.8 mm diameter, 60 mm long axles 55 mm apart.",
    "Put a 40 mm wheel, 10 mm thick, with a 6 mm hole on each end.",
)
Design = ToySpec | CarSpec
SHELL_HELP = """Describe a part, assembly, or change in plain language. Try:
  {make}
  {edit}
  {car}

Workshop commands
  examples      Show requests you can try
  show          Read back your current design and dimensions
  fit           Check the fit of a complete car assembly
  undo          Undo the last design change
  save FILE     Save editable MAGTEL JSON
  save! FILE    Replace an existing design file
  open FILE     Load an editable MAGTEL design
  open! FILE    Open a design and discard unsaved changes
  export FILE   Write an STL or a .zip of loose car parts
  export! FILE  Replace an existing export
  quit          Leave the workshop
  help          Show this guide
""".format(make=EXAMPLES[0], edit=EXAMPLES[1], car=CAR_EXAMPLES[0])


def _show_examples(*, car_only: bool = False) -> None:
    if not car_only:
        print("Part requests:")
        for example in EXAMPLES:
            print(f"  {example}")
    print("Car assembly, one line at a time:")
    for example in CAR_EXAMPLES:
        print(f"  {example}")


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


def _design_path(text: str, *, workshop: bool = False) -> Path:
    path = _path(text, workshop=workshop)
    if path.suffix.lower() != ".json":
        raise DesignError("Use a .magtel.json file name for the editable design.")
    return path


def _export(spec: Design, path: Path, *, force: bool = False) -> None:
    suffix = path.suffix.lower()
    if isinstance(spec, CarSpec):
        if suffix == ".zip":
            export_parts(spec, path, force=force)
            print(f"Exported the separate chassis, axle, and wheel STLs to {path}.")
            return
        if suffix == ".stl":
            export_car(spec, path, force=force)
            print(f"Exported assembled view to {path}. Use a .zip output to get separate parts for printing.")
            return
        raise DesignError("Use .stl for the assembled car or .zip for the separate printable parts.")
    if suffix != ".stl":
        raise DesignError("Use a .stl file name for the mesh, such as wheel.stl.")
    write_output(path, lambda temp: write_stl(spec, temp), force=force)
    print(f"Exported {path}. Use millimeters when importing it into your slicer.")


def _save(spec: Design, path: Path, *, force: bool = False) -> None:
    if isinstance(spec, CarSpec):
        save_car(spec, path, force=force)
        print(f"Saved editable assembly to {path}.")
    else:
        save_part(spec, path, force=force)
        print(f"Saved editable part to {path}.")


def _parse_design(request: str, current: Design | None, *, car: bool = False) -> Design:
    if car or isinstance(current, CarSpec) or starts_car(request):
        assembly = current if isinstance(current, CarSpec) else None
        return parse_car(request, assembly, load_component=load_part)
    return parse(request, current)


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


def _workshop(start: Path | None = None, *, car: bool = False) -> int:
    current = load_design(start) if start else CarSpec() if car else None
    saved = current
    history: list[Design | None] = []
    print(f"MAGTEL Toy Factory {__version__}. Describe a toy to get started, or type help.")
    if current:
        print(current.describe())
    else:
        print(f"Try: {EXAMPLES[0]}")
        print(f"To start an assembly: {CAR_EXAMPLES[0]}")
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
                _show_examples(car_only=isinstance(current, CarSpec))
            elif request.lower().rstrip(".!?") in ("fit", "check fit", "check the fit"):
                if not isinstance(current, CarSpec):
                    raise DesignError("Build or open a car first. For two saved parts, use magtel fit WHEEL AXLE.")
                print(current.fit_report())
            elif command == "undo" and not tail:
                if not history:
                    raise DesignError("There is no design change to undo yet.")
                current = history.pop()
                print(current.describe() if current else "Workshop cleared.")
            elif command in ("open", "open!"):
                if current != saved and current is not None and command == "open":
                    raise DesignError("Save your current design first, or use open! FILE to discard it.")
                current = load_design(_design_path(filename, workshop=True))
                saved = current
                history.clear()
                print(current.describe())
            elif command in ("show", "save", "save!", "export", "export!"):
                if current is None:
                    raise DesignError("Make or open a design first. Type examples for ideas.")
                if command == "show" and not tail:
                    print(current.describe())
                elif command in ("save", "save!"):
                    _save(current, _design_path(filename, workshop=True), force=command.endswith("!"))
                    saved = current
                elif command in ("export", "export!"):
                    _export(current, _path(filename, workshop=True), force=command.endswith("!"))
                else:
                    raise DesignError("Type show by itself to read back the current design.")
            else:
                updated = _parse_design(request, current)
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
        description="MAGTEL Toy Factory. Build toy parts and car assemblies in plain language.",
        epilog='Try magtel "Make a wheel 40 mm across with a 6 mm hole." Or run magtel to start a workshop.',
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    make = commands.add_parser("make", help="describe a new part or car")
    make.add_argument("request", nargs="+")
    assemble = commands.add_parser("assemble", help="build a toy car in the workshop or from a description")
    assemble.add_argument("request", nargs="*")
    edit = commands.add_parser("edit", help="describe changes to a saved design")
    edit.add_argument("file")
    edit.add_argument("request", nargs="+")
    for command in (make, edit, assemble):
        command.add_argument("-o", "--output", metavar="FILE", help="save editable .magtel.json")
        command.add_argument("--force", action="store_true", help="replace an existing output file")
    show = commands.add_parser("show", help="read back a saved design")
    show.add_argument("file")
    export = commands.add_parser("export", help="export a design to STL or a car to a zip of parts")
    export.add_argument("file")
    export.add_argument("-o", "--output", required=True, metavar="FILE", help="write a .stl or car parts .zip")
    export.add_argument("--force", action="store_true", help="replace an existing output file")
    fit = commands.add_parser("fit", help="check a car assembly or a wheel and axle pair")
    fit.add_argument("design", metavar="CAR_OR_WHEEL")
    fit.add_argument("axle", nargs="?", metavar="AXLE")
    workshop = commands.add_parser("workshop", help="start a conversation about a design")
    workshop.add_argument("file", nargs="?", help="start with an editable .magtel.json design")
    commands.add_parser("examples", help="show example language")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"make", "assemble", "edit", "show", "export", "fit", "workshop", "examples"}
    if argv and argv[0] not in commands and not argv[0].startswith("-"):
        argv.insert(0, "make")
    args = _parser().parse_args(argv)
    try:
        if args.command in (None, "workshop"):
            start = _design_path(args.file) if args.command and args.file else None
            return _workshop(start)
        if args.command == "assemble" and not args.request:
            if args.output:
                raise DesignError("Include a car description with --output, or run magtel assemble to start a workshop.")
            return _workshop(car=True)
        if args.command == "examples":
            _show_examples()
        elif args.command in ("make", "edit", "assemble"):
            current = load_design(_design_path(args.file)) if args.command == "edit" else None
            design = _parse_design(" ".join(args.request), current, car=args.command == "assemble")
            print(design.describe())
            if args.output:
                _save(design, _design_path(args.output), force=args.force)
        elif args.command == "show":
            print(load_design(_design_path(args.file)).describe())
        elif args.command == "export":
            _export(load_design(_design_path(args.file)), _path(args.output), force=args.force)
        elif args.command == "fit":
            if args.axle:
                return _fit(load_part(_design_path(args.design)), load_part(_design_path(args.axle)))
            design = load_design(_design_path(args.design))
            if not isinstance(design, CarSpec):
                raise DesignError("Pass a car assembly, or pass both a wheel file and an axle file.")
            print(design.fit_report())
    except FileExistsError as error:
        print(f"magtel: {error.filename} already exists. Choose another name or use --force.", file=sys.stderr)
        return 2
    except (DesignError, OSError) as error:
        print(f"magtel: {error}", file=sys.stderr)
        return 2
    return 0
