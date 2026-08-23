import type { AnalysisTask } from '../../contracts/workbench'

interface TaskHomeProps {
  tasks: AnalysisTask[]
  onOpenTask: (taskId: string) => void
  onCreateTask: () => void
}

export function TaskHome({ tasks, onOpenTask, onCreateTask }: TaskHomeProps) {
  return (
    <section className="task-home" aria-labelledby="task-home-title">
      <div className="canvas-heading">
        <div><p className="eyebrow">ANALYSIS TASKS</p><h1 id="task-home-title">业务分析任务</h1><p>从问题出发，组织数据、文本、证据和行动。</p></div>
        <button className="button button--primary" type="button" onClick={onCreateTask}>新建任务</button>
      </div>
      {tasks.length ? (
        <div className="task-grid">
          {tasks.map((task) => (
            <button className="home-task-card" type="button" key={task.task_id} onClick={() => onOpenTask(task.task_id)}>
              <span>{task.status === 'active' ? '进行中' : task.status}</span>
              <strong>{task.title}</strong>
              <p>{task.goal}</p>
              <small>{task.snapshot_refs.length} 项任务资产</small>
            </button>
          ))}
        </div>
      ) : (
        <div className="template-grid">
          {['异常调查', '周期复盘', '策略核验'].map((template) => <button type="button" key={template} onClick={onCreateTask}><strong>{template}</strong><span>从模板创建任务</span></button>)}
        </div>
      )}
    </section>
  )
}
