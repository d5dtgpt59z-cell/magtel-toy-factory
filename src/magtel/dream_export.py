"""Prepare the Dream viewport, printable invention sheet, and loose STL bundle."""

from __future__ import annotations

import io
import json
import math
import struct
import zlib
from base64 import b64encode
from html import escape
from zipfile import ZIP_DEFLATED, ZipFile

from .dream_model import DreamSpec
from .mesh import stl_bytes
from .model import mm
from .preview import preview_html

LIMITS = (
    "Nominal geometry only. Choose a material and check slicer settings, fit, and strength "
    "on physical prototypes. The slip-fit wheels need "
    "a separate retention method. This sheet does not establish product or child safety."
)
_RIGHT = (0.64, 0.7684, 0.0)
_UP = (-0.3611, 0.3008, 0.8827)
_VIEW = (0.6783, -0.5649, 0.4695)
_LIGHT = (0.26, -0.44, 0.86)


def studio_data(spec: DreamSpec) -> dict[str, object]:
    design = spec.design
    diameter = design["wheel_diameter"]
    wheel_travel = max(diameter / 2, design["axle_length"] / 2 - design["width"] / 2
                       - design["wheel_gap"] + diameter * 0.1)
    chassis_lift = (design["height"] + design["axle_diameter"]) / 2 + diameter / 4

    parts = []
    for key, triangles in spec.components().items():
        kind = key.split("-")[-1]
        part = {"id": key}
        if module := spec.body_modules.get(key):
            part.update({
                "name": module.name,
                "kind": "body",
                "role": module.role,
                "dimensions": spec.body_dimensions(key),
                "color": design["body_colors"][module.role],
            })
            top = (diameter + design["height"]) / 2
            bottom = min(point[2] for face in triangles for point in face)
            stacked = bottom > top + 1e-6
            offset = (0, 0, chassis_lift + diameter * (1.1 if stacked else 0.5))
        else:
            part.update({"name": key.replace("-", " ").title(), "color": design["colors"][kind]})
            if kind == "wheel":
                offset = (0, wheel_travel if "-left-" in key else -wheel_travel, 0)
            elif kind == "chassis":
                offset = (0, 0, chassis_lift)
            else:
                offset = (0, 0, 0)
        part.update({
            "vertices": [round(coord, 6) for face in triangles for point in face for coord in point],
            "explode": offset,
        })
        parts.append(part)

    return {
        "design": design,
        "parts": parts,
        "dimensions": spec.dimensions(),
        "fit": spec.fit(),
        "bom": spec.bom(),
    }


def dream_preview_html(spec: DreamSpec, data: dict | None = None) -> str:
    data = studio_data(spec) if data is None else data
    return preview_html({
        "title": spec.design["name"],
        "description": spec.describe(),
        "assembly": True,
        "parts": [{**part, "color": [channel / 255 for channel in _rgb(part["color"])]}
                  for part in data["parts"]],
    })


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _dot(point: tuple, axis: tuple) -> float:
    return sum(a * b for a, b in zip(point, axis))


def _cross(ab: tuple, ac: tuple) -> tuple:
    return (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0])


def _paint_triangle(pixels, depths, width, height, points, color):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points
    denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(denominator) < 1e-9:
        return
    dx_a = (by - cy) / denominator
    dx_b = (cy - ay) / denominator
    dy_a = (cx - bx) / denominator
    dy_b = (ax - cx) / denominator
    left, right = max(0, math.floor(min(ax, bx, cx))), min(width, math.ceil(max(ax, bx, cx)))
    top, bottom = max(0, math.floor(min(ay, by, cy))), min(height, math.ceil(max(ay, by, cy)))
    for y in range(top, bottom):
        u = (left + 0.5 - cx) * dx_a + (y + 0.5 - cy) * dy_a
        v = (left + 0.5 - cx) * dx_b + (y + 0.5 - cy) * dy_b
        index = y * width + left
        for _ in range(left, right):
            if u >= -1e-8 and v >= -1e-8 and u + v <= 1 + 1e-8:
                depth = cz + u * (az - cz) + v * (bz - cz)
                if depth > depths[index]:
                    depths[index] = depth
                    pixels[index * 3:index * 3 + 3] = color
            index += 1
            u += dx_a
            v += dx_b


