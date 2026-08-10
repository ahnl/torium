# CONTEXT.md — Kehityskonteksti (torium)

Fork projektista `ahnl/tori-client`. Tori.fi:n epävirallinen API-client (kirjasto + CLI + MCP-serveri), joka jäljittelee iOS-sovelluksen liikennettä (finn-gw-allekirjoitukset, apps-adinput-subdomain).

## Nykytila

- **Toimii:** haku, omat ilmoitukset, viestit, suosikit, create_listing (kuvineen), republish_listing, dispose/delete.
- **Korjattu ja live-vahvistettu 2026-07-13:** edit_listing / listings.edit() — hiljainen tietohäviö korjattu (ks. alla). Testattu oikeaa APIa vasten: 12265237 (EXPIRED → hinta 30 € + republish onnistui), 20701613 (kuvaus meni liveksi). Paikallinen MCP-serveri pitää käynnistää uudelleen ennen kuin korjaus on MCP-työkaluissa käytössä (editable install; lisäksi CLI-testit rotatoivat refresh-tokenin, jonka vanha serveriprosessi pitää muistissa).
- **Uutta 2026-08-10:** `listings.owner(ad_id)` ja MCP:n `get_listing` palauttavat myyjän tunnisteen (`owner_id`). Tämä on vaihe 0 "myyjän muut ilmoitukset" -ominaisuudesta (ks. Seuraavat askeleet). Testit: `tests/test_seller_identity.py`, ei verkkoa.
- **Kesken käyttäjän datassa:** 62 EXPIRED-ilmoitusta odottaa julkaisua. HUOM: 11.7. tehdyt tekstipäivitykset ovat tallessa niiden adinput-luonnosrevisioissa — commit (publish) riittää viemään ne liveksi, tekstejä ei tarvitse lähettää uudelleen. SpineGymin (12265237) live-kuvauksessa lukee yhä "Nyt 75 €" vaikka hintakenttä on 30 € — kuvausteksti pitää päivittää.

## Bugit ja korjaushistoria

| Bugi | Juurisyy | Korjaus |
|---|---|---|
| edit_listing kuittasi onnistuneeksi, mutta muutos ei tallentunut (silent write loss) | Adinput-API on kaksivaiheinen: `PUT .../update` tallentaa vain luonnosrevision; elävä ilmoitus päivittyy vasta commit-vaiheessa (`GET productcontext?adRevision` → `POST /order/choices`). Edit-polku pysähtyi PUT:iin ja päätteli onnistumisen pelkästä ETagista. | `listings.edit()`: update → publish (sama sekvenssi kuin create():ssa) → read-back-varmistus adview'sta. Lisäksi PUT-vastauksen `meta-data.violations` tarkistetaan (API palauttaa validointivirheet 200-statuksella). Testit: `tests/test_edit_flow.py`. |
| Uusi ilmoitus jäi jumiin "tarkistettavana"-tilaan | Publish ilman delivery-asetuksia / productcontext-hakua | Commitit `2eba60f`, `62637eb`: set_delivery + productcontext ennen order/choices-kutsua |

## Arkkitehtuuripäätökset

- **edit() ei kutsu set_delivery():ä** (toisin kuin create()): julkaistulla ilmoituksella toimitusasetukset ovat jo olemassa, eikä niitä haluta ylikirjoittaa oletuksilla.
- **Commit tehdään `POST /order/choices` -kutsulla (Basic, ilmainen)** — live-vahvistettu 2026-07-13 sekä EXPIRED- että editointitapauksessa. withModel-vastauksen `checkout-url` (`publish_free_ad?adRevision=...`) palauttaa POST:lle 404 — sitä EI käytetä. Huom: editissä `productcontext.choices` on tyhjä (ei ostettavaa), mutta order/choices committoi revision silti.
- **`edited`-aikaleima leimautuu revision LUONTIhetkestä, ei julkaisuhetkestä.** Älä käytä sitä "julkaistiinko juuri nyt" -tarkistukseen; vertaa kenttäarvoja.
- **Adview'n propagaatio kestää minuutteja** commitin jälkeen (mitattu: muutos näkyi vasta ~2–10 min). Read-back-turvaverkko odottaa porrastetusti ~5,5 min (`_READBACK_DELAYS`). Jos aikakatkaisu tulee, virheviesti kertoo että muutos voi silti vielä propagoitua.
- **Read-back-varmistus on pysyvä turvaverkko**, ei väliaikainen: edit() vertaa adview-kenttiä whitespace-normalisoituna. Jos kentät eivät muuttuneet → RuntimeError, ei koskaan valheellista onnistumista.
- **Myyjän tunniste luetaan adview'n `meta`-lohkosta, ei `ad`-rungosta.** Adview'ssa ei ole minkäänlaista myyjäkenttää ilmoituksen sisällössä — vain `meta.ownerId` ja `meta.ownerUrn` (`sdrn:aurora.tori.fi:user:{id}`). Siksi `owner_from_adview()` on oma pieni funktionsa: sama uutto tarvitaan sekä kirjastossa että MCP-kääreessä, ja se on ainoa silta ilmoituksesta myyjään.
- **update() heittää virheen validointirikkeistä** (`meta-data.violations`, tulevat 200-statuksella) mutta ei julkaise — julkaisu vain edit():n kautta, jotta create():n oma sekvenssi ei riko.

## Tunnetut riskit

