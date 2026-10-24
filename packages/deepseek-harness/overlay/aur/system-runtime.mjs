/** Describe pacman-owned interpreters without copying them into the application or Harness home. */
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, renameSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const distributions = ['numpy', 'pandas', 'python-dateutil', 'six', 'tzdata', 'python-docx', 'python-pptx',
  'openpyxl', 'Pillow', 'lxml', 'XlsxWriter', 'typing_extensions', 'et_xmlfile']

/**
 * Create or reuse metadata and links for the currently installed system packages.
 * @param {string} appRoot - Installed application directory, including runtime/office-skills.
 * @param {string} cacheRoot - User-owned metadata cache, also used by isolated build checks.
 * @returns {string} Absolute runtime directory containing primary-runtime/ and office-skills.
 */
export function prepareSystemRuntime(appRoot, cacheRoot) {
  const python = JSON.parse(execFileSync('/usr/bin/python', ['-I', '-B', '-c',
    'import importlib.metadata as m, json, platform, sys; import numpy, pandas, docx, pptx, openpyxl, PIL, lxml, xlsxwriter; print(json.dumps({"version": platform.python_version(), "packages": {n: m.version(n) for n in json.loads(sys.argv[1])}}))',
    JSON.stringify(distributions)], { encoding: 'utf8' }))
  const node = execFileSync('/usr/lib/electron/electron', ['-p', 'process.versions.node'], {
    encoding: 'utf8', env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
  }).trim()
  const pnpmRoot = join(appRoot, 'runtime/pnpm')
  const pnpm = JSON.parse(readFileSync(join(pnpmRoot, 'package.json'), 'utf8')).version
  const version = JSON.parse(readFileSync(join(appRoot, 'package.json'), 'utf8')).version
  const manifest = { desktopVersion: version, platform: 'linux', arch: 'x64', python: python.version,
    node, pnpm, pythonPackages: python.packages }
  const digest = createHash('sha256').update(JSON.stringify({ format: 4, appRoot: resolve(appRoot), manifest })).digest('hex')
  const destination = join(resolve(cacheRoot), digest)
  if (existsSync(join(destination, 'primary-runtime/runtime.json'))) return destination
  mkdirSync(cacheRoot, { recursive: true, mode: 0o700 })
  const staging = mkdtempSync(join(resolve(cacheRoot), '.prepare-'))
  try {
    const primary = join(staging, 'primary-runtime')
    const dependencies = join(primary, 'dependencies')
    mkdirSync(join(dependencies, 'node/bin'), { recursive: true })
    mkdirSync(join(dependencies, 'node/node_modules'))
    symlinkSync(join(appRoot, 'runtime/bin/node'), join(dependencies, 'node/bin/node'))
    const pythonRoot = join(dependencies, 'python')
    const interpreter = `python${python.version.split('.').slice(0, 2).join('.')}`
    mkdirSync(join(pythonRoot, 'bin'), { recursive: true })
    writeFileSync(join(pythonRoot, 'bin', interpreter), '#!/bin/sh\nexec /usr/bin/python "$@"\n', { mode: 0o755 })
    for (const name of ['python', 'python3']) symlinkSync(interpreter, join(pythonRoot, 'bin', name))
    symlinkSync('/usr/lib', join(pythonRoot, 'lib'))
    symlinkSync(pnpmRoot, join(dependencies, 'pnpm'))
    writeFileSync(join(staging, 'versions.json'), `${JSON.stringify({ node, pnpm, python: python.version }, null, 2)}\n`)
    symlinkSync(join(appRoot, 'runtime/bin'), join(staging, 'bin'))
    symlinkSync(join(appRoot, 'runtime/office-skills'), join(staging, 'office-skills'))
    writeFileSync(join(primary, 'runtime.json'), `${JSON.stringify({ ...manifest, payloadDigest: digest }, null, 2)}\n`)
    try { renameSync(staging, destination) } catch (error) {
      // Concurrent launches can publish identical metadata first.
      if (!['EEXIST', 'ENOTEMPTY'].includes(error.code)) throw error
    }
  } finally { rmSync(staging, { recursive: true, force: true }) }
  return destination
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv.length !== 4) throw new Error('Usage: system-runtime.mjs <application-directory> <metadata-cache>')
  console.log(prepareSystemRuntime(resolve(process.argv[2]), resolve(process.argv[3])))
}
