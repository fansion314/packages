/** Wait for Electron's asynchronous native visibility transition without accepting destruction. */
import assert from 'node:assert/strict'
import { setTimeout as delay } from 'node:timers/promises'

/** A close request can return before Electron dispatches the close/hide event. */
export async function waitForWindowVisibility(window, visible, { timeout = 30_000, interval = 25 } = {}) {
  const deadline = Date.now() + timeout
  for (;;) {
    const state = await window.evaluate(owner => {
      const destroyed = owner.isDestroyed()
      return { destroyed, visible: destroyed ? false : owner.isVisible() }
    })
    assert.equal(state.destroyed, false, 'Desktop window must survive hiding and reopening')
    if (state.visible === visible) return
    assert.ok(Date.now() < deadline, `Desktop window did not become ${visible ? 'visible' : 'hidden'} within ${timeout}ms`)
    await delay(Math.min(interval, Math.max(0, deadline - Date.now())))
  }
}
