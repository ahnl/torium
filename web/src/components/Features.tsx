import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const FEATURES = [
  {
    icon: '🤖',
    title: 'MCP-integraatio',
    desc: 'Yhdistä tekoäly suoraan Tori.fi-tiliisi. Selaa ilmoituksia, vastaa viesteihin ja tee toimenpiteitä luonnollisella kielellä.',
  },
  {
    icon: '🔍',
    title: 'Älykkäät haut',
    desc: 'Hae ilmoituksia sijainnin, hinnan ja kategorian mukaan. Tekoäly suodattaa ja vertailee tuloksia puolestasi.',
  },
  {
    icon: '🖼️',
    title: 'Kuvien tarkistus',
    desc: 'Tekoäly näkee ilmoitusten kuvat ja tunnistaa niistä kunnon, mallin, varusteet ja mahdolliset viat.',
  },
  {
    icon: '💬',
    title: 'Viestit ja hakuvahti',
    desc: 'Lue ja lähetä viestejä sekä hallinnoi hakuvahteja suoraan tekoälykeskustelussa.',
  },
];

const TOOL_CATEGORIES = [
  {
    icon: '📋',
    title: 'Ilmoitukset',
    tools: ['Ilmoituksen tiedot', 'Tarkastele ilmoituksen kuvaa', 'Aloita keskustelu'],
  },
  {
    icon: '✏️',
    title: 'Ilmoitusten hallinta',
    tools: ['Luo ilmoitus', 'Muokkaa ilmoitusta', 'Merkitse myydyksi', 'Poista ilmoitus', 'Näyttökerrat ja tilastot'],
  },
  {
    icon: '💬',
    title: 'Viestit',
    tools: ['Saapuneet viestit', 'Lue keskustelu', 'Lähetä viesti', 'Lukemattomat viestit'],
  },
  {
    icon: '🔍',
    title: 'Haku',
    tools: ['Hae ilmoituksia', 'Hae kategorioita'],
  },
  {
    icon: '🔔',
    title: 'Hakuvahti',
    tools: ['Omat hakuvahdit', 'Luo hakuvahti', 'Poista hakuvahti'],
  },
  {
    icon: '🖼️',
    title: 'Suosikit',
    tools: ['Suosikkini'],
  },
];

const TOOL_COUNT = TOOL_CATEGORIES.reduce((sum, cat) => sum + cat.tools.length, 0);

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <motion.svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      animate={{ rotate: open ? 90 : 0 }}
      transition={{ duration: 0.2 }}
      style={{ display: 'block', flexShrink: 0 }}
    >
      <path
        d="M5 3L9.5 7L5 11"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </motion.svg>
  );
}

export default function Features() {
  const [toolsOpen, setToolsOpen] = useState(false);

  return (
    <section style={{ padding: '96px 24px', background: 'var(--torium-purple-subtle)' }}>
      <div style={{ maxWidth: 1120, margin: '0 auto' }}>
        <motion.h2
          id="ominaisuudet"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4 }}
          style={{ textAlign: 'center', marginBottom: 56 }}
        >
          Ominaisuudet
        </motion.h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 24 }}>
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.08 }}
              whileHover={{ y: -4 }}
              style={{
                background: '#fff', borderRadius: 12,
                padding: 28, border: '1px solid #e5e5e5',
              }}
            >
              <div style={{ fontSize: 32, marginBottom: 12 }}>{f.icon}</div>
              <h3 style={{ marginBottom: 8 }}>{f.title}</h3>
              <p style={{ color: '#666', lineHeight: 1.6, margin: 0, fontSize: 15 }}>{f.desc}</p>
            </motion.div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.35 }}
          style={{ marginTop: 32, textAlign: 'center' }}
        >
          <button
            onClick={() => setToolsOpen(!toolsOpen)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '6px 2px',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontFamily: 'Inter, system-ui, sans-serif',
              fontSize: 14,
              fontWeight: 500,
              color: 'var(--torium-purple)',
              transition: 'opacity 0.15s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.7'; }}
            onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
          >
            Saatavilla olevat MCP-työkalut
            <span style={{
              background: 'rgba(147, 51, 234, 0.1)',
              color: 'var(--torium-purple)',
              fontSize: 12,
              fontWeight: 600,
              padding: '2px 7px',
              borderRadius: 10,
              lineHeight: '1.4',
            }}>
              {TOOL_COUNT}
            </span>
            <ChevronIcon open={toolsOpen} />
          </button>
        </motion.div>

        <AnimatePresence>
          {toolsOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: 'easeInOut' }}
              style={{ overflow: 'hidden' }}
            >
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
                gap: 20,
                paddingTop: 24,
              }}>
                {TOOL_CATEGORIES.map((cat, ci) => (
                  <motion.div
                    key={cat.title}
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: ci * 0.06 }}
                    style={{
                      background: '#fff',
                      borderRadius: 12,
                      padding: '24px 24px 20px',
                      border: '1px solid #e5e5e5',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                      <span style={{ fontSize: 20 }}>{cat.icon}</span>
                      <span style={{
                        fontFamily: 'Unbounded, sans-serif',
                        fontSize: 14,
                        fontWeight: 600,
                        color: 'var(--torium-purple)',
                        letterSpacing: '-0.01em',
                      }}>
                        {cat.title}
                      </span>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      {cat.tools.map((tool) => (
                        <span
                          key={tool}
                          style={{
                            background: 'var(--torium-purple-subtle)',
                            color: 'var(--torium-purple-dark)',
                            borderRadius: 6,
                            padding: '5px 10px',
                            fontSize: 13,
                            fontWeight: 500,
                            lineHeight: 1.3,
                          }}
                        >
                          {tool}
                        </span>
                      ))}
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
}
