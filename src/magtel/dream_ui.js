"use strict";

const $ = (selector) => document.querySelector(selector);
const starter = "A futuristic six-wheeled moon rover in lime green";
const current = {
  model: null,
  part: null,
  mode: "build",
  busy: false,
  variants: [],
  activeVariant: null,
  test: null,
  frame: null,
};

const fields = {
  chassis: [
    ["length", "Length"],
    ["width", "Width"],
    ["height", "Height"],
    ["axle_clearance", "Bore clearance"],
  ],
  axle: [
    ["axle_diameter", "Diameter"],
    ["axle_length", "Length"],
    ["wheelbase", "Wheelbase"],
  ],
  wheel: [
    ["wheel_diameter", "Diameter"],
    ["wheel_thickness", "Thickness"],
    ["wheel_bore", "Center bore"],
    ["wheel_gap", "Body gap"],
  ],
};
const fitLabels = {
  wheel_bore_clearance: "Wheel bore clearance",
  chassis_bore_clearance: "Chassis bore clearance",
  wheel_gap: "Body gap per side",
  axle_overhang: "Axle overhang",
  ground_clearance: "Ground clearance",
};
const profileLabels = {
  straight: "Straight tread",
  beveled: "Beveled tread",
  crowned: "Crowned tread",
  ribbed: "Ribbed tread",
  balloon: "Balloon tread",
  stepped: "Stepped tread",
};
const axleLengthLink = {width: 1, wheel_gap: 2, wheel_thickness: 2};
const mm = (value) => `${Number(value.toFixed(2))} mm`;
const message = (content, error = false, target = "#workbench-message") => {
  const status = $(target);
  status.textContent = content;
  status.hidden = !content;
  status.classList.toggle("error", error);
};

async function request(endpoint, payload) {
  const response = await fetch(`/api/${endpoint}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const failure = await response.json().catch(() => null);
    throw new Error(failure?.error || "The workshop could not complete that action.");
  }
  return endpoint === "export" ? response.blob() : response.json();
}

function updateControls() {
  const modelReady = Boolean(current.model);
  for (const id of ["part-select", "apply", "part-color", "variants-button", "export", "save", "test-mode"]) {
    $(`#${id}`).disabled = !modelReady || current.busy;
  }
  for (const item of document.querySelectorAll(".part-fields input, .variant-card, .chip")) {
    item.disabled = current.busy;
  }
  $("#invent").disabled = current.busy;
  $("#open").disabled = current.busy;
  $("#explode").disabled = !modelReady || current.mode !== "build";
}

async function perform(work, pending, target) {
  if (current.busy) return;
  current.busy = true;
  updateControls();
  message(pending, false, target);
  try {
    await work();
  } catch (error) {
    message(error.message || "The workshop could not complete that action.", true, target);
    if (!current.model) $("#toy-title").textContent = "Start with an idea";
  } finally {
    current.busy = false;
    updateControls();
  }
}

let stage;
let stageWarning = "";
try {
  stage = new MagtelStage($("#workbench-canvas"), {
    onSelect: (id) => {
      if (!current.busy && current.mode === "build" && id) selectPart(id);
    },
    onEdit: ({field, value}) => {
      if (!current.model || current.mode !== "build" || !Number.isFinite(value)) return;
      const previous = current.model.design;
      const design = {...previous, [field]: Number(value.toFixed(2))};
      const multiplier = axleLengthLink[field];
      if (multiplier) {
        design.axle_length = Number((previous.axle_length + multiplier * (design[field] - previous[field])).toFixed(2));
      }
      perform(async () => {
        install(await request("design", {design}));
        message(multiplier ? "Dimension and axle length updated to keep the same overhang." : "Dimension updated.");
      }, "Checking the edited geometry…");
    },
    onUnavailable: (warning) => {
      stageWarning = warning || "The interactive 3D view needs WebGL.";
      $("#view-hint").textContent = stageWarning;
    },
  });
} catch (error) {
  stageWarning = "The interactive 3D view could not start. The inspector and exports are available.";
  $("#view-hint").textContent = stageWarning;
}

function partKind(id) {
  return id === "chassis" ? "chassis" : id.endsWith("-axle") ? "axle" : "wheel";
}

