import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ChevronLeft, ChevronRight, AlertCircle } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8101';

interface Project {
  project_id: string;
  first_activity_date_local: string;
  last_activity_date_local: string;
  first_activity_date_utc: string;
  last_activity_date_utc: string;
  session_count: number;
  event_count: number;
  total_cost_usd: number;
  total_tokens: number;
}

interface Session {
  project_id: string;
  session_id: string;
  model_id: string;
  start_time_utc: string;
  start_time_local: string;
  end_time_utc: string;
  end_time_local: string;
  duration: string;
  event_count: number;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

interface Event {
  project_id: string;
  session_id: string;
  event_seq: number;
  model_id: string;
  role: string;
  timestamp_utc: string;
  timestamp_local: string;
  date_utc: string;
  date_local: string;
  hour_utc: number;
  hour_local: number;
  input_tokens: number;
  cache_5m_write_tokens: number;
  cache_read_tokens: number;
  output_tokens: number;
  total_tokens: number;
  event_cost_usd: number;
}

interface DailyDetail {
  project_id: string;
  date_local: string;
  date_utc: string;
  timezone_status: string;
  session_count: number;
  event_count: number;
  model_id: string;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

type ViewLevel = 'projects' | 'sessions' | 'events' | 'daily';

export default function DrillDown() {
  const [viewLevel, setViewLevel] = useState<ViewLevel>('projects');
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);

