export type ProjectStatus = 'queued' | 'processing' | 'ready' | 'exporting' | 'failed'
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed'
export type ExportPreset = 'alpha_mov' | 'mp4_solid'

export interface TranscriptWord {
  id: string
  text: string
  start: number
  end: number
  confidence?: number | null
}

export interface CaptionLine {
  id: string
  text: string
  start: number
  end: number
  position_x: number
  position_y: number
  disabled: boolean
}

export interface ExportArtifact {
  preset: ExportPreset
  status: JobStatus
  output_url?: string | null
  file_path?: string | null
  job_id?: string | null
  created_at: string
}

export interface RenderStyle {
  font_family: string
  font_file?: string | null
  font_asset_url?: string | null
  background_kind: 'color' | 'image' | 'video'
  background_file?: string | null
  background_asset_url?: string | null
  font_size: number
  text_color: string
  background_color: string
  blur: number
  stretch_y: number
  uppercase: boolean
  position_x: number
  position_y: number
  canvas_width: number
  canvas_height: number
  line_gap: number
  letter_spacing: number
  alignment: 'bottom_center'
}

export interface ProjectDocument {
  id: string
  status: ProjectStatus
  title: string
  created_at: string
  updated_at: string
  source_audio_path: string
  source_audio_url: string
  vocal_audio_path?: string | null
  vocal_audio_url?: string | null
  audio_duration_seconds?: number | null
  transcript_words: TranscriptWord[]
  captions: CaptionLine[]
  style: RenderStyle
  exports: Record<string, ExportArtifact>
  pipeline_job_id?: string | null
  errors: string[]
}

export interface JobDocument {
  id: string
  project_id: string
  kind: 'pipeline' | 'export'
  status: JobStatus
  progress: number
  message: string
  payload: Record<string, unknown>
  result: Record<string, unknown>
  error?: string | null
  created_at: string
  updated_at: string
}

export interface CreateProjectResponse {
  project: ProjectDocument
  job: JobDocument
}
