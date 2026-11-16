import assert from 'node:assert/strict'
import test from 'node:test'

import { retryOnConflict } from '../src/utils/retryOnConflict.ts'

const noWait = () => Promise.resolve()
const conflict = () => Object.assign(new Error('deadlock'), { status: 508 })

test('asks again after a conflict and returns the answer', async () => {
  let calls = 0
  const fetcher = async () => {
    if (++calls < 3) throw conflict()
    return 'saved'
  }
  assert.equal(await retryOnConflict(fetcher, noWait)({}), 'saved')
  assert.equal(calls, 3)
})

test('gives up after two retries and reports the failure once', async () => {
  const reported = []
  let calls = 0
  const fetcher = async (options) => {
    calls++
    const error = conflict()
    options.onError?.(error)
    throw error
  }
  await assert.rejects(retryOnConflict(fetcher, noWait)({ onError: (e) => reported.push(e) }))
  assert.equal(calls, 3)
  assert.equal(reported.length, 1)
})

test('does not retry other errors, and reports them once', async () => {
  const reported = []
  let calls = 0
  const fetcher = async () => {
    calls++
    throw Object.assign(new Error('forbidden'), { status: 403 })
  }
  await assert.rejects(retryOnConflict(fetcher, noWait)({ onError: (e) => reported.push(e) }))
  assert.equal(calls, 1)
  assert.equal(reported.length, 1)
})
