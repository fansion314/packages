import assert from "node:assert/strict";
import { test } from "node:test";
import { createInterfaceScale, INTERFACE_SCALES, scaleShortcut } from "../src/interfaceScale.ts";
import { detectPlatform, mediaOrigin } from "../src/platform.ts";

function host(saved = null) {
  let store = saved;
  const calls = [];
  return { calls, get stored() { return store; }, read: () => store, write: value => { store = value; }, setZoom: async value => { calls.push(value); } };
}

test("Linux protocol agrees with Rust and mobile UA precedence stays intact", () => {
  for (const [ua, points, expected] of [
    ["Mozilla/5.0 (X11; Linux x86_64) AppleWebKit", 0, "linux"],
    ["Mozilla/5.0 (Linux; Android 16)", 5, "android"],
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)", 5, "ios"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X)", 5, "ios"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X)", 0, "macos"],
    ["Mozilla/5.0 (Windows NT 10.0)", 0, "windows"],
  ]) assert.equal(detectPlatform(ua, points), expected);
  assert.equal(detectPlatform("Mozilla/5.0 AppleWebKit", 5, "MacIntel"), "ios");
  for (const platform of ["linux", "macos", "ios"]) assert.equal(mediaOrigin(platform), "hg://localhost");
  for (const platform of ["android", "windows"]) assert.equal(mediaOrigin(platform), "http://hg.localhost");
});

test("each supported scale applies natively, persists and survives restart", async () => {
  const storage = host();
  const controller = createInterfaceScale(storage);
  await controller.initialize();
  for (const scale of INTERFACE_SCALES) {
    await controller.set(scale);
    assert.equal(storage.calls.at(-1), scale / 100);
    assert.equal(storage.stored, String(scale));
    const restarted = createInterfaceScale(storage);
    await restarted.initialize();
    assert.equal(restarted.getSnapshot().value, scale);
  }
});

test("invalid stored values and blocked storage keep a usable default", async () => {
  for (const saved of [null, "", "broken", "NaN", "Infinity", "0", "-1", "300", "{}", "1.25"]) {
    const controller = createInterfaceScale(host(saved));
    await controller.initialize();
    assert.equal(controller.getSnapshot().value, 100);
  }
  const controller = createInterfaceScale({ setZoom: async () => {}, read() { throw Error(); }, write() { throw Error(); } });
  await controller.initialize();
  assert.equal(controller.getSnapshot().value, 100);
  assert.match(controller.getSnapshot().error, /无法保存/);
});

test("native failure retains successful state and allows retry", async () => {
  const storage = host("125");
  let fail = false;
  storage.setZoom = async value => { if (fail) throw Error(); storage.calls.push(value); };
  const controller = createInterfaceScale(storage);
  await controller.initialize();
  fail = true;
  await controller.set(200);
  assert.equal(controller.getSnapshot().value, 125);
  assert.equal(storage.stored, "125");
  assert.match(controller.getSnapshot().error, /缩放失败/);
  fail = false;
  await controller.set(150);
  assert.equal(controller.getSnapshot().value, 150);
  assert.equal(controller.getSnapshot().error, null);
});

test("queued requests serialize native calls and shortcuts use last successful state", async () => {
  const storage = host("100");
  const controller = createInterfaceScale(storage);
  await Promise.all([controller.initialize(), controller.initialize()]);
  assert.equal(storage.calls.length, 1);
  await Promise.all([controller.step(1), controller.step(1), controller.step(1)]);
  assert.deepEqual(storage.calls, [1, 1.1, 1.25, 1.5]);
  await controller.set(200);
  await controller.step(1);
  assert.equal(controller.getSnapshot().value, 200);
  await controller.set(75);
  await controller.step(-1);
  assert.equal(controller.getSnapshot().value, 75);
  await controller.step(0);
  assert.equal(controller.getSnapshot().value, 100);
  assert.equal(controller.getSnapshot().pending, false);
  await controller.set(123);
  assert.equal(controller.getSnapshot().value, 100);
  assert.match(controller.getSnapshot().error, /不支持/);
});

test("only Ctrl zoom shortcuts consume keys", () => {
  const event = { key: "=", code: "Equal", ctrlKey: true, metaKey: false, altKey: false, isComposing: false };
  for (const key of ["+", "="]) assert.equal(scaleShortcut({ ...event, key }), 1);
  assert.equal(scaleShortcut({ ...event, key: "-" }), -1);
  assert.equal(scaleShortcut({ ...event, key: "0" }), 0);
  assert.equal(scaleShortcut({ ...event, key: "1" }), null);
  for (const change of [{ ctrlKey: false }, { metaKey: true }, { altKey: true }, { isComposing: true }]) {
    assert.equal(scaleShortcut({ ...event, ...change }), null);
  }
});
