import type { RunEvent } from '../../contracts/run-events'

const TERMINAL_EVENTS = new Set<RunEvent['kind']>(['run.completed', 'run.failed', 'run.interrupted'])

export interface RunEventBuffer {
  push: (event: RunEvent) => void
  dispose: () => void
}

export function createRunEventBuffer(
  apply: (events: RunEvent[]) => void,
  requestFrame: (callback: FrameRequestCallback) => number = window.requestAnimationFrame.bind(window),
  cancelFrame: (handle: number) => void = window.cancelAnimationFrame.bind(window),
): RunEventBuffer {
  const pending = new Map<number, RunEvent>()
  let frameHandle: number | null = null
  let disposed = false

  function flush() {
    if (disposed || pending.size === 0) return
    const batch = [...pending.values()].sort((left, right) => left.sequence - right.sequence)
    pending.clear()
    frameHandle = null
    apply(batch)
  }

  return {
    push(event) {
      if (disposed) return
      pending.set(event.sequence, event)
      if (TERMINAL_EVENTS.has(event.kind)) {
        if (frameHandle !== null) cancelFrame(frameHandle)
        flush()
        return
      }
      if (frameHandle === null) {
        frameHandle = requestFrame(() => flush())
      }
    },
    dispose() {
      disposed = true
      pending.clear()
      if (frameHandle !== null) cancelFrame(frameHandle)
      frameHandle = null
    },
  }
}
