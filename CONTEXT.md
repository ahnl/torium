# CONTEXT.md — Kehityskonteksti (torium)

Fork projektista `ahnl/tori-client`. Tori.fi:n epävirallinen API-client (kirjasto + CLI + MCP-serveri), joka jäljittelee iOS-sovelluksen liikennettä (finn-gw-allekirjoitukset, apps-adinput-subdomain).

## Nykytila

- **Toimii:** haku, omat ilmoitukset, viestit, suosikit, create_listing (kuvineen), republish_listing, dispose/delete, **get_seller_listings (myyjän muut ilmoitukset — uusi 2026-08-11)**.
- **Uutta 2026-08-11 — "myyjän muut ilmoitukset" RATKAISTU:** kaapattiin natiivi gateway-endpoint (`/org/SEARCH_ID_BAP_COMMON?orgId=`, service `SEARCH-QUEST-RC`) Android-appista emulaattori+HTTP-Toolkitilla. Toteutus `seller_ads()` + MCP `get_seller_listings`, testit läpi. **Vielä live-vahvistamatta oikeaa APIa vasten** (unit-testit vihreät). Ks. Seuraavat askeleet + osio alempana.
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

### "Myyjän muut ilmoitukset" — RATKAISTU 2026-08-11 ✅

Tavoite: `get_seller_listings(ad_id)` → myyjän muut myynnissä olevat ilmoitukset. **Toteutettu portable MCP-työkaluna** (ei selainta, toimii myös mobiilissa).

**Endpoint (kaapattu Android-appista mitmproxy/HTTP-Toolkitilla, emulaattori API 33):**
```
GET /org/SEARCH_ID_BAP_COMMON?client=NMP-IOS&orgId={owner_id}&include_anonymous=false&page={n}
    host:            apps-gw-poc.svc.tori.fi   (sama kuin BASE_URL)
    finn-gw-service: SEARCH-QUEST-RC           (sama palvelu kuin päähaku!)
    EI x-client-id-otsaketta.  Vastaus: { "docs": [...], "metadata": { "paging": {param,current,last} } }
```
- `orgId` on **bitilleen sama kuin adview'n `meta.ownerId`** → olemassa oleva `owner()` syöttää suoraan.
- Vastaus on identtinen päähaun `docs`-muodon kanssa (`ad_id`, `heading`, `price.amount`, `location`, `canonical_url`, `image_urls`, `trade_type`, `extras`).
- Sivutus: `page`-parametri, loop kunnes `metadata.paging.last` saavutettu. Verna (451218839): 28 ilmoitusta, `last:1`.
- **Recon-oletus oli väärä:** ei TRUST-PROFILE-API + X-Client-Id, vaan hakuperheen `/org/{searchKey}?orgId=`.

**Toteutus:** `listings.seller_ads(owner_id, max_results=None)` (kirjasto) + MCP-työkalu `get_seller_listings(ad_id)` (owner→seller_ads→kompakti lista). Ei tarvinnut laajentaa `_request`ia (ei extra-headereita). Testit: `tests/test_seller_ads.py` (4 kpl, mock-client, ei verkkoa — läpi 2026-08-11).

**Vaiheet 0–2 (aiempi tutkinta, jää historiaksi):** `owner_id` saatavilla (`listings.owner()` + `get_listing`).

