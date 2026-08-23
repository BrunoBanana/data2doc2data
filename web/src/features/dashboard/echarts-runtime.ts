import { BarChart, LineChart, ScatterChart } from 'echarts/charts'
import { GraphicComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { init, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

use([BarChart, LineChart, ScatterChart, GraphicComponent, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

export { init }
