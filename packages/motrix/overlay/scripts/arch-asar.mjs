import { createPackageWithOptions } from '@electron/asar'

/** Keep native addons outside ASAR even when the source is inside a hidden build directory. */
export async function packArchApplication(source, destination) {
  // asar matches this pattern against absolute paths with matchBase enabled.
  // A basename pattern also works below .work; **/*.node skips hidden ancestors.
  await createPackageWithOptions(source, destination, {
    unpack: '*.node',
    unpackDir: 'dist/renderer',
  })
}
