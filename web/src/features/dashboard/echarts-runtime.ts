import { BarChart, LineChart, ScatterChart } from 'echarts/charts'
import { AriaComponent, GraphicComponent, GridComponent, LegendComponent, MarkPointComponent, TooltipComponent } from 'echarts/components'
import { init, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

use([BarChart, LineChart, ScatterChart, AriaComponent, GraphicComponent, GridComponent, LegendComponent, MarkPointComponent, TooltipComponent, CanvasRenderer])

export { init }
