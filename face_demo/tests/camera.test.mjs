import { test } from "node:test";
import assert from "node:assert/strict";
import { LiveCamera } from "../static/camera.mjs";

const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};
const settle = () => new Promise(setImmediate);
function fixtures() {
  const track = { stops: 0, listeners: {}, stop() { this.stops++; }, addEventListener(name, fn) { this.listeners[name] = fn; } };
  const stream = { getTracks: () => [track], getVideoTracks: () => [track] };
  const video = { srcObject: null, videoWidth: 1280, videoHeight: 720, readyState: 2, play: async () => {} };
  const canvas = { getContext: () => ({ drawImage() {} }), toBlob: (callback) => callback(new Blob(["frame"], { type: "image/jpeg" })) };
  return { track, stream, video, canvas };
}

test("cancelling while camera permission is pending releases the eventual stream", async () => {
  const { stream, track, video } = fixtures();
  const permission = deferred();
  const camera = new LiveCamera(video, { getMedia: () => permission.promise });
  let requests = 0;
  const started = camera.start({ requestFrame: () => { requests++; } });
  camera.stop(); permission.resolve(stream); await started;
  assert.equal(track.stops, 1);
  assert.equal(requests, 0);
  assert.equal(video.srcObject, null);
});

test("stopping during a frame request aborts it and ignores its late result", async () => {
  const { stream, track, video, canvas } = fixtures();
  const pending = deferred();
  const camera = new LiveCamera(video, { getMedia: async () => stream, createCanvas: () => canvas });
  let signal, results = 0;
  await camera.start({ requestFrame: (_blob, requestSignal) => { signal = requestSignal; return pending.promise; }, onFrame: () => { results++; } });
  await settle(); camera.stop(); pending.resolve({ captured: true }); await settle();
  assert.equal(signal.aborted, true);
  assert.equal(results, 0);
  assert.equal(track.stops, 1);
  assert.equal(camera.timer, null);
});

test("only one frame request is pending at a time and capture respects the CPU image limit", async () => {
  const { stream, video, canvas } = fixtures();
  const pending = deferred();
  const camera = new LiveCamera(video, { getMedia: async () => stream, createCanvas: () => canvas });
  let requests = 0, results = 0;
  await camera.start({ interval: 1, requestFrame: () => { requests++; return pending.promise; },
    onFrame: () => { results++; camera.stop(); } });
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(requests, 1);
  assert.equal(canvas.width, 640); assert.equal(canvas.height, 360);
  pending.resolve({ captured: true }); await settle();
  assert.equal(results, 1); assert.equal(camera.active, false);
});

test("denied camera permission reports the cause without sending a frame", async () => {
  const { video } = fixtures();
  const denied = new Error("denied"); denied.name = "NotAllowedError";
  const camera = new LiveCamera(video, { getMedia: async () => { throw denied; } });
  let reported, requests = 0;
  await camera.start({ requestFrame: () => { requests++; }, onError: (error) => { reported = error; } });
  assert.equal(reported, denied); assert.equal(requests, 0); assert.equal(camera.active, false);
});

test("a frame error releases camera tracks and stops further requests", async () => {
  const { stream, track, video, canvas } = fixtures();
  const camera = new LiveCamera(video, { getMedia: async () => stream, createCanvas: () => canvas });
  const failed = new Error("server failed"); let reported;
  await camera.start({ requestFrame: async () => { throw failed; }, onError: (error) => { reported = error; } });
  await settle();
  assert.equal(reported, failed); assert.equal(track.stops, 1); assert.equal(camera.timer, null);
});
