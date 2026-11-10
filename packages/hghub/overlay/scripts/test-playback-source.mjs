import assert from "node:assert/strict";
import { test } from "node:test";
import { loadPlayback, playbackSource } from "../src/playbackSource.ts";

const info = (fields) => ({ id: 42, ep_num: 1, duration: 60, title: "fixture", ...fields });
const flush = () => new Promise((resolve) => setImmediate(resolve));

// Minireel/HGhub#31: GET playback returned empty legacy fields after an API change.
test("main stream takes priority and legacy mirrors remain playable", () => {
  assert.equal(playbackSource(info({ streams: { main: "https://media.invalid/new.m3u8" } })), "https://media.invalid/new.m3u8");
  assert.equal(playbackSource(info({ streams: { main: "new" }, video_url: "old" })), "new");
  assert.equal(playbackSource(info({ video_url: "old" })), "old");
  assert.equal(playbackSource(info({ streams: { main: "" }, video_url: "old" })), "old");
});

test("missing full streams fail without substituting previews or unsupported HEVC", () => {
  for (const value of [undefined, null, info({}), info({ video_url: "", streams: { main: "" } }),
    info({ streams: { preview: "preview", hevc: "hevc" } })]) {
    assert.throws(() => playbackSource(value), /暂无播放地址/);
  }
});

test("successful and failed requests deliver the source or readable error", async () => {
  const sources = [], errors = [];
  const failure = new Error("服务器请求失败（HTTP 503）");
  loadPlayback(async () => info({ streams: { main: "new" } }), (url) => sources.push(url), (error) => errors.push(error));
  loadPlayback(async () => { throw failure; }, (url) => sources.push(url), (error) => errors.push(error));
  loadPlayback(async () => info({}), (url) => sources.push(url), (error) => errors.push(error));
  await flush();
  assert.deepEqual(sources, ["new"]);
  assert.equal(errors[0], failure);
  assert.match(errors[1].message, /暂无播放地址/);
});

test("switching episodes ignores the old response and old failure", async () => {
  const sources = [], errors = [];
  let resolveOld, rejectOld;
  const cancelSource = loadPlayback(() => new Promise((resolve) => { resolveOld = resolve; }),
    (url) => sources.push(url), (error) => errors.push(error));
  const cancelError = loadPlayback(() => new Promise((_resolve, reject) => { rejectOld = reject; }),
    (url) => sources.push(url), (error) => errors.push(error));
  cancelSource(); cancelError();
  loadPlayback(async () => info({ ep_num: 2, streams: { main: "episode-2" } }),
    (url) => sources.push(url), (error) => errors.push(error));
  resolveOld(info({ streams: { main: "episode-1" } }));
  rejectOld(new Error("late failure"));
  await flush();
  assert.deepEqual(sources, ["episode-2"]);
  assert.deepEqual(errors, []);
});
