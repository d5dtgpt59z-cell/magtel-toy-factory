const assert = require("node:assert/strict");
const {test} = require("node:test");

global.window = global;
require("../src/magtel/dream_physics.js");
const {create} = window.MagtelPhysics;

const rover = {
  length: 110, width: 48, height: 15, wheelbase: 80,
  axle_count: 3, wheel_diameter: 30, wheel_thickness: 10, wheel_gap: 1.5,
};

function finish(sim, frame) {
  for (let i = 0; !sim.sample.finished && i < 3000; i++) sim.advance(frame);
  assert.equal(sim.sample.finished, true);
  return sim.sample;
}

test("floor roll slows to rest and wheel spin matches travel", () => {
  const sim = create(rover, "floor");
  const initial = sim.sample;
  const moving = sim.advance(0.25);
  assert.ok(moving.speed < initial.speed && moving.speed > 0);
  assert.equal(moving.z, rover.wheel_diameter / 2);
  assert.equal(moving.pitch, 0);
  const result = finish(sim, 1 / 60);
  assert.equal(result.endReason, "Stopped");
  assert.equal(result.collisions, 0);
  assert.ok(result.distance > rover.length);
  assert.ok(Math.abs(result.rotation * rover.wheel_diameter / 2 - result.distance) < 1e-6);
});

test("a downhill track gains speed and checks center axle contact at the crest", () => {
  const sim = create(rover, "ramp");
  const initial = sim.sample;
  assert.equal(initial.stability, "Center axle rocking");
  const moving = sim.advance(0.25);
  assert.ok(moving.speed > initial.speed);
  assert.ok(moving.z < initial.z);
  assert.equal(moving.stability, "Within support");
  assert.equal(finish(sim, 1 / 60).endReason, "End of track");
  assert.notEqual(create({...rover, axle_count: 2}, "ramp").sample.stability, "Center axle rocking");
});

test("swept barrier collision prevents penetration and reverses the toy", () => {
  const sim = create(rover, "barrier");
  const face = sim.track.barrier - Math.max(rover.length, rover.wheelbase + rover.wheel_diameter) / 2;
  assert.ok(sim.track.ramp[2] > 0);
  let sample = sim.sample;
  while (!sample.collisions && !sample.finished) {
    sample = sim.advance(1 / 240);
    assert.ok(sample.x <= face);
  }
  assert.equal(sample.collisions, 1);
  assert.equal(sample.x, face);
  assert.ok(sim.advance(1 / 240).x < face);
  assert.ok(finish(sim, 1 / 60).distance > rover.length);
});

test("fixed-step results match across playback rates and large supported designs", () => {
  const longRover = {...rover, length: 1000, width: 220, wheelbase: 840, wheel_diameter: 100};
  for (const design of [rover, longRover]) {
    const fast = finish(create(design, "barrier"), 1 / 144);
    const slow = finish(create(design, "barrier"), 1 / 20);
    assert.deepEqual(fast, slow);
    assert.ok(fast.collisions >= 1);
    assert.ok(Number.isFinite(fast.supportMargin) && fast.supportMargin > 0);
  }
});

test("a taller body reduces the estimated longitudinal stability margin on a ramp", () => {
  const bare = create(rover, "ramp").advance(0.25);
  const tall = create(rover, "ramp", 52).advance(0.25);
  assert.equal(tall.pitch, bare.pitch);
  assert.ok(tall.supportMargin < bare.supportMargin);
});
