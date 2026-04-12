import { motion } from 'framer-motion';
import { useState } from 'react';
import type { ReactNode } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

interface Step {
  n: string;
  title: string;
  code?: string;
  note?: string;
  content?: ReactNode;
}

const SELFHOST_STEPS: Step[] = [
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

function RemoteConnectorFields() {
  return (
    <p style={{ color: '#666', margin: '6px 0 0', fontSize: 14, lineHeight: 1.6 }}>
      Mene{' '}
      <a
        href="https://claude.ai/settings/connectors"
        target="_blank"
        rel="noopener noreferrer"
        style={{ color: 'var(--torium-purple)', textDecoration: 'none', fontWeight: 500 }}
      >
        claude.ai/settings/connectors
      </a>{' '}
      ja paina <strong>Add custom connector</strong>. Syötä palvelimesi URL (esim.{' '}
      <code style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>
        https://tori.example.com/mcp
      </code>
      ) ja paina <strong>Add</strong>.
    </p>
  );
}

const REMOTE_SELFHOST_STEPS: Step[] = [
  {
    n: '1',
    title: 'Kloonaa ja asenna',
    code: `git clone https://github.com/ahnl/torium\nuv tool install ./torium`,
  },
  {
    n: '2',
    title: 'Salli sähköpostiosoitteesi',
    code: `torium-mcp allow sinä@example.com --note "nimi"\ntorium-mcp list-allowed    # tarkista lista\ntorium-mcp revoke sinä@example.com  # poista oikeus`,
    note: 'Tämä on tehtävä ennen ensimmäistä kirjautumista.',
  },
  {
    n: '3',
    title: 'Käynnistä palvelin',
    code: `torium-mcp --transport streamable-http --host 127.0.0.1 --port 5001 --base-url https://tori.example.com`,
    note: '--base-url on julkinen HTTPS-osoite, jonka claude.ai pystyy tavoittamaan (esim. käänteisproxylla tai SSH-tunnelilla).',
  },
  {
    n: '4',
    title: 'Lisää liitin claude.ai:hin',
    content: <RemoteConnectorFields />,
  },
  {
    n: '5',
    title: 'Kirjaudu palvelimelle',
    note: 'Claude avaa kirjautumisikkunan. Paina Log in to Tori.fi, tee Schibsted-kirjautuminen ja kopioi fi.tori.www...-ohjausURL selaimen konsolista. Liitä se lomakkeeseen. Istunto on voimassa 180 päivää.',
  },
];

function CodeBlock({ code }: { code: string }) {
  return (
    <pre style={{
      background: '#1a1a1a', color: '#e8e8e8',
      borderRadius: 8, padding: '14px 18px',
      fontFamily: 'JetBrains Mono, monospace',
      fontSize: 13, overflowX: 'auto', margin: '10px 0 0',
      lineHeight: 1.6, whiteSpace: 'pre', wordBreak: 'normal',
    }}>
      <code>{code}</code>
    </pre>
  );
}

function CopyField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  }

  return (
    <div className="copy-field-row" style={{
      display: 'flex', alignItems: 'center',
      padding: '10px 0',
      borderBottom: '1px solid #ebebeb',
      gap: 12, flexWrap: 'wrap',
    }}>
      <span className="copy-field-label" style={{ color: '#888', fontSize: 13, width: 160, flexShrink: 0 }}>{label}</span>
      <code className="copy-field-value" style={{
        background: '#1a1a1a', color: '#e8e8e8',
        padding: '3px 10px', borderRadius: 5,
        fontFamily: 'JetBrains Mono, monospace', fontSize: 13,
        flex: 1, minWidth: 0, wordBreak: 'break-all',
      }}>{value}</code>
      <button
        onClick={handleCopy}
        style={{
          background: copied ? '#e6f9ed' : '#f0f0f0',
          color: copied ? '#1a7a3a' : '#555',
          border: 'none', borderRadius: 5,
          padding: '4px 10px', fontSize: 12, fontWeight: 500,
          cursor: 'pointer', fontFamily: 'inherit',
          flexShrink: 0, transition: 'background 0.2s, color 0.2s',
          minWidth: 72,
        }}
      >
        {copied ? 'Kopioitu ✓' : 'Kopioi'}
      </button>
    </div>
  );
}

function ConnectorFields() {
  return (
    <>
      <p style={{ color: '#666', margin: '6px 0 10px', fontSize: 14 }}>
        Paina <strong>Add custom connector</strong> ja täytä tiedot:
      </p>
      <div style={{
        background: '#f8f8f8', border: '1px solid #e5e5e5',
        borderRadius: 8, padding: '0 16px',
      }}>
        <CopyField label="Nimi" value="Tori.fi" />
        <div style={{ borderBottom: 'none' }}>
          <CopyField label="Remote MCP server URL" value="https://torium.fi/mcp" />
        </div>
      </div>
      <p style={{ color: '#666', margin: '8px 0 0', fontSize: 14 }}>
        Paina <strong>Add</strong>.
      </p>
    </>
  );
}

