# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
map_nou_taxonomy.py

Maps all NOU records in `frontend/lib/nou_metadata_extra.json` to the 2-tier public administration taxonomy defined in `frontend/lib/taxonomy.json`.

Outputs updated `frontend/lib/nou_metadata_extra.json` in place with:
- primary_category (slug)
- subcategory (slug)
- tags (Norwegian display labels for primary & subcategory for backward compatibility)
"""

import json
import os
import re
import sqlite3
import sys

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TAXONOMY_PATH = os.path.join(PROJECT_ROOT, "frontend", "lib", "taxonomy.json")
METADATA_PATH = os.path.join(PROJECT_ROOT, "frontend", "lib", "nou_metadata_extra.json")
MARKDOWN_DIR = os.path.join(PROJECT_ROOT, "data", "markdown")
DB_PATHS = [
    os.path.join(PROJECT_ROOT, "data", "nou.db"),
    os.path.join(PROJECT_ROOT, "data", "nou_guru.db")
]

# Comprehensive Rule patterns mapping all 40 subcategory slugs -> list of keyword regex patterns
SUBCATEGORY_RULES = {
    # 1. Statsforvaltning & Demokrati
    "kommunesektor-lokaldemokrati": [
        r"\b(kommune|kommunal|kommunale|kommuner|kommunene|fylkeskommune|fylkeskommuner|fylkeskommunale|kommunestruktur|lokaldemokrati|sjølvstyre|selvstyre|interkommunalt|interkommunal|lokalsamfunn|skjønnsmidler|kommunelov|kommuneloven|bystyret|bystyre|byråd|bydeler|formannskap|ordfører|kommunesektor|kommuneøkonomi|kommunereform|fylkesmann|statsforvalter)\w*\b"
    ],
    "forvaltningsrett-offentlighet": [
        r"\b(forvaltningslov|forvaltningsloven|offentlegheit|offentlighet|offentleghetslov|offentlighetslov|offentleghetsloven|offentlighetsloven|saksbehandling|saksbehandlingsregler|klage|klageorgan|innsyn|forvaltninga|statsforvaltningen|taushetsplikt|forvaltningsrett|partsinnsyn|postjournal|revisjon|tilsynsmyndighet|revisor|revisjonstjeneste)\w*\b"
    ],
    "digitalisering-personvern-ki": [
        r"\b(digitalisering|digital|digitale|personvern|gdpr|personopplysning|personopplysninger|personopplysningslov|personopplysningsloven|kunstig intelligens|ki|ai|datainfrastruktur|datasikkerhet|cybersikkerhet|digital sårbarhet|skytenester|skytjenester|informasjonssikkerhet|elektronisk forvaltning|e-forvaltning|digitalisering i forvaltninga)\w*\b"
    ],
    "statsorganisering-etikk": [
        r"\b(departement|departementene|direktorat|direktorater|tilsyn|statsorganisering|etikk|etisk|etiske|korrupsjon|varsling|varsler|varslere|offentlig virksomhet|tilsynsorgan|granskingsutvalg|gransking|granskning|kommisjon|kommisjonen|kommisjonens|statlig eierskap|statlig eierandel|frittstående organer|selskapsorganisering)\w*\b"
    ],

    # 2. Helse & Omsorg
    "folkehelse-forebygging": [
        r"\b(folkehelse|smittevern|smittevernlov|forebygging|forebyggende|førebygging|tannhelse|tannlege|tannhelsetjeneste|ernæring|livsstil|vaksinasjon|vaksine|epidemi|pandemi|helseopplysning|tobakk|tobakkskadeloven|alkoholpolitikk|smittsomme|sykdommer|klorering|drikkevann|badedam|badevann|folkehelseinstituttet|fhi|helseførebygging)\w*\b"
    ],
    "spesialisthelseteneste": [
        r"\b(sykehus|sykehuset|sykehusene|sjukehus|sjukehuset|spesialisthelseteneste|spesialisthelsetjeneste|spesialisthelsetjenesteloven|helseforetak|helseforetakene|akuttmedisin|kirurgi|medisinsk utstyr|strålevern|sykehusbehandling|poliklinikk|elsikkerhet|nemko|organdonasjon|transplantasjon|sykehusstruktur)\w*\b"
    ],
    "omsorgstjenester-rehabilitering": [
        r"\b(eldreomsorg|elderomsorg|eldre|pleie|omsorg|omsorgstjenester|omsorgstenester|fastlege|fastlegen|fastlegeordning|fastlegeordningen|primærhelsetjeneste|primærhelseteneste|rehabilitering|hjemmesykepleie|funksjonshemma|funksjonshemmede|sykehjem|hjemmetjeneste|pleie- og omsorg|pårørende|brukerstyrt personlig assistanse|bpa|hjelpemidler|rehabiliteringstjenester)\w*\b"
    ],
    "psykisk-helse-rus": [
        r"\b(psykisk|psykiatri|psykisk helse|psykisk helsevern|psykisk helsevernlov|rus|rusomsorg|narkotika|alkohol|avhengighet|lavterskel|mental|selvmord|rusbehandling|psykiatrisk|lobotomi|gaustad|tvangsmedisinering|skjerming|rusreform|narkotikapolitikk)\w*\b"
    ],

    # 3. Arbeid, Velferd & Inkludering
    "arbeidsmarked-arbeidsrett": [
        r"\b(arbeidsmiljø|arbeidsmiljølov|arbeidsmiljøloven|arbeidsgiver|arbeidstaker|sysselsetting|sysselsetjing|lønnsdanning|lønnsdannelse|tariff|tariffavtale|trepartssamarbeid|arbeidsrett|permittering|permitteringer|arbeidsledighet|arbeidstid|arbeidsformidling|arbeidsleie|stillinger|kode|stilling|lønnsregulativ|streik|mekling|arbeidsavtale|arbeidstakere|arbeidsledige|bemanningsforetak)\w*\b"
    ],
    "pensjon-trygdeordninger": [
        r"\b(pensjon|pensjoner|folketrygd|folketrygden|uføretrygd|uførepensjon|uførepensjonister|sykelønn|sykelonn|sykepenger|nav|trygd|trygdeordninger|alderspensjon|pensjonskasse|afp|stønader|grunnbeløp|grunnbeløpet|pensjonist|fødselspenger|foreldrepenger|permisjon|barnetrygd|kontantstøtte|etterlattepensjon|uføre|uførhet|sykemelding|sykefravær)\w*\b"
    ],
    "inkludering-integrering": [
        r"\b(innvandring|asyl|flyktning|flyktninger|integrering|kvalifisering|språkopplæring|utlendingslov|utlendingsloven|oppholdstillatelse|asylsøker|introduksjonsordning|norskopplæring|bosetting|integreringslov|mottak|asylmottak)\w*\b"
    ],
    "likestilling-diskriminering": [
        r"\b(likestilling|diskriminering|diskrimineringsvern|kjønn|universell utforming|likelønn|kvinne|kvinner|rasisme|likestillingsombud|kvinnebevegelse|kjønnskvoteringsloven|trakassering|likestillingsloven|diskrimineringsloven)\w*\b"
    ],

    # 4. Kunnskap, Utdanning & Forskning
    "barnehage-oppvekst-grunnskole": [
        r"\b(barnehage|barnehagen|barnehager|oppvekst|grunnskole|grunnskolen|skole|skolen|skoler|elev|elever|læreplan|læreplanar|skolegang|skolemiljø|sfo|barneskole|ungdomsskole|skolestart|seksåringer|opplæringslov|opplæringsloven|tilpasset opplæring|tilpassa opplæring|spesialundervisning)\w*\b"
    ],
    "videregaende-yrkesfag": [
        r"\b(videregående|vidaregåande|yrkesfag|lærling|lærlinger|fagbrev|svennebrev|yrkesopplæring|lærlingordning|fagopplæring|yrkesfaglige|fagskole|yrkesfagene|lærlingplasser)\w*\b"
    ],
    "hoyere-utdanning-forskning": [
        r"\b(universitet|universiteter|høgskole|høgskoler|høyskole|høyskoler|forskning|forskningsråd|doktorgrad|student|studenter|lånekassen|studiefinansiering|akademisk|høgskolesektor|doktorgrader|stipend|forskningsfinansiering|vitenskapelig|forskere|forskningspolitikk)\w*\b"
    ],
    "kompetanse-livslang-laering": [
        r"\b(voksenopplæring|voksenopplæringsloven|etterutdanning|videreutdanning|kompetanse|realkompetanse|livslang|kompetansereform|etter- og videreutdanning|voksenrett|fagbrev på jobb|kompetanseutvikling|voksnes læring)\w*\b"
    ],

    # 5. Klima, Miljø & Naturressursar
    "klimapolitikk-omstilling": [
        r"\b(klima|klimagass|klimagasser|utslipp|utslippene|kvotehandel|grønt skifte|parisavtalen|klimamål|karbon|klimakrise|grønne skatter|klimatiltak|lavutslipp|klimaloven|klimakvoter|klimapolitikk)\w*\b"
    ],
    "naturmangfold-arealbruk": [
        r"\b(naturmangfold|naturmangfoldloven|artsvern|nasjonalpark|nasjonalparker|verneområder|areal|arealforvaltning|kystsone|jordvern|skogvern|biologisk mangfold|markagrensen|villrein|rovvilt|naturvern|naturreservat)\w*\b"
    ],
    "forurensning-avfall": [
        r"\b(forurensning|forureining|forurensningsloven|avfall|avfallshåndtering|gjenvinning|plast|miljøgifter|sirkulærøkonomi|støy|utslippskrav|avfallsbehandling|farlig avfall|kjemikalier|panteordning|kildesortering)\w*\b"
    ],
    "hav-vassdrag-ressursar": [
        r"\b(fiskeri|fiskerier|fisk|fiske|fiskeindustriens|fiskeflåten|fiskeriforvaltning|laks|lakseoppdrett|havbruk|oppdrett|sjømat|vassdrag|vassdraget|nedbørfelt|nedbørfeltet|havmiljø|marin|marine|vannforskriften|kyst|akvakultur|kvoter|kvotesystem|fiskerett|kvotemeldingen|saltvannsfiske|ferskvannsfiske|sjøressursloven)\w*\b"
    ],

    # 6. Justis, Rettssikkerhet & Samfunnssikkerhet
    "strafferett-kriminalomsorg": [
        r"\b(straff|strafferett|straffeloven|straffeprosess|straffeprosessloven|fengsel|kriminalomsorg|økokrim|voldtekt|sedelighet|promillegrense|straffeansvar|foretaksstraff|soning|vold|straffegjennomføring|kriminalomsorgen|bøter|bøtestraff|narkotikalovgivning|strafferettslig)\w*\b"
    ],
    "domstoler-sivilprosess-rettshjelp": [
        r"\b(domstol|domstolar|domstolene|domstolstruktur|tingretten|lagmannsretten|høyesterett|sivilprosess|tvistelov|tvisteloven|rettshjelp|fri rettshjelp|voldgift|namsmannen|forliksrådet|utlegg|dommer|rettspleie|domstolloven|rettsgebyr|anke|sakskostnader)\w*\b"
    ],
    "sivilrett-familie-barnevern": [
        r"\b(arvelov|arveloven|arv|arveavgift|barnelov|barneloven|barnevern|barnevernslov|barnevernsloven|fosterhjem|adopsjon|internasjonal adopsjon|ekkteskapslov|ekteskap|skifte|skiftelov|tingsrett|avtalerett|kjøpslov|forbruker|forbrukerkjøpslov|pant|panteloven|foreldreansvar|bidrag|bidragsfogd|familierett|sivilrett)\w*\b"
    ],
    "politi-samfunnssikkerhet-beredskap": [
        r"\b(politi|politiet|politidirektoratet|politistruktur|etterforskning|kriminalitet|kriminalitetsforebygging|kriminalitetsførebygging|politiloven|beredskap|krise|kriser|samfunnssikkerhet|sivilbeskyttelse|kritisk infrastruktur|digital sikkerhet|redning|redningstjeneste|sivilforsvar|totalforsvar|forsvar|forsvaret|verneplikt|nato)\w*\b"
    ],

    # 7. Finans, Skatt & Makroøkonomi
    "skatt-avgift-formue": [
        r"\b(skatt|skatter|skattelegging|beskatning|skattelov|skatteloven|avgift|avgifter|formueskatt|merverdiavgift|mva|selskapsbeskatning|grunnrente|grunnrenteskatt|skattesystem|skatteetaten|skatterett|formue|skatteutvalg|skatteregnskap|frådrag|fradrag|inntektsskatt|skattefradrag|eiendomsskatt|særavgifter|skatteplikt|skattemelding|skatteoppgjør|skatteparadiser|internasjonal beskatning)\w*\b"
    ],
    "fiskalpolitikk-oljefondet-statsbudsjett": [
        r"\b(statsbudsjett|statsbudsjettet|offentlige finanser|offentlege finansar|handlingsregelen|oljefondet|statens pensjonsfond|statens pensjonsfond utland|spu|norges bank|fiskalpolitikk|overføringer|statsbankene|tilskuddsordninger|statsrekneskapen|budsjettprosess|fiskal|budsjettpolitikken|statens utgifter|perspektivmeldingen|energiaksjer i spu)\w*\b"
    ],
    "finansmarked-bank-kreditt": [
        r"\b(finans|finansmarked|bank|bankene|bankvesen|finanstilsynet|aksje|verdipapir|kreditt|kredittvesen|forsikring|børs|revisjon|regnskap|kapitalkrav|finansinstitusjon|sparebank|investeringsforetak|børsvirksomhet|varederivater|verdipapirsentral|finansforetak|sikringsordninger|storebrand|skandia|egenkapitalbevis|gjeldsordning|skyldneren|kreditorene|konkurs|boet|kredittkort|boliglån|betalingssystemer|finansavtaleloven|investeringskontroll|investeringskontrollutvalget|utenlandsinvesteringer|kapitaltilgang|kapital|stiftelseslov|stiftelsesloven|stiftelser|kapitalforvaltning)\w*\b"
    ],
    "makrookonomi-konjunktur": [
        r"\b(makroøkonomi|rente|styringsrente|inflasjon|pengepolitikk|konjunktur|nasjonalregnskap|valutakurs|prisvekst|produktivitet|inntektsoppgjør|inntektsoppgjøret|kronemodell|prisstabilitet|økonomisk vekst|kapitalbevegelser|pris- og lønnsvekst)\w*\b"
    ],

    # 8. Næring, Energi & Distrikt
    "energisystem-fornybar": [
        r"\b(energi|kraft|vannkraft|vindkraft|kjernekraft|strøm|kraftnett|energiloven|nve|nettleie|elektrisitet|kraftsektor|energiforsyning|strømpris|effektbalanse|kraftmarked|kabler|nettutbygging|fornybar energi|enova)\w*\b"
    ],
    "petroleum-havnaringar": [
        r"\b(petroleum|olje|gass|offshore|maritim|leverandørindustri|offshore vind|kontinentalsokkelen|oljeutvinning|petroleumsloven|utvinning|gassrør|oljeboring|sokkelen|equinor|statoil)\w*\b"
    ],
    "offentlige-anskaffelser-konkurranse": [
        r"\b(offentlige anskaffelser|offentlege anskaffelsar|anskaffelseslov|anskaffelsesloven|anbud|anbudsregler|konkurranselov|konkurranseloven|konkurranserett|konkurransetilsynet|eøs-rett|statleg støtte|markedsregulering|anbudskonkurranse)\w*\b"
    ],
    "naring-innovasjon-landbruk": [
        r"\b(næring|næringsliv|innovasjon|virkemiddelapparat|innovasjon norge|gründer|reiseliv|reiselivsnæringen|patent|patentloven|bedrift|bedrifter|markedsføringsloven|håndverker|varemerkebeskyttelse|franchise|næringspolitikk|reiselivet|landbruk|landbruket|jordbruk|jordbruket|skogbruk|distrikt|distriktsstøtte|distriktsutvikling|matforsyning|jordbruksavtalen|bygdeutvikling|distriktspolitikk|matvare|odelsrett|jordlov|konsesjonslov)\w*\b"
    ],

    # 9. Transport, Kommunikasjon & Infrastruktur
    "vei-jernbane-kollektiv": [
        r"\b(vei|veg|vegvesenet|vegvesen|jernbane|tog|kollektiv|kollektivtransport|ntp|nasjonal transportplan|byvekstavtale|veitrafikk|samferdsel|veitrafikkloven|bompenger|jernbaneverket|vy|vegnett|jernbanenett|jernbaneloven)\w*\b"
    ],
    "luftfart-sjotrafikk": [
        r"\b(luftfart|fly|flyplass|avinor|sjøtransport|havn|havner|kystverket|maritime|båt|skipsfart|losvesen|skip|sjofart|skipssikkerhetsloven|flytrafikk|luftfartsloven)\w*\b"
    ],
    "ecom-digital-infrastruktur": [
        r"\b(ekom|bredbånd|5g|tele|telenor|post|postverket|postloven|sendinger|digital infrastruktur|mobilnett|frekvenser|telekom|ikt|telenettet|posttjenester|postgangen|postens|nkom)\w*\b"
    ],
    "byutvikling-bolig-infrastruktur": [
        r"\b(bolig|bustad|boligpolitikk|byutvikling|husbanken|knutepunkt|leieboer|borettslag|plan- og bygningslov|plan- og bygningsloven|husrom|husleie|husleielov|tomtefeste|eierseksjon|tilstandsrapport|bygningsmasse|boligbygging|leieboere|bofellesskap)\w*\b"
    ],

    # 10. Kultur, Medier & Fritid
    "kultur-kunst-kulturarv": [
        r"\b(kultur|kunst|kunstnere|kulturarv|museum|museer|scenekunst|teater|litteratur|språk|språkpolitikken|mållag|bibliotek|bibliotekene|folkebibliotek|kulturfond|norsk kulturråd|kulturminne|kulturminneloven|arkiv|arkiver|riksarkivet|arkivverket|nasjonalbiblioteket|kulturpolitikken|opphavsrett|åndsverkloven)\w*\b"
    ],
    "medier-ytringsfrihet-pressestotte": [
        r"\b(medier|media|presse|pressestøtte|nrk|kringkasting|avis|aviser|avisene|redaksjonell|ytringsfrihet|mediepolitikk|annonsering|medietilsynet|redaktøransvar|kringkastingsloven|mediefeltet|fagpresse|lokalaviser|ytringsfridom|nrk-plakat)\w*\b"
    ],
    "urfolksrett-samerett-kultur": [
        r"\b(sametinget|sameting|samiske|samer|samerett|reindrift|reindriftslov|reindriftsloven|finnmark|finnmarkslov|finnmarksloven|finnmarkskommisjonen|alta-saken|urfolk|urfolksrettigheter|samisk språk|samisk kultur)\w*\b"
    ],
    "frivillighet-trossamfunn": [
        r"\b(frivillighet|frivilligheit|idrett|friluftsliv|spillemidler|tippemidler|foreningsliv|idrettsanlegg|fritid|ungdomsorganisasjoner|norges idrettsforbund|idrettspolitikk|dugnad|frivillige organisasjoner|frivillig sektor|kirke|kirken|kirkens|kirkelige|sokn|trossamfunn|gravferd|gravplass|religion|trosfrihet|den norske kirke|livssyn|kirkelov|trossamfunnslov|tros- og livssynssamfunn)\w*\b"
    ]
}

# Mapping from legacy tags to primary category slug and default subcategory slug
LEGACY_TAG_MAPPING = {
    "Energi": ("naring-energi-distrikt", "energisystem-fornybar"),
    "Finans": ("finans-skatt-makrookonomi", "finansmarked-bank-kreditt"),
    "Helse": ("helse-omsorg", "spesialisthelseteneste"),
    "Lov og rett": ("justis-rettssikkerhet-samfunnssikkerhet", "strafferett-kriminalomsorg"),
    "Miljø": ("klima-miljo-naturressurser", "naturmangfold-arealbruk"),
    "Samfunnstryggleik": ("justis-rettssikkerhet-samfunnssikkerhet", "politi-samfunnssikkerhet-beredskap"),
    "Teknologi": ("statsforvaltning-demokrati", "digitalisering-personvern-ki"),
    "Utdanning": ("kunnskap-utdanning-forskning", "barnehage-oppvekst-grunnskole"),
    "Økonomi": ("finans-skatt-makrookonomi", "skatt-avgift-formue"),
    "Arbeidsliv": ("arbeid-velferd-inkludering", "arbeidsmarked-arbeidsrett"),
    "Kultur": ("kultur-medier-fritid", "kultur-kunst-kulturarv"),
    "Kommunesektor": ("statsforvaltning-demokrati", "kommunesektor-lokaldemokrati"),
    "Velferd": ("arbeid-velferd-inkludering", "pensjon-trygdeordninger")
}

def load_taxonomy():
    with open(TAXONOMY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    primary_map = {} # slug -> obj
    sub_to_primary = {} # sub_slug -> (primary_slug, sub_obj)
    
    for cat in data:
        primary_map[cat["id"]] = cat
        for sub in cat["subcategories"]:
            sub_to_primary[sub["id"]] = (cat["id"], sub)
            
    return data, primary_map, sub_to_primary

def load_extra_text_data():
    """Build a mapping nou_id -> {'title': title, 'summary': summary} for extra classification context."""
    nou_texts = {}
    
    # 1. Try loading title from frontend/lib/nou_catalog.json
    catalog_path = os.path.join(PROJECT_ROOT, "frontend", "lib", "nou_catalog.json")
    if os.path.exists(catalog_path):
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                catalog = json.load(f)
                for item in catalog:
                    nid = str(item.get("id"))
                    nou_texts[nid] = {"title": item.get("title", ""), "summary": ""}
        except Exception:
            pass

    # 2. Try SQLite databases if available for extra summary context
    for db_p in DB_PATHS:
        if os.path.exists(db_p):
            try:
                conn = sqlite3.connect(db_p)
                cur = conn.cursor()
                cur.execute("SELECT id, title, summary FROM nous")
                for row in cur.fetchall():
                    nid = str(row[0])
                    title = row[1] or nou_texts.get(nid, {}).get("title", "")
                    summary = row[2] or ""
                    nou_texts[nid] = {"title": title, "summary": summary}
                conn.close()
            except Exception:
                pass

    return nou_texts

def classify_nou(nou_id, nou_entry, nou_extra_info, sub_to_primary):
    """
    Determines best subcategory slug and primary category slug for an NOU entry using weighted field scoring.
    """
    keywords = nou_entry.get("keywords", [])
    legacy_tags = nou_entry.get("tags", [])
    
    title = nou_extra_info.get("title", "") if isinstance(nou_extra_info, dict) else str(nou_extra_info or "")
    summary = nou_extra_info.get("summary", "") if isinstance(nou_extra_info, dict) else ""
    
    title_lower = title.lower()
    keywords_str = " ".join(keywords).lower()
    summary_lower = summary.lower()
    full_text = title_lower + " " + keywords_str + " " + summary_lower

    sub_scores = {sub_id: 0.0 for sub_id in sub_to_primary.keys()}

    for sub_id, patterns in SUBCATEGORY_RULES.items():
        for pat in patterns:
            # 1. Title matches (Weight: 10.0 per term)
            t_matches = re.findall(pat, title_lower)
            sub_scores[sub_id] += len(t_matches) * 10.0
            
            # 2. Keywords matches (Weight: 4.0 per term)
            k_matches = re.findall(pat, keywords_str)
            sub_scores[sub_id] += len(k_matches) * 4.0

            # 3. Summary matches (Weight: 1.0 per term)
            s_matches = re.findall(pat, summary_lower)
            sub_scores[sub_id] += len(s_matches) * 1.0

    # Domain disambiguation rules
    # 1. Oljefondet / Sovereign Wealth Fund -> fiskalpolitikk-oljefondet-statsbudsjett (prevent pensjon collision)
    if re.search(r"\b(statens pensjonsfond utland|statens pensjonsfond norge|oljefondet|norges bank|handlingsregelen)\w*\b", full_text):
        sub_scores["fiskalpolitikk-oljefondet-statsbudsjett"] += 35.0
        sub_scores["pensjon-trygdeordninger"] = max(0.0, sub_scores["pensjon-trygdeordninger"] - 30.0)

    # 2. Civil Law / Family / Inheritance / Child Welfare -> sivilrett-familie-barnevern
    if re.search(r"\b(arvelov|arveloven|barnelov|barneloven|barnevern|barnevernslov|fosterhjem|adopsjon|ekteskapslov|tingsrett|avtalerett|kjøpslov|forbrukere?|forbrukerrett)\w*\b", title_lower + " " + keywords_str):
        sub_scores["sivilrett-familie-barnevern"] += 35.0

    # 3. Digitalization / Privacy / AI -> digitalisering-personvern-ki
    if re.search(r"\b(personvern|gdpr|kunstig intelligens|digital sårbarhet|det digitale|e-forvaltning|digitalisering)\w*\b", title_lower + " " + keywords_str):
        sub_scores["digitalisering-personvern-ki"] += 30.0

    # 4. Public Procurement & Competition Law -> offentlige-anskaffelser-konkurranse
    if re.search(r"\b(offentlige anskaffelser|offentlege anskaffelsar|anskaffelseslov|konkurranselov|konkurranseloven|konkurranserett)\w*\b", title_lower):
        sub_scores["offentlige-anskaffelser-konkurranse"] += 35.0

    # 5. Defense & Total Defense -> politi-samfunnssikkerhet-beredskap
    if re.search(r"\b(forsvar|forsvaret|forsvarets|militær|verneplikt)\w*\b", title_lower + " " + keywords_str) and \
       re.search(r"\b(arkiv|arkiver)\w*\b", title_lower + " " + keywords_str):
        sub_scores["politi-samfunnssikkerhet-beredskap"] += 25.0

    # 6. Disability Pension -> pensjon-trygdeordninger
    if re.search(r"\b(uførepensjon|uførepensjonister|uføretrygd)\w*\b", title_lower + " " + keywords_str):
        sub_scores["pensjon-trygdeordninger"] += 20.0

    # 7. Sami Rights / Indigenous Rights -> urfolksrett-samerett-kultur
    if re.search(r"\b(finnmark|samerett|sametinget|samiske|reindrift|urfolk)\w*\b", title_lower + " " + keywords_str):
        sub_scores["urfolksrett-samerett-kultur"] += 30.0

    # 8. Church & Religious Communities -> frivillighet-trossamfunn
    if re.search(r"\b(kirke|sokn|kirkelige|trossamfunn|trosfrihet)\w*\b", title_lower + " " + keywords_str):
        sub_scores["frivillighet-trossamfunn"] += 25.0

    # 9. Child abuse / Crime -> strafferett-kriminalomsorg
    if re.search(r"\b(overgrep|utuktig|barnemishandling|sedelighet|økokrim|voldtekt|straffelov)\w*\b", title_lower + " " + keywords_str):
        sub_scores["strafferett-kriminalomsorg"] += 25.0

    # 10. Fisheries & Marine Resources -> hav-vassdrag-ressursar
    if re.search(r"\b(fisk|fiskeri|fiskeindustriens|laks|akvakultur|havbruk)\w*\b", title_lower + " " + keywords_str):
        sub_scores["hav-vassdrag-ressursar"] += 20.0

    # 11. Agriculture -> naring-innovasjon-landbruk
    if re.search(r"\b(jordbruk|jordbruket|landbruk|landbruket|korn|odelsrett)\w*\b", title_lower + " " + keywords_str):
        sub_scores["naring-innovasjon-landbruk"] += 20.0

    # 12. Income Tax -> skatt-avgift-formue
    if re.search(r"\b(skatt|beskatning|formueskatt|merverdiavgift|mva|frådrag|skattelov)\w*\b", title_lower + " " + keywords_str):
        sub_scores["skatt-avgift-formue"] += 20.0

    # 13. Municipal governance -> kommunesektor-lokaldemokrati
    if re.search(r"\b(bystyret|byråd|kommunesektor|lokaldemokrati|kommunestruktur)\w*\b", title_lower + " " + keywords_str):
        sub_scores["kommunesektor-lokaldemokrati"] += 20.0

    best_sub = max(sub_scores.items(), key=lambda x: x[1])

    if best_sub[1] > 0:
        sub_slug = best_sub[0]
        primary_slug = sub_to_primary[sub_slug][0]
    else:
        # Fallback to legacy tag or default if zero matches
        fallback_found = False
        for tag in legacy_tags:
            if tag in LEGACY_TAG_MAPPING:
                primary_slug, sub_slug = LEGACY_TAG_MAPPING[tag]
                fallback_found = True
                break
        if not fallback_found:
            primary_slug = "statsforvaltning-demokrati"
            sub_slug = "statsorganisering-etikk"

    return primary_slug, sub_slug

def main():
    print("--- Starting NOU Taxonomy Mapping ---", flush=True)
    taxonomy, primary_map, sub_to_primary = load_taxonomy()
    print("Loaded Taxonomy: %d Primary Categories, %d Subcategories." % (len(primary_map), len(sub_to_primary)), flush=True)

    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    print("Loaded %d NOU metadata entries from %s." % (len(metadata), METADATA_PATH), flush=True)
    
    extra_texts = load_extra_text_data()
    print("Extracted extra text context for %d NOUs." % len(extra_texts), flush=True)

    # Collect all primary & subcategory Norwegian display names to clean up legacy tags
    all_category_names = set()
    for cat in taxonomy:
        all_category_names.add(cat["name"])
        for sub in cat["subcategories"]:
            all_category_names.add(sub["name"])

    mapped_count = 0
    primary_counts = {p: 0 for p in primary_map.keys()}
    subcategory_counts = {s: 0 for s in sub_to_primary.keys()}

    for nou_id, entry in metadata.items():
        extra_info = extra_texts.get(str(nou_id), {})
        p_slug, s_slug = classify_nou(nou_id, entry, extra_info, sub_to_primary)

        p_obj = primary_map[p_slug]
        s_obj = sub_to_primary[s_slug][1]

        entry["primary_category"] = p_slug
        entry["subcategory"] = s_slug

        # Maintain backward compatibility for `tags` field with display labels
        p_name = p_obj["name"]
        s_name = s_obj["name"]
        
        # Filter existing tags to remove former category display names, retaining true legacy tags
        existing_tags = entry.get("tags", [])
        legacy_tags_filtered = [t for t in existing_tags if t not in all_category_names]

        # Construct tags array: [p_name, s_name] + remaining legacy tags
        tags = [p_name, s_name]
        for t in legacy_tags_filtered:
            if t not in tags:
                tags.append(t)

        entry["tags"] = tags
        mapped_count += 1
        primary_counts[p_slug] += 1
        subcategory_counts[s_slug] += 1

    # Save updated metadata in place
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("Successfully mapped %d NOUs!" % mapped_count, flush=True)
    print("\nPrimary Category Breakdown:", flush=True)
    for p_slug, count in primary_counts.items():
        p_name = primary_map[p_slug]["name"]
        print("  [%s] %s: %d NOUs" % (p_slug, p_name, count), flush=True)

    print("\n--- Mapping Completed Successfully ---", flush=True)

if __name__ == "__main__":
    main()
