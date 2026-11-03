"use strict";

const byId = id => document.getElementById(id);
const viewer = byId("viewer");
const dimensions = byId("dimensions");
const partPicker = byId("part-picker");
const featurePicker = byId("feature-picker");
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

const references = [];
const undoHistory = [];
const redoHistory = [];
let currentRecipe = null;
let draft = null;
let measurements = [];
let camera = null;
let busy = "";
let dirty = false;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function setStatus(id, message, error = false) {
  const status = byId(id);
  status.textContent = message;
  status.classList.toggle("error", error);
}

function refreshControls() {
  const working = Boolean(busy);
  byId("generate").disabled = working || !references.length || !brief.value.trim();
  byId("rebuild").disabled = working || !dirty || !draft;
  undoButton.disabled = working || dirty || !undoHistory.length;
  redoButton.disabled = working || dirty || !redoHistory.length;
  discardButton.disabled = working;
  discardButton.hidden = !dirty;
  byId("load-demo").disabled = working;
  byId("open-project").disabled = working;
  byId("save-project").disabled = working || !currentRecipe || dirty;
  byId("save-step").disabled = working || !currentRecipe || dirty;
  dropzone.disabled = working;
  brief.readOnly = busy === "generate";
  for (const input of dimensions.querySelectorAll("input, select")) input.disabled = working;
  for (const remove of document.querySelectorAll(".remove")) remove.disabled = working;

  const state = byId("model-state");
  const activity = {
    demo: "Loading example",
    generate: "Generating",
    rebuild: "Rebuilding",
    undo: "Undoing",
    redo: "Redoing",
    open: "Opening project",
    step: "Exporting STEP",
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
brief.addEventListener("input", refreshControls);

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
      byId("empty-view").querySelector("p").textContent = "Load the example or generate a part from your art.";
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
  const row = node("div", undefined, "number-row" + (labels.length === 2 ? " two" : ""));
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

const kinds = {box: "Box", cylinder: "Cylinder", extrude: "Extrusion", loft: "Loft"};
const sizeLabels = {
  box: ["Width X", "Depth Y", "Height Z"],
  cylinder: ["Radius", "Height"],
  extrude: ["Height"],
};

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
  const part = draft.parts[Number(partPicker.value)];
  measurePart();
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

function applyModel(payload, preserve = false) {
  const previousPart = preserve ? Number(partPicker.value) : 0;
  const previousFeature = preserve ? Number(featurePicker.value) : 0;
  currentRecipe = payload.recipe;
  draft = structuredClone(currentRecipe);
  measurements = payload.parts;
  dirty = false;
  if (!preserve) {
    camera = null;
    undoHistory.length = 0;
    redoHistory.length = 0;
  }

  byId("empty-view").hidden = true;
  viewer.hidden = false;
  viewer.srcdoc = payload.viewer;
  byId("model-name").textContent = currentRecipe.name;
  const count = currentRecipe.parts.length;
  byId("part-count").textContent = count + (count === 1 ? " part" : " parts") + " · mm";
  byId("empty-inspector").hidden = true;
  dimensions.hidden = false;

  partPicker.replaceChildren();
  for (const [index, part] of draft.parts.entries()) addOption(partPicker, index, part.name);
  partPicker.value = String(draft.parts[previousPart] ? previousPart : 0);
  renderPart(previousFeature, preserve);
  byId("assumptions").replaceChildren(...draft.assumptions.map(assumption => node("li", assumption)));
  byId("assumption-panel").hidden = !draft.assumptions.length;
  setStatus("dimension-status", "Measurements reflect the last successful build.");
}

window.addEventListener("message", event => {
  if (event.source !== viewer.contentWindow || event.origin !== "null") return;
  if (event.data?.type === "magtel-select-part") {
    const {index} = event.data;
    if (Number.isInteger(index) && draft?.parts[index] && index !== Number(partPicker.value)) {
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
  if (event.data?.type !== "magtel-camera") return;
  const {yaw, pitch, zoom} = event.data;
  if ([yaw, pitch, zoom].every(Number.isFinite) && Math.abs(yaw) <= 2 * Math.PI
      && Math.abs(pitch) <= 1.48 && zoom >= 0.4 && zoom <= 5) {
    camera = {type: "magtel-camera", yaw, pitch, zoom};
  }
});
viewer.addEventListener("load", () => {
  if (camera) viewer.contentWindow.postMessage(camera, "*");
  if (currentRecipe) sendSelectedPart();
});

function loadDemo() {
  run("demo", "art-status", "Loading the example…", async () => {
    applyModel(await request("api/demo"));
    setStatus("art-status", "Example ready. Try editing its dimensions or attach your own art.");
  });
}

byId("load-demo").addEventListener("click", loadDemo);
byId("generate-form").addEventListener("submit", event => {
  event.preventDefault();
  const requestBrief = brief.value.trim();
  if (!references.length || !requestBrief) return;
  run("generate", "art-status", "Interpreting the references and building the model…", async () => {
    const images = await Promise.all(references.map(async ({file}) => ({
      name: file.name,
      data: await base64(file),
    })));
    applyModel(await request("api/generate", {brief: requestBrief, images}));
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
  setStatus("dimension-status", "Pending edits discarded.");
  refreshControls();
  featurePicker.focus();
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
    if (data?.format !== "magtel-art" || data.version !== 1 || data.units !== "mm" || !data.recipe) {
      throw new Error("Choose a version 1 MAGTEL art project in millimeters.");
    }
    applyModel(await request("api/rebuild", {recipe: data.recipe}));
    setStatus("art-status", "Opened " + file.name + ".");
  });
});

function projectName() {
  return currentRecipe.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "magtel-part";
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
  const data = {format: "magtel-art", version: 1, units: "mm", recipe: currentRecipe};
  download(new Blob([JSON.stringify(data, null, 2) + "\n"], {type: "application/json"}), projectName() + ".magtel-art.json");
  setStatus("dimension-status", "Editable project downloaded.");
});

byId("save-step").addEventListener("click", () => {
  if (!currentRecipe || dirty) return;
  run("step", "dimension-status", "Preparing the STEP export…", async () => {
    const step = await request("api/step", {recipe: currentRecipe}, true);
    download(step, projectName() + ".step");
    setStatus("dimension-status", "STEP file downloaded.");
  });
});

loadDemo();
