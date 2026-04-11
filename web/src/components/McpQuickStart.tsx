import { motion } from 'framer-motion';

const PRIMARY_STEPS = [
  {
    n: '1',
    title: 'Avaa liitinyhteyksien asetukset',
    content: (
      <>
        <p style={{ color: '#666', margin: '6px 0 0', fontSize: 14, lineHeight: 1.6 }}>
          Mene MCP-yhteensopivan tekoälypalvelusi liitinasetuksiin. Esimerkiksi Claude.ai:ssa:{' '}
          <a href="https://claude.ai/settings/connectors" target="_blank" rel="noopener noreferrer"
            style={{ color: 'var(--torium-red)', textDecoration: 'none', fontWeight: 500 }}>
            claude.ai/settings/connectors
          </a>
        </p>
      </>
    ),
  },
  {
    n: '2',
    title: 'Lisää mukautettu liitin',
    content: (
      <>
        <p style={{ color: '#666', margin: '6px 0 10px', fontSize: 14 }}>
          Paina <strong>Add custom connector</strong> ja täytä tiedot:
        </p>
        <div style={{
          background: '#f8f8f8', border: '1px solid #e5e5e5',
          borderRadius: 8, padding: '12px 16px',
          display: 'flex', flexDirection: 'column', gap: 8,
        }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'baseline', fontSize: 14 }}>
            <span style={{ color: '#888', minWidth: 140 }}>Nimi</span>
            <code style={{
              background: '#1a1a1a', color: '#e8e8e8',
              padding: '2px 8px', borderRadius: 4,
              fontFamily: 'JetBrains Mono, monospace', fontSize: 13,
            }}>Torium</code>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'baseline', fontSize: 14 }}>
            <span style={{ color: '#888', minWidth: 140 }}>Remote MCP server URL</span>
            <code style={{
              background: '#1a1a1a', color: '#e8e8e8',
              padding: '2px 8px', borderRadius: 4,
              fontFamily: 'JetBrains Mono, monospace', fontSize: 13,
            }}>https://torium.fi/mcp</code>
          </div>
        </div>
        <p style={{ color: '#666', margin: '8px 0 0', fontSize: 14 }}>
          Paina <strong>Add</strong>.
        </p>
      </>
    ),
  },
  {
    n: '3',
    title: 'Yhdistä ja kirjaudu',
    content: (
      <p style={{ color: '#666', margin: '6px 0 0', fontSize: 14, lineHeight: 1.6 }}>
        Paina <strong>Connect</strong> — sinut ohjataan kirjautumissivulle, jossa voit
        yhdistää Tori.fi-tilisi. Seuraa ohjeita.
      </p>
    ),
  },
];

const SELFHOST_STEPS = [
  {
    n: '1',
    title: 'Kloonaa ja asenna',
    code: `git clone https://github.com/ahnl/torium\nuv tool install ./torium`,
  },
  {
    n: '2',
    title: 'Kirjaudu sisään Tori.fi:hin',
    code: `torium auth setup`,
    note: 'Avaa selainpohjaisen OAuth-kirjautumisen. Tunnistetiedot tallennetaan ~/.config/torium/credentials.json.',
  },
  {
    n: '3',
    title: 'Lisää Claude Desktopiin',
    code: `{\n  "mcpServers": {\n    "torium": {\n      "command": "torium-mcp"\n    }\n  }\n}`,
    note: 'Lisää tämä Claude Desktopin asetuksiin: Asetukset → Kehittäjä → Muokkaa asetuksia.',
  },
  {
    n: '4',
    title: 'Käynnistä Claude Desktop uudelleen',
    note: 'Torium-työkalut ovat nyt käytettävissä.',
  },
];

function CodeBlock({ code }: { code: string }) {
  return (
    <pre style={{
      background: '#1a1a1a', color: '#e8e8e8',
      borderRadius: 8, padding: '14px 18px',
      fontFamily: 'JetBrains Mono, monospace',
      fontSize: 13, overflowX: 'auto', margin: '10px 0 0',
      lineHeight: 1.6,
    }}>
      <code>{code}</code>
    </pre>
  );
}

export default function McpQuickStart() {
  return (
    <section id="aloita" style={{ padding: '96px 24px' }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4 }}
          style={{ marginBottom: 10 }}
        >
          Pääset alkuun helposti
        </motion.h2>
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.1 }}
          style={{ color: '#666', marginBottom: 48, fontSize: 16 }}
        >
          Muutamassa minuutissa tekoälysi hallitsee Tori.fi-tilisi.
        </motion.p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
          {PRIMARY_STEPS.map((step, i) => (
            <motion.div
              key={step.n}
              initial={{ opacity: 0, x: -16 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.07 }}
              style={{ display: 'flex', gap: 20 }}
            >
              <div style={{
                width: 36, height: 36, borderRadius: '50%',
                background: 'var(--torium-red)', color: '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontFamily: 'Montserrat, sans-serif', fontWeight: 600,
                fontSize: 15, flexShrink: 0, marginTop: 3,
              }}>
                {step.n}
              </div>
              <div style={{ flex: 1 }}>
                <h3 style={{ margin: 0 }}>{step.title}</h3>
                {step.content}
              </div>
            </motion.div>
          ))}
        </div>

        {/* Self-hosting collapsible */}
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.3 }}
          style={{ marginTop: 56 }}
        >
          <details style={{ borderTop: '1px solid #e5e5e5', paddingTop: 24 }}>
            <summary style={{
              cursor: 'pointer', fontSize: 15, fontWeight: 500,
              color: '#444', userSelect: 'none', listStyle: 'none',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <span style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                width: 20, height: 20, borderRadius: '50%',
                border: '1px solid #ccc', color: '#888', fontSize: 11, flexShrink: 0,
              }}>▶</span>
              Itsehostaus — asenna paikallisesti tai omalle palvelimelle
            </summary>
            <div style={{ marginTop: 28, display: 'flex', flexDirection: 'column', gap: 28 }}>
              {SELFHOST_STEPS.map((step) => (
                <div key={step.n} style={{ display: 'flex', gap: 20 }}>
                  <div style={{
                    width: 28, height: 28, borderRadius: '50%',
                    border: '2px solid var(--torium-red)', color: 'var(--torium-red)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontFamily: 'Montserrat, sans-serif', fontWeight: 600,
                    fontSize: 13, flexShrink: 0, marginTop: 3,
                  }}>
                    {step.n}
                  </div>
                  <div style={{ flex: 1 }}>
                    <h3 style={{ margin: 0, fontSize: 17 }}>{step.title}</h3>
                    {step.note && <p style={{ color: '#666', margin: '6px 0 0', fontSize: 14 }}>{step.note}</p>}
                    {step.code && <CodeBlock code={step.code} />}
                  </div>
                </div>
              ))}
            </div>
          </details>
        </motion.div>
      </div>
    </section>
  );
}
