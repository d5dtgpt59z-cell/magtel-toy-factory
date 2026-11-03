# MAGTEL Toy Factory

Tell MAGTEL what part you want, then change your mind in the same conversation.
MAGTEL reads back the dimensions, saves an editable part, and can export an STL
for your 3D printer's slicer. The CLI runs locally with no API key, model download,
or runtime dependencies.

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

Version 0.1 uses a fixed vocabulary and part families. Unsupported descriptions
return an error and leave the current part intact. The release exports
triangulated STL and versioned MAGTEL JSON. Freeform sketches, general assemblies,
drawings, STEP export, and SOLIDWORKS file import are outside this release.

## Contributing

Run `python -m unittest discover -s tests -v` after installing the project. The
language parser converts a request into validated part parameters. Geometry is
built from those parameters, so an edit regenerates the shape. Changes to
supported language should include examples and rejection cases.

MAGTEL is an independent implementation. Public SOLIDWORKS documentation on
[extrusions and cuts](https://help.solidworks.com/2026/english/SolidWorks/sldworks/r_extrude_propertymanager.htm?format=P)
served as a reference for general CAD concepts. All MAGTEL code is released
under the [MIT License](LICENSE).
