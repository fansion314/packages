// Pin the -bin recipe to the single application archive produced by CI.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { basename, join } from 'node:path';
import { createHash } from 'node:crypto';

const [template, output, version, release, archive] = process.argv.slice(2);
if (!/^\d[\w.+]*$/.test(version) || !/^\d+$/.test(release)) {
  throw new Error('Invalid package version or release');
}
const name = basename(archive);
if (name !== `bitwarden-electron-${version}-${release}-x86_64.pkg.tar.zst`) {
  throw new Error(`Unexpected application archive name: ${name}`);
}
const digest = createHash('sha256').update(readFileSync(archive)).digest('hex');
let text = readFileSync(template, 'utf8');
for (const [pattern, replacement] of [
  [/^pkgver=.*$/gm, `pkgver=${version}`],
  [/^pkgrel=.*$/gm, `pkgrel=${release}`],
  [/^_release=.*$/gm, `_release='${version}-${release}'`],
  [/^_archive=.*$/gm, `_archive='${name}'`],
  [/^sha256sums=.*$/gm, `sha256sums=('${digest}')`],
]) {
  if ([...text.matchAll(pattern)].length !== 1) throw new Error(`Invalid template: ${pattern}`);
  text = text.replace(pattern, () => replacement);
}
mkdirSync(output, { recursive: true });
writeFileSync(join(output, 'PKGBUILD'), text);
