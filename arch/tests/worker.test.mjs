import assert from "node:assert/strict";
import test from "node:test";
import { createWorker } from "../worker.mjs";

const package1 = "/x86_64/foo-1.0-1-x86_64.pkg.tar.zst";
const package2 = "/x86_64/foo-2.0-1-x86_64.pkg.tar.zst";
function router(active, phase) {
  return createWorker({ active, candidate: "new", phase, snapshots: ["old", "new"], instructions: "setup",
    mirror: { repository: "test/mirror", active, snapshots: ["old", "new"] }, assets: {
    "/x86_64/fansionia.db": `https://pages.example/snapshots/${active}/fansionia.db`,
    [package1]: "https://github.com/example/foo/releases/download/v1/foo-1.0-1-x86_64.pkg.tar.zst",
    [package2]: "https://github.com/example/foo/releases/download/v2/foo-2.0-1-x86_64.pkg.tar.zst",
    [package2 + ".sig"]: "https://github.com/example/foo/releases/download/v2/foo-2.0-1-x86_64.pkg.tar.zst.sig",
    "/mirror/x86_64/fansionia.db": `https://cnb.cool/test/mirror/-/releases/download/${active}/fansionia.db`,
    ["/mirror" + package1]: "https://cnb.cool/test/mirror/-/releases/download/v1/foo-1.0-1-x86_64.pkg.tar.zst",
    ["/mirror" + package2]: "https://cnb.cool/test/mirror/-/releases/download/v2/foo-2.0-1-x86_64.pkg.tar.zst",
  } });
}
const request = (path, method = "GET") => new Request(`https://packages.example${path}`, { method });

test("a new database can download its package through the previous preparation version", async () => {
  const prepare = router("old", "prepare");
  const active = router("new", "active");
  assert.match(active.fetch(request("/x86_64/fansionia.db")).headers.get("location"), /snapshots\/new\//);
  assert.match(prepare.fetch(request("/x86_64/fansionia.db")).headers.get("location"), /snapshots\/old\//);
  for (const worker of [prepare, active]) {
    for (const path of [package1, package2, package2 + ".sig"]) {
      assert.equal(worker.fetch(request(path)).status, 302);
    }
  }
});

test("both origins select the same phase and the mirror never falls back to GitHub", async () => {
  for (const [selected, phase] of [["old", "prepare"], ["new", "active"]]) {
    const worker = router(selected, phase);
    const primary = worker.fetch(request("/x86_64/fansionia.db")).headers.get("location");
    const mirror = worker.fetch(request("/mirror/x86_64/fansionia.db")).headers.get("location");
    assert.match(primary, new RegExp(`/snapshots/${selected}/`));
    assert.match(mirror, new RegExp(`^https://cnb.cool/.*/${selected}/`));
    assert.match(worker.fetch(request("/mirror" + package2)).headers.get("location"), /^https:\/\/cnb.cool\//);
    const status = await worker.fetch(request("/mirror/status.json")).json();
    assert.equal(status.active, status.mirror.active);
    assert.equal(worker.fetch(request("/mirror/x86_64/unknown")).status, 404);
    assert.equal(worker.fetch(request("/mirror/x86_64/__proto__")).status, 404);
    assert.equal(worker.fetch(request("/mirror" + package2, "POST")).status, 405);
    assert.equal(worker.fetch(request("/mirror" + package2, "HEAD")).body, null);
  }
});

test("rollback keeps packages referenced by the newer cached database", () => {
  const rollback = router("old", "active");
  assert.equal(rollback.fetch(request(package2)).status, 302);
});

test("only exact embedded locations are redirected; unsafe paths and methods fail", () => {
  const worker = router("new", "active");
  for (const path of ["/x86_64/__proto__", "/x86_64/unknown.pkg.tar.zst", "/x86_64/%2Ffoo.pkg.tar.zst", "//github.com/evil"]) {
    assert.equal(worker.fetch(request(path)).status, 404);
  }
  assert.equal(worker.fetch(request(package2, "POST")).status, 405);
  const response = worker.fetch(request(package2, "HEAD"));
  assert.equal(response.status, 302);
  assert.equal(response.body, null);
  assert.equal(response.headers.get("cache-control"), "no-store");
});
