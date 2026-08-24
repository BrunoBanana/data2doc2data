export interface TrailingRefresh {
  schedule: () => void
  whenIdle: () => Promise<void>
}

export function createTrailingRefresh<T>(
  request: () => Promise<T>,
  apply: (value: T) => void,
  onError: (error: unknown) => void = () => undefined,
): TrailingRefresh {
  let active: Promise<void> | null = null
  let pending = false

  function start() {
    active = request()
      .then(apply)
      .catch(onError)
      .then(() => undefined)
      .finally(() => {
        if (pending) {
          pending = false
          start()
        } else {
          active = null
        }
      })
  }

  return {
    schedule() {
      if (active) {
        pending = true
        return
      }
      start()
    },
    async whenIdle() {
      while (active) await active
    },
  }
}
