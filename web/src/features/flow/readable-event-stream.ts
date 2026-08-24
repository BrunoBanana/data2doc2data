import { useEffect, useMemo, useState } from 'react'

import type { RunEvent } from '../../contracts/run-events'

const VISUAL_MILESTONES = new Set<RunEvent['kind']>([
  'plan.created',
  'plan.revised',
  'step.added',
  'step.started',
  'step.failed',
  'tool.failed',
  'node.added',
  'node.updated',
  'conflict.detected',
  'hypothesis.created',
  'validation.completed',
  'conclusion.created',
  'report.generated',
  'cycle.started',
  'round.planned',
  'round.started',
  'artifact.created',
  'round.completed',
  'cycle.completed',
  'run.completed',
  'run.failed',
  'run.interrupted',
])

interface ReadableEventStream {
  visibleEvents: RunEvent[]
  pendingCount: number
  paused: boolean
  speed: number
  revealLatest: () => void
  togglePaused: () => void
  setSpeed: (speed: number) => void
}

interface PlaybackState {
  runId: string | null
  visibleCount: number
  followLatest: boolean
  paused: boolean
  speed: number
}

const PLAYBACK_SPEEDS = new Set([0.75, 1, 1.5, 2])

/**
 * Presentation-only scheduler. Source events remain persisted and available
 * immediately; this hook only controls how quickly the audit trail is drawn.
 */
export function useReadableEventStream(events: RunEvent[], reducedMotion: boolean): ReadableEventStream {
  const orderedEvents = useMemo(
    () => [...events].sort((left, right) => left.sequence - right.sequence),
    [events],
  )
  const runId = orderedEvents[0]?.run_id ?? null
  const [playback, setPlayback] = useState<PlaybackState>({ runId, visibleCount: 0, followLatest: false, paused: false, speed: 1 })
  const currentCount = playback.runId === runId ? Math.min(playback.visibleCount, orderedEvents.length) : 0
  const visibleCount = reducedMotion || playback.followLatest ? orderedEvents.length : currentCount

  useEffect(() => {
    if (playback.runId === runId) return
    setPlayback({ runId, visibleCount: 0, followLatest: false, paused: false, speed: 1 })
  }, [playback.runId, runId])

  useEffect(() => {
    if (reducedMotion || playback.paused || playback.followLatest || playback.runId !== runId || currentCount >= orderedEvents.length) return
    const schedule = readablePlaybackStep(orderedEvents, currentCount, playback.speed)
    const timer = window.setTimeout(() => {
      setPlayback((current) => {
        if (current.runId !== runId || current.followLatest || current.paused) return current
        return { ...current, visibleCount: readablePlaybackStep(orderedEvents, current.visibleCount).nextCount }
      })
    }, schedule.delayMs)
    return () => window.clearTimeout(timer)
  }, [currentCount, orderedEvents, playback.followLatest, playback.paused, playback.runId, playback.speed, reducedMotion, runId])

  return {
    visibleEvents: orderedEvents.slice(0, visibleCount),
    pendingCount: Math.max(0, orderedEvents.length - visibleCount),
    paused: playback.paused,
    speed: playback.speed,
    revealLatest: () => setPlayback((current) => ({ ...current, runId, visibleCount: orderedEvents.length, followLatest: true, paused: false })),
    togglePaused: () => setPlayback((current) => ({ ...current, paused: !current.paused })),
    setSpeed: (speed) => setPlayback((current) => ({ ...current, speed: PLAYBACK_SPEEDS.has(speed) ? speed : 1 })),
  }
}

export function readablePlaybackStep(events: RunEvent[], visibleCount: number, speed = 1): { nextCount: number; delayMs: number } {
  const safeSpeed = PLAYBACK_SPEEDS.has(speed) ? speed : 1
  return { nextCount: nextReadableCount(events, visibleCount), delayMs: Math.round(500 / safeSpeed) }
}

export function nextReadableCount(events: RunEvent[], visibleCount: number): number {
  let cursor = Math.max(0, visibleCount)
  while (cursor < events.length) {
    const event = events[cursor]
    cursor += 1
    if (VISUAL_MILESTONES.has(event.kind)) return cursor
  }
  return cursor
}