function SelfhostStepList({ steps }: { steps: Step[] }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      {steps.map((step) => (
        <div key={step.n} style={{ display: 'flex', gap: 20 }}>
          <div style={{
            width: 28, height: 28, borderRadius: '50%',
            border: '2px solid var(--torium-purple)', color: 'var(--torium-purple)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'Unbounded, sans-serif', fontWeight: 600,
            fontSize: 13, flexShrink: 0, marginTop: 3,
          }}>
            {step.n}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3 style={{ margin: 0, fontSize: 17 }}>{step.title}</h3>
            {step.note && <p style={{ color: '#666', margin: '6px 0 0', fontSize: 14 }}>{step.note}</p>}
            {step.code && <CodeBlock code={step.code} />}
            {step.content && step.content}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function McpQuickStart() {
  const primarySteps = [
    {
      n: '1',
      title: 'Avaa liitinyhteyksien asetukset',
      content: (
        <p style={{ color: '#666', margin: '6px 0 0', fontSize: 14, lineHeight: 1.6 }}>
          Mene MCP-yhteensopivan tekoälypalvelusi liitinasetuksiin. Esimerkiksi Claude.ai:ssa:{' '}
          <a href="https://claude.ai/settings/connectors" target="_blank" rel="noopener noreferrer"
            style={{ color: 'var(--torium-purple)', textDecoration: 'none', fontWeight: 500 }}>
            claude.ai/settings/connectors
          </a>
        </p>
      ),
    },
    {
      n: '2',
      title: 'Lisää mukautettu liitin',
      content: <ConnectorFields />,
    },
    {
      n: '3',
      title: 'Yhdistä ja kirjaudu',
      content: (
        <p style={{ color: '#666', margin: '6px 0 0', fontSize: 14, lineHeight: 1.6 }}>
          Paina <strong>Connect</strong>, niin sinut ohjataan kirjautumissivulle, jossa voit
          yhdistää Tori.fi-tilisi. Seuraa ohjeita.
        </p>
      ),
    },
  ];

  return (
    <>
    <style>{`
      @media (max-width: 540px) {
        .copy-field-label { width: 100% !important; }
        .copy-field-value { flex: unset !important; width: 100% !important; min-width: 0; }
      }
    `}</style>
    <section style={{ padding: '96px 24px' }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <motion.h2
          id="aloita"
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

        <div style={{
          background: '#f8f8f8',
          border: '1px solid #e5e5e5',
          borderRadius: 8,
          padding: '12px 16px',
          marginBottom: 40,
          fontSize: 13,
          color: '#666',
          lineHeight: 1.6,
          display: 'flex',
          gap: 10,
          alignItems: 'flex-start',
        }}>
          <span style={{ color: '#aaa', fontSize: 15, flexShrink: 0, marginTop: 1 }}>ⓘ</span>
          <span>Torium on ei-kaupallinen kolmannen osapuolen MCP-liitin, jolla ei ole Tori.fi:n virallista hyväksyntää. Käyttö tapahtuu ilman takuita ja täysin omalla vastuullasi. Vastaat itse Tori.fi:n käyttöehtojen noudattamisesta. Kehittäjät eivät ota vastuuta mahdollisista seurauksista, kuten tilisi sulkemisesta.</span>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.1 }}
        >
          <Tabs defaultValue="julkinen">
            <TabsList style={{
              background: '#e8e8e8', padding: 4,
              borderRadius: 10, gap: 2, height: 'auto',
              display: 'inline-flex', marginBottom: 40,
            }}>
              <TabsTrigger
                value="julkinen"
                style={{ borderRadius: 7, padding: '8px 20px', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}
              >
                <span style={{ marginRight: 6 }}>☁️</span> torium.fi
              </TabsTrigger>
              <TabsTrigger
                value="itsehostaus"
                style={{ borderRadius: 7, padding: '8px 20px', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}
              >
                <span style={{ marginRight: 6 }}>🖥️</span> Itsehostaus
              </TabsTrigger>
            </TabsList>

            <TabsContent value="julkinen">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
                {primarySteps.map((step, i) => (
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
                      background: 'var(--torium-purple)', color: '#fff',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontFamily: 'Unbounded, sans-serif', fontWeight: 600,
                      fontSize: 15, flexShrink: 0, marginTop: 3,
                    }}>
                      {step.n}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <h3 style={{ margin: 0 }}>{step.title}</h3>
                      {step.content}
                    </div>
                  </motion.div>
                ))}
              </div>
              <details style={{ borderTop: '1px solid #e5e5e5', padding: '16px 0', marginTop: 40 }}>
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
                  Ohjevideo
                </summary>
                <div style={{ marginTop: 20 }}>
                  <video
                    src="/setup.mp4"
                    controls
                    style={{
                      width: '100%', borderRadius: 10,
                      background: '#000', display: 'block',
                    }}
                  />
                </div>
              </details>
            </TabsContent>

            <TabsContent value="itsehostaus">
              <Tabs defaultValue="paikallinen">
                <TabsList style={{
                  background: '#ebebeb', padding: 3,
                  borderRadius: 8, gap: 2, height: 'auto',
                  display: 'inline-flex', marginBottom: 32,
                }}>
                  <TabsTrigger
                    value="paikallinen"
                    style={{ borderRadius: 6, padding: '6px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
                  >
                    Paikallinen (stdio)
                  </TabsTrigger>
                  <TabsTrigger
                    value="etapalvelin"
                    style={{ borderRadius: 6, padding: '6px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
                  >
                    Etäpalvelin
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="paikallinen">
                  <SelfhostStepList steps={SELFHOST_STEPS} />
                </TabsContent>

                <TabsContent value="etapalvelin">
                  <SelfhostStepList steps={REMOTE_SELFHOST_STEPS} />
                </TabsContent>
              </Tabs>
            </TabsContent>
          </Tabs>
        </motion.div>

      </div>
    </section>

    </>
  );
}
