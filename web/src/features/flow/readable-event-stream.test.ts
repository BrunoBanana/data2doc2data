import { describe, expect, it } from 'vitest'

import type { RunEvent } from '../../contracts/run-events'
import { readablePlaybackStep } from './readable-event-stream'

function events(count: number): RunEvent[] {
  return Array.from({ length: count }, (_, index) => ({
    contract_version: 1,
    run_id: 'run-readable',
    sequence: index + 1,
    kind: index === count - 1 ? 'run.completed' : 'node.added',
    phase: 'cross-reasoning',
    summary: {},
    artifact_refs: [],
    created_at: '2026-08-24T00:00:00Z',
  }))
}

describe('readable playback scheduling', () => {
  it('keeps every semantic milestone readable instead of accelerating a large burst', () => {
    const large = readablePlaybackStep(events(125), 0)
    expect(large.delayMs).toBeGreaterThanOrEqual(450)
    expect(large.nextCount).toBe(1)

    const short = readablePlaybackStep(events(4), 0)
    expect(short.delayMs).toBeGreaterThanOrEqual(450)
    expect(short.nextCount).toBe(1)
  })

  it('pauses at every persisted analysis round and artifact milestone', () => {
    const cycleEvents: RunEvent[] = [
      { ...events(1)[0], sequence: 1, kind: 'cycle.started' },
      { ...events(1)[0], sequence: 2, kind: 'round.planned' },
      { ...events(1)[0], sequence: 3, kind: 'round.started' },
      { ...events(1)[0], sequence: 4, kind: 'artifact.created' },
      { ...events(1)[0], sequence: 5, kind: 'round.completed' },
    ]

    expect(readablePlaybackStep(cycleEvents, 0).nextCount).toBe(1)
    expect(readablePlaybackStep(cycleEvents, 1).nextCount).toBe(2)
    expect(readablePlaybackStep(cycleEvents, 2).nextCount).toBe(3)
    expect(readablePlaybackStep(cycleEvents, 3).nextCount).toBe(4)
    expect(readablePlaybackStep(cycleEvents, 4).nextCount).toBe(5)
  })
})
