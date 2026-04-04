import {
  type ChangeEvent,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
  useTransition,
} from 'react'
import './App.css'
import {
  apiUrl,
  assetUrl,
  createProject,
  exportDownloadUrl,
  fetchJob,
  fetchProject,
  saveCaptions,
  saveStyle,
  startExport,
  uploadBackground,
  uploadFont,
} from './api'
import { WaveformPlayer } from './components/WaveformPlayer'
import type {
  CaptionLine,
  ExportArtifact,
  ExportPreset,
  JobDocument,
  ProjectDocument,
  RenderStyle,
} from './types'

const EMPTY_STYLE: RenderStyle = {
  font_family: 'Arial Narrow',
  font_file: null,
  font_asset_url: null,
  background_kind: 'color',
  background_file: null,
  background_asset_url: null,
  font_size: 86,
  text_color: '#111111',
  background_color: '#FFFFFF',
  blur: 0.8,
  stretch_y: 145,
  uppercase: false,
  position_x: 540,
  position_y: 540,
  canvas_width: 1080,
  canvas_height: 1080,
  line_gap: 10,
  letter_spacing: 0,
  alignment: 'bottom_center',
}

const TYPEWRITER_MIN_STEP_SECONDS = 0.045
const TYPEWRITER_MAX_REVEAL_SECONDS = 1.2
const TYPEWRITER_REVEAL_RATIO = 0.68

function makeId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function formatTime(value: number) {
  if (!Number.isFinite(value)) {
    return '0:00.00'
  }
  const minutes = Math.floor(value / 60)
  const seconds = (value % 60).toFixed(2).padStart(5, '0')
  return `${minutes}:${seconds}`
}