function selectPart(id) {
  current.part = id;
  $("#part-select").value = id;
  stage?.select(id);
  const design = current.model.design;
  const kind = partKind(id);
  if (current.mode === "build" && !stageWarning) $("#view-hint").textContent = "Drag a dimension handle to edit";
  $("#part-fields").replaceChildren(...fields[kind].map(([key, caption]) => {
    const label = document.createElement("label");
    label.className = "field";
    const text = document.createElement("span");
    text.textContent = caption;
    const input = document.createElement("input");
    input.type = "number";
    input.name = key;
    input.min = "0.1";
    input.max = "1000";
    input.step = "any";
    input.value = design[key];
    input.required = true;
    input.setAttribute("aria-label", `${caption} in millimeters`);
    label.append(text, input);
    return label;
  }));
  $("#part-color").value = design.colors[kind];
  $("#part-note").textContent = {
    chassis: "Dragging the width also adjusts axle length.",
    axle: "Edits apply to all axles. Wheelbase spans the front and rear axle centers.",
    wheel: "Edits apply to all wheels. Dragging gap or thickness also adjusts axle length.",
  }[kind];
  updateControls();
}

function fitDetails(fit) {
  return Object.entries(fitLabels).map(([key, title]) => {
    const row = document.createElement("div");
    const name = document.createElement("dt");
    const value = document.createElement("dd");
    name.textContent = title;
    value.textContent = mm(fit[key]);
    row.append(name, value);
    return row;
  });
}

function install(model, {fresh = false, variant = null} = {}) {
  current.model = model;
  message("");
  if (variant === null) {
    current.variants = [];
    message("", false, "#variant-status");
  }
  current.activeVariant = variant;
  renderVariants();
  const {design, parts, fit, dimensions} = model;
  $("#toy-title").textContent = design.name;
  $("#concept").textContent = `${design.concept} recipe · ${design.axle_count * 2} wheels.`;
  $("#notes").replaceChildren(...design.notes.map((note) => {
    const item = document.createElement("li");
    item.textContent = note;
    return item;
  }));
  $("#assumptions").hidden = !design.notes.length;
  if (fresh) $("#assumptions").open = design.notes.length > 2;
  $("#interpretation").hidden = false;
  $("#part-count").textContent = String(parts.length).padStart(2, "0");
  $("#part-select").replaceChildren(...parts.map((part) => new Option(part.name, part.id)));
  $("#fit-list").replaceChildren(...fitDetails(fit));
  $("#fit-panel").hidden = false;
  $("#envelope").textContent = [
    dimensions.length, dimensions.width, dimensions.height,
  ].map((value) => Number(value.toFixed(2))).join(" × ") + " mm";
  stage?.setModel(model);
  if (fresh) {
    $("#explode").value = "0";
    stage?.setExplode(0);
    stage?.camera("reset");
    setMode("build");
  }
  selectPart(parts.some((part) => part.id === current.part) && !fresh ? current.part : "chassis");
  if (current.mode === "playtest") resetTest();
}

function renderVariants() {
  $("#variant-list").replaceChildren(...current.variants.map((design, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "variant-card";
    button.setAttribute("aria-pressed", String(index === current.activeVariant));
    const title = document.createElement("strong");
    title.textContent = design.variant || design.name;
    const swatch = document.createElement("span");
    swatch.className = "variant-swatch";
    swatch.setAttribute("aria-hidden", "true");
    for (const color of Object.values(design.colors)) {
      const chip = document.createElement("i");
      chip.style.backgroundColor = color;
      swatch.append(chip);
    }
    const profile = document.createElement("small");
    profile.textContent = profileLabels[design.wheel_profile];
    button.append(swatch, title, profile);
    button.addEventListener("click", () => perform(async () => {
      install(await request("design", {design}), {variant: index});
      message(`${title.textContent} variant installed.`, false, "#variant-status");
      revealWorkbench();
    }, "Checking modular fit…", "#variant-status"));
    return button;
  }));
}

function revealWorkbench() {
  if (!window.matchMedia("(max-width: 970px)").matches) return;
  $(".workspace").scrollIntoView({block: "start"});
  $("#toy-title").focus({preventScroll: true});
}

function invent(prompt, preview = false) {
  return perform(async () => {
    install(await request("invent", {prompt}), {fresh: true});
    message(preview ? "" : "Invention ready. Choose a part to start building.");
    if (!preview) revealWorkbench();
  }, preview ? "Opening the example assembly…" : "Turning your idea into editable geometry…");
}

function setMode(mode) {
  if (!current.model || mode === current.mode) return;
  current.mode = mode;
  const testing = mode === "playtest";
  $("#build-panel").hidden = testing;
  $("#test-panel").hidden = !testing;
  $("#edit-mode").setAttribute("aria-pressed", String(!testing));
  $("#test-mode").setAttribute("aria-pressed", String(testing));
  $("#view-caption").textContent = testing ? "TRACK VIEW" : "ASSEMBLY VIEW";
  $("#view-hint").textContent = stageWarning || (testing ? "Estimated motion · dimensions in mm" : "Drag to orbit · click a part to edit");
  if (testing) {
    resetTest();
  } else {
    stopTest();
    stage?.setPlaytest(null);
    stage?.select(current.part);
    stage?.setExplode(Number($("#explode").value) / 100);
  }
  updateControls();
}

