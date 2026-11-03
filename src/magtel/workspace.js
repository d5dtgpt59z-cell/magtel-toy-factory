"use strict";

const byId = id => document.getElementById(id);
const viewer = byId("viewer");
const dimensions = byId("dimensions");
const partPicker = byId("part-picker");
const featurePicker = byId("feature-picker");
const finishPicker = byId("finish-picker");
const partColor = byId("part-color");
const undoButton = byId("undo");
const redoButton = byId("redo");
const discardButton = byId("discard-edits");
const artFiles = byId("art-files");
const projectFile = byId("project-file");
const brief = byId("brief");
const dropzone = byId("dropzone");
const maxImageBytes = 16 * 1024 * 1024;
const maxTotalBytes = 32 * 1024 * 1024;
const maxHistoryEntries = 50;
const carFormat = "magtel-assembly";

const references = [];
const undoHistory = [];
const redoHistory = [];
let currentRecipe = null;
let draft = null;
let measurements = [];
let camera = null;
let carPose = null;
let fitReport = "";
let busy = "";
let dirty = false;
let composing = false;
let submittedBuild = false;

function isCar() {
  return currentRecipe?.format === carFormat;
}

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function setStatus(id, message, error = false) {
  const status = byId(id);
  if (status.textContent !== message) status.textContent = message;
  status.classList.toggle("error", error);
}

function refreshControls() {
  const working = Boolean(busy);
  const canExport = !working && currentRecipe && !dirty;
  const hasBrief = Boolean(brief.value.trim());
  byId("generate").disabled = working || !hasBrief;
  byId("brief-help").textContent = hasBrief
    ? "Include any important dimensions."
    : "Type a description to enable Generate model.";
  byId("rebuild").disabled = working || !dirty || !draft;
  undoButton.disabled = working || dirty || !undoHistory.length;
  redoButton.disabled = working || dirty || !redoHistory.length;
  discardButton.disabled = working;
  discardButton.hidden = !dirty;
  byId("new-build").disabled = working;
  byId("return-fit").disabled = working;
  byId("load-car").disabled = working;
  byId("load-gripper").disabled = working;
  byId("load-demo").disabled = working;
  byId("open-project").disabled = working;
  byId("save-project").disabled = !canExport;
  byId("save-step").disabled = !canExport || isCar();
  byId("save-part").disabled = !canExport || !isCar();
  byId("save-parts").disabled = !canExport || !isCar();
  byId("check-fit").disabled = working || !isCar();
  dropzone.disabled = working;
  brief.readOnly = busy === "generate";
  for (const input of dimensions.querySelectorAll("input, select")) input.disabled = working;
  for (const remove of document.querySelectorAll(".remove")) remove.disabled = working;

  const state = byId("model-state");
  const activity = {
    demo: "Loading example",
    car: "Loading toy car",
    gripper: "Loading robot gripper",
    generate: "Generating",
    rebuild: "Rebuilding",
    undo: "Undoing",
    redo: "Redoing",
    open: "Opening project",
    step: "Exporting STEP",
    fit: "Checking fit",
    stl: "Exporting STL",
    parts: "Packing parts",
  };
  state.textContent = activity[busy] || (dirty ? "Edits pending" : currentRecipe ? "Model ready" : "No model");
  state.classList.toggle("busy", working);
  state.classList.toggle("dirty", dirty);
  byId("frame-area").setAttribute("aria-busy", String(working));
}

function renderReferences() {
  const list = byId("references");
  list.replaceChildren();
  list.hidden = references.length === 0;
  byId("reference-count").textContent = references.length + " / 4";
  for (const [index, reference] of references.entries()) {
    const item = node("li");
    const thumbnail = node("img");
    thumbnail.src = reference.url;
    thumbnail.alt = "";
    const filename = node("span", reference.file.name);
    filename.title = reference.file.name;
    const remove = node("button", "×", "remove");
    remove.type = "button";
    remove.setAttribute("aria-label", "Remove " + reference.file.name);
    remove.addEventListener("click", () => {
      submittedBuild = false;
      references.splice(index, 1);
      URL.revokeObjectURL(reference.url);
      setStatus("art-status", "");
      renderReferences();
      dropzone.focus();
    });
    item.append(thumbnail, filename, remove);
    list.append(item);
  }
  refreshControls();
}