def _png(pixels, width, height):
    def chunk(kind, content):
        return (struct.pack(">I", len(content)) + kind + content
                + struct.pack(">I", zlib.crc32(kind + content)))

    stride = width * 3
    rows = b"".join(b"\0" + pixels[i:i + stride] for i in range(0, len(pixels), stride))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows))
            + chunk(b"IEND", b""))


def _render(parts: list[dict], *, exploded: bool, axes=(_RIGHT, _UP, _VIEW),
            drawing_scale: float | None = None) -> bytes:
    """Shade the actual mesh with orthographic projection and per-pixel depth."""
    right, up, view = axes
    projected = []
    guide_lines = []
    for part in parts:
        vertices = part["vertices"]
        offset = part["explode"] if exploded else (0, 0, 0)
        color = _rgb(part["color"])
        for i in range(0, len(vertices), 9):
            a, b, c = [tuple(vertices[j + axis] + offset[axis] for axis in range(3))
                       for j in (i, i + 3, i + 6)]
            ab = tuple(y - x for x, y in zip(a, b))
            ac = tuple(y - x for x, y in zip(a, c))
            normal = _cross(ab, ac)
            if _dot(normal, view) <= 1e-12:
                continue
            light = 0.61 + 0.39 * max(0, _dot(normal, _LIGHT) / math.hypot(*normal))
            fill = bytes(round(channel * light) for channel in color)
            points = [(_dot(p, right), -_dot(p, up), _dot(p, view)) for p in (a, b, c)]
            projected.append((points, fill))
        if exploded and any(offset):
            center = tuple((min(vertices[axis::3]) + max(vertices[axis::3])) / 2 for axis in range(3))
            end = tuple(x + dx for x, dx in zip(center, offset))
            guide_lines.append([(_dot(p, right), -_dot(p, up), 0) for p in (center, end)])

    xs, ys, _ = zip(*(point for points, _ in projected for point in points))
    xmid, ymid = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    width, height = 900, 500
    scale = drawing_scale or min((width - 110) / (max(xs) - min(xs)), (height - 82) / (max(ys) - min(ys)))

    def position(point):
        x, y, z = point
        return width / 2 + (x - xmid) * scale, height / 2 + (y - ymid) * scale, z

    pixels = bytearray(bytes((242, 244, 238)) * (width * height))
    depths = [-math.inf] * (width * height)
    for start, end in guide_lines:
        ax, ay, _ = position(start)
        bx, by, _ = position(end)
        distance = max(1, math.ceil(math.hypot(bx - ax, by - ay)))
        for i in range(distance):
            if i % 12 < 6:
                x, y = round(ax + i / distance * (bx - ax)), round(ay + i / distance * (by - ay))
                if 0 <= x < width and 0 <= y < height:
                    index = (y * width + x) * 3
                    pixels[index:index + 3] = b"\x83\x94\x89"
    for points, color in projected:
        _paint_triangle(pixels, depths, width, height, [position(point) for point in points], color)
    return _png(pixels, width, height)


