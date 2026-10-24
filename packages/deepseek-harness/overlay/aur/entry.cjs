/** Select distribution-owned resource paths when launched by Arch's system Electron. */
const { app } = require('electron')
Object.defineProperty(app, 'isPackaged', { value: false })
app.setPath('exe', '/usr/bin/dsh-desktop')
app.setDesktopName('dsh-electron.desktop')
import('./lib/main.js')
