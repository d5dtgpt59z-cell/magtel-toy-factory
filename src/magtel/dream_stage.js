/* Offline orthographic WebGL workbench for the authoritative model meshes. */
(() => {
  "use strict";

  const initialYaw = 1.02;
  const initialPitch = 0.54;
  const noShift = [0, 0, 0];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const add = (a, b) => a.map((v, i) => v + b[i]);
  const subtract = (a, b) => a.map((v, i) => v - b[i]);
  const scale = (a, s) => a.map(v => v * s);
  const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

  function rgb(color) {
    if (Array.isArray(color)) return color;
    if (/^#[a-f\d]{6}$/i.test(color)) {
      return [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16) / 255);
    }
    return [0.26, 0.42, 0.42];
  }

  function bounds(vertices) {
    const low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < vertices.length; i++) {
      const axis = i % 3;
      low[axis] = Math.min(low[axis], vertices[i]);
      high[axis] = Math.max(high[axis], vertices[i]);
    }
    return {low, high, center: scale(add(low, high), 0.5)};
  }

  function normals(v) {
    const result = new Float32Array(v.length);
    for (let i = 0; i < v.length; i += 9) {
      const ax = v[i + 3] - v[i], ay = v[i + 4] - v[i + 1], az = v[i + 5] - v[i + 2];
      const bx = v[i + 6] - v[i], by = v[i + 7] - v[i + 1], bz = v[i + 8] - v[i + 2];
      const x = ay * bz - az * by, y = az * bx - ax * bz, z = ax * by - ay * bx;
      const size = Math.hypot(x, y, z) || 1;
      for (let j = i; j < i + 9; j += 3) {
        result[j] = x / size;
        result[j + 1] = y / size;
        result[j + 2] = z / size;
      }
    }
    return result;
  }

  function shader(gl, type, source) {
    const handle = gl.createShader(type);
    gl.shaderSource(handle, source);
    gl.compileShader(handle);
    if (!gl.getShaderParameter(handle, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(handle));
    }
    return handle;
  }

  function renderer(gl) {
    const vertex = shader(gl, gl.VERTEX_SHADER, `
      attribute vec3 aPosition, aNormal;
      uniform vec3 uOffset, uTarget, uRight, uUp;
      uniform mediump vec3 uToward;
      uniform vec2 uScale, uPitch, uSpin, uHub;
      uniform float uDepth, uRadius;
      varying mediump vec3 vNormal;
      vec2 rotate(vec2 p, vec2 cs) {
        return vec2(p.x * cs.x - p.y * cs.y, p.x * cs.y + p.y * cs.x);
      }
      void main() {
        vec3 p = aPosition;
        vec3 n = aNormal;
        p.xz = rotate(p.xz - uHub, uSpin) + uHub;
        n.xz = rotate(n.xz, uSpin);
        p.xz = rotate(p.xz - vec2(0.0, uRadius), uPitch) + vec2(0.0, uRadius);
        n.xz = rotate(n.xz, uPitch);
        p += uOffset - uTarget;
        gl_Position = vec4(dot(p, uRight) / uScale.x, dot(p, uUp) / uScale.y,
          -dot(p, uToward) / uDepth, 1.0);
        vNormal = n;
      }`);
    const fragment = shader(gl, gl.FRAGMENT_SHADER, `
      precision mediump float;
      varying mediump vec3 vNormal;
      uniform vec4 uColor;
      uniform vec3 uToward;
      uniform bool uLit;
      uniform float uSelected;
      void main() {
        vec3 color = uColor.rgb;
        if (uLit) {
          vec3 n = normalize(vNormal);
          vec3 key = normalize(vec3(0.28, 0.48, 1.0));
          float diffuse = max(dot(n, key), 0.0);
          float facing = max(dot(n, uToward), 0.0);
          vec3 halfVector = normalize(key + uToward);
          float highlight = pow(max(dot(n, halfVector), 0.0), 24.0);
          color = color * (0.55 + diffuse * 0.37 + facing * 0.08) + highlight * 0.11;
          color = mix(color, vec3(1.0, 0.69, 0.28), uSelected * (0.16 + 0.17 * (1.0 - facing)));
        }
        gl_FragColor = vec4(color, uColor.a);
      }`);
    const program = gl.createProgram();
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    gl.deleteShader(vertex);
    gl.deleteShader(fragment);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program));
    }
    gl.useProgram(program);
    gl.enable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    const position = gl.getAttribLocation(program, "aPosition");
    const normal = gl.getAttribLocation(program, "aNormal");
    const u = Object.fromEntries(
      ["Offset", "Target", "Right", "Up", "Toward", "Scale", "Depth", "Color", "Lit",
        "Pitch", "Spin", "Hub", "Radius", "Selected"]
        .map(name => [name, gl.getUniformLocation(program, "u" + name)])
    );

    function buffer(data) {
      const handle = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, handle);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.STATIC_DRAW);
      return handle;
    }

    function attribute(index, handle) {
      gl.bindBuffer(gl.ARRAY_BUFFER, handle);
      gl.enableVertexAttribArray(index);
      gl.vertexAttribPointer(index, 3, gl.FLOAT, false, 0, 0);
    }

    return {
      mesh(vertices, {lit = true, mode = gl.TRIANGLES} = {}) {
        return {position: buffer(vertices), normal: lit ? buffer(normals(vertices)) : null,
          count: vertices.length / 3, mode};
      },
      free(mesh) {
        if (!mesh) return;
        gl.deleteBuffer(mesh.position);
        gl.deleteBuffer(mesh.normal);
      },
      frame(view, width, height) {
        gl.viewport(0, 0, width, height);
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
        gl.uniform3fv(u.Target, view.target);
        gl.uniform3fv(u.Right, view.right);
        gl.uniform3fv(u.Up, view.up);
        gl.uniform3fv(u.Toward, view.toward);
        gl.uniform2fv(u.Scale, view.scale);
        gl.uniform1f(u.Depth, view.depth);
      },
      draw(mesh, color, {offset = noShift, pitch = 0, spin = 0,
        hub = [0, 0], radius = 0, selected = false, alpha = 1} = {}) {
        attribute(position, mesh.position);
        if (mesh.normal) attribute(normal, mesh.normal);
        else gl.disableVertexAttribArray(normal);
        gl.uniform4f(u.Color, ...color, alpha);
        gl.uniform3fv(u.Offset, offset);
        gl.uniform2f(u.Pitch, Math.cos(pitch), Math.sin(pitch));
        gl.uniform2f(u.Spin, Math.cos(spin), Math.sin(spin));
        gl.uniform2fv(u.Hub, hub);
        gl.uniform1f(u.Radius, radius);
        gl.uniform1i(u.Lit, Boolean(mesh.normal));
        gl.uniform1f(u.Selected, selected ? 1 : 0);
        gl.drawArrays(mesh.mode, 0, mesh.count);
      },
    };
  }

  function addQuad(vertices, a, b, c, d) {
    vertices.push(...a, ...b, ...c, ...a, ...c, ...d);
  }

  function box(x0, x1, y0, y1, z0, z1) {
    const a = [x0, y0, z0], b = [x1, y0, z0], c = [x1, y1, z0], d = [x0, y1, z0];
    const A = [x0, y0, z1], B = [x1, y0, z1], C = [x1, y1, z1], D = [x0, y1, z1];
    const result = [];
    addQuad(result, d, c, b, a);
    addQuad(result, A, B, C, D);
    addQuad(result, a, b, B, A);
    addQuad(result, b, c, C, B);
    addQuad(result, c, d, D, C);
    addQuad(result, d, a, A, D);
    return result;
  }

  function grid(size, z, target) {
    const result = [];
    const step = size / 8;
    for (let i = -8; i <= 8; i++) {
      const x = i * step;
      result.push(
        target[0] - size, target[1] + x, z, target[0] + size, target[1] + x, z,
        target[0] + x, target[1] - size, z, target[0] + x, target[1] + size, z,
      );
    }
    return result;
  }

  function trackMeshes(track, renderer, gl) {
    const {start, end, width, ramp, barrier, barrierHeight, barrierDepth} = track;
    const shoulder = width / 2;
    const joints = [start, ramp[0], ramp[1], end];
    const elevation = [ramp[2], ramp[2], 0, 0];
    const thickness = width * 0.06;
    const deck = [], lines = [];
    for (let i = 0; i < 3; i++) {
      const x0 = joints[i], x1 = joints[i + 1], z0 = elevation[i], z1 = elevation[i + 1];
      addQuad(deck, [x0, -shoulder, z0], [x1, -shoulder, z1],
        [x1, shoulder, z1], [x0, shoulder, z0]);
      addQuad(deck, [x0, -shoulder, -thickness], [x1, -shoulder, -thickness],
        [x1, -shoulder, z1], [x0, -shoulder, z0]);
      addQuad(deck, [x1, shoulder, -thickness], [x0, shoulder, -thickness],
        [x0, shoulder, z0], [x1, shoulder, z1]);
      for (const y of [-shoulder * 0.78, shoulder * 0.78]) {
        lines.push(x0, y, z0 + width * 0.002, x1, y, z1 + width * 0.002);
      }
      for (let j = 0; j < 8; j++) {
        const a = (j + 0.1) / 8, b = (j + 0.6) / 8;
        lines.push(x0 + a * (x1 - x0), 0, z0 + a * (z1 - z0) + width * 0.002,
          x0 + b * (x1 - x0), 0, z0 + b * (z1 - z0) + width * 0.002);
      }
    }
    addQuad(deck, [start, shoulder, -thickness], [start, -shoulder, -thickness],
      [start, -shoulder, elevation[0]], [start, shoulder, elevation[0]]);
    addQuad(deck, [end, -shoulder, -thickness], [end, shoulder, -thickness],
      [end, shoulder, 0], [end, -shoulder, 0]);
    return {
      deck: renderer.mesh(deck),
      lines: renderer.mesh(lines, {lit: false, mode: gl.LINES}),
      barrier: barrier === null ? null : renderer.mesh(box(
        barrier, barrier + barrierDepth, -shoulder, shoulder, 0, barrierHeight)),
    };
  }

  function contactShadow(partBounds, z) {
    const vertices = [];
    const center = [...partBounds.center];
    center[2] = z;
    const sizes = subtract(partBounds.high, partBounds.low);
    const rx = sizes[0] * 0.58, ry = sizes[1] * 0.54;
    const point = i => {
      const angle = i * Math.PI / 24;
      return [center[0] + rx * Math.cos(angle), center[1] + ry * Math.sin(angle), z];
    };
    for (let i = 0; i < 48; i++) vertices.push(...center, ...point(i), ...point(i + 1));
    return vertices;
  }

  function wheelMark(part, radius) {
    const {center, high, low} = part.bounds;
    const side = part.id.includes("-left-") ? 1 : -1;
    const y = side > 0 ? high[1] + radius * 0.008 : low[1] - radius * 0.008;
    const x0 = center[0] - radius * 0.055, x1 = center[0] + radius * 0.055;
    const z0 = center[2] + radius * 0.66, z1 = center[2] + radius * 0.87;
    const result = [];
    addQuad(result, [x0, y, z0], [x1, y, z0], [x1, y, z1], [x0, y, z1]);
    return result;
  }

  function definitions(part, design) {
    const {center, high, low} = part.bounds;
    const sign = part.id.includes("-left-") ? 1 : -1;
    const side = sign > 0 ? high[1] : low[1];
    const wheel = part.id.endsWith("-wheel");
    if (wheel) return [
      {field: "wheel_diameter", label: "Ø Wheel", point: [center[0], side, high[2]], axis: [0, 0, 1], factor: 1},
      {field: "wheel_gap", label: "Gap", point: [center[0], side, center[2]], axis: [0, sign, 0], factor: 1},
    ];
    if (part.id === "chassis") return [
      {field: "length", label: "Length", point: [high[0], center[1], high[2]], axis: [1, 0, 0], factor: 2},
      {field: "width", label: "Width", point: [center[0], high[1], high[2]], axis: [0, 1, 0], factor: 2},
      {field: "height", label: "Height", point: [center[0], center[1], high[2]], axis: [0, 0, 1], factor: 2},
    ];
    const axleSign = part.id.startsWith("rear") ? -1 : 1;
    const controls = [
      {field: "axle_length", label: "Axle length", point: [center[0], high[1], center[2]], axis: [0, 1, 0], factor: 2},
    ];
    if (!part.id.startsWith("middle") && design.wheelbase) controls.push(
      {field: "wheelbase", label: "Wheelbase", point: [center[0], low[1], center[2]],
        axis: [axleSign, 0, 0], factor: 2},
    );
    return controls;
  }

  class MagtelStage {
    constructor(canvas, {onSelect = () => {}, onEdit = () => {}, onUnavailable = () => {}} = {}) {
      this.canvas = canvas;
      this.onSelect = onSelect;
      this.onEdit = onEdit;
      this.onUnavailable = onUnavailable;
      this.parts = [];
      this.exploded = 0;
      this.pending = false;
      this.selected = null;
      this.playtest = null;
      this.yaw = initialYaw;
      this.pitch = initialPitch;
      this.zoom = 1;
      this.handles = [];
      this.pointers = new Map();
      this.drag = null;
      this.gl = canvas.getContext("webgl", {antialias: true, alpha: true});
      if (!this.gl) {
        onUnavailable("3D preview needs WebGL. Use the dimension editor and export tools in this browser.");
        return;
      }
      try {
        this.renderer = renderer(this.gl);
      } catch (error) {
        console.error(error);
        onUnavailable("The 3D preview could not start. The dimension editor and export tools are available.");
        return;
      }

      const layer = document.createElement("div");
      layer.className = "magtel-stage-handles";
      layer.setAttribute("aria-hidden", "true");
      Object.assign(layer.style, {position: "absolute", inset: "0", overflow: "hidden", pointerEvents: "none"});
      canvas.parentElement.append(layer);
      this.layer = layer;
      this.bind();
      if ("ResizeObserver" in window) new ResizeObserver(() => this.schedule()).observe(canvas);
      window.addEventListener("resize", () => this.schedule());
      canvas.addEventListener("webglcontextlost", () => {
        this.renderer = null;
        layer.replaceChildren();
        onUnavailable("The 3D preview was interrupted. Reload Dream Mode to restore the viewport.");
      });
    }

    setModel({parts, design}) {
      this.design = design;
      if (!this.renderer || !parts.length) return;
      if (this.playtest) this.setPlaytest(null);
      for (const part of this.parts) {
        this.renderer.free(part.mesh);
        this.renderer.free(part.mark);
      }
      this.renderer.free(this.grid);
      this.renderer.free(this.shadow);

      this.parts = parts.map(part => {
        const item = {...part, explode: part.explode || noShift, color: rgb(part.color),
          mesh: this.renderer.mesh(part.vertices), bounds: bounds(part.vertices)};
        if (part.id.endsWith("-wheel")) item.mark = this.renderer.mesh(
          wheelMark(item, design.wheel_diameter / 2), {lit: false});
        return item;
      });
      const low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity];
      for (const part of this.parts) {
        for (let axis = 0; axis < 3; axis++) {
          low[axis] = Math.min(low[axis], part.bounds.low[axis]);
          high[axis] = Math.max(high[axis], part.bounds.high[axis]);
        }
      }
      const center = scale(add(low, high), 0.5);
      this.radius = Math.hypot(...subtract(high, center));
      const ground = low[2] - this.radius * 0.006;
      this.grid = this.renderer.mesh(grid(this.radius * 2.4, ground, center), {lit: false, mode: this.gl.LINES});
      this.shadow = this.renderer.mesh(contactShadow({low, high, center}, ground + this.radius * 0.002),
        {lit: false});
      if (!this.parts.some(part => part.id === this.selected)) this.selected = null;
      this.updateHandles();
      this.schedule();
    }

    select(id) {
      if (id === this.selected) return;
      this.selected = id;
      this.updateHandles();
      this.schedule();
    }

    setExplode(amount) {
      this.exploded = clamp(amount, 0, 1);
      this.updateHandles();
      this.schedule();
    }

    setPlaytest(state) {
      if (!this.renderer) return;
      const nextTrack = state?.track;
      if (nextTrack !== this.playtest?.track) {
        if (this.track) Object.values(this.track).forEach(mesh => this.renderer.free(mesh));
        this.track = nextTrack ? trackMeshes(nextTrack, this.renderer, this.gl) : null;
      }
      if (state && !this.playtest) {
        this.editorCamera = [this.yaw, this.pitch, this.zoom];
        this.yaw = -1.15;
        this.pitch = 0.55;
        this.zoom = 1;
      }
      if (!state && this.playtest) [this.yaw, this.pitch, this.zoom] = this.editorCamera;
      const switched = Boolean(state) !== Boolean(this.playtest);
      this.playtest = state;
      if (switched) this.updateHandles();
      this.schedule();
    }

    camera(action) {
      if (action === "left") this.yaw -= 0.19;
      if (action === "right") this.yaw += 0.19;
      if (action === "up") this.pitch = clamp(this.pitch + 0.14, -1.42, 1.42);
      if (action === "down") this.pitch = clamp(this.pitch - 0.14, -1.42, 1.42);
      if (action === "near") this.zoom = clamp(this.zoom * 1.19, 0.44, 4);
      if (action === "far") this.zoom = clamp(this.zoom / 1.19, 0.44, 4);
      if (action === "reset") {
        this.yaw = this.playtest ? -1.15 : initialYaw;
        this.pitch = initialPitch;
        this.zoom = 1;
      }
      this.schedule();
    }

    schedule() {
      if (this.pending || !this.renderer) return;
      this.pending = true;
      requestAnimationFrame(() => {
        this.pending = false;
        this.render();
      });
    }

    view(width, height, exploded, playtest) {
      const cx = Math.cos(this.yaw), cy = Math.sin(this.yaw);
      const cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
      const right = [-cy, cx, 0], up = [-cx * sp, -cy * sp, cp];
      let target, extent;
      const aspect = width / height;
      if (playtest) {
        const {start, end, ramp, width: trackWidth} = playtest.track;
        target = [(start + end) / 2, 0, ramp[2] * 0.5];
        const horizontal = (end - start) * 0.55;
        extent = Math.max(horizontal / Math.max(1, aspect), horizontal * 0.55, trackWidth * 0.62);
      } else {
        const low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity];
        for (const part of this.parts) {
          for (let axis = 0; axis < 3; axis++) {
            const offset = part.explode[axis] * exploded;
            low[axis] = Math.min(low[axis], part.bounds.low[axis] + offset);
            high[axis] = Math.max(high[axis], part.bounds.high[axis] + offset);
          }
        }
        target = scale(add(low, high), 0.5);
        const half = scale(subtract(high, low), 0.5);
        const modelWidth = dot(half, right.map(Math.abs));
        const modelHeight = dot(half, up.map(Math.abs));
        extent = Math.max(modelWidth / (0.76 * Math.max(1, aspect)),
          modelHeight / (0.68 * Math.max(1, 1 / aspect)));
      }
      extent /= this.zoom;
      return {target, right, up, toward: [cx * cp, cy * cp, sp],
        scale: [extent * Math.max(1, aspect), extent * Math.max(1, 1 / aspect)],
        depth: this.radius * (playtest ? 18 : 9)};
    }

    render() {
      if (!this.renderer || !this.parts.length) return;
      const canvas = this.canvas;
      const {exploded, playtest} = this;
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, Math.round(canvas.clientWidth * pixelRatio));
      const height = Math.max(1, Math.round(canvas.clientHeight * pixelRatio));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      const view = this.view(width, height, exploded, playtest);
      this.renderer.frame(view, width, height);
      if (playtest) {
        this.renderer.draw(this.track.deck, [0.24, 0.40, 0.37]);
        this.renderer.draw(this.track.lines, [0.79, 0.92, 0.81], {alpha: 0.82});
        if (this.track.barrier) this.renderer.draw(this.track.barrier, [0.99, 0.44, 0.19]);
      } else {
        this.renderer.draw(this.grid, [0.19, 0.40, 0.37], {alpha: 0.17});
        this.renderer.draw(this.shadow, [0.22, 0.37, 0.32], {alpha: 0.12 * (1 - exploded * 0.7)});
      }
      for (const part of this.parts) {
        const params = {offset: scale(part.explode, exploded), selected: !playtest && this.selected === part.id};
        if (playtest) {
          const {x, z, pitch, rotation} = playtest.sample;
          const radius = this.design.wheel_diameter / 2;
          Object.assign(params, {offset: [x, 0, z - radius], pitch, radius});
          if (part.mark) {
            params.hub = [part.bounds.center[0], part.bounds.center[2]];
            params.spin = -rotation;
          }
        }
        this.renderer.draw(part.mesh, part.color, params);
        if (playtest && part.mark) this.renderer.draw(part.mark, [1.0, 0.79, 0.36], params);
      }
      if (!playtest) this.placeHandles(view);
    }

    project(point, view) {
      const p = subtract(point, view.target);
      return [
        (0.5 + dot(p, view.right) / (2 * view.scale[0])) * this.canvas.clientWidth,
        (0.5 - dot(p, view.up) / (2 * view.scale[1])) * this.canvas.clientHeight,
        dot(p, view.toward),
      ];
    }

    pick(x, y) {
      const {clientWidth: width, clientHeight: height} = this.canvas;
      const view = this.view(width, height, this.exploded, null);
      let result = null, bestDepth = -Infinity;
      for (const part of this.parts) {
        const v = part.vertices, offset = scale(part.explode, this.exploded);
        for (let i = 0; i < v.length; i += 9) {
          const a = this.project(add(v.slice(i, i + 3), offset), view);
          const b = this.project(add(v.slice(i + 3, i + 6), offset), view);
          const c = this.project(add(v.slice(i + 6, i + 9), offset), view);
          const denom = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1]);
          if (Math.abs(denom) < 1e-7) continue;
          const u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / denom;
          const w = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / denom;
          if (u < 0 || w < 0 || u + w > 1) continue;
          const depth = u * a[2] + w * b[2] + (1 - u - w) * c[2];
          if (depth > bestDepth) {
            bestDepth = depth;
            result = part.id;
          }
        }
      }
      return result;
    }

    updateHandles() {
      if (!this.layer) return;
      this.layer.replaceChildren();
      this.handles = [];
      const part = this.parts.find(part => part.id === this.selected);
      if (this.playtest || !part) return;
      for (const handle of definitions(part, this.design)) {
        const element = document.createElement("span");
        element.className = "magtel-stage-handle";
        element.dataset.field = handle.field;
        element.textContent = handle.label;
        element.title = "Drag to change " + handle.label.toLowerCase();
        Object.assign(element.style, {
          position: "absolute", transform: "translate(-50%, -50%)", background: "#fff8eb",
          color: "#202d2b", border: "2px solid #e85925", borderRadius: "20px",
          boxShadow: "0 2px 10px #24443d32", font: "700 11px/1.1 system-ui, sans-serif",
          padding: "7px 9px", whiteSpace: "nowrap", cursor: "grab", pointerEvents: "auto",
          userSelect: "none", touchAction: "none",
        });
        this.layer.append(element);
        const item = {...handle, element, part};
        this.handles.push(item);
        element.addEventListener("pointerdown", event => this.beginEdit(event, item));
        element.addEventListener("pointermove", event => this.moveEdit(event));
        element.addEventListener("pointerup", event => this.endEdit(event, true));
        element.addEventListener("pointercancel", event => this.endEdit(event, false));
        element.addEventListener("lostpointercapture", event => this.endEdit(event, false));
      }
    }

    placeHandles(view) {
      for (const handle of this.handles) {
        const point = add(handle.point, scale(handle.part.explode, this.exploded));
        const origin = this.project(point, view);
        const end = this.project(add(point, handle.axis), view);
        const vector = [end[0] - origin[0], end[1] - origin[1]];
        const length = Math.hypot(...vector);
        handle.vector = length > 0.075 ? vector : [Math.max(0.5, this.canvas.clientWidth / (2 * view.scale[0])), 0];
        const active = this.drag?.item === handle;
        const displacement = active ? (this.drag.value - this.drag.start) / handle.factor : 0;
        const [dx, dy] = handle.vector;
        const pull = displacement + 17 / Math.hypot(dx, dy);
        handle.element.style.left = clamp(origin[0] + dx * pull, 37, this.canvas.clientWidth - 37) + "px";
        handle.element.style.top = clamp(origin[1] + dy * pull, 15, this.canvas.clientHeight - 15) + "px";
        handle.element.textContent = active ? `${handle.label} · ${this.drag.value} mm` : handle.label;
      }
    }

    beginEdit(event, item) {
      if (event.button !== 0 || this.drag || !item.vector) return;
      event.preventDefault();
      item.element.setPointerCapture(event.pointerId);
      const start = this.design[item.field];
      this.drag = {id: event.pointerId, item, x: event.clientX, y: event.clientY,
        start, value: start, vector: item.vector};
      item.element.style.cursor = "grabbing";
      this.schedule();
    }

    moveEdit(event) {
      if (event.pointerId !== this.drag?.id) return;
      const {item, vector: [dx, dy], start, x, y} = this.drag;
      const distance = ((event.clientX - x) * dx + (event.clientY - y) * dy) / (dx * dx + dy * dy);
      this.drag.value = clamp(Math.round((start + distance * item.factor) * 10) / 10, 0.1, 1000);
      this.schedule();
    }

    endEdit(event, commit) {
      if (event.pointerId !== this.drag?.id) return;
      const {item, value, start} = this.drag;
      this.drag = null;
      item.element.style.cursor = "grab";
      if (commit && value !== start) this.onEdit({field: item.field, value});
      this.schedule();
    }

    bind() {
      const canvas = this.canvas;
      const keyActions = {ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down",
        "+": "near", "=": "near", "-": "far", Home: "reset"};
      canvas.addEventListener("keydown", event => {
        if (!Object.hasOwn(keyActions, event.key)) return;
        event.preventDefault();
        this.camera(keyActions[event.key]);
      });
      canvas.addEventListener("wheel", event => {
        if (!this.parts.length || event.ctrlKey) return;
        event.preventDefault();
        const factor = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? canvas.clientHeight : 1;
        this.zoom = clamp(this.zoom * Math.exp(-clamp(event.deltaY * factor, -240, 240) * 0.002), 0.44, 4);
        this.schedule();
      }, {passive: false});
      canvas.addEventListener("pointerdown", event => {
        if (event.button !== 0 || this.pointers.size === 2 || !this.parts.length) return;
        canvas.setPointerCapture(event.pointerId);
        this.pointers.set(event.pointerId, {x: event.clientX, y: event.clientY, moved: false});
        if (this.pointers.size === 2) for (const point of this.pointers.values()) point.moved = true;
      });
      canvas.addEventListener("pointermove", event => {
        const pointer = this.pointers.get(event.pointerId);
        if (!pointer) return;
        const x = event.clientX, y = event.clientY;
        if (this.pointers.size === 2) {
          const other = [...this.pointers.values()].find(p => p !== pointer);
          const previous = Math.hypot(pointer.x - other.x, pointer.y - other.y);
          const distance = Math.hypot(x - other.x, y - other.y);
          if (distance > 1 && previous > 1) this.zoom = clamp(this.zoom * distance / previous, 0.44, 4);
        } else {
          if (!pointer.moved && Math.hypot(x - pointer.x, y - pointer.y) < 4) return;
          this.yaw -= (x - pointer.x) * 0.009;
          this.pitch = clamp(this.pitch + (y - pointer.y) * 0.009, -1.42, 1.42);
        }
        Object.assign(pointer, {x, y, moved: true});
        this.schedule();
      });
      canvas.addEventListener("pointerup", event => {
        const pointer = this.pointers.get(event.pointerId);
        this.pointers.delete(event.pointerId);
        if (!pointer || pointer.moved || this.playtest) return;
        const rect = canvas.getBoundingClientRect();
        const id = this.pick(event.clientX - rect.left, event.clientY - rect.top);
        if (!id) return;
        this.select(id);
        this.onSelect(id);
      });
      for (const name of ["pointercancel", "lostpointercapture"]) {
        canvas.addEventListener(name, event => this.pointers.delete(event.pointerId));
      }
    }
  }

  window.MagtelStage = MagtelStage;
})();
