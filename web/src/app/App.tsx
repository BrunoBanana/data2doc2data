import { useState } from 'react'

const tabs = ['总览', '数据', '文本', '证据', '假设', '历史'] as const

export function App() {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>('总览')
  const [assistantOpen, setAssistantOpen] = useState(true)

  return (
    <div className="app-frame">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Data2Doc2Data 首页">
          <span className="brand-mark" aria-hidden="true">D2</span>
          <span>Data2Doc2Data</span>
        </a>
        <div className="topbar-status" role="status">
          <span className="status-dot status-dot--idle" aria-hidden="true" />
          未连接助手
        </div>
        <button className="button button--quiet" type="button" onClick={() => setAssistantOpen((open) => !open)}>
          {assistantOpen ? '收起助手' : '打开助手'}
        </button>
      </header>

      <div className={`workbench-grid${assistantOpen ? '' : ' workbench-grid--assistant-closed'}`}>
        <nav className="asset-rail" aria-label="任务与资产">
          <div className="rail-heading">
            <span>分析任务</span>
            <button className="icon-button" type="button" aria-label="新建分析任务">＋</button>
          </div>
          <button className="task-card task-card--active" type="button">
            <span className="task-card__eyebrow">当前任务</span>
            <strong>业务分析工作台</strong>
            <span>等待接入数据</span>
          </button>
          <div className="rail-section">
            <h2>任务资产</h2>
            <button type="button"><span aria-hidden="true">▦</span> 数据集 <b>0</b></button>
            <button type="button"><span aria-hidden="true">▤</span> 文档 <b>0</b></button>
            <button type="button"><span aria-hidden="true">◇</span> 运行记录 <b>0</b></button>
          </div>
        </nav>

        <main className="analysis-canvas">
          <div className="canvas-heading">
            <div>
              <p className="eyebrow">任务工作区</p>
              <h1>业务分析工作台</h1>
              <p>数据、文档与可验证证据会在这里汇合。</p>
            </div>
            <button className="button button--primary" type="button">接入数据</button>
          </div>
          <div className="tabs" role="tablist" aria-label="分析视图">
            {tabs.map((tab) => (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={activeTab === tab}
                className={activeTab === tab ? 'tab tab--active' : 'tab'}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>
          <section className="empty-workspace" aria-labelledby="empty-title">
            <div className="empty-visual" aria-hidden="true">
              <span className="empty-node" />
              <span className="empty-line" />
              <span className="empty-node empty-node--accent" />
            </div>
            <p className="eyebrow">LOCAL-FIRST ANALYSIS</p>
            <h2 id="empty-title">从一项真实业务问题开始</h2>
            <p>接入数据后自动生成数据画像、质量检查和基础 Dashboard；文档可以稍后补充。</p>
            <div className="empty-actions">
              <button className="button button--primary" type="button">创建任务并接入数据</button>
              <button className="button button--secondary" type="button">使用虚拟演示数据</button>
            </div>
          </section>
        </main>

        {assistantOpen && (
          <aside className="assistant-drawer" aria-label="AI 助手">
            <div className="assistant-heading">
              <div>
                <p className="eyebrow">协作分析</p>
                <h2>AI 助手</h2>
              </div>
              <span className="connection-badge">未连接助手</span>
            </div>
            <div className="assistant-empty">
              <div className="assistant-orb" aria-hidden="true" />
              <strong>先完成连接，或直接分析</strong>
              <p>仍可使用本地数据画像与确定性 Dashboard</p>
              <button className="button button--secondary" type="button">连接 Codex / WorkBuddy</button>
            </div>
            <form className="assistant-composer">
              <label htmlFor="assistant-message">发送给助手</label>
              <textarea id="assistant-message" rows={3} placeholder="连接助手后，可基于当前任务继续分析…" disabled />
              <button className="button button--primary" type="submit" disabled>发送</button>
            </form>
          </aside>
        )}
      </div>
    </div>
  )
}