**Tiedustelun tulokset (Chrome, kirjautunut web-sessio, 2026-08-10):**
- `https://www.tori.fi/profile/ads?userId=X` **näyttää toisen myyjän ilmoitukset** — nimi, "Torin käyttäjä vuodesta", arvostelumäärä, välilehdet "Ilmoitukset (n)" / "Arvostelut (n)", ja kortit joissa hinta, ToriDiili-merkki, sijainti, päiväys ja linkki `/{adId}`.
- **JSON-endpointtia ei ole.** Sivun kaikki verkkopyynnöt luettiin (`performance.getEntriesByType('resource')`): ainoa `www.tori.fi`-XHR on `/profile/podium-resource/header/api` (yläpalkki). Ilmoituslista tulee täysin palvelinrenderöitynä podletista `trust-public-profile-layout`. Backend-kutsu tapahtuu Torin sisäverkossa — selain ei näe sitä.
- Sivu vaatii web-kirjautumisen (ulos kirjautuneena 302 → `/auth/login`).
- Kääntöpuoli: koska renderöinti on SSR, HTML on valmis heti — raapiminen on luotettavaa, ei hydraatio-odottelua.
- **Sivutusta ei ole vielä testattu** (testimyyjällä 1 ilmoitus). Selvitettävä ennen toteutusta.

**Vaihe 1 — SPiD-web-sessio headlessina: TUTKITTU JA UMPIKUJA (2026-08-10).**
Kokeiltu perusteellisesti. `auth.py`:n virta laajennettiin: refresh → access → `api/2/oauth/exchange` **`type=session`** (redirectUri-kentällä) palauttaa 64-merkkisen sessiokoodin. Webin login-sivu (`tori.fi/auth/login`) renderöi kaikki OIDC-parametrit palvelimella piilokenttiin: `spidClientId=650421cf50eeae31ecd2a2d3` (**sama kuin auth.py:n SPID_SERVER_CLIENT_ID**), `redirectUri=https://www.tori.fi/auth/loginCallback`, valmis `state` (base64-JSON + finnFlowId), `acrValues=otp-email`.
**Miksi kaatuu:** sessiokoodin lunastus (`login.vend.fi/session/{code}`) asettaa SPiD-identiteettievästeet, mutta **ei täyttä interaktiivista SSO-sessiota**. OAuth `authorize` näillä evästeillä pomppaa `authn/email-login`iin (OTP-sähköpostikirjautuminen), ei palauta hiljaisesti koodia. Lisäksi login-sivun uudelleenohjaus rakennetaan **client-side-JS:llä** (`login-redirect-identity-sdk`), joten `requests` ei koskaan pääse authorize-vaiheeseen. Verdikti: ei saavutettavissa headlessina ilman OTP-syöttöä.

**Natiivi gateway-endpoint (vaiheen 3 johtolanka) — OSITTAIN AUKI.**
- `TRUST-PROFILE-API /profile/{id}/ads` ilman `X-Client-Id`-otsaketta → 400 "No X-Client-Id header provided". **X-Client-Id-otsake (mikä tahansa ei-tyhjä arvo, esim. `tori`) läpäisee suodattimen.** Sen jälkeen reititys → 404: palvelu etuliittää polun `/public/`-osalla ja kaikki arvatut aliresurssit (`/ads`, `/listings`, `/items`, `/adverts`, `/reviews`, `/summary`, versioidut, URN-muoto) → 404. Jopa `/reviews` → 404 vaikka arvosteluja on. Eli joko väärä palvelunimi tai polkumuoto — hakuavaruus liian laaja arvattavaksi.
- **KUOLLUT:** `AD-SUMMARIES /search?ownerId=X` ohittaa parametrin — palauttaa AINA omat ilmoitukset (bearer-tokenista johdettu käyttäjä). Vahvistettu: neljä eri ownerId-arvoa → identtinen total=144.
- **KUOLLUT:** `SEARCH-QUEST-RC` seller_id/owner_id/user_id → 400 (tuntematon parametri).
- Ratkaisu vaatii todellisen sovellusliikenteen: **Android-emulaattori (Google APIs -image, `adb root` → system-store-varmenne) + mitmproxy**, katso mitä Tori-appi kutsuu myyjäprofiilinäkymässä. Rootiton laite ei toiminut (käyttäjä-CA:han ei luoteta). Kun polku + `finn-gw-service` (+ mahdollinen X-Client-Id-arvo) tiedetään, `signing.gw_key()` allekirjoittaa sen ja toteutus on triviaali.

