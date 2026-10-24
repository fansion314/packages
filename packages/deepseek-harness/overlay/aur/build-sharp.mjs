/** Compile the deployed sharp addon against Arch libvips without changing workspace dependencies. */
import { execFileSync } from 'node:child_process'
import { readdirSync, rmSync } from 'node:fs'
import { join } from 'node:path'

/**
 * Build and retain only the Node-API addon, removing bundled sharp/libvips binaries.
 * @param {string} modules - Materialized production node_modules directory.
 */
export function buildSystemSharp(modules) {
  const sharp = join(modules, 'sharp')
  const env = { ...process.env, SHARP_FORCE_GLOBAL_LIBVIPS: '1', SHARP_IGNORE_GLOBAL_LIBVIPS: '',
    NODE_PATH: `${modules}:/usr/lib/node_modules` }
  execFileSync('node-gyp', ['rebuild', '--directory', join(sharp, 'src'), '--nodedir=/usr'], { env, stdio: 'inherit' })
  const build = join(sharp, 'src/build')
  const release = join(build, 'Release')
  const addon = readdirSync(release).find(name => name.endsWith('.node'))
  if (!addon) throw new Error('sharp build produced no Node-API addon')
  const binary = join(release, addon)
  execFileSync('strip', ['--strip-unneeded', binary])
  const libraries = execFileSync('ldd', [binary], { encoding: 'utf8' })
  if (!/libvips-cpp\.so[^\n]*=> \/usr\/lib\//u.test(libraries) || /not found|@img/u.test(libraries)) {
    throw new Error(`sharp must link installed system libraries:\n${libraries}`)
  }
  for (const entry of readdirSync(build)) {
    if (entry !== 'Release') rmSync(join(build, entry), { recursive: true, force: true })
  }
  for (const entry of readdirSync(release)) {
    if (entry !== addon) rmSync(join(release, entry), { recursive: true, force: true })
  }
  for (const entry of readdirSync(join(modules, '@img'))) {
    if (entry.startsWith('sharp-')) rmSync(join(modules, '@img', entry), { recursive: true, force: true })
  }
}
