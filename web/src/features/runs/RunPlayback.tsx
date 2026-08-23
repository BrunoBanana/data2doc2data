import { LazyMotion, domAnimation, m, useReducedMotion } from 'motion/react'
import { useEffect, useMemo, useState } from 'react'

import type { EvidenceGraphSpec, RunEvent } from '../../contracts/run-events'
import { EvidenceGraph } from '../evidence/EvidenceGraph'
import { RunTimeline } from './RunTimeline'

interface RunPlaybackProps {
  events: RunEvent[]
  graph: EvidenceGraphSpec
  autoPlay?: boolean
  reducedMotionOverride?: boolean
}

export function RunPlayback({ events, graph, autoPlay = true, reducedMotionOverride }: RunPlaybackProps) {
  const systemReducedMotion = useReducedMotion()
  const reducedMotion = reducedMotionOverride ?? Boolean(systemReducedMotion)
  const ordered = useMemo(() => [...events].sort((a, b) => a.sequence - b.sequence), [events])
  const [visibleCount, setVisibleCount] = useState(reducedMotion ? ordered.length : Math.min(1, ordered.length))
  const [playing, setPlaying] = useState(autoPlay && !reducedMotion && ordered.length > 1)
  const [speed, setSpeed] = useState(1)

  useEffect(() => {
    if (reducedMotion) {
      setVisibleCount(ordered.length)
      setPlaying(false)
    } else if (visibleCount > ordered.length) {
      setVisibleCount(ordered.length)
    }
  }, [ordered.length, reducedMotion, visibleCount])

  useEffect(() => {
    if (!playing || reducedMotion || visibleCount >= ordered.length) return
    const timer = window.setTimeout(() => setVisibleCount((count) => Math.min(ordered.length, count + 1)), 800 / speed)
    return () => window.clearTimeout(timer)
  }, [ordered.length, playing, reducedMotion, speed, visibleCount])

  useEffect(() => {
    if (visibleCount >= ordered.length) setPlaying(false)
  }, [ordered.length, visibleCount])

  const visible = ordered.slice(0, visibleCount)
  const active = visible.at(-1)
  const activeRefs = active?.artifact_refs ?? []

  function toggle() {
    if (reducedMotion || ordered.length < 2) return
    if (visibleCount >= ordered.length) setVisibleCount(1)
    setPlaying((value) => !value)
  }

  return <LazyMotion features={domAnimation}>
    <section className="run-playback" aria-labelledby="playback-title">
      <div className="playback-heading"><div><p className="eyebrow">AUDIT PLAYBACK</p><h2 id="playback-title">分析过程与证据联动</h2><p>这是可审计事件回放，不是模型隐性思维过程。</p></div><m.div className="playback-counter" animate={{ scale: playing ? 1.04 : 1 }} transition={{ duration: reducedMotion ? 0 : .2 }}>{visibleCount}<span> / {ordered.length}</span></m.div></div>
      <div className="playback-controls" aria-label="回放控制">
        <button className="button button--secondary" type="button" aria-label={playing ? '暂停回放' : '播放回放'} disabled={reducedMotion || ordered.length < 2} onClick={toggle}>{playing ? '暂停' : visibleCount >= ordered.length ? '重新播放' : '播放'}</button>
        <label>回放进度<input aria-label="回放进度" type="range" min={ordered.length ? 1 : 0} max={ordered.length} value={visibleCount} onChange={(event) => { setPlaying(false); setVisibleCount(Number(event.target.value)) }} /></label>
        <label>速度<select aria-label="回放速度" value={String(speed)} onChange={(event) => setSpeed(Number(event.target.value))}><option value="0.5">0.5×</option><option value="1">1×</option><option value="2">2×</option></select></label>
        <button className="button button--quiet" type="button" onClick={() => { setPlaying(false); setVisibleCount(ordered.length) }}>跳到结果</button>
      </div>
      {reducedMotion && <p className="reduced-motion-notice">已按减少动态效果设置直接展示全部事件</p>}
      <div className="playback-grid"><RunTimeline events={visible} activeSequence={active?.sequence} reducedMotion={reducedMotion} /><EvidenceGraph graph={graph} activeArtifactRefs={activeRefs} /></div>
    </section>
  </LazyMotion>
}
