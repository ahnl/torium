import { motion } from 'framer-motion';

const STEPS = [
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
    note: 'Torium-työkalut ovat nyt käytettävissä. Voit pyytää Claudea hallitsemaan ilmoituksiasi.',
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
          Aloita Claude.ai:ssa
        </motion.h2>
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.1 }}
          style={{ color: '#666', marginBottom: 48, fontSize: 16 }}
        >
          Muutamassa minuutissa Claude hallitsee Tori.fi-tilisi.
        </motion.p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
          {STEPS.map((step, i) => (
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
                {step.note && <p style={{ color: '#666', margin: '6px 0 0', fontSize: 14 }}>{step.note}</p>}
                {step.code && <CodeBlock code={step.code} />}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
