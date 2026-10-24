/** Assemble the Linux desktop and its production dependencies for system Electron. */
import { execFileSync } from 'node:child_process'
import { chmodSync, cpSync, existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve, sep } from 'node:path'
import { prepareOfficeSkillAssets } from '../scripts/primary-runtime/prepare.ts'
import { prepareSystemRuntime } from './system-runtime.mjs'
import { buildSystemSharp } from './build-sharp.mjs'
import { packDesktopAsar } from './pack-asar.mjs'
import { writeDesktopRuntime, verifyDesktopRuntime } from '../apps/desktop/src/runtime-tree.ts'
import { DESKTOP_HOST_PROTOCOL_VERSION } from '../apps/desktop/src/host-protocol.ts'
import { desktopRuntimeFileExclusion } from '../apps/desktop/scripts/runtime-file-policy.ts'

const root = resolve(import.meta.dirname, '..')
process.chdir(root)
if (process.platform !== 'linux' || process.arch !== 'x64') throw new Error('Arch packaging requires Linux x86_64')
const version = JSON.parse(readFileSync('package.json', 'utf8')).version as string
const pkgrel = process.env.DSH_ARCH_PKGREL ?? '1'
if (!/^[1-9]\d*$/u.test(pkgrel)) throw new Error('DSH_ARCH_PKGREL must be a positive integer')
const work = join(root, '.arch-build')
const payload = join(work, 'root')
const app = join(payload, 'usr/lib/dsh-electron')
const runtime = join(app, 'runtime')
const dsh = join(app, 'dsh')
const run = (command: string, args: string[], env = process.env): Buffer => execFileSync(command, args, { stdio: 'inherit', env })
const electron = '/usr/lib/electron/electron'
const versions = JSON.parse(execFileSync(electron, ['-p', 'JSON.stringify(process.versions)'], {
  encoding: 'utf8', env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
})) as { electron: string; node: string }
rmSync(payload, { recursive: true, force: true })
mkdirSync(app, { recursive: true })

function copy(source: string, destination: string): void {
  mkdirSync(dirname(destination), { recursive: true })
  cpSync(source, destination, { recursive: true, dereference: true })
}

/** Materialize pnpm's hoisted deploy, including direct workspace packages hoisted outside its destination. */
function deploy(name: string, source: string, destination: string): void {
  const staging = join(work, `deploy-${name}`)
  rmSync(staging, { recursive: true, force: true })
  run('pnpm', ['--filter', name, 'deploy', '--legacy', '--prod', '--config.allow-unused-patches=true',
    '--config.node-linker=hoisted', '--config.auto-install-peers=false', '--config.link-workspace-packages=true', staging])
  const manifest = JSON.parse(readFileSync(join(staging, 'package.json'), 'utf8')) as { dependencies?: Record<string, string> }
  for (const dependency of Object.keys(manifest.dependencies ?? {})) {
    const target = join(staging, 'node_modules', dependency)
    if (existsSync(target)) continue
    const from = realpathSync(join(root, source, 'node_modules', dependency))
    mkdirSync(dirname(target), { recursive: true })
    cpSync(from, target, { recursive: true, dereference: true,
      filter: path => path !== join(from, 'node_modules') && !path.startsWith(join(from, 'node_modules') + sep) })
  }
  const materialize = (directory: string): void => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name)
      if (entry.name === '.bin') { rmSync(path, { recursive: true, force: true }); continue }
      if (entry.isSymbolicLink()) {
        const from = realpathSync(path)
        rmSync(path)
        cpSync(from, path, { recursive: true, dereference: true,
          filter: file => file !== join(from, 'node_modules') && !file.startsWith(join(from, 'node_modules') + sep) })
      } else if (entry.isDirectory()) materialize(path)
    }
  }
  materialize(join(staging, 'node_modules'))
  // Workspace link: overrides are omitted by the legacy hoister, including transitive uses.
  for (const vendor of ['cosmokit', 'schemastery']) {
    const from = join(root, 'vendor', vendor)
    const target = join(staging, 'node_modules/@deepseek-ai', vendor)
    mkdirSync(dirname(target), { recursive: true })
    cpSync(from, target, { recursive: true, dereference: true,
      filter: path => path !== join(from, 'node_modules') && !path.startsWith(join(from, 'node_modules') + sep) })
  }
  mkdirSync(destination, { recursive: true })
  cpSync(staging, destination, { recursive: true, dereference: true, filter: path => {
    const entry = relative(staging, path)
    if (name === '@deepseek-ai/dsh-desktop' && entry !== ''
      && !['package.json', 'lib', 'renderer', 'resources', 'node_modules'].includes(entry.split(sep)[0]!)) return false
    const modules = `node_modules${sep}`
    return !entry.startsWith(modules)
      || desktopRuntimeFileExclusion(entry.slice(modules.length), { platform: 'linux', arch: 'x64' }, 'wasm') === undefined
  } })
}