function addFiles(files) {
  if (busy) return;
  let total = references.reduce((size, reference) => size + reference.file.size, 0);
  const errors = [];
  for (const file of files) {
    if (!/\.(png|jpe?g|webp)$/i.test(file.name)) {
      errors.push("Choose PNG, JPEG or WebP images.");
      continue;
    }
    if (references.some(({file: previous}) =>
      previous.name === file.name && previous.size === file.size && previous.lastModified === file.lastModified
    )) continue;
    if (references.length === 4) {
      errors.push("Attach up to four images.");
      break;
    }
    if (!file.size || file.size > maxImageBytes || total + file.size > maxTotalBytes) {
      errors.push("Use images up to 16 MiB each and 32 MiB total.");
      continue;
    }
    total += file.size;
    submittedBuild = false;
    references.push({file, url: URL.createObjectURL(file)});
  }
  setStatus("art-status", [...new Set(errors)].join(" "), errors.length > 0);
  renderReferences();
}

dropzone.addEventListener("click", () => artFiles.click());
artFiles.addEventListener("change", () => {
  addFiles(artFiles.files);
  artFiles.value = "";
});
dropzone.addEventListener("dragover", event => {
  event.preventDefault();
  event.dataTransfer.dropEffect = busy ? "none" : "copy";
  if (!busy) dropzone.classList.add("is-over");
});
dropzone.addEventListener("dragleave", event => {
  if (!dropzone.contains(event.relatedTarget)) dropzone.classList.remove("is-over");
});
dropzone.addEventListener("drop", event => {
  event.preventDefault();
  dropzone.classList.remove("is-over");
  addFiles(event.dataTransfer.files);
});
for (const type of ["dragover", "drop"]) {
  document.addEventListener(type, event => {
    if (event.dataTransfer.types.includes("Files")) event.preventDefault();
  });
}
brief.addEventListener("input", () => {
  submittedBuild = false;
  refreshControls();
});

function base64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(reader.result.split(",", 2)[1]), {once: true});
    reader.addEventListener("error", () => reject(new Error("Could not read " + file.name + ".")), {once: true});
    reader.readAsDataURL(file);
  });
}

