/* Longitudinal, fixed-step rolling model in mm, seconds, and radians. */
(() => {
  "use strict";

  const gravity = 9810;
  const step = 1 / 240;
  const restitution = 0.22;
  const rollingLoss = 0.023;
  const inertiaRatio = 0.14; // Lumped wheel inertia as a fraction of m*r².
  const limitations = "Estimate only. One-dimensional rigid rolling with approximate grip, mass distribution and barrier bounce. No steering, suspension, deformation or material validation.";

  function create(design, scenario) {
    if (!["floor", "ramp", "barrier"].includes(scenario)) {
      throw new RangeError("Choose a floor, ramp or barrier track.");
    }
    const {length, width, height, wheelbase, wheel_diameter: diameter, axle_count: axles} = design;
    const radius = diameter / 2;
    const size = Math.max(length, wheelbase + diameter);
    const halfTrack = width / 2 + design.wheel_gap + design.wheel_thickness / 2;
    const slope = scenario === "floor" ? 0 : 0.22;
    const run = size * 2.1;
    const runStart = -size * 0.55;
    const runEnd = runStart + run;
    const barrier = scenario === "barrier" ? size * 2.7 : null;
    const limit = size * 3.45;
    const start = -size * 0.55;
    const track = {
      start: start - size * 0.6,
      end: limit + size * 0.55,
      ramp: [runStart, runEnd, run * slope],
      width: Math.max(halfTrack * 3.1, size * 0.8),
      barrier,
      barrierHeight: diameter * 0.72,
      barrierDepth: size * 0.12,
    };

    const floor = x => slope * Math.max(0, Math.min(run, runEnd - x));

    function pose(x) {
      let angle = 0;
      for (let i = 0; i < 5; i++) {
        const wheelOffset = Math.cos(angle) * wheelbase / 2;
        angle = Math.asin((floor(x + wheelOffset) - floor(x - wheelOffset)) / wheelbase);
      }
      const offset = Math.cos(angle) * wheelbase / 2;
      const ground = (floor(x - offset) + floor(x + offset)) / 2;
      // A third axle can lift the outside wheels over a convex transition.
      const middleLift = axles === 3 ? Math.max(0, floor(x) - ground) : 0;
      return {pitch: angle, z: ground + middleLift + radius / Math.cos(angle), middleLift};
    }

    let x = start;
    let speed = Math.sqrt(2 * gravity * (slope ? 0.009 : 0.075) * size);
    let elapsed = 0;
    let distance = 0;
    let rotation = 0;
    let collisions = 0;
    let remainder = 0;
    let endReason = "";

    const sample = () => {
      const {pitch, z, middleLift} = pose(x);
      // Nominal symmetric mass. Check gravity's line of action against outer axles.
      const supportMargin = wheelbase / 2 - Math.abs(Math.tan(pitch)) * (radius + height / 8);
      const stability = supportMargin <= 0 ? "Tip risk"
        : middleLift > diameter * 0.015 ? "Center axle rocking"
          : supportMargin < wheelbase * 0.12 ? "Narrow support" : "Within support";
      return {x, z, pitch, rotation, speed: Math.abs(speed), distance, collisions,
        stability, supportMargin, finished: Boolean(endReason), endReason, time: elapsed};
    };

    function integrate() {
      const {pitch} = pose(x);
      const downhill = -gravity * Math.sin(pitch) / (1 + inertiaRatio);
      const drag = gravity * rollingLoss * Math.cos(pitch);
      if (Math.abs(speed) <= drag * step && Math.abs(downhill) <= drag) {
        speed = 0;
      } else {
        const sign = Math.sign(speed) || Math.sign(downhill);
        const next = speed + (downhill - sign * drag) * step;
        speed = Math.sign(next) === sign || Math.abs(downhill) > drag ? next : 0;
      }
      let nextX = x + Math.cos(pitch) * speed * step;
      if (barrier !== null) {
        const contact = barrier - size / 2;
        if (speed > 0 && nextX >= contact) {
          nextX = contact;
          speed *= -restitution;
          collisions++;
        }
      }
      nextX = Math.max(track.start + size / 2, Math.min(limit, nextX));
      const travel = Math.hypot(nextX - x, pose(nextX).z - pose(x).z) * Math.sign(nextX - x);
      distance += Math.abs(travel);
      rotation += travel / radius;
      x = nextX;
      elapsed += step;
      if (speed === 0) endReason = "Stopped";
      else if (x === limit || x === track.start + size / 2) endReason = "End of track";
      else if (elapsed >= 12) endReason = "Time limit";
    }

    return {
      track,
      get sample() { return sample(); },
      advance(seconds) {
        if (Number.isFinite(seconds) && seconds > 0) remainder += Math.min(0.25, seconds);
        while (!endReason && remainder + 1e-12 >= step) {
          remainder -= step;
          integrate();
        }
        return sample();
      },
    };
  }

  window.MagtelPhysics = Object.freeze({create, limitations});
})();
