'use client';
import { useEffect, useState } from 'react';

const NAV_LINKS = [
  { href: '#ominaisuudet', label: 'Ominaisuudet' },
  { href: '#aloita', label: 'Aloita' },
  { href: '#cli', label: 'CLI' },
  { href: 'https://github.com/ahnl/torium', label: 'GitHub', external: true },
];

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 8);
    window.addEventListener('scroll', handler, { passive: true });
    return () => window.removeEventListener('scroll', handler);
  }, []);

  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 50,
      background: '#ffffff',
      borderBottom: scrolled ? '1px solid var(--border)' : '1px solid transparent',
      transition: 'border-color 0.2s',
    }}>
      <div style={{ maxWidth: 1120, margin: '0 auto', padding: '0 24px', display: 'flex', alignItems: 'center', height: 64, gap: 32 }}>
        <a href="/" style={{ fontFamily: 'Montserrat, sans-serif', fontWeight: 600, fontSize: 22, color: 'var(--torium-red)', textDecoration: 'none' }}>
          torium
        </a>
        <nav style={{ display: 'flex', gap: 24, marginLeft: 'auto', alignItems: 'center', flexWrap: 'wrap' }}>
          {NAV_LINKS.map(link => (
            <a
              key={link.href}
              href={link.href}
              target={link.external ? '_blank' : undefined}
              rel={link.external ? 'noopener noreferrer' : undefined}
              style={{ color: '#333', textDecoration: 'none', fontSize: 15, fontWeight: 500 }}
            >
              {link.label}
            </a>
          ))}
          <a
            href="https://claude.ai/settings/connectors"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              background: 'var(--torium-red)', color: '#fff',
              padding: '8px 18px', borderRadius: 6,
              textDecoration: 'none', fontSize: 15, fontWeight: 500,
            }}
          >
            Lisää Claude.ai:hin
          </a>
        </nav>
      </div>
    </header>
  );
}