- **Matala:** read-backin aikakatkaisu (~5,5 min) voi antaa vääriä hälytyksiä jos Torin propagaatio on poikkeuksellisen hidas — mutta ei koskaan väärää onnistumiskuittausta. Tarkista `get_listing`illä ennen uudelleenyritystä.
- **Matala/huomio:** EXPIRED-ilmoituksen editointi tekee samalla republishin (sama commit-endpoint) — massa-ajossa yksi edit-kutsu hoitaa molemmat.
- **Matala:** rinnakkaiset clientit samalla refresh-tokenilla pudottavat autentikoinnin (token rotation; pitkään ajossa oleva prosessi pitää tokenin muistissa eikä lue tiedostoa uudelleen). Älä aja CLI:tä/probeja kun paikallinen MCP-serveri on käynnissä — ja MCP-serverin restart korjaa tilanteen, koska se lukee credentials.json:n tuoreena.

## Seuraavat askeleet

1. Käynnistä paikallinen MCP-serveri uudelleen (lataa korjatun koodin JA tuoreen tokenin — CLI-testit 13.7. rotatoivat sen).
2. Massa-ajo 62 EXPIRED-ilmoitukselle: 11.7. tekstipäivitykset ovat jo luonnosrevisioissa, joten `republish_listing` committoi ne samalla — TAI aja `edit_listing` uusilla teksteillä (varmistetumpi: read-back todistaa). SpineGymin kuvausteksti pitää joka tapauksessa päivittää ("Nyt 75 €" → 30 €).
3. Tarkista massa-ajon jälkeen pistokokein pari ilmoitusta `get_listing`illä (muista ~minuuttien propagaatio).

### "Myyjän muut ilmoitukset" — tilanne 2026-08-10

Tavoite: `get_seller_listings(ad_id)` → myyjän muut myynnissä olevat ilmoitukset.

**Vaihe 0 — VALMIS.** `owner_id` saatavilla (`listings.owner()` + `get_listing`).

**Tiedustelun tulokset (Chrome, kirjautunut web-sessio, 2026-08-10):**
- `https://www.tori.fi/profile/ads?userId=X` **näyttää toisen myyjän ilmoitukset** — nimi, "Torin käyttäjä vuodesta", arvostelumäärä, välilehdet "Ilmoitukset (n)" / "Arvostelut (n)", ja kortit joissa hinta, ToriDiili-merkki, sijainti, päiväys ja linkki `/{adId}`.
- **JSON-endpointtia ei ole.** Sivun kaikki verkkopyynnöt luettiin (`performance.getEntriesByType('resource')`): ainoa `www.tori.fi`-XHR on `/profile/podium-resource/header/api` (yläpalkki). Ilmoituslista tulee täysin palvelinrenderöitynä podletista `trust-public-profile-layout`. Backend-kutsu tapahtuu Torin sisäverkossa — selain ei näe sitä.
- Sivu vaatii web-kirjautumisen (ulos kirjautuneena 302 → `/auth/login`).
- Kääntöpuoli: koska renderöinti on SSR, HTML on valmis heti — raapiminen on luotettavaa, ei hydraatio-odottelua.
- **Sivutusta ei ole vielä testattu** (testimyyjällä 1 ilmoitus). Selvitettävä ennen toteutusta.

**Vaihe 1 (seuraava, aikaboksi ~1 h) — SPiD-web-sessio toriumin sisällä.**
`auth.py` autentikoituu jo Schibstedin `login.vend.fi`-kautta (`oauth/token` → `api/2/oauth/exchange` spidCodella → `public/login`). Tämä on sama identiteettipalvelu jota tori.fi-sivusto käyttää. Kokeiltava: saako samalla refresh-tokenilla web-sessioevästeen tori.fi:hin, jolloin torium voi hakea SSR-sivun itse ja parsia kortit → puhdas MCP-työkalu, ei selainta.
*Riski:* session-vaihto voi vaatia web-clientin oman `client_id`:n → koe kaatuu. **HUOM: sammuta paikallinen MCP-serveri probejen ajaksi** (refresh-token rotatoituu).

**Vaihe 2 (varasuunnitelma, jos vaihe 1 kaatuu) — selainadapteri.**
Skill joka avaa profiilisivun Claude-in-Chromessa ja lukee kortit accessibility-puusta. Todennettu toimivaksi 2026-08-10. Sama kuvio kuin `vinted-era`-skillissä (Vinted/DataDome).

**Vaihe 3 (vain jos natiivi gateway-endpoint halutaan) — emulaattorikaappaus.**
Android-emulaattori (Google APIs -image, system-store-varmenne) + mitmproxy, katsotaan mitä Tori-appi kutsuu myyjäprofiilinäkymässä. Aiempi yritys rootittomalla laitteella epäonnistui (käyttäjä-CA:han ei luoteta). Johtolanka: `TRUST-PROFILE-API /profile/{id}/ads` palautti **400 eikä 404** — polku on olemassa, parametrit olivat väärin. Podletin nimi `trust-public-profile-layout` viittaa samaan backendiin.
`signing.gw_key()` allekirjoittaa minkä tahansa polun, joten toteutus on triviaali heti kun polku + `finn-gw-service` tiedetään.

## Ympäristötiedot

- Koodi: `C:\Users\nmlus\Documents\asklepios\Claude\koodaus\torium` (git, fork `ahnl/tori-client`)
- Venv: `.venv\Scripts\python.exe`, asennettu editable-tilassa (`pip install -e .`)
- Testit: `.venv\Scripts\python.exe -m unittest tests.test_edit_flow -v` (ei verkkoa, mock-client)
- MCP-serveri: `torium-mcp` (stdio) tai HTTP-tila (docker-compose.yml); `build/lib/`-hakemisto on vanhentunut build-artefakti, ei käytössä
- Probe-JSONit (`_probe*.json`) ovat toukokuun 2026 withModel/adview-vastauksia — hyödyllisiä API-rakenteen tarkistukseen ilman live-kutsuja
