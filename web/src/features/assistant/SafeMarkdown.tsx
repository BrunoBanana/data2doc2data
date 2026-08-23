import type { ReactNode } from 'react'

export function SafeMarkdown({ text }: { text: string }) {
  const lines = text.split(/\r?\n/)
  return <div className="safe-markdown">{lines.map((line, index) => renderLine(line, index))}</div>
}

function renderLine(line: string, key: number): ReactNode {
  if (line.startsWith('### ')) return <h5 key={key}>{inline(line.slice(4))}</h5>
  if (line.startsWith('## ')) return <h4 key={key}>{inline(line.slice(3))}</h4>
  if (line.startsWith('# ')) return <h3 key={key}>{inline(line.slice(2))}</h3>
  if (line.startsWith('> ')) return <blockquote key={key}>{inline(line.slice(2))}</blockquote>
  if (/^[-*] /.test(line)) return <div className="markdown-list-item" key={key}>• {inline(line.slice(2))}</div>
  return line ? <p key={key}>{inline(line)}</p> : <br key={key} />
}

function inline(text: string): ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>
    return part
  })
}
