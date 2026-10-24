/** Exercise the public CLI and a locally installed plugin with isolated profile data. */
import assert from 'node:assert/strict'
import { execFile, spawn } from 'node:child_process'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { promisify } from 'node:util'

const app = resolve(process.argv[2] ?? '.arch-build/root/usr/lib/dsh-electron')
const cli = resolve(app, '../../bin/dsh')
const scratch = await mkdtemp(join(tmpdir(), 'dsh-arch-cli-'))
const env = {
  ...Object.fromEntries(Object.entries(process.env).filter(([name]) => !/(?:KEY|SECRET|TOKEN|PASSWORD|^DSH_|^ELECTRON_)/iu.test(name))),
  DSH_HOME: join(scratch, 'home'), DSH_AGENTS_HOME: join(scratch, 'agents'),
}
const run = args => promisify(execFile)(cli, args, { cwd: scratch, env, timeout: 120_000, maxBuffer: 4 * 1024 * 1024 })
let child
let exited
let deadline
try {
  assert.match((await run(['--help'])).stdout, /dsh plugin/)
  const version = JSON.parse(await readFile(join(app, 'package.json'), 'utf8')).version
  assert.equal((await run(['--version'])).stdout.trim(), version)
  assert.match((await run(['web', '--help'])).stdout, /Serve the DeepSeek Harness browser UI/)
  for (const profile of ['headless', 'sdk', 'sdk-minimal', 'acp']) {
    const result = await run(['--profile', profile, '--dump-default-config'])
    assert.ok(result.stdout.includes('name:'), `${profile} ships its composition`)
  }
  const plugin = join(scratch, 'plugin')
  const name = 'dsh-arch-cli-smoke-plugin'
  await mkdir(plugin)
  await writeFile(join(plugin, 'package.json'), JSON.stringify({ name, version: '1.0.0', type: 'module',
    exports: './index.js', dsh: { bundle: { patch: 'bundle.yml' } } }))
  await writeFile(join(plugin, 'index.js'), `export function apply(ctx) {
  ctx.effect(() => ctx.webServer.register({ kind: 'exact', path: '/arch-cli-smoke',
    handler(_request, response) { response.end('installed plugin works') } }))
}\n`)
  await writeFile(join(plugin, 'bundle.yml'), `- insert:\n    - id: arch-cli-smoke\n      name: ${name}\n      inject: [webServer]\n`)
  await run(['plugin', '--profile', 'web', 'add', `file:${plugin}`, '--offline', '--ignore-scripts'])
  assert.match((await run(['plugin', '--profile', 'web', 'list', '--json'])).stdout, new RegExp(name))
  child = spawn(cli, ['web', '--host', '127.0.0.1', '--port', '0', '--no-open'], { cwd: scratch, env, stdio: ['ignore', 'pipe', 'pipe'] })
  exited = new Promise(resolveExit => { child.once('close', (code, signal) => { resolveExit({ code, signal }) }) })
  let output = ''
  const ready = new Promise((resolveReady, reject) => {
    child.once('error', reject)
    child.stdout.on('data', (data) => {
      output += data.toString()
      const match = output.match(/dsh web: (http:\/\/127\.0\.0\.1:\d+\/\?token=[^\s]+)/)
      if (match) resolveReady(match[1])
    })
    child.stderr.on('data', data => { output += data.toString() })
    child.once('exit', () => { reject(new Error(`CLI exited before readiness:\n${output}`)) })
    deadline = setTimeout(() => { reject(new Error(`CLI readiness timed out:\n${output}`)) }, 120_000)
  })
  const url = await ready
  clearTimeout(deadline)
  const login = await fetch(url, { redirect: 'manual', signal: AbortSignal.timeout(30_000) })
  const cookie = login.headers.getSetCookie().map(value => value.split(';')[0]).join('; ')
  const page = await fetch(new URL('/', url), { headers: { cookie }, signal: AbortSignal.timeout(30_000) })
  assert.match(await page.text(), /<html/)
  const response = await fetch(new URL('/arch-cli-smoke', url), { headers: { cookie }, signal: AbortSignal.timeout(30_000) })
  assert.equal(await response.text(), 'installed plugin works')
  child.kill('SIGINT')
  const outcome = await Promise.race([exited, new Promise((_, reject) => {
    deadline = setTimeout(() => { reject(new Error('CLI shutdown timed out')) }, 30_000)
  })])
  assert.deepEqual(outcome, { code: 130, signal: null })
  console.log('Arch CLI: help, version, shipped profiles, bundled pnpm, local plugin installation and dsh web passed')
} finally {
  clearTimeout(deadline)
  if (child && child.exitCode === null && child.signalCode === null) child.kill('SIGKILL')
  if (exited) await exited
  await rm(scratch, { recursive: true, force: true })
}