function drawTest(sample) {
  stage?.setPlaytest({track: current.test.track, sample});
  $("#speed").textContent = `${Math.round(sample.speed)} mm/s`;
  $("#distance").textContent = `${Math.round(sample.distance)} mm`;
  $("#collisions").textContent = sample.collisions;
  $("#stability").textContent = sample.stability;
}

function stopTest() {
  if (current.frame !== null) cancelAnimationFrame(current.frame);
  current.frame = null;
  $("#run-test").textContent = current.test?.sample.time > 0 && !current.test.sample.finished ? "Resume test" : "Run test";
}

function resetTest() {
  stopTest();
  current.test = MagtelPhysics.create(current.model.design, $("#track").value);
  $("#run-test").textContent = "Run test";
  $("#test-result").textContent = "";
  drawTest(current.test.sample);
}

function toggleTest() {
  if (current.frame !== null) {
    stopTest();
    $("#test-result").textContent = "Test paused.";
    return;
  }
  if (!current.test || current.test.sample.finished) resetTest();
  $("#run-test").textContent = "Pause";
  $("#test-result").textContent = "Playtest running.";
  let last = performance.now();
  const step = (now) => {
    const sample = current.test.advance(Math.min(0.1, (now - last) / 1000) * 0.55);
    last = now;
    drawTest(sample);
    if (sample.finished) {
      stopTest();
      const impacts = sample.collisions === 1 ? "impact" : "impacts";
      $("#test-result").textContent = `Test ended. Travel ${Math.round(sample.distance)} mm. ${sample.collisions} ${impacts}. ${sample.stability}.`;
    } else {
      current.frame = requestAnimationFrame(step);
    }
  };
  current.frame = requestAnimationFrame(step);
}

function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$("#idea-form").addEventListener("submit", (event) => {
  event.preventDefault();
  invent($("#idea").value);
});
for (const button of document.querySelectorAll("[data-prompt]")) {
  button.addEventListener("click", () => {
    $("#idea").value = button.dataset.prompt;
    $("#idea").focus();
  });
}

$("#part-select").addEventListener("change", (event) => selectPart(event.target.value));
$("#part-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const design = {...current.model.design};
  for (const input of $("#part-fields").querySelectorAll("input")) design[input.name] = input.valueAsNumber;
  design.colors = {...design.colors, [partKind(current.part)]: $("#part-color").value};
  perform(async () => {
    install(await request("design", {design}));
    message("Part edits applied.");
  }, "Checking the edited geometry…");
});

$("#explode").addEventListener("input", (event) => stage?.setExplode(Number(event.target.value) / 100));
for (const button of document.querySelectorAll("[data-camera]")) {
  button.addEventListener("click", () => stage?.camera(button.dataset.camera));
}

$("#edit-mode").addEventListener("click", () => setMode("build"));
$("#test-mode").addEventListener("click", () => setMode("playtest"));
$("#track").addEventListener("change", resetTest);
$("#run-test").addEventListener("click", toggleTest);
$("#reset-test").addEventListener("click", resetTest);
$("#test-limits").textContent = MagtelPhysics.limitations;

$("#variants-button").addEventListener("click", () => perform(async () => {
  const {variants} = await request("variants", {design: current.model.design});
  current.variants = variants;
  current.activeVariant = variants.findIndex((variant) => variant.variant === current.model.design.variant);
  renderVariants();
  message(`${variants.length} compatible variants ready.`, false, "#variant-status");
}, "Generating compatible variants…", "#variant-status"));

$("#save").addEventListener("click", () => {
  const json = JSON.stringify(current.model.design, null, 2) + "\n";
  download(new Blob([json], {type: "application/json"}), "magtel-design.json");
});
$("#open").addEventListener("click", () => $("#file").click());
$("#file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  perform(async () => {
    if (file.size > 64 * 1024) throw new Error("Choose a MAGTEL JSON design under 64 KB.");
    let design;
    try {
      design = JSON.parse(await file.text());
    } catch {
      throw new Error("Choose a valid MAGTEL JSON design.");
    }
    const model = await request("import", {design});
    install(model, {fresh: true});
    $("#idea").value = model.design.prompt;
    message("Design loaded.", false, "#file-status");
    revealWorkbench();
  }, "Opening design…", "#file-status");
});
$("#export").addEventListener("click", () => perform(async () => {
  const blob = await request("export", {design: current.model.design});
  download(blob, "magtel-invention.zip");
  message("Invention sheet ZIP download started.", false, "#file-status");
}, "Packaging the sheet, renders, and STL meshes…", "#file-status"));

invent(starter, true);
