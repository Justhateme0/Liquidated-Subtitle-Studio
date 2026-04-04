import type {
  CreateProjectResponse,
  JobDocument,
  ProjectDocument,
  RenderStyle,
  CaptionLine,
  ExportPreset,
} from './types'

const configuredBase = import.meta.env.VITE_API_BASE?.replace(/\/$/, '')
export const API_BASE = configuredBase || 'http://127.0.0.1:8000'

function withVersion(url: string, version?: string | null) {
  if (!url || !version) {
    return url
  }
  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}v=${encodeURIComponent(version)}`
}

export function apiUrl(path: string | null | undefined) {
  if (!path) {
    return ''
  }
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path
  }
  return `${API_BASE}${path}`
}

export function assetUrl(path: string | null | undefined, version?: string | null) {
  return withVersion(apiUrl(path), version)
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText
    try {
      const payload = (await response.json()) as { detail?: string }
      detail = payload.detail || detail
    } catch {
      // Ignore JSON parse failures and fall back to status text.
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export async function createProject(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(apiUrl('/api/projects'), {
    method: 'POST',
    body: formData,
  })
  return parseResponse<CreateProjectResponse>(response)
}

export async function fetchProject(projectId: string) {
  const response = await fetch(apiUrl(`/api/projects/${projectId}`))
  return parseResponse<ProjectDocument>(response)
}

export async function fetchJob(jobId: string) {
  const response = await fetch(apiUrl(`/api/jobs/${jobId}`))
  return parseResponse<JobDocument>(response)
}

export async function saveCaptions(projectId: string, captions: CaptionLine[]) {
  const response = await fetch(apiUrl(`/api/projects/${projectId}/captions`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ captions }),
  })
  return parseResponse<ProjectDocument>(response)
}

export async function saveStyle(projectId: string, style: RenderStyle) {
  const response = await fetch(apiUrl(`/api/projects/${projectId}/style`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ style }),
  })
  return parseResponse<ProjectDocument>(response)
}

export async function uploadFont(projectId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(apiUrl(`/api/projects/${projectId}/fonts`), {
    method: 'POST',
    body: formData,
  })
  return parseResponse<ProjectDocument>(response)
}

export async function uploadBackground(projectId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(apiUrl(`/api/projects/${projectId}/background`), {
    method: 'POST',
    body: formData,
  })
  return parseResponse<ProjectDocument>(response)
}

export async function startExport(projectId: string, preset: ExportPreset) {
  const response = await fetch(apiUrl(`/api/projects/${projectId}/exports`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preset }),
  })
  return parseResponse<JobDocument>(response)
}

export function exportDownloadUrl(projectId: string, preset: ExportPreset, version?: string | null) {
  return withVersion(apiUrl(`/api/projects/${projectId}/exports/${preset}/download`), version)
}
