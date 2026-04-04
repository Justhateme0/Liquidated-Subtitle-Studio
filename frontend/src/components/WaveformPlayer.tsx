import { useEffect, useRef, useState } from 'react'
import WaveSurfer from 'wavesurfer.js'

type WaveformPlayerProps = {
  audioUrl: string
  onTimeUpdate: (value: number) => void
}

function formatTime(value: number) {
  const totalSeconds = Math.max(0, Math.floor(value))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export function WaveformPlayer({ audioUrl, onTimeUpdate }: WaveformPlayerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const waveSurferRef = useRef<WaveSurfer | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)

  useEffect(() => {
    if (!containerRef.current) {
      return
    }

    const waveSurfer = WaveSurfer.create({
      container: containerRef.current,
      url: audioUrl,
      height: 96,
      waveColor: '#273020',
      progressColor: '#d9ff61',
      cursorColor: '#f4f8ee',
      barWidth: 3,
      barGap: 2,
      normalize: true,
      dragToSeek: true,
      hideScrollbar: true,
    })

    waveSurfer.on('ready', () => {
      setDuration(waveSurfer.getDuration())
    })

    waveSurfer.on('timeupdate', (value) => {
      setCurrentTime(value)
      onTimeUpdate(value)
    })

    waveSurfer.on('play', () => setIsPlaying(true))
    waveSurfer.on('pause', () => setIsPlaying(false))
    waveSurfer.on('finish', () => setIsPlaying(false))

    waveSurferRef.current = waveSurfer

    return () => {
      waveSurfer.destroy()
      waveSurferRef.current = null
    }
  }, [audioUrl, onTimeUpdate])

  return (
    <section className="wave-shell">
      <div className="wave-toolbar">
        <button
          type="button"
          className="ghost-button"
          onClick={() => void waveSurferRef.current?.playPause()}
        >
          {isPlaying ? 'Pause' : 'Play'}
        </button>
        <span>
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>
      </div>
      <div className="wave-stage" ref={containerRef} />
    </section>
  )
}
