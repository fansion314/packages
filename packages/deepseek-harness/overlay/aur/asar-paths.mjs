/** Office's standalone workers and engine probes require the complete physical package closure. */
import { registerHooks } from 'node:module'

const source = new URL('../app.asar/dsh/node_modules/@deepseek-ai/libreoffice-kit', import.meta.url).href
const physical = new URL('../app.asar.unpacked/dsh/node_modules/@deepseek-ai/libreoffice-kit', import.meta.url).href

registerHooks({
  resolve(specifier, context, nextResolve) {
    const result = nextResolve(specifier, context)
    if (!result.url.startsWith(source + '/') && !result.url.startsWith(source + '-')) return result
    return { ...result, url: physical + result.url.slice(source.length) }
  },
})
