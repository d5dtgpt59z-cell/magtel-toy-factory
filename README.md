# MAGTEL Toy Factory

Tell MAGTEL what part you want or how parts should fit together, then change
your mind in the same conversation. MAGTEL reads back the dimensions, saves an
editable design, and exports STL files for your slicer. The CLI runs locally
with no API key, model download, or runtime dependencies.

## Get started

Install Python 3.10 or later, then run these commands from the source folder on
macOS or Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
magtel
```

On Windows, use PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\magtel.exe
```

If Python reports version 3.9 or earlier, use your newer Python executable when
creating the virtual environment. You can also download the universal
`.whl` from the release and pass that file to `python -m pip install`.

## Build your first part

Type each line in the workshop and press Enter.

```text
Make a wheel 40 mm across and 10 mm thick with a 6 mm axle hole.
Make it 45 mm across.
Make the hole 6.4 mm.
Show
Save wheel.magtel.json
Export wheel.stl
Quit
```

The wheel is now 45 mm across and 10 mm thick with a centered 6.4 mm
through-hole. Keep the JSON to edit the part again. Import the STL in
millimeters. Type `help` for workshop commands or `undo` to back up one edit.
Existing files require explicit replacement with `save!`, `export!`, or the
one-shot `--force` option.

## Assemble a toy car

Run `magtel` and enter these requests one line at a time:

```text
Build a toy car.
Use an 80 x 30 x 12 mm chassis.
Mount two 5.8 mm diameter, 60 mm long axles 55 mm apart.
Put a 40 mm wheel, 10 mm thick, with a 6 mm hole on each end.
Check the fit.
Save car.magtel.json
Export car.stl
Export car-parts.zip
Quit
```

The two axles run across the chassis, through bores sized for them. The
wheelbase is the distance between the front and rear axles. MAGTEL places the
wheels on the axle ends and checks for overlap, axle reach, bore clearance, and
ground clearance. The chassis dimensions are length × width × height.

Use `car.stl` to inspect the assembled geometry. Use `car-parts.zip` for
separate STLs. The bundle includes one chassis design, one axle design to print
twice, and one wheel design to print four times. The wheels use a slip fit.
Plan how to retain them on the axles and test the clearances on your printer.

Reopen the design with `magtel workshop car.magtel.json`, then try
`Move the axles 58 mm apart` or `Leave 2 mm between each wheel and the chassis`.
`Set axle clearance to 0.4 mm` sets the difference in diameter between the
chassis bores and the axles. You can also reuse a saved part with
`Use the wheels from "wheel.magtel.json"`, `Use the axles from "axle.magtel.json"`,
or `Use the chassis from "block.magtel.json"`. Use a plain block for the chassis
and an axle long enough to reach through both wheels.

For one command, separate the requests with semicolons inside the quotation
marks:

```sh
magtel assemble "Use an 80 x 30 x 12 mm chassis; mount two 5.8 mm diameter, 60 mm long axles 55 mm apart; put a 40 mm wheel, 10 mm thick, with a 6 mm hole on each end" -o car.magtel.json
magtel fit car.magtel.json
magtel export car.magtel.json -o car-parts.zip
```

Or open the [example car](examples/toy-car.magtel.json) with
`magtel workshop examples/toy-car.magtel.json` from the source folder.

## Inspect a design in 3D

Type `Preview it` in the workshop to open the current model in your browser.
Drag to orbit, scroll to zoom, and use the **Explode** slider on a car to
separate the chassis, axles, and wheels. The viewer also has keyboard and
on-screen controls.

Open a saved part or car from the terminal:

```sh
magtel preview car.magtel.json
```

Use `magtel preview car.magtel.json -o car.html` or type `Preview car.html` in
the workshop to save a standalone viewer you can share. It opens offline and
shows a snapshot of the design. Preview again after an edit to see the new
geometry. Keep the MAGTEL JSON to make further edits.

## Run it from scripts

```sh
magtel "Make a wheel 40 mm across with a 6 mm hole" -o wheel.magtel.json
magtel edit wheel.magtel.json "Make it 45 mm across" -o wide-wheel.magtel.json
magtel "Make an axle 5.8 mm in diameter and 24 mm long" -o axle.magtel.json
magtel fit wide-wheel.magtel.json axle.magtel.json
magtel export wide-wheel.magtel.json -o wide-wheel.stl
magtel "Make a 40 x 20 x 10 mm block with 2 x 3 studs" -o block.magtel.json
magtel export block.magtel.json -o block.stl
```

`fit` reports the nominal diameter difference between the axle and hole. It
returns 0 when there is clearance, 1 for equal diameters or interference, and
2 for an invalid request or unreadable file. Actual printed fit depends on your
printer, material, and print settings.

## What MAGTEL understands

| Part | Editable parameters |
| --- | --- |
| Wheel | Outside diameter, thickness, centered through-hole diameter or solid center |
| Axle | Diameter and length |
| Block | Width, depth, height, and an optional grid of round studs with editable diameter and height |

Try `Make a wheel` to see the default dimensions or `Make it 5 mm wider` to
change one dimension in the workshop. Dimensions default to millimeters.
Centimeters and inches are accepted and converted to millimeters. Block
dimensions follow width × depth × height. Stud counts follow columns × rows.
The studs are solid posts fused to the top of a flat-bottomed block.

Version 0.3 uses a fixed vocabulary, part families, and a symmetric four-wheel
car assembly. Both axles share one design and all four wheels share one design.
Unsupported descriptions return an error and leave the current design intact.
The release exports
triangulated STL and versioned MAGTEL JSON. Freeform sketches, custom joints
between arbitrary parts, drawings, STEP export, and SOLIDWORKS file import are
outside this release.

## Contributing

Run `python -m unittest discover -s tests -v` after installing the project. The
language parser converts a request into validated part parameters. Geometry is
built from those parameters, so an edit regenerates the shape. Changes to
supported language should include examples and rejection cases.

MAGTEL is an independent implementation. Public SOLIDWORKS documentation on
[extrusions and cuts](https://help.solidworks.com/2026/english/SolidWorks/sldworks/r_extrude_propertymanager.htm?format=P)
served as a reference for general CAD concepts. All MAGTEL code is released
under the [MIT License](LICENSE).