def _orthographic_drawing(data: dict) -> str:
    """Project the assembled mesh at one common scale and dimension its envelope."""
    length, width, height = (data["dimensions"][axis] for axis in ("length", "width", "height"))
    scale = min(790 / length, 418 / max(width, height))
    ratio = 0.52
    views = (
        ("SIDE VIEW", height, ((1, 0, 0), (0, 0, 1), (0, -1, 0))),
        ("TOP VIEW", width, ((1, 0, 0), (0, 1, 0), (0, 0, 1))),
    )
    title = escape(data["design"]["name"])
    panels = []
    for index, (label, cross, axes) in enumerate(views):
        left = 28 + index * 528
        cx, cy = left + 450 * ratio, 211
        half_length, half_cross = length * scale * ratio / 2, cross * scale * ratio / 2
        x1, x2, y1, y2 = cx - half_length, cx + half_length, cy - half_cross, cy + half_cross
        h, v = 360, left + 485
        render = _render(data["parts"], exploded=False, axes=axes, drawing_scale=scale)
        src = b64encode(render).decode("ascii")
        panels.append(f"""
  <g>
    <text class="label" x="{left}" y="67">{label}</text>
    <image x="{left}" y="{cy - 250 * ratio}" width="{900 * ratio}" height="{500 * ratio}"
           href="data:image/png;base64,{src}"/>
    <path class="extension" d="M{x1} {y2}V{h + 7} M{x2} {y2}V{h + 7} M{x2} {y1}H{v + 7} M{x2} {y2}H{v + 7}"/>
    <path class="dim" d="M{x1} {h}H{x2}"/>
    <path class="dim" d="M{v} {y1}V{y2}"/>
    <text class="number" x="{cx}" y="{h + 20}">{mm(length)} mm</text>
    <text class="number" x="{v + 16}" y="{cy}" transform="rotate(-90 {v + 16} {cy})">{mm(cross)} mm</text>
  </g>""")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 440" role="img" aria-labelledby="title">
  <title id="title">{title} orthographic envelope drawing</title>
  <style>
    text{{fill:#22352b;font-family:system-ui,sans-serif}} .label{{font-size:12px;font-weight:bold;letter-spacing:1px}}
    .number{{font-size:12px;font-weight:bold;text-anchor:middle}}
    .extension,.dim{{fill:none;stroke:#62766a;stroke-width:1}}
    .dim{{marker-start:url(#arrow);marker-end:url(#arrow)}}
  </style>
  <defs><marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M0 0L8 4L0 8Z" fill="#62766a"/>
  </marker></defs>
  <rect x="1" y="1" width="1078" height="438" fill="#fffdf8" stroke="#aab6ac"/>
  <text x="28" y="31" font-size="22" font-weight="bold">{title}</text>
  {"".join(panels)}
  <path d="M28 401H1052" stroke="#aab6ac"/>
  <text class="label" x="28" y="423">MAGTEL / ORTHOGRAPHIC ENVELOPE</text>
  <text x="1052" y="423" text-anchor="end" font-size="12">Matched view scale · nominal dimensions · use labeled values</text>
</svg>"""


def _sheet_html(data: dict, hero: bytes, exploded: bytes) -> str:
    design = data["design"]
    name = escape(design["name"])
    prompt = escape(design["prompt"])
    hero_src, exploded_src = (b64encode(png).decode("ascii") for png in (hero, exploded))
    dims = " × ".join(mm(data["dimensions"][axis]) for axis in ("length", "width", "height"))
    notes = "".join(f"<li>{escape(note)}</li>" for note in design["notes"])
    variant = escape(design.get("variant") or "Original build")
    mount = _mount_note(data["design"])
    rows = []
    for entry in data["bom"]:
        part = entry["part"]
        rows.append(f'<tr><th scope="row"><span style="background:{entry["color"]}"></span>'
                    f'{escape(entry["name"])}</th><td>{entry["quantity"]}</td>'
                    f'<td>{escape(entry["dimensions"])}</td><td>{escape(entry["material"])}</td>'
                    f'<td><a href="stl/{part}.stl">{part}.stl</a></td></tr>')
    fit_labels = {
        "wheel_bore_clearance": "Wheel bore clearance across",
        "chassis_bore_clearance": "Chassis bore clearance across",
        "wheel_gap": "Wheel gap per side",
        "axle_overhang": "Axle overhang per side",
        "ground_clearance": "Ground clearance",
    }
    fits = "".join(f"<li>{label} <strong>{mm(data['fit'][key])} mm</strong></li>"
                   for key, label in fit_labels.items())
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} | MAGTEL Invention Sheet</title>
<style>
*{{box-sizing:border-box}} body{{background:#e9ede5;color:#202720;font:15px/1.45 system-ui,sans-serif;margin:0}}
main{{max-width:1080px;margin:22px auto;padding:32px;background:#fffdf8;border:1px solid #ccd2c6}}
header{{display:flex;justify-content:space-between;align-items:start;gap:16px;border-top:5px solid #23352b;padding-top:12px}}
.tag,figcaption{{font:700 11px/1.3 ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase}}
h1{{font-size:clamp(28px,5vw,58px);line-height:1;margin:.3em 0;overflow-wrap:anywhere}}
h2{{font-size:16px;margin:1.1em 0 .5em}} p{{margin:.4em 0 .8em;overflow-wrap:anywhere}}
.figures,.info{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} figure{{margin:0}}
img{{display:block;width:100%;height:auto;border:1px solid #ccd2c6}} figcaption{{padding:7px 0;border-bottom:1px solid #ccd2c6}}
a{{color:#214b38}} table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{padding:6px;text-align:left;border-bottom:1px solid #d7dccf}}
th span{{display:inline-block;width:9px;height:9px;margin-right:6px;border:1px solid #576257}}
ul{{margin:.35em 0;padding-left:1.2em;overflow-wrap:anywhere}} footer{{border-top:1px solid #b8c0b2;padding-top:10px;margin-top:14px;font-size:12px}}
button{{font:inherit;color:#fff;background:#23352b;padding:8px 12px;border:0;cursor:pointer;flex:none}}
.scroll{{overflow-x:auto}} .dim{{font-variant-numeric:tabular-nums}}
@media(max-width:600px){{main{{margin:0;padding:16px}} .info{{grid-template-columns:1fr}}}}
@page{{size:landscape;margin:11mm}}
@media print{{
  body{{background:#fff;font-size:10px;line-height:1.3;print-color-adjust:exact;-webkit-print-color-adjust:exact}}
  main{{padding:0;margin:0;border:0;max-width:none}} button{{display:none}}
  h1{{font-size:28px;margin:.22em 0}} h2{{font-size:13px;margin:.75em 0 .35em}}
  figure img{{height:172px;object-fit:contain;background:#f2f4ee}}
  th,td{{font-size:10px;padding:3px 5px}} footer{{font-size:9px;margin-top:8px;padding-top:4px}}
  figure,table,footer{{break-inside:avoid}}
}}
</style>
<main>
<header><div class="tag">MAGTEL Toy Factory / Invention Sheet</div><button type="button" onclick="window.print()">Print or save PDF</button></header>
<h1>{name}</h1>
<p>{prompt}</p>
<p class="dim"><strong>{dims} mm</strong> · Overall length × width × height · {variant}</p>
<div class="figures">
<figure><img alt="Assembled prototype" src="data:image/png;base64,{hero_src}"><figcaption>01 / Assembled</figcaption></figure>
<figure><img alt="Exploded assembly" src="data:image/png;base64,{exploded_src}"><figcaption>02 / Exploded</figcaption></figure>
</div>
<h2>Prototype bill of materials</h2>
<div class="scroll"><table>
<thead><tr><th scope="col">Part</th><th scope="col">Qty</th><th scope="col">Dimensions</th><th scope="col">Material</th><th scope="col">File</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<div class="info">
<section><h2>Nominal fit</h2><ul>{fits}</ul></section>
<section><h2>Prototype notes</h2><p>Slide each axle through a chassis bore, then fit a wheel on each end. {mount}</p><ul>{notes}</ul></section>
</div>
<footer><p>{LIMITS}</p><a href="preview.html">Interactive offline 3D preview</a> ·
<a href="design.magtel.json">Editable design</a> · <a href="orthographic.svg">Orthographic drawing</a> · Use millimeters in your slicer.</footer>
</main>
</html>
"""


def _mount_note(design: dict) -> str:
    if design["body_style"] == "plain":
        return ""
    return ("Body pieces are separate prints with flat contact faces. Use the exploded view for placement "
            "and secure them with a suitable adhesive or retainer before handling.")


def invention_bundle(spec: DreamSpec) -> bytes:
    """Build a self-contained zip with the sheet, preview, design and printable meshes."""
    data = studio_data(spec)
    hero = _render(data["parts"], exploded=False)
    exploded = _render(data["parts"], exploded=True)
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("invention-sheet.html", _sheet_html(data, hero, exploded))
        archive.writestr("hero.png", hero)
        archive.writestr("exploded.png", exploded)
        archive.writestr("orthographic.svg", _orthographic_drawing(data))
        archive.writestr("preview.html", dream_preview_html(spec, data))
        archive.writestr("design.magtel.json", json.dumps(spec.design, ensure_ascii=False, indent=2) + "\n")
        for part, faces in spec.part_meshes().items():
            archive.writestr(f"stl/{part}.stl", stl_bytes(faces))
        instructions = "\n".join(f'{item["quantity"]} × stl/{item["part"]}.stl' for item in data["bom"])
        archive.writestr("START HERE.txt", f"""Extract the entire zip, then open invention-sheet.html.

STL coordinates are in millimeters. Print these quantities for one prototype:
{instructions}

{_mount_note(spec.design)}
{LIMITS}
""")
    return output.getvalue()
