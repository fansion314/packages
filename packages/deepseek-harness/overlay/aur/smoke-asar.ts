/** Verify the archived runtime through Electron's filesystem before publishing the Arch payload. */
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { existsSync, lstatSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { inventoryDesktopRuntime, readDesktopRuntime } from '../apps/desktop/src/runtime-tree.ts'
import { smokeDesktopRuntime } from '../apps/desktop/scripts/smoke-runtime.ts'

const app = resolve(process.argv[2]!)
const resources = resolve(process.argv[3]!)
const version = process.argv[4]!
assert.equal(process.versions.electron?.split('.')[0], '44')
const runtime = join(app, 'app.asar', 'dsh')
const descriptor = readDesktopRuntime(runtime)
assert.equal(descriptor.release.version, version)
assert.equal(descriptor.platform, process.platform)
assert.equal(descriptor.arch, process.arch)
// Electron's virtual stat omits executable bits for unpacked files; inspect their physical copies.
const files = inventoryDesktopRuntime(runtime).map((file) => {
  const physical = join(app, 'app.asar.unpacked', 'dsh', file.path)
  return existsSync(physical) ? { ...file, executable: (lstatSync(physical).mode & 0o111) !== 0 } : file
})
assert.deepEqual(files, descriptor.files)
const node = join(app, 'runtime/bin/node')
execFileSync(node, ['apps/desktop/tests/fixtures/runtime-payload-smoke.mjs', runtime, resources], {
  env: process.env, stdio: 'inherit',
})
await smokeDesktopRuntime(runtime, node, descriptor, process.env, resources)
