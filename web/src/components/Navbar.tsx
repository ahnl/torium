import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useState } from 'react';

const NAV_LINKS = [
  { href: '#ominaisuudet', label: 'Ominaisuudet' },
  { href: '#aloita', label: 'Aloita' },
  { href: '#cli', label: 'CLI & kirjasto' },
  { href: 'https://github.com/ahnl/torium', label: 'GitHub', external: true },
];

function BurgerIcon({ open }: { open: boolean }) {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
      <motion.line
        x1="3" y1="6" x2="19" y2="6"
        stroke="#333" strokeWidth="1.75" strokeLinecap="round"
        animate={open ? { y1: 11, y2: 11, rotate: 45, x1: 4, x2: 18 } : { y1: 6, y2: 6, rotate: 0, x1: 3, x2: 19 }}
        transition={{ duration: 0.22 }}
      />
      <motion.line
        x1="3" y1="11" x2="19" y2="11"
        stroke="#333" strokeWidth="1.75" strokeLinecap="round"
        animate={open ? { opacity: 0 } : { opacity: 1 }}
        transition={{ duration: 0.15 }}
      />
      <motion.line
        x1="3" y1="16" x2="19" y2="16"
        stroke="#333" strokeWidth="1.75" strokeLinecap="round"
        animate={open ? { y1: 11, y2: 11, rotate: -45, x1: 4, x2: 18 } : { y1: 16, y2: 16, rotate: 0, x1: 3, x2: 19 }}
        transition={{ duration: 0.22 }}
      />
    </svg>
  );
}

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 8);
    window.addEventListener('scroll', handler, { passive: true });
    return () => window.removeEventListener('scroll', handler);
  }, []);

  // Close menu on resize to desktop
  useEffect(() => {
    const handler = () => { if (window.innerWidth > 640) setMenuOpen(false); };
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);

  function scrollToHash(href: string) {
    const el = document.getElementById(href.slice(1));
    if (el) {
      const y = el.getBoundingClientRect().top + window.scrollY - 80;
      window.scrollTo({ top: Math.max(0, y), behavior: 'smooth' });
    }
  }

  function handleNavClick(e: React.MouseEvent<HTMLAnchorElement>) {
    const href = e.currentTarget.getAttribute('href');
    if (href?.startsWith('#')) {
      e.preventDefault();
      setMenuOpen(false);
      scrollToHash(href);
    }
  }

  return (
    <>
      <style>{`
        .navbar-desktop-links { display: flex; }
        .navbar-burger { display: none; }
        @media (max-width: 640px) {
          .navbar-desktop-links { display: none !important; }
          .navbar-burger { display: flex !important; }
        }
      `}</style>
      <header style={{
        position: 'sticky', top: 0, zIndex: 50,
        background: '#ffffff',
        borderBottom: scrolled || menuOpen ? '1px solid var(--border)' : '1px solid transparent',
        transition: 'border-color 0.2s',
      }}>
        <div style={{ maxWidth: 1120, margin: '0 auto', padding: '0 24px', display: 'flex', alignItems: 'center', height: 64, gap: 32 }}>
          <a href="/" style={{ fontFamily: 'Unbounded, sans-serif', fontWeight: 600, fontSize: 22, color: 'var(--torium-purple)', textDecoration: 'none' }}>
            Torium
          </a>

          {/* Desktop nav */}
          <nav className="navbar-desktop-links" style={{ gap: 24, marginLeft: 'auto', alignItems: 'center' }}>
            {NAV_LINKS.map(link => (
              <a
                key={link.href}
                href={link.href}
                onClick={handleNavClick}
                target={link.external ? '_blank' : undefined}
                rel={link.external ? 'noopener noreferrer' : undefined}
                style={{ color: '#333', textDecoration: 'none', fontSize: 15, fontWeight: 500 }}
              >
                {link.label}
              </a>
            ))}
            <a
              href="#aloita"
              onClick={handleNavClick}
              style={{
                background: 'var(--torium-purple)', color: '#fff',
                padding: '8px 18px', borderRadius: 6,
                textDecoration: 'none', fontSize: 15, fontWeight: 500,
                whiteSpace: 'nowrap',
              }}
            >
              Aloita
            </a>
          </nav>

          {/* Mobile right side: burger */}
          <div className="navbar-burger" style={{ marginLeft: 'auto', alignItems: 'center' }}>
            <button
              onClick={() => setMenuOpen(o => !o)}
              aria-label="Valikko"
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: 4, display: 'flex', alignItems: 'center',
              }}
            >
              <BurgerIcon open={menuOpen} />
            </button>
          </div>
        </div>

        {/* Mobile dropdown menu — absolutely positioned to overlay content */}
        <AnimatePresence>
          {menuOpen && (
            <motion.nav
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              style={{
                position: 'absolute', top: '100%', left: 0, right: 0,
                background: '#fff', borderTop: '1px solid var(--border)',
                boxShadow: '0 8px 24px rgba(0,0,0,0.08)',
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', padding: '8px 24px 16px' }}>
                {NAV_LINKS.map((link, i) => (
                  <motion.a
                    key={link.href}
                    href={link.href}
                    target={link.external ? '_blank' : undefined}
                    rel={link.external ? 'noopener noreferrer' : undefined}
                    onClick={handleNavClick}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04, duration: 0.18 }}
                    style={{
                      color: '#333', textDecoration: 'none',
                      fontSize: 16, fontWeight: 500,
                      padding: '12px 0',
                      borderBottom: i < NAV_LINKS.length - 1 ? '1px solid #f0f0f0' : 'none',
                      display: 'block',
                    }}
                  >
                    {link.label}
                  </motion.a>
                ))}
              </div>
            </motion.nav>
          )}
        </AnimatePresence>
      </header>
    </>
  );
}
