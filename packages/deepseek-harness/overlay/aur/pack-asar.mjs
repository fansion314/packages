/** Archive the application while retaining native binaries and the upstream Office closure on disk. */
import { cpSync, mkdirSync, renameSync, rmSync } from 'node:fs'
import { createRequire } from 'node:module'
import { join, relative } from 'node:path'
import { officePackageDirectories } from '../scripts/libreoffice-packages.mjs'

const desktopRequire = createRequire(new URL('../apps/desktop/package.json', import.meta.url))
const { createPackageWithOptions } = createRequire(desktopRequire.resolve('app-builder-lib'))('@electron/asar')

/**
 * Package the verified application using electron-builder's ASAR toolchain and Office exclusions.
 * @param {string} app - Output directory, including the external runtime resources.
 * @param {string} staging - Disposable directory used to assemble the archive.
 * @returns {Promise<string>} Final application archive path.
 */
export async function packDesktopAsar(app, staging) {
  rmSync(staging, { recursive: true, force: true })
  mkdirSync(staging, { recursive: true })
  for (const entry of ['lib', 'renderer', 'resources', 'node_modules', 'dsh', 'entry.cjs']) {
    renameSync(join(app, entry), join(staging, entry))
  }
  cpSync(join(app, 'package.json'), join(staging, 'package.json'))
  rmSync(join(staging, 'lib/types'), { recursive: true, force: true })
  const office = await officePackageDirectories(join(staging, 'dsh'), { platform: 'linux', arch: 'x64' })
  const archive = join(app, 'app.asar')
  await createPackageWithOptions(staging, archive, {
    unpack: '{*.node,*.dylib,*.dll,*.so,*.so.*,*.exe,spawn-helper,rg}',
    unpackDir: `{${office.map(directory => relative(staging, directory)).join(',')}}`,
  })
  return archive
}
