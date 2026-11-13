// Disposable native Arch CI only: load the packaged bootstrap with system Electron.
const assert = require('node:assert/strict')
const path = require('node:path')
const { app } = require('electron')

const archive = path.resolve(process.argv[2], 'app.asar')
const metadata = require(path.join(archive, 'package.json'))
assert.equal(app.getVersion(), metadata.version)
app.setAppPath(archive)
app.setName(metadata.name)
let finished = false
const timeout = setTimeout(() => {
  console.error('Obsidian did not finish loading a window')
  app.exit(1)
}, 60000)

app.on('browser-window-created', (_event, window) => {
  window.webContents.on('render-process-gone', (_event, details) => {
    console.error('Obsidian renderer exited', details)
    app.exit(1)
  })
  window.webContents.on('did-finish-load', async () => {
    if (finished) return
    try {
      let state
      for (let attempt = 0; attempt < 100; attempt++) {
        state = await window.webContents.executeJavaScript(
          '({ready: document.readyState, text: document.body.innerText})'
        )
        if (window.isVisible() && /Obsidian|vault/i.test(state.text)) break
        await new Promise(resolve => setTimeout(resolve, 100))
      }
      assert.equal(state.ready, 'complete')
      assert.match(state.text, /Obsidian|vault/i)
      assert.ok(window.isVisible(), 'Obsidian window must be visible')
      finished = true
      clearTimeout(timeout)
      console.log('OBSIDIAN_STARTUP_OK', JSON.stringify({ version: metadata.version, electron: process.versions.electron }))
      app.exit(0)
    } catch (error) {
      console.error(error)
      app.exit(1)
    }
  })
})

require(archive)
