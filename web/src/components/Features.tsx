import { motion } from 'framer-motion';

const FEATURES = [
  {
    icon: '🤖',
    title: 'MCP-integraatio',
    desc: 'Yhdistä Claude suoraan Tori.fi-tiliisi. Selaa ilmoituksia, vastaa viesteihin ja tee toimenpiteitä luonnollisella kielellä.',
  },
  {
    icon: '🔍',
    title: 'Älykkäät haut',
    desc: 'Hae ilmoituksia sijainnin, hinnan ja kategorian mukaan. Claude suodattaa ja vertailee tuloksia puolestasi.',
  },
  {
    icon: '🖼️',
    title: 'Kuvien tarkistus',
    desc: 'Claude näkee ilmoitusten kuvat ja tunnistaa kunnon, mallin, varusteet ja mahdolliset viat.',
  },
  {
    icon: '💬',
    title: 'Viestit ja hakuvahti',
    desc: 'Lue ja lähetä viestejä sekä hallinnoi hakuvahteja suoraan Claude-keskustelussa.',
  },
];

export default function Features() {
  return (
    <section id="ominaisuudet" style={{ padding: '96px 24px', background: 'var(--torium-red-subtle)' }}>
      <div style={{ maxWidth: 1120, margin: '0 auto' }}>
        <motion.h2
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
      </div>
    </section>
  );
}