function withCacheBust(url: string, version: string | null | undefined) {
  if (!url || !version) {
    return url
  }
  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}v=${encodeURIComponent(version)}`
}

function jobTone(status: JobDocument['status']) {
  if (status === 'completed') return 'good'
  if (status === 'failed') return 'bad'
  if (status === 'running') return 'active'
  return 'muted'
}

function collectTrackedJobIds(project: ProjectDocument | null) {
  if (!project) {
    return []
  }

  const ids = new Set<string>()
  if (project.pipeline_job_id) {
    ids.add(project.pipeline_job_id)
  }

  Object.values(project.exports).forEach((artifact) => {
    if (artifact.job_id) {
      ids.add(artifact.job_id)
    }
  })

  return [...ids]
}

function activeCaptionsAtTime(captions: CaptionLine[], currentTime: number) {
  return captions.filter(
    (caption) =>
      !caption.disabled && currentTime >= caption.start && currentTime <= caption.end,
  )
}

function splitCaption(caption: CaptionLine) {
  const parts = caption.text.trim().split(/\s+/)
  if (parts.length < 2) {
    return null
  }

  const splitIndex = Math.ceil(parts.length / 2)
  const midpoint = Number(((caption.start + caption.end) / 2).toFixed(3))
  return [
    {
      ...caption,
      id: makeId(),
      text: parts.slice(0, splitIndex).join(' '),
      end: midpoint,
    },
    {
      ...caption,
      id: makeId(),
      text: parts.slice(splitIndex).join(' '),
      start: midpoint,
    },
  ]
}

function resolvePreviewText(
  caption: CaptionLine,
  currentTime: number,
  uppercase: boolean,
  animate: boolean,
) {
  const fullText = uppercase ? caption.text.toUpperCase() : caption.text
  if (!animate) {
    return { text: fullText, typing: false }
  }

  const characters = Array.from(fullText)
  const duration = Math.max(0, caption.end - caption.start)
  if (characters.length < 2 || duration < TYPEWRITER_MIN_STEP_SECONDS * 2) {
    return { text: fullText, typing: false }
  }

  const revealWindow = Math.min(duration * TYPEWRITER_REVEAL_RATIO, TYPEWRITER_MAX_REVEAL_SECONDS)
  const progress = Math.min(1, Math.max(0, (currentTime - caption.start) / revealWindow))
  const visibleCount = 1 + Math.floor((characters.length - 1) * progress)

  return {
    text: characters.slice(0, visibleCount).join(''),
    typing: progress < 1,
  }
}

function App() {
  const [project, setProject] = useState<ProjectDocument | null>(null)
  const [jobs, setJobs] = useState<Record<string, JobDocument>>({})
  const [draftCaptions, setDraftCaptions] = useState<CaptionLine[]>([])
  const [draftStyle, setDraftStyle] = useState<RenderStyle>(EMPTY_STYLE)
  const [captionsDirty, setCaptionsDirty] = useState(false)
  const [styleDirty, setStyleDirty] = useState(false)
  const [selectedCaptionId, setSelectedCaptionId] = useState<string | null>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [previewMode, setPreviewMode] = useState<'checker' | 'solid'>('checker')
  const [banner, setBanner] = useState('Загрузите MP3, дождитесь распознавания и начните править субтитры.')
  const [error, setError] = useState('')
  const [isPending, startTransition] = useTransition()
  const fontStyleRef = useRef<HTMLStyleElement | null>(null)
  const backgroundVideoRef = useRef<HTMLVideoElement | null>(null)
  const previewStageRef = useRef<HTMLDivElement | null>(null)
  const previousBackgroundKindRef = useRef<RenderStyle['background_kind']>('color')
  const pendingAutoDownloadsRef = useRef<Set<string>>(new Set())
  const handledDownloadJobsRef = useRef<Set<string>>(new Set())
  const deferredCaptions = useDeferredValue(draftCaptions)
  const projectId = project?.id ?? ''
  const pipelineJobId = project?.pipeline_job_id ?? ''
  const exportSignature = project ? JSON.stringify(project.exports) : ''
  const playbackUrl = project
    ? apiUrl(project.vocal_audio_url || project.source_audio_url)
    : ''
  const backgroundPreviewUrl = withCacheBust(
    assetUrl(draftStyle.background_asset_url),
    project?.updated_at ?? null,
  )
  const customBackgroundActive =
    draftStyle.background_kind !== 'color' && Boolean(draftStyle.background_asset_url)

  const refreshProject = useEffectEvent(async () => {
    if (!project?.id) {
      return
    }

    try {
      const nextProject = await fetchProject(project.id)
      startTransition(() => {
        setProject(nextProject)
      })
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Не удалось обновить проект.')
    }
  })

  const refreshJobs = useEffectEvent(async () => {
    const jobIds = collectTrackedJobIds(project)
    if (jobIds.length === 0) {
      return
    }

    try {
      const nextJobs = await Promise.all(jobIds.map((jobId) => fetchJob(jobId)))
      startTransition(() => {
        setJobs((current) => {
          const updated = { ...current }
          nextJobs.forEach((job) => {
            updated[job.id] = job
          })
          return updated
        })
      })
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Не удалось обновить статус job.')
    }
  })

  useEffect(() => {
    if (!project) {
      return
    }
    if (!captionsDirty) {
      setDraftCaptions(project.captions)
      if (!selectedCaptionId && project.captions[0]) {
        setSelectedCaptionId(project.captions[0].id)
      }
    }
  }, [project, captionsDirty, selectedCaptionId])

  useEffect(() => {
    if (!project) {
      return
    }
    if (!styleDirty) {
      setDraftStyle(project.style)
    }
  }, [project, styleDirty])

  useEffect(() => {
    if (!projectId) {
      return
    }

    void refreshProject()
    void refreshJobs()

    const timer = window.setInterval(() => {
      void refreshProject()
      void refreshJobs()
    }, 2000)

    return () => window.clearInterval(timer)
  }, [projectId, pipelineJobId, exportSignature])

  useEffect(() => {
    if (!fontStyleRef.current) {
      const styleTag = document.createElement('style')
      document.head.appendChild(styleTag)
      fontStyleRef.current = styleTag
    }

    return () => {
      fontStyleRef.current?.remove()
      fontStyleRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!fontStyleRef.current) {
      return
    }
    if (!projectId || !draftStyle.font_asset_url) {
      fontStyleRef.current.textContent = ''
      return
    }

    fontStyleRef.current.textContent = `@font-face {
      font-family: "ProjectFont-${projectId}";
      src: url("${apiUrl(draftStyle.font_asset_url)}");
    }`
  }, [projectId, draftStyle.font_asset_url])

  useEffect(() => {
    const previousKind = previousBackgroundKindRef.current
    if (draftStyle.background_kind !== 'color' && previousKind !== draftStyle.background_kind) {
      setPreviewMode('solid')
    }
    previousBackgroundKindRef.current = draftStyle.background_kind
  }, [draftStyle.background_kind])

  useEffect(() => {
    const video = backgroundVideoRef.current
    if (
      !video ||
      previewMode !== 'solid' ||
      draftStyle.background_kind !== 'video' ||
      !backgroundPreviewUrl
    ) {
      return
    }

    const duration = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : null
    const targetTime = duration ? currentTime % duration : currentTime
    if (Math.abs(video.currentTime - targetTime) > 0.25) {
      video.currentTime = targetTime
    }
  }, [backgroundPreviewUrl, currentTime, draftStyle.background_kind, previewMode])

  useEffect(() => {
    const video = backgroundVideoRef.current
    if (
      !video ||
      previewMode !== 'solid' ||
      draftStyle.background_kind !== 'video' ||
      !backgroundPreviewUrl
    ) {
      return
    }

    video.muted = true
    video.defaultMuted = true
    video.preload = 'auto'
    video.load()
    const playPromise = video.play()
    if (playPromise && typeof playPromise.catch === 'function') {
      playPromise.catch(() => {})
    }
  }, [backgroundPreviewUrl, draftStyle.background_kind, previewMode])

  useEffect(() => {
    if (!project || !projectId) {
      return
    }

    for (const pendingToken of [...pendingAutoDownloadsRef.current]) {
      const [pendingProjectId, preset] = pendingToken.split(':') as [string, ExportPreset]
      if (pendingProjectId !== projectId) {
        continue
      }

      const artifact = project.exports[preset]
      if (!artifact) {
        continue
      }
      if (artifact.status === 'failed') {
        pendingAutoDownloadsRef.current.delete(pendingToken)
        continue
      }
      if (artifact.status !== 'completed' || !artifact.job_id || !artifact.output_url) {
        continue
      }

      const handledToken = `${projectId}:${preset}:${artifact.job_id}`
      if (handledDownloadJobsRef.current.has(handledToken)) {
        pendingAutoDownloadsRef.current.delete(pendingToken)
        continue
      }

      handledDownloadJobsRef.current.add(handledToken)
      pendingAutoDownloadsRef.current.delete(pendingToken)

      const link = document.createElement('a')
      link.href = exportDownloadUrl(projectId, preset, artifact.job_id)
      link.rel = 'noreferrer'
      document.body.appendChild(link)
      link.click()
      link.remove()

      setBanner(
        preset === 'alpha_mov'
          ? 'alpha MOV готов. Скачиваю файл.'
          : 'MP4 готов. Скачиваю файл.',
      )
    }
  }, [project, projectId])

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }

    setError('')
    setBanner(`Загружаю ${file.name} и ставлю pipeline в очередь.`)

    try {
      const response = await createProject(file)
      startTransition(() => {
        setProject(response.project)
        setJobs({ [response.job.id]: response.job })
        setDraftCaptions(response.project.captions)
        setDraftStyle(response.project.style)
        setCaptionsDirty(false)
        setStyleDirty(false)
        setSelectedCaptionId(response.project.captions[0]?.id ?? null)
        setCurrentTime(0)
      })
      setBanner('Файл принят. Идёт Demucs -> Whisper -> сборка строк субтитров.')
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Не удалось загрузить файл.')
    } finally {
      event.target.value = ''
    }
  }

  async function handleFontUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file || !project) {
      return
    }

    setError('')
    setBanner(`Загружаю шрифт ${file.name}.`)
    try {
      const nextProject = await uploadFont(project.id, file)
      startTransition(() => {
        setProject(nextProject)
        setDraftStyle(nextProject.style)
        setStyleDirty(false)
      })
      setBanner('Кастомный шрифт привязан к проекту.')
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Не удалось загрузить шрифт.')
    } finally {
      event.target.value = ''
    }
  }

  async function handleBackgroundUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file || !project) {
      return
    }

    setError('')
    setBanner(`Загружаю фон ${file.name}.`)
    try {
      const nextProject = await uploadBackground(project.id, file)
      startTransition(() => {
        setProject(nextProject)
        setDraftStyle(nextProject.style)
        setStyleDirty(false)
      })
      setPreviewMode('solid')
      requestAnimationFrame(() => {
        previewStageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      })
      setBanner(
        nextProject.style.background_kind === 'video'
          ? 'Видео-фон загружен. Его звук в экспорте не используется.'
          : 'Фоновое изображение загружено.',
      )
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Не удалось загрузить фон.')
    } finally {
      event.target.value = ''
    }
  }

  async function persistCaptions() {
    if (!project) {
      return
    }

    setError('')
    setBanner('Сохраняю правки строк и таймингов.')
    try {
      const nextProject = await saveCaptions(project.id, draftCaptions)
      startTransition(() => {
        setProject(nextProject)
        setDraftCaptions(nextProject.captions)
        setCaptionsDirty(false)
      })
      setBanner('Капшены сохранены.')
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Не удалось сохранить капшены.')
    }
  }

  async function persistStyle() {
    if (!project) {
      return
    }

    setError('')
    setBanner('Сохраняю параметры стиля.')
    try {
      const nextProject = await saveStyle(project.id, draftStyle)
      startTransition(() => {
        setProject(nextProject)
        setDraftStyle(nextProject.style)
        setStyleDirty(false)
      })
      setBanner('Стиль сохранён.')
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Не удалось сохранить стиль.')
    }
  }

  async function queueExport(preset: ExportPreset) {
    if (!project) {
      return
    }

    const pendingToken = `${project.id}:${preset}`
    setError('')
    pendingAutoDownloadsRef.current.add(pendingToken)
    setBanner(
      preset === 'alpha_mov'
        ? 'Запускаю экспорт alpha MOV.'
        : draftStyle.background_kind === 'color'
          ? 'Запускаю экспорт MP4 с однотонным фоном.'
          : 'Запускаю экспорт MP4 с вашим фоном.',
    )

    try {
      const job = await startExport(project.id, preset)
      startTransition(() => {
        setJobs((current) => ({ ...current, [job.id]: job }))
      })
    } catch (nextError) {
      pendingAutoDownloadsRef.current.delete(pendingToken)
      setError(nextError instanceof Error ? nextError.message : 'Не удалось поставить экспорт в очередь.')
    }
  }

  function patchCaption(captionId: string, patch: Partial<CaptionLine>) {
    setCaptionsDirty(true)
    setDraftCaptions((current) =>
      current.map((caption) => (caption.id === captionId ? { ...caption, ...patch } : caption)),
    )
  }

  function removeCaption(captionId: string) {
    setCaptionsDirty(true)
    setDraftCaptions((current) => current.filter((caption) => caption.id !== captionId))
    if (selectedCaptionId === captionId) {
      setSelectedCaptionId(null)
    }
  }

  function splitSelectedCaption() {
    if (!selectedCaptionId) {
      return
    }
    setDraftCaptions((current) => {
      const index = current.findIndex((caption) => caption.id === selectedCaptionId)
      if (index === -1) {
        return current
      }
      const split = splitCaption(current[index])
      if (!split) {
        return current
      }
      const next = [...current]
      next.splice(index, 1, split[0], split[1])
      setCaptionsDirty(true)
      setSelectedCaptionId(split[0].id)
      return next
    })
  }

  function mergeSelectedWithNext() {
    if (!selectedCaptionId) {
      return
    }

    setDraftCaptions((current) => {
      const index = current.findIndex((caption) => caption.id === selectedCaptionId)
      const active = current[index]
      const nextCaption = current[index + 1]
      if (!active || !nextCaption) {
        return current
      }

      const merged: CaptionLine = {
        ...active,
        id: makeId(),
        text: `${active.text} ${nextCaption.text}`.trim(),
        end: nextCaption.end,
      }
      const next = [...current]
      next.splice(index, 2, merged)
      setCaptionsDirty(true)
      setSelectedCaptionId(merged.id)
      return next
    })
  }

  function patchStyle<K extends keyof RenderStyle>(key: K, value: RenderStyle[K]) {
    setStyleDirty(true)
    setDraftStyle((current) => ({ ...current, [key]: value }))
  }

  function clearBackground() {
    setStyleDirty(true)
    setDraftStyle((current) => ({
      ...current,
      background_kind: 'color',
      background_file: null,
      background_asset_url: null,
    }))
  }

  const currentPreviewCaptions = activeCaptionsAtTime(deferredCaptions, currentTime)
  const selectedCaption =
    draftCaptions.find((caption) => caption.id === selectedCaptionId) || draftCaptions[0] || null
  const previewCaptions =
    currentPreviewCaptions.length > 0 ? currentPreviewCaptions : selectedCaption ? [selectedCaption] : []
  const previewFontFamily =
    project && draftStyle.font_asset_url ? `ProjectFont-${project.id}` : draftStyle.font_family

  return (
    <main className="app-shell">
      <section className="hero-card">
        <div>
          <p className="eyebrow">Liquidated Subtitle Studio</p>
          <h1>MP3 to распознанные субтитры.</h1>
        </div>

        <div className="hero-actions">
          <label className="upload-pill">
            <input type="file" accept=".mp3,.wav,.m4a,.flac,.ogg" onChange={handleUpload} />
            Загрузить MP3
          </label>
          <div className="hero-link-row">
            <a
              className="ghost-button hero-link"
              href="https://soundcloud.com/liquidated"
              target="_blank"
              rel="noreferrer"
            >
              SoundCloud
            </a>
            <a
              className="ghost-button hero-link"
              href="https://t.me/liquidatedbeats"
              target="_blank"
              rel="noreferrer"
            >
              Telegram
            </a>
          </div>
          <div className="hero-meta">
            <span>{banner}</span>
            <span>{isPending ? 'Обновляю интерфейс…' : 'UI готов к правкам.'}</span>
          </div>
        </div>
      </section>

      {error ? <section className="error-banner">{error}</section> : null}

      <section className="dashboard-grid">
        <div className="stack">
          <section className="panel">
            <div className="panel-head">
              <div>
                <p className="panel-label">Preview</p>
                <h2>{project ? project.title : 'Пока без проекта'}</h2>
              </div>
              <div className="toggle-row">
                <button
                  type="button"
                  className={previewMode === 'checker' ? 'mode-button active' : 'mode-button'}
                  onClick={() => setPreviewMode('checker')}
                >
                  Alpha view
                </button>
                <button
                  type="button"
                  className={previewMode === 'solid' ? 'mode-button active' : 'mode-button'}
                  onClick={() => setPreviewMode('solid')}
                >
                  Solid view
                </button>
              </div>
            </div>

            <div
              ref={previewStageRef}
              className={previewMode === 'checker' ? 'preview-stage checker' : 'preview-stage solid'}
              style={{
                backgroundColor:
                  previewMode === 'solid' ? draftStyle.background_color : undefined,
              }}
            >
              <div className="preview-frame">
                {previewMode === 'solid' && backgroundPreviewUrl && draftStyle.background_kind === 'image' ? (
                  <img
                    key={backgroundPreviewUrl}
                    className="preview-background-media"
                    src={backgroundPreviewUrl}
                    alt="Project background"
                  />
                ) : null}
                {previewMode === 'solid' && backgroundPreviewUrl && draftStyle.background_kind === 'video' ? (
                  <video
                    key={backgroundPreviewUrl}
                    ref={backgroundVideoRef}
                    className="preview-background-media"
                    autoPlay
                    loop
                    muted
                    playsInline
                    preload="auto"
                  >
                    <source src={backgroundPreviewUrl} type="video/mp4" />
                  </video>
                ) : null}
                {previewCaptions.length === 0 ? (
                  <p className="preview-placeholder">Здесь появятся активные строки субтитров.</p>
                ) : null}

                {previewCaptions.map((caption) => {
                  const isActiveCaption = currentPreviewCaptions.some(
                    (activeCaption) => activeCaption.id === caption.id,
                  )
                  const previewText = resolvePreviewText(
                    caption,
                    currentTime,
                    draftStyle.uppercase,
                    isActiveCaption,
                  )

                  return (
                    <p
                      key={caption.id}
                      className={previewText.typing ? 'preview-caption typing' : 'preview-caption'}
                      style={{
                        left: `${(caption.position_x / draftStyle.canvas_width) * 100}%`,
                        top: `${(caption.position_y / draftStyle.canvas_height) * 100}%`,
                        fontFamily: previewFontFamily,
                        fontSize: `${draftStyle.font_size / 16}rem`,
                        color: draftStyle.text_color,
                        letterSpacing: `${draftStyle.letter_spacing}px`,
                        textTransform: draftStyle.uppercase ? 'uppercase' : 'none',
                        transform: `translate(-50%, -50%) scaleY(${draftStyle.stretch_y / 100})`,
                        filter: `blur(${draftStyle.blur}px)`,
                      }}
                    >
                      {previewText.text}
                    </p>
                  )
                })}
              </div>
            </div>

            {playbackUrl ? (
              <WaveformPlayer audioUrl={playbackUrl} onTimeUpdate={setCurrentTime} />
            ) : (
              <div className="empty-shell">После загрузки проекта здесь появится waveform плеер.</div>
            )}
          </section>

          <section className="panel">
            <div className="panel-head">
              <div>
                <p className="panel-label">Pipeline / exports</p>
                <h2>Очереди и результаты</h2>
              </div>
            </div>

            <div className="status-grid">
              <article className="status-card">
                <span>Project status</span>
                <strong>{project?.status ?? 'idle'}</strong>
              </article>
              <article className="status-card">
                <span>Words</span>
                <strong>{project?.transcript_words.length ?? 0}</strong>
              </article>
              <article className="status-card">
                <span>Caption lines</span>
                <strong>{draftCaptions.length}</strong>
              </article>
              <article className="status-card">
                <span>Audio cursor</span>
                <strong>{formatTime(currentTime)}</strong>
              </article>
            </div>

            <div className="job-list">
              {Object.values(jobs).length === 0 ? (
                <div className="empty-shell">После запуска pipeline здесь появятся job-статусы.</div>
              ) : null}
              {Object.values(jobs).map((job) => (
                <article key={job.id} className={`job-card ${jobTone(job.status)}`}>
                  <div className="job-meta">
                    <strong>{job.kind === 'pipeline' ? 'Pipeline' : 'Export'}</strong>
                    <span>{job.status}</span>
                  </div>
                  <p>{job.message}</p>
                  <div className="job-progress">
                    <span style={{ width: `${job.progress}%` }} />
                  </div>
                </article>
              ))}
            </div>

            <div className="download-grid">
              {(Object.entries(project?.exports ?? {}) as Array<[ExportPreset, ExportArtifact]>)?.map(
                ([preset, artifact]) => (
                  <a
                    key={preset}
                    className={artifact.output_url ? 'download-card ready' : 'download-card'}
                    href={
                      artifact.output_url && projectId
                        ? exportDownloadUrl(projectId, preset, artifact.job_id ?? null)
                        : undefined
                    }
                    rel="noreferrer"
                  >
                    <strong>{preset}</strong>
                    <span>{artifact.output_url ? 'Открыть файл' : artifact.status}</span>
                  </a>
                ),
              )}
            </div>
          </section>
        </div>

        <div className="stack">
          <section className="panel">
            <div className="panel-head">
              <div>
                <p className="panel-label">Style system</p>
                <h2>Liquidated preset</h2>
              </div>
              <span className={styleDirty ? 'dirty-badge' : 'clean-badge'}>
                {styleDirty ? 'Есть несохранённые правки' : 'Синхронизировано'}
              </span>
            </div>

            <div className="control-grid">
              <label>
                Font size
                <input
                  type="number"
                  min="24"
                  max="160"
                  value={draftStyle.font_size}
                  onChange={(event) => patchStyle('font_size', Number(event.target.value))}
                />
              </label>
              <label>
                Blur
                <input
                  type="number"
                  min="0"
                  max="8"
                  step="0.1"
                  value={draftStyle.blur}
                  onChange={(event) => patchStyle('blur', Number(event.target.value))}
                />
              </label>
              <label>
                Stretch Y
                <input
                  type="number"
                  min="80"
                  max="220"
                  value={draftStyle.stretch_y}
                  onChange={(event) => patchStyle('stretch_y', Number(event.target.value))}
                />
              </label>
              <label>
                Letter spacing
                <input
                  type="number"
                  min="-4"
                  max="20"
                  step="0.5"
                  value={draftStyle.letter_spacing}
                  onChange={(event) => patchStyle('letter_spacing', Number(event.target.value))}
                />
              </label>
              <label>
                X
                <input
                  type="number"
                  min="0"
                  max={draftStyle.canvas_width}
                  value={draftStyle.position_x}
                  onChange={(event) => patchStyle('position_x', Number(event.target.value))}
                />
              </label>
              <label>
                Y
                <input
                  type="number"
                  min="0"
                  max={draftStyle.canvas_height}
                  value={draftStyle.position_y}
                  onChange={(event) => patchStyle('position_y', Number(event.target.value))}
                />
              </label>
              <label>
                Text color
                <input
                  type="color"
                  value={draftStyle.text_color}
                  onChange={(event) => patchStyle('text_color', event.target.value)}
                />
              </label>
              <label>
                Background
                <input
                  type="color"
                  value={draftStyle.background_color}
                  onChange={(event) => patchStyle('background_color', event.target.value)}
                />
              </label>
            </div>

            <label className="switch-row">
              <input
                type="checkbox"
                checked={draftStyle.uppercase}
                onChange={(event) => patchStyle('uppercase', event.target.checked)}
              />
              Force uppercase
            </label>

            <div className="background-meta">
              <span>
                {draftStyle.background_kind === 'color'
                  ? 'Фон: однотонный цвет'
                  : draftStyle.background_kind === 'video'
                    ? 'Фон: своё видео, звук будет удалён'
                    : 'Фон: своё изображение'}
              </span>
              {customBackgroundActive ? (
                <span>Фон показывается в Solid view и экспортируется только в MP4.</span>
              ) : null}
            </div>

            {customBackgroundActive ? (
              <div className="background-preview-card">
                {draftStyle.background_kind === 'image' ? (
                  <img
                    src={backgroundPreviewUrl}
                    alt="Background preview"
                    className="background-preview-media"
                  />
                ) : (
                  <video
                    key={`panel-${backgroundPreviewUrl}`}
                    className="background-preview-media"
                    src={backgroundPreviewUrl}
                    autoPlay
                    loop
                    muted
                    playsInline
                    preload="auto"
                  />
                )}
              </div>
            ) : null}

            <div className="action-row">
              <button type="button" className="primary-button" onClick={() => void persistStyle()}>
                Сохранить стиль
              </button>
              <label className="ghost-button upload-font">
                Загрузить шрифт
                <input type="file" accept=".ttf,.otf" onChange={handleFontUpload} />
              </label>
              <label className="ghost-button upload-font">
                Загрузить фон
                <input
                  type="file"
                  accept=".png,.jpg,.jpeg,.webp,.mp4,.mov,.webm,.mkv"
                  onChange={handleBackgroundUpload}
                />
              </label>
              <button type="button" className="ghost-button" onClick={clearBackground}>
                Очистить фон
              </button>
            </div>

            <div className="action-row">
              <button
                type="button"
                className="accent-button"
                onClick={() => void queueExport('alpha_mov')}
                disabled={customBackgroundActive}
                title={
                  customBackgroundActive
                    ? 'Прозрачный MOV не включает фон. Для собственного фона экспортируй MP4.'
                    : undefined
                }
              >
                Export alpha MOV
              </button>
              <button type="button" className="accent-button" onClick={() => void queueExport('mp4_solid')}>
                {customBackgroundActive ? 'Export Background MP4' : 'Export MP4'}
              </button>
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <div>
                <p className="panel-label">Caption editor</p>
                <h2>Текст, тайминги и позиция</h2>
              </div>
              <span className={captionsDirty ? 'dirty-badge' : 'clean-badge'}>
                {captionsDirty ? 'Несохранённые строки' : 'Синхронизировано'}
              </span>
            </div>

            <div className="editor-actions">
              <button type="button" className="ghost-button" onClick={splitSelectedCaption}>
                Split selected
              </button>
              <button type="button" className="ghost-button" onClick={mergeSelectedWithNext}>
                Merge with next
              </button>
              <button type="button" className="primary-button" onClick={() => void persistCaptions()}>
                Сохранить строки
              </button>
            </div>

            <div className="caption-list">
              {draftCaptions.length === 0 ? (
                <div className="empty-shell">
                  После завершения пайплайна здесь появятся распознанные строки для ручной правки.
                </div>
              ) : null}

              {draftCaptions.map((caption) => (
                <article
                  key={caption.id}
                  className={selectedCaptionId === caption.id ? 'caption-card selected' : 'caption-card'}
                  onClick={() => setSelectedCaptionId(caption.id)}
                >
                  <div className="caption-meta">
                    <strong>{formatTime(caption.start)} to {formatTime(caption.end)}</strong>
                    <label className="switch-row compact">
                      <input
                        type="checkbox"
                        checked={!caption.disabled}
                        onChange={(event) =>
                          patchCaption(caption.id, { disabled: !event.target.checked })
                        }
                      />
                      visible
                    </label>
                  </div>

                  <textarea
                    value={caption.text}
                    onChange={(event) => patchCaption(caption.id, { text: event.target.value })}
                  />

                  <div className="caption-grid">
                    <label>
                      Start
                      <input
                        type="number"
                        step="0.01"
                        value={caption.start}
                        onChange={(event) =>
                          patchCaption(caption.id, { start: Number(event.target.value) })
                        }
                      />
                    </label>
                    <label>
                      End
                      <input
                        type="number"
                        step="0.01"
                        value={caption.end}
                        onChange={(event) =>
                          patchCaption(caption.id, { end: Number(event.target.value) })
                        }
                      />
                    </label>
                    <label>
                      X
                      <input
                        type="number"
                        step="1"
                        value={caption.position_x}
                        onChange={(event) =>
                          patchCaption(caption.id, { position_x: Number(event.target.value) })
                        }
                      />
                    </label>
                    <label>
                      Y
                      <input
                        type="number"
                        step="1"
                        value={caption.position_y}
                        onChange={(event) =>
                          patchCaption(caption.id, { position_y: Number(event.target.value) })
                        }
                      />
                    </label>
                  </div>

                  <div className="caption-actions">
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={(event) => {
                        event.stopPropagation()
                        removeCaption(caption.id)
                      }}
                    >
                      Удалить
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      </section>
    </main>
  )
}

export default App
