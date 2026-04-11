import { motion } from 'framer-motion';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const CLI_EXAMPLES = `# Omat ilmoitukset
torium listings
torium listings --facet ALL

# Hae julkisia ilmoituksia
torium search "iphone" --price-from 100 --price-to 500
torium search "iphone" --category 1.93.3217

# Viestit
torium messages
torium messages read 1
torium messages send 1 "Kiinnostaa!"

# Luo ilmoitus
torium listings create --title "Kenkä" --price 10 --category 193 --postal-code 00100

# Merkitse myydyksi / poista
torium listings dispose 12345
torium listings delete 12345`;

const PYTHON_EXAMPLES = `from torium import ToriClient

client = ToriClient()  # lukee ~/.config/torium/credentials.json

# Ilmoitukset
listings = client.listings.search(facet="ACTIVE")
client.listings.dispose(12345)   # merkitse myydyksi
stats   = client.listings.stats(12345)

# Haku
results = client.search.search("iphone", price_from=100, price_to=500)

# Viestit
convs = client.messaging.list_conversations()
client.messaging.send(conv_id, "Kiinnostaa!")

# Suosikit
favs = client.favorites.list()`;

function CodeBlock({ code }: { code: string }) {
  return (
    <pre style={{
      background: '#1a1a1a', color: '#e8e8e8',
      borderRadius: 8, padding: '20px 24px',
      fontFamily: 'JetBrains Mono, monospace',
      fontSize: 13, overflowX: 'auto',
      lineHeight: 1.7, margin: 0,
    }}>
      <code>{code}</code>
    </pre>
  );
}

export default function CliSection() {
  return (
    <section id="cli" style={{ padding: '96px 24px', background: '#f5f5f5' }}>
      <div style={{ maxWidth: 820, margin: '0 auto' }}>
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4 }}
          style={{ marginBottom: 8 }}
        >
          CLI & kirjasto
        </motion.h2>
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.1 }}
          style={{ color: '#666', marginBottom: 32, fontSize: 16 }}
        >
          Kehittäjille: käytä toriumia komentorivillä tai Python-kirjastona.
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.15 }}
        >
          <Tabs defaultValue="cli">
            <TabsList>
              <TabsTrigger value="cli">CLI</TabsTrigger>
              <TabsTrigger value="python">Python-kirjasto</TabsTrigger>
            </TabsList>
            <TabsContent value="cli" style={{ marginTop: 16 }}>
              <CodeBlock code={CLI_EXAMPLES} />
            </TabsContent>
            <TabsContent value="python" style={{ marginTop: 16 }}>
              <CodeBlock code={PYTHON_EXAMPLES} />
            </TabsContent>
          </Tabs>
        </motion.div>
      </div>
    </section>
  );
}
