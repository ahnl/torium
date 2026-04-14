import { motion } from 'framer-motion';
import VideoPlayer from './VideoPlayer';

export default function Hero() {
  return (
    <section style={{ padding: '88px 24px 64px', maxWidth: 1120, margin: '0 auto', textAlign: 'center' }}>
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <h1 style={{ marginBottom: 20 }}>
          Tori.fi tekoälysi käyttöön
        </h1>
        <p style={{ fontSize: 20, color: '#555', maxWidth: 560, margin: '0 auto 36px', lineHeight: 1.6 }}>
          Torium yhdistää tekoälysi Tori.fi-tiliin. Selaa, hallitse ja vastaa
          ilmoituksiin luonnollisella kielellä.
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
          <a
            href="#aloita"
            style={{
              background: 'var(--torium-purple)', color: '#fff',
              padding: '13px 28px', borderRadius: 8,
              textDecoration: 'none', fontSize: 16, fontWeight: 500,
            }}
          >
            Aloita →
          </a>
          <a
            href="https://github.com/ahnl/torium"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              border: '2px solid var(--torium-purple)', color: 'var(--torium-purple)',
              padding: '11px 28px', borderRadius: 8,
              textDecoration: 'none', fontSize: 16, fontWeight: 500,
              background: 'transparent',
            }}
          >
            GitHub
          </a>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 32 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        style={{ marginTop: 64 }}
      >
        <div style={{
          maxWidth: 820, margin: '0 auto',
          borderRadius: 12, overflow: 'hidden',
          boxShadow: '0 8px 48px rgba(0,0,0,0.13)',
          background: '#111',
        }}>
          <VideoPlayer src="/demo.mp4" poster="/demo-poster.jpg" autoPlay loop />
        </div>
      </motion.div>
    </section>
  );
}
