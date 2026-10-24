import assert from 'node:assert/strict'
import { test } from 'node:test'
import { waitForWindowVisibility } from './smoke-window.mjs'

test('native visibility waits for an asynchronous hide and reopen without replacing the window', async () => {
  let visible = true
  const owner = { isDestroyed: () => false, isVisible: () => visible }
  const window = { evaluate: async callback => callback(owner) }
  const hidden = waitForWindowVisibility(window, false, { interval: 1 })
  setImmediate(() => { visible = false })
  await hidden
  const shown = waitForWindowVisibility(window, true, { interval: 1 })
  setImmediate(() => { visible = true })
  await shown
})

test('a destroyed window cannot satisfy the hidden assertion', async () => {
  const window = { evaluate: async callback => callback({ isDestroyed: () => true }) }
  await assert.rejects(waitForWindowVisibility(window, false), /must survive hiding and reopening/u)
})

test('a close request that never hides still fails the smoke check', async () => {
  const window = { evaluate: async callback => callback({ isDestroyed: () => false, isVisible: () => true }) }
  await assert.rejects(waitForWindowVisibility(window, false, { timeout: 0 }), /did not become hidden/u)
})