try {
  deploy('@deepseek-ai/dsh-desktop', 'apps/desktop', app)
  deploy('dsh-python-runtime-closure', 'python/sdk-runtime', dsh)
} finally {
  // Legacy deploy changes workspace dependency links even when its destination is separate.
  run('pnpm', ['install', '--frozen-lockfile'], { ...process.env, ELECTRON_SKIP_BINARY_DOWNLOAD: '1' })
}
const host = join(dsh, 'node_modules/@deepseek-ai/dsh-desktop-host')
copy('apps/desktop-host/lib', join(host, 'lib'))
copy('apps/desktop-host/package.json', join(host, 'package.json'))
copy('apps/desktop/lib', join(app, 'lib'))
copy('aur/entry.cjs', join(app, 'entry.cjs'))
copy('aur/system-runtime.mjs', join(app, 'system-runtime.mjs'))
const appManifest = JSON.parse(readFileSync(join(app, 'package.json'), 'utf8'))
appManifest.main = 'entry.cjs'
writeFileSync(join(app, 'package.json'), `${JSON.stringify(appManifest, null, 2)}\n`)
copy('apps/desktop/resources', join(app, 'resources'))
copy('apps/desktop/scripts/node-bin', join(runtime, 'bin'))
copy('aur/node', join(runtime, 'bin/node'))
copy('aur/asar-paths.mjs', join(runtime, 'asar-paths.mjs'))
chmodSync(join(runtime, 'bin/node'), 0o755)
copy('aur/pnpm', join(runtime, 'bin/pnpm'))
chmodSync(join(runtime, 'bin/pnpm'), 0o755)
copy('apps/desktop/node_modules/pnpm', join(runtime, 'pnpm'))
// Desktop CLI and the Arch launcher share the same physical pnpm installation.
mkdirSync(join(runtime, 'primary-runtime/dependencies'), { recursive: true })
symlinkSync('../../pnpm', join(runtime, 'primary-runtime/dependencies/pnpm'))
buildSystemSharp(join(dsh, 'node_modules'))
run('patch', ['--batch', '--forward', '-p1', '-d', join(dsh, 'node_modules/node-addon-require-builtin'),
  '-i', join(root, 'aur/require-builtin.patch')])
await prepareOfficeSkillAssets(resolve('packages/skill/skill-office/assets'), join(runtime, 'office-skills'))
const systemRuntime = prepareSystemRuntime(app, join(work, 'system-runtimes'))
const sharedNames = readdirSync(join(dsh, 'node_modules/@deepseek-ai')).map(name => `@deepseek-ai/${name}`)
const ripgrep = join(dsh, 'node_modules/@vscode/ripgrep-linux-x64/bin/rg')
writeFileSync(ripgrep, '#!/bin/sh\nexec /usr/bin/rg "$@"\n', { mode: 0o755 })
rmSync(join(dsh, 'node_modules/node-pty/third_party'), { recursive: true, force: true })
const pnpmVersion = JSON.parse(readFileSync(join(runtime, 'pnpm/package.json'), 'utf8')).version as string
const release = { schemaVersion: 1 as const, version, hostProtocolVersion: DESKTOP_HOST_PROTOCOL_VERSION,
  nodeVersion: versions.node, pnpmVersion }
writeDesktopRuntime(dsh, release, sharedNames)
await verifyDesktopRuntime(dsh, version)
await packDesktopAsar(app, join(work, 'asar-input'))
const smokeEnvironment = { ...Object.fromEntries(Object.entries(process.env).filter(([name]) => !/(?:KEY|SECRET|TOKEN|PASSWORD)/iu.test(name))),
  DSH_DESKTOP_PRIMARY_RUNTIME_IN_PLACE: '1', ELECTRON_RUN_AS_NODE: '1' }
run(electron, ['--expose-internals', '--import', 'tsx/esm', 'aur/smoke-asar.ts', app, systemRuntime, version], smokeEnvironment)
copy('aur/dsh-electron.sh', join(payload, 'usr/bin/dsh-desktop'))
chmodSync(join(payload, 'usr/bin/dsh-desktop'), 0o755)
copy('aur/dsh', join(payload, 'usr/bin/dsh'))
chmodSync(join(payload, 'usr/bin/dsh'), 0o755)
copy('aur/dsh-electron.desktop', join(payload, 'usr/share/applications/dsh-electron.desktop'))
copy('apps/desktop/resources/icon.svg', join(payload, 'usr/share/icons/hicolor/scalable/apps/dsh-electron.svg'))
copy('LICENSE', join(payload, 'usr/share/licenses/dsh-electron/LICENSE'))
copy('THIRD_PARTY_NOTICES.md', join(payload, 'usr/share/licenses/dsh-electron/THIRD_PARTY_NOTICES.md'))
writeFileSync(join(app, 'arch-build.json'), `${JSON.stringify({ version, pkgrel, electron: versions.electron }, null, 2)}\n`)
mkdirSync('release', { recursive: true })
run('tar', ['--zstd', '-cf', `release/dsh-electron-${version}-${pkgrel}-x86_64.tar.zst`, '-C', payload, 'usr'])
