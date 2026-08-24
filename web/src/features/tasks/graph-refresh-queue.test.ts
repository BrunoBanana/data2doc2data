import { describe, expect, it, vi } from 'vitest'

import { createTrailingRefresh } from './graph-refresh-queue'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

describe('createTrailingRefresh', () => {
  it('coalesces an event burst into one active request and one trailing refresh', async () => {
    const first = deferred<string>()
    const second = deferred<string>()
    const request = vi.fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const apply = vi.fn()
    const refresh = createTrailingRefresh(request, apply)

    for (let index = 0; index < 50; index += 1) refresh.schedule()
    expect(request).toHaveBeenCalledTimes(1)

    first.resolve('first')
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2))
    expect(apply).toHaveBeenCalledWith('first')

    second.resolve('latest')
    await refresh.whenIdle()
    expect(request).toHaveBeenCalledTimes(2)
    expect(apply).toHaveBeenLastCalledWith('latest')
  })
})