async function request(path, data, binary = false) {
  const response = await fetch(path, data === undefined ? undefined : {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    let message = "The workspace could not finish this operation.";
    try {
      const result = await response.json();
      if (typeof result.error === "string") message = result.error;
    } catch {
      // Keep the default message if the service returned a non-JSON response.
    }
    throw new Error(message);
  }
  return binary ? response.blob() : response.json();
}

async function run(action, status, pendingMessage, operation) {
  if (busy) return;
  busy = action;
  setStatus(status, pendingMessage);
  refreshControls();
  try {
    await operation();
  } catch (error) {
    setStatus(status, error.message || "The workspace operation failed.", true);
    if (!currentRecipe) {
      byId("empty-view").querySelector("strong").textContent = "No model loaded";
      byId("empty-view").querySelector("p").textContent = "Describe a part, load an example, or open a project.";
    }
  } finally {
    busy = "";
    refreshControls();
  }
}

function addOption(select, value, text) {
  const option = node("option", text);
  option.value = String(value);
  select.append(option);
}

function measurePart() {
  const sizes = measurements[Number(partPicker.value)]?.size || [];
  const measured = byId("measured");
  measured.replaceChildren();
  for (const [index, axis] of ["X", "Y", "Z"].entries()) {
    const block = node("div");
    const size = sizes[index];
    block.append(node("dt", axis + " · mm"), node("dd", Number.isFinite(size)
      ? new Intl.NumberFormat("en", {maximumFractionDigits: 3, useGrouping: false}).format(size)
      : "—"));
    measured.append(block);
  }
}

function markEdit() {
  dirty = JSON.stringify(draft) !== JSON.stringify(currentRecipe);
  setStatus("dimension-status", dirty
    ? "Rebuild or discard pending edits to use model history."
    : "Measurements reflect the last successful build.");
  if (isCar()) showCommittedFit();
  refreshControls();
}

function numberField(label, value, onEdit, positive = false) {
  const field = node("label");
  const input = node("input");
  input.type = "number";
  input.step = "any";
  input.required = true;
  if (positive) input.min = "0.0001";
  input.value = Number.isFinite(value) ? value : "";
  input.addEventListener("input", () => {
    onEdit(Number.isFinite(input.valueAsNumber) ? input.valueAsNumber : null);
    markEdit();
  });
  field.append(node("span", label), input);
  return field;
}

function numberRow(values, labels, positive = false) {
  const row = node("div", undefined, "number-row" + ([2, 4].includes(labels.length) ? " two" : ""));
  for (const [index, label] of labels.entries()) {
    row.append(numberField(label, values[index], value => { values[index] = value; }, positive));
  }
  return row;
}

function editSection(title, contents, open) {
  const details = node("details");
  details.dataset.section = title;
  details.open = open;
  details.append(node("summary", title), contents);
  return details;
}

function pointsEditor(points) {
  const list = node("div", undefined, "point-list");
  for (const [index, point] of points.entries()) {
    const row = numberRow(point, ["Point " + (index + 1) + " X", "Point " + (index + 1) + " Y"]);
    list.append(row);
  }
  return list;
}

const kinds = {
  box: "Box", rounded_box: "Rounded box", chamfer_box: "Beveled box",
  cylinder: "Cylinder", extrude: "Extrusion", loft: "Loft",
};
const sizeLabels = {
  box: ["Width X", "Depth Y", "Height Z"],
  rounded_box: ["Width X", "Depth Y", "Height Z", "Edge radius"],
  chamfer_box: ["Width X", "Depth Y", "Height Z", "Bevel"],
  cylinder: ["Radius", "Height"],
  extrude: ["Height"],
};
const carPartFields = {
  chassis: [["width", "Length"], ["depth", "Width"], ["height", "Height"]],
  axle: [["diameter", "Diameter"], ["thickness", "Length"]],
  wheel: [["diameter", "Diameter"], ["thickness", "Thickness"], ["hole", "Bore diameter"]],
};
const carAssemblyFields = [
  ["wheelbase", "Wheelbase"], ["wheel_gap", "Side gap"], ["axle_clearance", "Bore clearance"],
];

function carNumberRow(values, fields) {
  const row = node("div", undefined, "number-row" + (fields.length === 2 ? " two" : ""));
  for (const [key, label] of fields) {
    row.append(numberField(label, values[key], value => { values[key] = value; }, true));
  }
  return row;
}

function renderCarPart(kind) {
  const fields = byId("fields");
  fields.replaceChildren(node("h3", "Size (mm)"), carNumberRow(draft.assembly[kind], carPartFields[kind]));
  if (kind === "wheel" || kind === "axle") {
    fields.append(node("p", kind === "wheel" ? "All four wheels share these dimensions." :
      "Both axles share these dimensions.", "hint"));
  }
  byId("save-part").textContent = "Download " + kind + " STL";
}

function renderCarSettings() {
  const fields = byId("assembly-fields");
  if (!isCar()) {
    fields.replaceChildren();
    return;
  }
  fields.replaceChildren(
    carNumberRow(draft.assembly, carAssemblyFields),
    node("p", "All values are in mm. Side gap is per wheel. Bore clearance is added to the axle diameter.", "hint"),
  );
}

function showFit(report, label, message) {
  const readout = byId("fit-report");
  if (readout.dataset.report !== report) {
    const rows = [];
    for (const line of report.split("\n").slice(1)) {
      const [metric, value] = line.trim().split(" — ", 2);
      if (!value) continue;
      const row = node("div");
      row.append(node("dt", metric), node("dd", value));
      rows.push(row);
    }
    readout.replaceChildren(...rows);
    readout.dataset.report = report;
  }
  byId("fit-tag").textContent = label;
  setStatus("fit-status", message);
}

function showCommittedFit() {
  showFit(fitReport, dirty ? "Last build" : "Nominal", dirty
    ? "Showing the last build. Check fit to test pending edits."
    : "The current build passes the nominal fit checks.");
}

function renderFeature(keepOpen = false) {
  const fields = byId("fields");
  const openSections = new Set(keepOpen
    ? Array.from(fields.querySelectorAll("details[open]"), details => details.dataset.section)
    : []);
  const previousLoftSection = keepOpen ? Number(fields.querySelector("#loft-section")?.value) : 0;
  fields.replaceChildren();
  const feature = draft.parts[Number(partPicker.value)].features[Number(featurePicker.value)];
  if (sizeLabels[feature.kind]) {
    fields.append(node("h3", "Size (mm)"), numberRow(feature.size, sizeLabels[feature.kind], true));
  } else {
    fields.append(node("p", "A loft follows its section heights and outlines.", "hint"));
  }

  const placement = node("div");
  placement.append(
    node("h3", "Position (mm)"), numberRow(feature.position, ["Position X", "Position Y", "Position Z"]),
    node("h3", "Rotation (deg)"), numberRow(feature.rotation, ["Rotation X", "Rotation Y", "Rotation Z"]),
  );
  fields.append(editSection("Position & rotation", placement, openSections.has("Position & rotation")));

  if (feature.kind === "extrude") {
    fields.append(editSection("Profile points (mm)", pointsEditor(feature.profile),
      openSections.has("Profile points (mm)")));
  }
  if (feature.kind === "loft") {
    const loft = node("div");
    const label = node("label", undefined, "picker");
    const select = node("select");
    select.id = "loft-section";
    for (const index of feature.sections.keys()) addOption(select, index, "Section " + (index + 1));
    select.value = String(feature.sections[previousLoftSection] ? previousLoftSection : 0);
    label.append(node("span", "Loft section", "field-label"), select);
    const sectionFields = node("div");
    const renderSection = () => {
      const section = feature.sections[Number(select.value)];
      const heightRow = node("div", undefined, "number-row");
      heightRow.append(numberField("Section height Z", section.z, value => { section.z = value; }));
      sectionFields.replaceChildren(heightRow, pointsEditor(section.profile));
    };
    select.addEventListener("change", renderSection);
    renderSection();
    loft.append(label, sectionFields);
    fields.append(editSection("Loft sections (mm)", loft, openSections.has("Loft sections (mm)")));
  }
}

function renderPart(featureIndex = 0, keepOpen = false) {
  const index = Number(partPicker.value);
  measurePart();
  if (isCar()) {
    renderCarPart(measurements[index].kind);
    return;
  }
  const part = draft.parts[index];
  finishPicker.value = part.finish ?? "polymer";
  partColor.value = part.color;
  featurePicker.replaceChildren();
  for (const [index, feature] of part.features.entries()) {
    addOption(featurePicker, index,
      (index + 1) + " · " + (feature.operation === "cut" ? "Cut" : "Add") + " " + kinds[feature.kind].toLowerCase());
  }
  featurePicker.value = String(part.features[featureIndex] ? featureIndex : 0);
  renderFeature(keepOpen);
}

function sendSelectedPart() {
  viewer.contentWindow.postMessage({type: "magtel-select-part", index: Number(partPicker.value)}, "*");
}

partPicker.addEventListener("change", () => {
  renderPart();
  sendSelectedPart();
});
featurePicker.addEventListener("change", () => renderFeature());
finishPicker.addEventListener("change", () => {
  const index = Number(partPicker.value);
  const part = draft.parts[index];
  if (finishPicker.value === "polymer" && currentRecipe.parts[index].finish === undefined) {
    delete part.finish;
  } else {
    part.finish = finishPicker.value;
  }
  markEdit();
});
partColor.addEventListener("input", () => {
  draft.parts[Number(partPicker.value)].color = partColor.value;
  markEdit();
});

function renderSource() {
  const showFit = isCar() && !composing;
  byId("source-title").textContent = showFit ? "Assembly fit" : "Build brief";
  byId("generate-form").hidden = showFit;
  byId("car-fit").hidden = !showFit;
  byId("fit-tag").hidden = !showFit;
  byId("return-fit").hidden = !isCar();
}

function applyModel(payload, preserve = false) {
  const previousPart = preserve ? Number(partPicker.value) : 0;
  const previousFeature = preserve ? Number(featurePicker.value) : 0;
  currentRecipe = payload.recipe;
  draft = structuredClone(currentRecipe);
  measurements = payload.parts;
  dirty = false;
  if (!preserve) {
    composing = false;
    camera = null;
    carPose = null;
    undoHistory.length = 0;
    redoHistory.length = 0;
    byId("car-settings").open = false;
  }

  const car = isCar();
  byId("workspace-kicker").textContent = car ? "Assembly workshop" : "Part design";
  byId("workspace-title").textContent = car ? "Toy car assembly" : "Design workspace";
  byId("workspace-description").textContent = car
    ? "Select a part in the viewport, test its fit, and download it for printing."
    : "Describe a part, then refine the geometry in place. Reference art is optional.";
  renderSource();
  byId("surface-fields").hidden = car;
  byId("feature-selection").hidden = car;
  byId("car-settings").hidden = !car;
  byId("save-step").hidden = car;
  byId("save-part").hidden = !car;
  byId("save-parts").hidden = !car;
  byId("format-note").textContent = car ? "Editable assembly · STL parts" : "Editable CAD projects · STEP exchange";

  byId("empty-view").hidden = true;
  viewer.hidden = false;
  viewer.srcdoc = payload.viewer;
  byId("model-name").textContent = car ? currentRecipe.assembly.name : currentRecipe.name;
  const count = measurements.length;
  byId("part-count").textContent = count + (count === 1 ? " part" : " parts") + " · mm";
  byId("empty-inspector").hidden = true;
  dimensions.hidden = false;

  partPicker.replaceChildren();
  for (const [index, part] of measurements.entries()) addOption(partPicker, index, part.name);
  partPicker.value = String(measurements[previousPart] ? previousPart : 0);
  renderPart(previousFeature, preserve);
  renderCarSettings();
  const assumptions = car ? [] : draft.assumptions;
  byId("assumptions").replaceChildren(...assumptions.map(assumption => node("li", assumption)));
  byId("assumption-panel").hidden = !assumptions.length;
  fitReport = car ? payload.fit : "";
  if (car) showCommittedFit();
  setStatus("dimension-status", "Measurements reflect the last successful build.");
}

window.addEventListener("message", event => {
  if (event.source !== viewer.contentWindow || event.origin !== "null") return;
  if (event.data?.type === "magtel-select-part") {
    const {index} = event.data;
    if (Number.isInteger(index) && measurements[index] && index !== Number(partPicker.value)) {
      partPicker.value = String(index);
      renderPart();
      refreshControls();
    }
    return;
  }
  if (event.data?.type === "magtel-history") {
    const {direction} = event.data;
    if (direction === "undo" || direction === "redo") changeHistory(direction);
    return;
  }
  if (event.data?.type === "magtel-car-pose" && isCar()) {
    const {front, rear, explode} = event.data;
    if ([front, rear, explode].every(Number.isFinite)
        && front >= 0 && front <= 360 && rear >= 0 && rear <= 360 && explode >= 0 && explode <= 100) {
      carPose = {type: "magtel-car-pose", front, rear, explode};
    }
    return;
  }
  if (event.data?.type !== "magtel-camera") return;
  const {yaw, pitch, zoom} = event.data;
  if ([yaw, pitch, zoom].every(Number.isFinite) && Math.abs(yaw) <= 2 * Math.PI
      && Math.abs(pitch) <= 1.48 && zoom >= 0.4 && zoom <= 5) {
    camera = {type: "magtel-camera", yaw, pitch, zoom};
  }
});
viewer.addEventListener("load", () => {
  if (camera) viewer.contentWindow.postMessage(camera, "*");
  if (carPose) viewer.contentWindow.postMessage(carPose, "*");
  if (currentRecipe) sendSelectedPart();
});

function loadDemo() {
  run("demo", "art-status", "Loading the example…", async () => {
    applyModel(await request("api/demo"));
    setStatus("art-status", "Example ready. Try editing its dimensions or describe your own build.");
  });
}

byId("new-build").addEventListener("click", () => {
  if (submittedBuild) {
    brief.value = "";
    for (const reference of references.splice(0)) URL.revokeObjectURL(reference.url);
    submittedBuild = false;
    renderReferences();
  }
  composing = true;
  renderSource();
  setStatus("art-status", currentRecipe ? "Your current model stays open until the new one is ready." : "");
  brief.focus();
});
byId("return-fit").addEventListener("click", () => {
  composing = false;
  renderSource();
  setStatus("art-status", "");
  byId("check-fit").focus();
});
byId("load-demo").addEventListener("click", loadDemo);
byId("load-gripper").addEventListener("click", () => {
  run("gripper", "art-status", "Loading the robot gripper…", async () => {
    applyModel(await request("api/gripper"));
    setStatus("art-status", "Gripper ready. Select a part to inspect its finish and dimensions.");
  });
});
byId("load-car").addEventListener("click", () => {
  run("car", "art-status", "Loading the toy car…", async () => {
    applyModel(await request("api/car"));
    setStatus("art-status", "");
  });
});

byId("check-fit").addEventListener("click", () => {
  if (!isCar()) return;
  run("fit", "fit-status", "Checking the wheel, axle, and chassis clearances…", async () => {
    const result = await request("api/fit", {recipe: draft});
    if (dirty) showFit(result.fit, "Draft", "The draft passes the fit checks. Rebuild to apply these dimensions.");
    else showCommittedFit();
  });
});

byId("generate-form").addEventListener("submit", event => {
  event.preventDefault();
  const requestBrief = brief.value.trim();
  if (busy || !requestBrief) return;
  if (dirty && !window.confirm("A new model will replace your current model and its pending dimension edits. Continue?")) return;
  run("generate", "art-status", "Building the model from your description…", async () => {
    const images = await Promise.all(references.map(async ({file}) => ({
      name: file.name,
      data: await base64(file),
    })));
    applyModel(await request("api/generate", {brief: requestBrief, images}));
    submittedBuild = true;
    setStatus("art-status", "Model generated. Review the dimensions and assumptions.");
  });
});
dimensions.addEventListener("submit", event => {
  event.preventDefault();
  if (!dirty || !draft) return;
  const invalid = dimensions.querySelector("input:invalid");
  if (invalid) {
    for (let ancestor = invalid.parentElement; ancestor !== dimensions; ancestor = ancestor.parentElement) {
      if (ancestor.tagName === "DETAILS") ancestor.open = true;
    }
    invalid.reportValidity();
    return;
  }
  run("rebuild", "dimension-status", "Rebuilding your dimensions…", async () => {
    const previous = currentRecipe;
    applyModel(await request("api/rebuild", {recipe: draft}), true);
    undoHistory.push(previous);
    if (undoHistory.length > maxHistoryEntries) undoHistory.shift();
    redoHistory.length = 0;
    setStatus("dimension-status", "Model rebuilt with your dimensions.");
  });
});

function changeHistory(direction) {
  const undoing = direction === "undo";
  const from = undoing ? undoHistory : redoHistory;
  const to = undoing ? redoHistory : undoHistory;
  if (busy || dirty || !from.length) return false;
  run(direction, "dimension-status", undoing ? "Undoing the last rebuild…" : "Redoing the last rebuild…", async () => {
    const previous = currentRecipe;
    applyModel(await request("api/rebuild", {recipe: from.at(-1)}), true);
    from.pop();
    to.push(previous);
    setStatus("dimension-status", undoing ? "Rebuild undone." : "Rebuild redone.");
  });
  return true;
}

undoButton.addEventListener("click", () => changeHistory("undo"));
redoButton.addEventListener("click", () => changeHistory("redo"));
discardButton.addEventListener("click", () => {
  if (busy || !dirty) return;
  draft = structuredClone(currentRecipe);
  dirty = false;
  renderPart(Number(featurePicker.value), true);
  if (isCar()) {
    renderCarSettings();
    showCommittedFit();
  }
  setStatus("dimension-status", "Pending edits discarded.");
  refreshControls();
  (isCar() ? partPicker : featurePicker).focus();
});

document.addEventListener("keydown", event => {
  if (event.defaultPrevented || event.repeat || event.altKey || !(event.ctrlKey || event.metaKey)
      || event.key.toLowerCase() !== "z") return;
  if (event.target.closest?.("input, textarea, select") || event.target.isContentEditable) return;
  if (changeHistory(event.shiftKey ? "redo" : "undo")) event.preventDefault();
});

byId("open-project").addEventListener("click", () => projectFile.click());
projectFile.addEventListener("change", () => {
  const file = projectFile.files[0];
  projectFile.value = "";
  if (!file) return;
  run("open", "art-status", "Opening the project…", async () => {
    if (file.size > 2 * 1024 * 1024) throw new Error("Choose a project under 2 MiB.");
    let data;
    try {
      data = JSON.parse(await file.text());
    } catch {
      throw new Error("Choose a MAGTEL project JSON file.");
    }
    if (data?.format === carFormat) {
      applyModel(await request("api/rebuild", {recipe: data}));
    } else if (data?.format === "magtel-art" && data.version === 1 && data.units === "mm" && data.recipe) {
      applyModel(await request("api/rebuild", {recipe: data.recipe}));
    } else {
      throw new Error("Choose a MAGTEL toy car or art project JSON file.");
    }
    setStatus("art-status", "Opened " + file.name + ".");
  });
});

function projectName() {
  const name = isCar() ? currentRecipe.assembly.name : currentRecipe.name;
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "magtel-project";
}

function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = node("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

byId("save-project").addEventListener("click", () => {
  if (!currentRecipe || busy || dirty) return;
  const car = isCar();
  const data = car ? currentRecipe : {format: "magtel-art", version: 1, units: "mm", recipe: currentRecipe};
  const suffix = car ? ".magtel.json" : ".magtel-art.json";
  download(new Blob([JSON.stringify(data, null, 2) + "\n"], {type: "application/json"}), projectName() + suffix);
  setStatus("dimension-status", "Editable project downloaded.");
});

byId("save-step").addEventListener("click", () => {
  if (!currentRecipe || dirty || isCar()) return;
  run("step", "dimension-status", "Preparing the STEP export…", async () => {
    const step = await request("api/step", {recipe: currentRecipe}, true);
    download(step, projectName() + ".step");
    setStatus("dimension-status", "STEP file downloaded.");
  });
});

byId("save-part").addEventListener("click", () => {
  if (!isCar() || dirty) return;
  const part = measurements[Number(partPicker.value)].kind;
  run("stl", "dimension-status", "Preparing the " + part + " STL…", async () => {
    const file = await request("api/part", {recipe: currentRecipe, part}, true);
    download(file, projectName() + "-" + part + ".stl");
    setStatus("dimension-status", "Selected " + part + " STL downloaded.");
  });
});

byId("save-parts").addEventListener("click", () => {
  if (!isCar() || dirty) return;
  run("parts", "dimension-status", "Packing the printable parts…", async () => {
    const file = await request("api/parts", {recipe: currentRecipe}, true);
    download(file, projectName() + "-parts.zip");
    setStatus("dimension-status", "Parts ZIP downloaded. It includes quantities and assembly notes.");
  });
});

loadDemo();
