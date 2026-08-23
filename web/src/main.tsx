import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './app/App'
import './styles/tokens.css'
import './styles/app.css'

const root = document.getElementById('root')

if (!root) {
  throw new Error('Workbench root element is missing')
}

const supported = typeof globalThis.fetch === 'function' && typeof globalThis.URL === 'function' && typeof globalThis.Blob === 'function'

createRoot(root).render(supported ? <StrictMode><App /></StrictMode> : <main className="startup-state"><p className="eyebrow">BROWSER SUPPORT</p><h1>当前浏览器版本不受支持</h1><p>请使用较新的 Chrome、Edge、Safari 或 Firefox 打开本地工作台。</p></main>)
