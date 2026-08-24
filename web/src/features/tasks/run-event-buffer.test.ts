import { describe, expect, it, vi } from 'vitest'

import type { RunEvent } from '../../contracts/run-events'
import { createRunEventBuffer } from './run-event-buffer'

function event(sequence: number, kind: RunEvent['kind'] = 'node.added'): RunEvent {
  return {
    contract_version: 1,
    run_id: 'run-buffer',
    sequence,
    kind,
    phase: 'compute',
    summary: {},
    artifact_refs: [],
    created_at: '2026-08-24T00:00:00Z',
  }
}

describe('run event frame buffer', () => {
  it('coalesces a large SSE burst into one render and flushes immediately at the terminal event', () => {
    let scheduled: FrameRequestCallback | null = null
    const requestFrame = vi.fn((callback: FrameRequestCallback) => {
      scheduled = callback
      return 17
    })
    const cancelFrame = vi.fn()
    const apply = vi.fn()
    const buffer = createRunEventBuffer(apply, requestFrame, cancelFrame)

    for (let sequence = 1; sequence <= 100; sequence += 1) buffer.push(event(sequence))
    expect(apply).not.toHaveBeenCalled()
    expect(requestFrame).toHaveBeenCalledTimes(1)

    buffer.push(event(101, 'run.completed'))

    expect(apply).toHaveBeenCalledTimes(1)
    expect(apply.mock.calls[0][0]).toHaveLength(101)
    expect(apply.mock.calls[0][0].at(-1)?.kind).toBe('run.completed')
    expect(cancelFrame).toHaveBeenCalledWith(17)
    expect(scheduled).not.toBeNull()
  })
})