  const [projects, setProjects] = useState<Project[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [dailyDetails, setDailyDetails] = useState<DailyDetail[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch projects on mount
  useEffect(() => {
    fetchProjects();
  }, []);

  const fetchProjects = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/drilldown/projects`);
      if (!response.ok) throw new Error('Failed to fetch projects');
      const data = await response.json();
      setProjects(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const fetchSessions = async (projectId: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/drilldown/sessions/${encodeURIComponent(projectId)}`);
      if (!response.ok) throw new Error('Failed to fetch sessions');
      const data = await response.json();
      setSessions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const fetchEvents = async (projectId: string, sessionId: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${API_BASE}/api/drilldown/events/${encodeURIComponent(projectId)}/${encodeURIComponent(sessionId)}`
      );
      if (!response.ok) throw new Error('Failed to fetch events');
      const data = await response.json();
      setEvents(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const fetchDailyDetails = async (projectId: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/drilldown/daily/${encodeURIComponent(projectId)}`);
      if (!response.ok) throw new Error('Failed to fetch daily details');
      const data = await response.json();
      setDailyDetails(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const handleProjectClick = (projectId: string) => {
    setSelectedProject(projectId);
    setViewLevel('sessions');
    fetchSessions(projectId);
  };

  const handleSessionClick = (sessionId: string) => {
    if (!selectedProject) return;
    setSelectedSession(sessionId);
    setViewLevel('events');
    fetchEvents(selectedProject, sessionId);
  };

  const handleViewDailyDetails = (projectId: string) => {
    setSelectedProject(projectId);
    setViewLevel('daily');
    fetchDailyDetails(projectId);
  };

  const handleBack = () => {
    if (viewLevel === 'events') {
      setViewLevel('sessions');
      setSelectedSession(null);
    } else if (viewLevel === 'sessions' || viewLevel === 'daily') {
      setViewLevel('projects');
      setSelectedProject(null);
      setSessions([]);
      setEvents([]);
      setDailyDetails([]);
    }
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleString();
  };

  const formatDuration = (duration: string) => {
    if (!duration) return 'N/A';
    // Duration is in format like "01:23:45.123456"
    return duration.split('.')[0]; // Remove microseconds
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          {viewLevel !== 'projects' && (
            <Button onClick={handleBack} variant="outline" size="sm">
              <ChevronLeft className="h-4 w-4 mr-2" />
              Back
            </Button>
          )}
          <div>
            <h1 className="text-3xl font-bold">Cost Drill-Down</h1>
            <p className="text-sm text-muted-foreground mt-1">
              {viewLevel === 'projects' && 'Select a project to drill down'}
              {viewLevel === 'sessions' && `Sessions for: ${selectedProject}`}
              {viewLevel === 'events' && `Events for session: ${selectedSession}`}
              {viewLevel === 'daily' && `Daily timezone analysis for: ${selectedProject}`}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
            UTC timestamps shown
          </span>
          <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">
            Local: Australia/Melbourne
          </span>
        </div>
      </div>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 text-red-800">
              <AlertCircle className="h-5 w-5" />
              <p>{error}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <Card>
          <CardContent className="pt-6">
            <p className="text-center text-muted-foreground">Loading...</p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Projects View */}
          {viewLevel === 'projects' && (
            <Card>
              <CardHeader>
                <CardTitle>All Projects</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left p-2">Project ID</th>
                        <th className="text-right p-2">Cost (USD)</th>
                        <th className="text-right p-2">Sessions</th>
                        <th className="text-right p-2">Events</th>
                        <th className="text-right p-2">Total Tokens</th>
                        <th className="text-left p-2">First Activity (Local)</th>
                        <th className="text-left p-2">Last Activity (Local)</th>
                        <th className="text-center p-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {projects.map((project) => (
                        <tr key={project.project_id} className="border-b hover:bg-gray-50">
                          <td className="p-2 font-mono text-xs">{project.project_id}</td>
                          <td className="p-2 text-right font-semibold">
                            ${project.total_cost_usd.toFixed(2)}
                          </td>
                          <td className="p-2 text-right">{project.session_count}</td>
                          <td className="p-2 text-right">{project.event_count.toLocaleString()}</td>
                          <td className="p-2 text-right">{project.total_tokens.toLocaleString()}</td>
                          <td className="p-2 text-xs">{project.first_activity_date_local}</td>
                          <td className="p-2 text-xs">{project.last_activity_date_local}</td>
                          <td className="p-2 text-center">
                            <div className="flex gap-1 justify-center">
                              <Button
                                onClick={() => handleProjectClick(project.project_id)}
                                size="sm"
                                variant="outline"
                              >
                                Sessions <ChevronRight className="h-3 w-3 ml-1" />
                              </Button>
                              <Button
                                onClick={() => handleViewDailyDetails(project.project_id)}
                                size="sm"
                                variant="outline"
                              >
                                Daily
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Sessions View */}
          {viewLevel === 'sessions' && (
            <Card>
              <CardHeader>
                <CardTitle>Sessions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left p-2">Session ID</th>
                        <th className="text-left p-2">Model</th>
                        <th className="text-left p-2">Start (Local)</th>
                        <th className="text-left p-2">Start (UTC)</th>
                        <th className="text-right p-2">Duration</th>
                        <th className="text-right p-2">Events</th>
                        <th className="text-right p-2">Cost (USD)</th>
                        <th className="text-right p-2">Input Tokens</th>
                        <th className="text-right p-2">Output Tokens</th>
                        <th className="text-center p-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sessions.map((session) => (
                        <tr key={session.session_id} className="border-b hover:bg-gray-50">
                          <td className="p-2 font-mono text-xs max-w-xs truncate">
                            {session.session_id}
                          </td>
                          <td className="p-2 text-xs">{session.model_id}</td>
                          <td className="p-2 text-xs">{formatDate(session.start_time_local)}</td>
                          <td className="p-2 text-xs text-muted-foreground">
                            {formatDate(session.start_time_utc)}
                          </td>
                          <td className="p-2 text-right">{formatDuration(session.duration)}</td>
                          <td className="p-2 text-right">{session.event_count}</td>
                          <td className="p-2 text-right font-semibold">
                            ${session.total_cost_usd.toFixed(4)}
                          </td>
                          <td className="p-2 text-right">{session.total_input_tokens.toLocaleString()}</td>
                          <td className="p-2 text-right">{session.total_output_tokens.toLocaleString()}</td>
                          <td className="p-2 text-center">
                            <Button
                              onClick={() => handleSessionClick(session.session_id)}
                              size="sm"
                              variant="outline"
                            >
                              Events <ChevronRight className="h-3 w-3 ml-1" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Events View */}
          {viewLevel === 'events' && (
            <Card>
              <CardHeader>
                <CardTitle>Event-Level Details</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left p-2">#</th>
                        <th className="text-left p-2">Timestamp (Local)</th>
                        <th className="text-left p-2">Timestamp (UTC)</th>
                        <th className="text-left p-2">Date Local</th>
                        <th className="text-left p-2">Date UTC</th>
                        <th className="text-center p-2">Hour Local</th>
                        <th className="text-center p-2">Hour UTC</th>
                        <th className="text-left p-2">Role</th>
                        <th className="text-right p-2">Input</th>
                        <th className="text-right p-2">Cache Read</th>
                        <th className="text-right p-2">Output</th>
                        <th className="text-right p-2">Total</th>
                        <th className="text-right p-2">Cost (USD)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {events.map((event) => {
                        const tzMismatch = event.date_local !== event.date_utc;
                        return (
                          <tr
                            key={event.event_seq}
                            className={`border-b hover:bg-gray-50 ${
                              tzMismatch ? 'bg-yellow-50' : ''
                            }`}
                          >
                            <td className="p-2">{event.event_seq}</td>
                            <td className="p-2 text-xs">{formatDate(event.timestamp_local)}</td>
                            <td className="p-2 text-xs text-muted-foreground">
                              {formatDate(event.timestamp_utc)}
                            </td>
                            <td className="p-2 text-xs font-semibold">{event.date_local}</td>
                            <td className="p-2 text-xs text-muted-foreground">{event.date_utc}</td>
                            <td className="p-2 text-center font-semibold">{event.hour_local}</td>
                            <td className="p-2 text-center text-muted-foreground">{event.hour_utc}</td>
                            <td className="p-2 text-xs">{event.role}</td>
                            <td className="p-2 text-right">{event.input_tokens.toLocaleString()}</td>
                            <td className="p-2 text-right">{event.cache_read_tokens.toLocaleString()}</td>
                            <td className="p-2 text-right">{event.output_tokens.toLocaleString()}</td>
                            <td className="p-2 text-right font-semibold">
                              {event.total_tokens.toLocaleString()}
                            </td>
                            <td className="p-2 text-right">${event.event_cost_usd.toFixed(6)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  <div className="mt-4 text-xs text-muted-foreground">
                    <p>
                      <span className="inline-block w-4 h-4 bg-yellow-50 border border-yellow-200 mr-2"></span>
                      Yellow rows indicate events where local date differs from UTC date (timezone boundary)
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Daily Details View */}
          {viewLevel === 'daily' && (
            <Card>
              <CardHeader>
                <CardTitle>Daily Timezone Analysis</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left p-2">Date (Local)</th>
                        <th className="text-left p-2">Date (UTC)</th>
                        <th className="text-left p-2">Timezone Status</th>
                        <th className="text-left p-2">Model</th>
                        <th className="text-right p-2">Sessions</th>
                        <th className="text-right p-2">Events</th>
                        <th className="text-right p-2">Cost (USD)</th>
                        <th className="text-right p-2">Input Tokens</th>
                        <th className="text-right p-2">Output Tokens</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dailyDetails.map((detail, idx) => {
                        const isMismatch = detail.timezone_status === 'TIMEZONE_MISMATCH';
                        return (
                          <tr
                            key={idx}
                            className={`border-b hover:bg-gray-50 ${
                              isMismatch ? 'bg-red-50' : ''
                            }`}
                          >
                            <td className="p-2 font-semibold">{detail.date_local}</td>
                            <td className="p-2 text-muted-foreground">{detail.date_utc}</td>
                            <td className="p-2">
                              <span
                                className={`text-xs px-2 py-1 rounded ${
                                  isMismatch
                                    ? 'bg-red-200 text-red-800'
                                    : 'bg-green-200 text-green-800'
                                }`}
                              >
                                {detail.timezone_status}
                              </span>
                            </td>
                            <td className="p-2 text-xs">{detail.model_id}</td>
                            <td className="p-2 text-right">{detail.session_count}</td>
                            <td className="p-2 text-right">{detail.event_count}</td>
                            <td className="p-2 text-right font-semibold">
                              ${detail.total_cost_usd.toFixed(4)}
                            </td>
                            <td className="p-2 text-right">{detail.total_input_tokens.toLocaleString()}</td>
                            <td className="p-2 text-right">{detail.total_output_tokens.toLocaleString()}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  <div className="mt-4 space-y-2 text-xs text-muted-foreground">
                    <p>
                      <span className="inline-block w-4 h-4 bg-red-50 border border-red-200 mr-2"></span>
                      <strong>TIMEZONE_MISMATCH</strong>: Events that occurred on different calendar days in
                      UTC vs local time. This is the likely cause of cost attribution issues.
                    </p>
                    <p>
                      <span className="inline-block w-4 h-4 bg-green-50 border border-green-200 mr-2"></span>
                      <strong>ALIGNED</strong>: Events where UTC and local dates match.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
