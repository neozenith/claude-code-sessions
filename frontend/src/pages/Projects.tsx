import Plot from 'react-plotly.js'
import { useApi } from '@/hooks/useApi'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface ProjectData {
  project_id: string
  total_cost_usd: number
  session_count: number
  event_count: number
}

export default function Projects() {
  const { data, loading, error } = useApi<ProjectData[]>('/projects')

  if (loading) return <div className="text-center py-8">Loading...</div>
  if (error) return <div className="text-center py-8 text-red-500">Error: {error}</div>

  // Sort projects by cost
  const sortedProjects = [...(data || [])].sort(
    (a, b) => Number(b.total_cost_usd) - Number(a.total_cost_usd)
  )

  // Format project names for display
  const formatProjectName = (name: string) => {
    return name.replace(/-Users-joshpeak-/, '').replace(/-/g, '/')
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold text-gray-900">Projects</h1>

      {/* Projects Bar Chart */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold mb-4">Cost by Project</h2>
        <Plot
          data={[
            {
              x: sortedProjects.map((p) => Number(p.total_cost_usd)),
              y: sortedProjects.map((p) => formatProjectName(p.project_id)),
              type: 'bar',
              orientation: 'h',
              marker: {
                color: sortedProjects.map((_, i) =>
                  `hsl(${(i * 360) / sortedProjects.length}, 70%, 50%)`
                ),
              },
            },
          ]}
          layout={{
            autosize: true,
            margin: { l: 200, r: 30, t: 30, b: 50 },
            xaxis: { title: 'Cost (USD)' },
            yaxis: { automargin: true },
          }}
          useResizeHandler
          style={{ width: '100%', height: `${Math.max(400, sortedProjects.length * 40)}px` }}
        />
      </div>

      {/* Projects Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <h2 className="text-xl font-semibold p-6 border-b">Project Details</h2>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Project
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  Cost (USD)
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  Sessions
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  Events
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {sortedProjects.map((project) => (
                <tr key={project.project_id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm text-gray-900">
                    {formatProjectName(project.project_id)}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900 text-right">
                    ${Number(project.total_cost_usd).toFixed(2)}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900 text-right">
                    {project.session_count}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900 text-right">
                    {project.event_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