**Vaihe 2 — SELAINADAPTERI: suositeltu toteutusreitti.**
Ilmoituslista on **täysin SSR** (podlet `trust-public-profile-layout`); ainoa client-XHR on `/profile/podium-resource/header/api` (yläpalkki) — cookie-autentikoitua JSON-endpointtia EI ole. Skill joka avaa `tori.fi/profile/ads?userId={owner_id}` Claude-in-Chromessa (kirjautunut sessio) ja lukee kortit accessibility-puusta: hinta, ToriDiili, sijainti, päiväys, linkki `/{adId}`. Todennettu toimivaksi 2026-08-10. Torium antaa `owner_id`:n (`get_listing`), jokainen kortti-adId voidaan rikastaa `get_listing`illä. Sama kuvio kuin `vinted-era`-skillissä.
- **Sivutus (todennettu 2026-08-10, myyjä 451218839 "Verna", 28 aktiivista):** kaikki 28 korttia renderöityvät kerralla DOM:iin, ei "näytä lisää" -nappia eikä ääretöntä vieritystä (vieritys pohjaan ei kasvattanut määrää), ei `?page=`-parametria. Profiili näyttää siis kaikki aktiiviset ilmoitukset yhdellä sivulla. Kortin kentät: sijainti, päiväys ("Tänään"/pvm), otsikko, hinta, ToriDiili-merkki, linkki `/{adId}`. **Vielä auki:** käyttäytyminen 50+ ilmoituksella (suurin testattu 28) — mekanismi (täysi SSR-render) viittaa siihen ettei client-sivutusta ole, mutta palvelin voi silti katkaista jossain rajassa.
- **Re-verifiointi ja verkkotason näyttö (2026-08-11, sama myyjä Verna):**
  - `performance.getEntriesByType('resource')` (71 resurssia): ainoa tori.fi-client-XHR on `/profile/podium-resource/header/api`, ja se kuuluu **yläpalkin** `<topbar-data-service api-url=...>` -web-komponentille — EI ilmoituslistalle. Ilmoituslistalle ei ole omaa client-endpointtia edes 28 ilmoituksella. Vahvistaa: cookie-autentikoitua JSON-endpointtia ei ole, vain SSR-HTML raaputettavaksi.
  - **Sivun HTML ei paljasta gatewaysta mitään:** haku `client-id` / `x-client-id` / `TRUST-PROFILE` / `apps-gw` / `svc.tori` / `podlet` → kaikki `null`. Web-taso proxyttaa upstream-gateway-kutsun palvelinpuolella, joten **selaintarkastelu ei voi tuottaa portable-endpointin polkua/X-Client-Id-arvoa.** → Vaiheen 3 mobiilikaappaus on ainoa reitti natiiviin MCP-työkaluun.
  - **DOM-scrape vankka 28 kortilla:** 28 korttia, jokainen adId `/{adId}`-linkistä (regex `/(\d{6,})`) + otsikko linkin tekstistä. Rikastus `get_listing`illä toimii kortti kerrallaan. Selain-fallback on siis valmis skilliksi jo nyt.

## Ympäristötiedot

- Koodi: `C:\Users\nmlus\Documents\asklepios\Claude\koodaus\torium` (git, fork `ahnl/tori-client`)
- Venv: `.venv\Scripts\python.exe`, asennettu editable-tilassa (`pip install -e .`)
- Testit: `.venv\Scripts\python.exe -m unittest tests.test_edit_flow -v` (ei verkkoa, mock-client)
- MCP-serveri: `torium-mcp` (stdio) tai HTTP-tila (docker-compose.yml); `build/lib/`-hakemisto on vanhentunut build-artefakti, ei käytössä
- Probe-JSONit (`_probe*.json`) ovat toukokuun 2026 withModel/adview-vastauksia — hyödyllisiä API-rakenteen tarkistukseen ilman live-kutsuja
