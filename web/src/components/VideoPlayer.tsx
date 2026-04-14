import { motion } from 'framer-motion';
import { useRef, useState, useCallback, useEffect } from 'react';

function fmt(s: number) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

function PlayPauseIcon({ isPlaying }: { isPlaying: boolean }) {
  return (
    <motion.svg
      width="18" height="18" viewBox="0 0 18 18" fill="none"
      key={isPlaying ? 'pause' : 'play'}
      initial={{ scale: 0.75, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.15 }}
    >
      {isPlaying ? (
        <>
          <rect x="4" y="3" width="3.5" height="12" rx="0.75" fill="currentColor" />
          <rect x="10.5" y="3" width="3.5" height="12" rx="0.75" fill="currentColor" />
        </>
      ) : (
        <path d="M5 2.5L15 9L5 15.5V2.5Z" fill="currentColor" />
      )}
    </motion.svg>
  );
}

function FullscreenIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <motion.path
        d="M2 5.5V3.5C2 2.95 2.45 2.5 3 2.5H5.5M10.5 2.5H13C13.55 2.5 14 2.95 14 3.5V5.5M14 10.5V12.5C14 13.05 13.55 13.5 13 13.5H10.5M5.5 13.5H3C2.45 13.5 2 13.05 2 12.5V10.5"
        stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
      />
    </svg>
  );
}

const controlBtnStyle: React.CSSProperties = {
  background: 'transparent', border: 'none',
  color: '#fff', cursor: 'pointer',
  padding: '5px 7px', display: 'flex', alignItems: 'center',
  flexShrink: 0, borderRadius: 6,
  transition: 'background 0.2s, color 0.2s',
};

interface VideoPlayerProps {
  src: string;
  poster?: string;
  autoPlay?: boolean;
  loop?: boolean;
}

export default function VideoPlayer({ src, poster, autoPlay = false, loop = false }: VideoPlayerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(autoPlay);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [hovered, setHovered] = useState(false);
  const [dragging, setDragging] = useState(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout>>(null);
  const seekRef = useRef<(clientX: number) => void>(null);
  const startDragRef = useRef<(clientX: number) => void>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    let raf: number;
    function tick() {
      if (video) {
        setCurrent(video.currentTime);
        setDuration(video.duration || 0);
      }
      raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const progress = duration > 0 ? current / duration : 0;

  const seek = useCallback((clientX: number) => {
    const track = trackRef.current;
    const video = videoRef.current;
    if (!track || !video) return;
    const rect = track.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    video.currentTime = ratio * video.duration;
    setCurrent(video.currentTime);
  }, []);
  seekRef.current = seek;

  const startDrag = useCallback((clientX: number) => {
    setDragging(true);
    seek(clientX);

    const onMove = (e: TouchEvent) => { e.preventDefault(); seekRef.current?.(e.touches[0].clientX); };
    const onPointerMove = (e: PointerEvent) => { seekRef.current?.(e.clientX); };
    const onEnd = () => {
      setDragging(false);
      window.removeEventListener('touchmove', onMove);
      window.removeEventListener('touchend', onEnd);
      window.removeEventListener('touchcancel', onEnd);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onEnd);
    };
    window.addEventListener('touchmove', onMove, { passive: false });
    window.addEventListener('touchend', onEnd);
    window.addEventListener('touchcancel', onEnd);
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onEnd);
  }, [seek]);
  startDragRef.current = startDrag;

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    const handler = (e: TouchEvent) => {
      e.preventDefault();
      e.stopPropagation();
      startDragRef.current?.(e.touches[0].clientX);
    };
    track.addEventListener('touchstart', handler, { passive: false });
    return () => track.removeEventListener('touchstart', handler);
  }, []);

  function togglePlay() {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) { v.play(); setPlaying(true); }
    else { v.pause(); setPlaying(false); }
  }

  const visible = hovered || !playing || dragging;

  function showControlsBriefly() {
    setHovered(true);
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => setHovered(false), 3000);
  }

  return (
    <div
      ref={containerRef}
      style={{ position: 'relative', cursor: 'pointer' }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onTouchEnd={(e) => {
        if (!(e.target as HTMLElement).closest('[data-controls]')) {
          showControlsBriefly();
        }
      }}
    >
      <video
        ref={videoRef}
        src={src}
        poster={poster}
        autoPlay={autoPlay}
        muted={autoPlay}
        loop={loop}
        playsInline
        onClick={togglePlay}
        style={{ width: '100%', display: 'block' }}
      />

      <motion.div
        data-controls
        animate={{ opacity: visible ? 1 : 0 }}
        transition={{ duration: 0.2 }}
        style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          background: 'linear-gradient(transparent, rgba(0,0,0,0.7))',
          padding: '28px 16px 12px',
          display: 'flex', alignItems: 'center', gap: 12,
          userSelect: 'none', WebkitUserSelect: 'none',
          pointerEvents: visible ? 'auto' : 'none',
        }}
      >
        <motion.button
          onClick={(e) => { e.stopPropagation(); togglePlay(); }}
          style={controlBtnStyle}
          whileHover={{ background: 'rgba(147,51,234,0.25)', color: '#d8b4fe' }}
          whileTap={{ scale: 0.9 }}
          aria-label={playing ? 'Pause' : 'Play'}
        >
          <PlayPauseIcon isPlaying={playing} />
        </motion.button>

        <span style={{
          color: 'rgba(255,255,255,0.7)', fontSize: 12,
          fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
          flexShrink: 0, minWidth: 36,
        }}>
          {fmt(current)}
        </span>

        <div
          ref={trackRef}
          onPointerDown={(e) => { e.stopPropagation(); startDrag(e.clientX); }}
          style={{
            flex: 1, height: 32,
            display: 'flex', alignItems: 'center',
            cursor: 'pointer', touchAction: 'none',
          }}
        >
          <div style={{
            width: '100%', height: 4, borderRadius: 2,
            background: 'rgba(255,255,255,0.2)', position: 'relative',
          }}>
            <div style={{
              position: 'absolute', top: 0, left: 0, bottom: 0,
              borderRadius: 2,
              background: 'var(--torium-purple)',
              width: `${progress * 100}%`,
            }} />
            <div style={{
              position: 'absolute', top: '50%',
              left: `${progress * 100}%`,
              width: 14, height: 14, borderRadius: '50%',
              background: '#fff',
              boxShadow: '0 1px 4px rgba(0,0,0,0.3)',
              transform: 'translate(-50%, -50%)',
              pointerEvents: 'none',
            }} />
          </div>
        </div>

        <span style={{
          color: 'rgba(255,255,255,0.7)', fontSize: 12,
          fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
          flexShrink: 0, minWidth: 36, textAlign: 'right',
        }}>
          {fmt(duration)}
        </span>

        <motion.button
          onClick={(e) => {
            e.stopPropagation();
            const el = containerRef.current;
            const video = videoRef.current as any;
            if (!el) return;
            if (document.fullscreenElement) {
              document.exitFullscreen();
            } else if (el.requestFullscreen) {
              el.requestFullscreen();
            } else if (video?.webkitEnterFullscreen) {
              video.webkitEnterFullscreen();
            }
          }}
          style={{ ...controlBtnStyle, marginLeft: 2 }}
          whileHover={{ background: 'rgba(147,51,234,0.25)', color: '#d8b4fe' }}
          whileTap={{ scale: 0.9 }}
          aria-label="Fullscreen"
        >
          <FullscreenIcon />
        </motion.button>
      </motion.div>
    </div>
  );
}
