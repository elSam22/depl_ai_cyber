"""Prétraitement partagé entre l'entraînement (notebooks) et l'API.

UNE SEULE source de vérité : les notebooks ET l'API importent ce module, pour que le
modèle reçoive en production exactement le même type de texte qu'à l'entraînement.

    texte brut -> anonymize() -> clean_text() -> texte prêt pour le modèle

Code repris tel quel de notebooks/anonyme_2.ipynb et notebooks/clean_text.ipynb (commit 9ec6901).
Toute modification impose d'incrémenter PREPROCESSING_VERSION, de relancer anonymisation +
nettoyage + entraînement, puis de redéployer l'API.
"""
import ipaddress
import re

import spacy

PREPROCESSING_VERSION = "1.0"

# Balises de remplacement : UN SEUL endroit à modifier (pas de balise pour les lieux : ils ne sont plus masqués)
BALISES = {"PERSONNE": "personne_tag", "ORGANISATION": "organisation_tag", "EMAIL": "email_tag", "URL": "url_tag", "IP": "ip_tag", "TELEPHONE": "telephone_tag", "PSEUDO": "pseudo_tag", "ADRESSE": "adresse_tag"}

# Un span = (début, fin, étiquette) en indices de caractères du texte ORIGINAL
Span = tuple[int, int, str]


# =============================================================================
# 1. REGEX (notebooks/anonyme_2.ipynb, cellule « REGEX »)
# =============================================================================
# --- Motifs regex (compilés une seule fois) ---
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_URL = re.compile(r"(?:https?://|ftp://|www\.)[^\s<>\"')\]]+", re.IGNORECASE)
# Candidats IPv4 / IPv6 : on valide ensuite avec le module ipaddress (évite 999.1.1.1, "21:51", etc.)
# IPv4 : peut suivre un point ("now.89.205.38.27") ; on exclut seulement les suites plus longues ("1.2.3.4.5") et les chiffres collés
RE_IPV4 = re.compile(r"(?<!\d)(?<!\d\.)(?:\d{1,3}\.){3}\d{1,3}(?!\d)(?!\.\d)")
RE_IPV6 = re.compile(r"(?<![\w:.])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")
# Téléphone FR (0X XX XX XX XX, +33 X ..., 0033 ...) et international (+CC ...)
RE_TEL_FR = re.compile(r"(?<![\w+])(?:(?:\+|00)33[\s.-]?\(?0?\)?|0)[1-9](?:[\s.-]?\d{2}){4}(?!\d)")
RE_TEL_INTL = re.compile(r"(?<![\w+])\+\d{1,3}[\s.-]?\(?\d{1,4}\)?(?:[\s.-]?\d{2,4}){2,4}(?!\d)")
# Pseudos : @pseudo, "User:Pseudo", "User talk:Pseudo" (on ne masque que le pseudo, pas le préfixe)
RE_AROBASE = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{2,30})")
RE_USER = re.compile(r"\buser(?:[ _]talk)?:\s?([^\s\]|/#<>\[\"]+)", re.IGNORECASE)
# Adresses précises (rue + numéro, code postal) -> [ADRESSE]. On ne masque jamais une simple ville ou un pays.
# Motifs volontairement prudents (précision avant rappel) : un faux positif coûte du texte utile.
_TYPES_RUE_FR = r"(?i:rue|avenue|av\.?|boulevard|bd|chemin|impasse|allée|allee|place|route|quai|cours|square|passage)"
_NOM_RUE_FR = r"(?:(?:de|du|des|la|le|les|d'|l')\s*)*[A-ZÀ-Ý][\w'’-]*(?:[ ]+(?:(?:de|du|des|la|le|les)[ ]+)*[A-ZÀ-Ý][\w'’-]*){0,3}"
# "12 rue de la Paix" (éventuellement suivi de ", 75002 Paris" sur la même ligne)
RE_ADRESSE_FR = re.compile(r"\b\d{1,4}(?:[ ]?(?:bis|ter))?,?[ ]+" + _TYPES_RUE_FR + r"[ ]+" + _NOM_RUE_FR
                           + r"(?:,?[ ]+(?:0[1-9]|[1-8]\d|9[0-5])\d{3}[ ]+[A-ZÀ-Ý][\w'’-]+)?")
# "221 Baker Street" : nom de rue en majuscule initiale ; types ambigus exclus (Way, Place, Court, Dr = Doctor...)
RE_ADRESSE_EN = re.compile(r"\b(\d{1,4})[ ]+((?:[A-Z][\w'.-]*[ ]+){1,3})"
                           r"(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Drive|Boulevard|Blvd)\b")
# Mots qui, avant "Drive", désignent une campagne Wikipédia et non une rue ("2007 Assessment Drive")
MOTS_CAMPAGNE = {"improvement", "assessment", "cleanup", "clean", "membership", "fund", "funding", "donation",
                 "editing", "fundraising", "photo", "recruitment", "backlog", "review", "outreach", "image",
                 "article", "wikipedia", "wiki", "content", "quality", "test", "reference", "citation",
                 "translation", "merge", "stub", "redirect", "the", "annual"}
# Codes postaux : Royaume-Uni "SW1A 1AA" et États-Unis "NY 10001" (sigle d'État valide uniquement).
# Le code postal français seul n'est PAS masqué (trop de faux positifs : "20006 Annual", "50000 People").
RE_CP_UK = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?[ ]\d([A-Z]{2})\b")   # l'espace est obligatoire ("N00BS", "D0D4FF" ne sont pas des codes postaux)
RE_CP_US = re.compile(r"\b(?:AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)[ ]\d{5}(?:-\d{4})?\b")
UNITES = {"GB", "MB", "KB", "TB", "MG", "KG", "HZ", "GH", "ML", "CM", "MM"}   # "MP3 4GB" n'est pas un code postal


def _adresse_en_valide(m) -> bool:
    """Écarte les années ("2012 MTC Drive") et les campagnes Wikipédia ("2007 Assessment Drive")."""
    if 1900 <= int(m.group(1)) <= 2035:
        return False
    mots = {w.strip(".-'").lower() for w in m.group(2).split()}
    return not (mots & MOTS_CAMPAGNE)


def _chiffres(s):
    return sum(ch.isdigit() for ch in s)


def find_regex_spans(text: str) -> list[Span]:
    """Retourne les spans (début, fin, étiquette) détectés par regex.

    Étiquettes : EMAIL, URL, IP, TELEPHONE, PSEUDO, ADRESSE.
    Les spans peuvent se chevaucher entre motifs ; la fusion est faite dans anonymize_A.
    """
    spans: list[Span] = []

    for m in RE_EMAIL.finditer(text):
        spans.append((m.start(), m.end(), "EMAIL"))

    for m in RE_URL.finditer(text):
        # on retire la ponctuation finale collée à l'URL ("... http://x.com.")
        fin = m.end()
        while fin > m.start() and text[fin - 1] in ".,;:!?":
            fin -= 1
        spans.append((m.start(), fin, "URL"))

    for m in RE_IPV4.finditer(text):
        try:
            ipaddress.IPv4Address(m.group())
            spans.append((m.start(), m.end(), "IP"))
        except ValueError:
            pass

    for m in RE_IPV6.finditer(text):
        brut = m.group()
        # exige "::" ou une adresse complète (7 ":") pour ne pas prendre des heures "21:51",
        # et au moins un chiffre hexadécimal ("::" seul n'est pas une adresse utile)
        if ("::" not in brut and brut.count(":") != 7) or not re.search(r"[0-9A-Fa-f]", brut):
            continue
        try:
            ipaddress.IPv6Address(brut)
            spans.append((m.start(), m.end(), "IP"))
        except ValueError:
            pass

    for motif in (RE_TEL_FR, RE_TEL_INTL):
        for m in motif.finditer(text):
            if 9 <= _chiffres(m.group()) <= 15:   # filtre les suites de chiffres trop courtes/longues
                spans.append((m.start(), m.end(), "TELEPHONE"))

    for motif in (RE_AROBASE, RE_USER):
        for m in motif.finditer(text):
            # on retire la ponctuation finale collée au pseudo ("User:Physicq210," -> "Physicq210")
            fin = m.end(1)
            while fin > m.start(1) and text[fin - 1] in ".,;:!?)'":
                fin -= 1
            if fin > m.start(1):
                spans.append((m.start(1), fin, "PSEUDO"))

    for m in RE_ADRESSE_FR.finditer(text):
        spans.append((m.start(), m.end(), "ADRESSE"))
    for m in RE_ADRESSE_EN.finditer(text):
        if _adresse_en_valide(m):
            spans.append((m.start(), m.end(), "ADRESSE"))
    for m in RE_CP_UK.finditer(text):
        if m.group(1) not in UNITES:
            spans.append((m.start(), m.end(), "ADRESSE"))
    for m in RE_CP_US.finditer(text):
        spans.append((m.start(), m.end(), "ADRESSE"))

    return spans

# =============================================================================
# 2. NER spaCy + filtres (notebooks/anonyme_2.ipynb, cellule « Spacy »)
# =============================================================================
# Modèle spaCy : on désactive ce dont le NER n'a pas besoin (plus rapide)
# Chargé UNE fois à l'import du module (au démarrage de l'API)
nlp = spacy.load("en_core_web_sm", disable=["tagger", "parser", "attribute_ruler", "lemmatizer"])

# Étiquette spaCy -> étiquette de remplacement.
# NORP (groupes) et GPE / LOC (villes, pays, continents) volontairement absents : on ne les masque pas.
NER_VERS_ETIQUETTE = {"PERSON": "PERSONNE", "ORG": "ORGANISATION"}


# --- Listes de filtrage : entités que spaCy détecte mais qu'on NE masque PAS ---
# Mots toxiques : c'est le signal à classer (mots entiers + racines sûres ; "dick"/"cock" restent des prénoms/noms possibles)
MOTS_TOXIQUES = {
    "moron", "morons", "idiot", "idiots", "stupid", "dumb", "dumbass", "retard", "retarded", "loser", "losers",
    "jerk", "scum", "trash", "garbage", "pig", "pigs", "dog", "dogs", "freak", "creep", "pervert", "coward",
    "ass", "arse", "asses", "bastard", "bastards", "bitch", "bitches", "slut", "sluts", "whore", "whores",
    "faggot", "faggots", "fag", "fags", "gay", "homo", "queer", "nigger", "niggers", "nigga", "niggas",
    "cunt", "cunts", "twat", "wanker", "tosser", "prick", "dick", "dicks", "cock", "cocks", "pussy", "penis",
    "vagina", "boob", "boobs", "tits", "fuck", "fucker", "fuckers", "fucking", "fucked", "shit", "shits",
    "crap", "piss", "damn", "hell", "suck", "sucks", "sucker", "douche", "douchebag", "scumbag", "dumbfuck",
    "butthead", "nazi", "nazis", "die", "kill", "killed", "murder", "rape", "raped", "terrorist", "terrorists", "rapist", "pedophile", "paedophile", "lunatic", "psycho",
}
RACINES_TOXIQUES = ("fuck", "shit", "bitch", "faggot", "nigg", "cunt", "asshole", "retard", "motherfuck",
                    "bastard", "whore", "slut", "douche")

# Jargon Wikipédia : sigles et noms de projet, pas des organisations
JARGON_WIKI = {"wikipedia", "wiki", "wikiproject", "wikimedia", "wikia", "wikidata", "wikitionary", "wikipedians",
               "utc", "pov", "npov", "blp", "lol", "arbcom", "ani", "afd", "rfc", "rfa", "rfar", "fac", "fa", "ga",
               "gan", "wp", "cfd", "csd", "afc", "mos", "nor", "rs", "dyk", "itn", "otd", "tfd", "mfd", "rfd",
               "vfd", "an", "ip", "ips", "ok", "faq", "tbh", "imo", "imho", "lmao", "wtf", "omg", "wp", "gfdl"}

# Personnalités publiques et figures historiques / religieuses : pas des données personnelles de commentateurs
PERSONNALITES_PUBLIQUES = {
    "hitler", "stalin", "lenin", "mao", "castro", "mussolini", "napoleon", "churchill", "lincoln", "jefferson",
    "washington", "obama", "bush", "clinton", "trump", "romney", "reagan", "nixon", "kennedy", "putin", "merkel",
    "sarkozy", "assad", "saddam", "hussein", "osama", "laden", "gandhi", "darwin", "einstein", "newton",
    "jesus", "christ", "muhammad", "mohammed", "mohammad", "allah", "buddha", "moses", "abraham", "marx",
    "obama's", "bush's", "hitler's", "clinton's", "trump's", "jimbo", "wales",
}
# Mots courants que le NER prend parfois pour des personnes / organisations
MOTS_COURANTS = {"hi", "hello", "hey", "thanks", "thank", "dear", "please", "yes", "no", "yeah", "wow", "ok",
                 "sir", "mr", "mrs", "ms", "dr", "lol", "haha", "hahaha", "bye", "welcome", "regards",
                 "admin", "admins", "article", "articles", "cheers", "fyi", "contribs", "media", "islam", "fire",
                 "church", "lifetime", "irc", "talk", "page", "pages", "user", "users", "editor", "editors"}


def _mots(texte: str) -> list[str]:
    """Mots en minuscules d'un texte, sans ponctuation (utilisé pour comparer aux listes ci-dessus)."""
    return re.findall(r"[a-z0-9']+", texte.lower())


def _est_toxique(mot: str) -> bool:
    """Vrai si le mot (en minuscules) est une insulte / un gros mot."""
    return mot in MOTS_TOXIQUES or mot.startswith(RACINES_TOXIQUES)


def _morceaux_sans_insulte(texte: str, debut: int):
    """Découpe une entité autour de ses mots toxiques : "Stupid Fucking Bob" -> [(position de "Bob")].

    Renvoie les morceaux (début, fin) en indices du texte original qui ne contiennent aucun mot toxique.
    Un mot toxique collé à de la ponctuation ("faggot!!!!") est reconnu aussi.
    """
    morceaux, courant = [], None
    for m in re.finditer(r"\S+", texte):
        mots = _mots(m.group())
        if any(_est_toxique(w) for w in mots):     # mot toxique : on ferme le morceau en cours
            if courant:
                morceaux.append(courant)
            courant = None
        elif courant is None:
            courant = [debut + m.start(), debut + m.end()]
        else:
            courant[1] = debut + m.end()
    if courant:
        morceaux.append(courant)
    return [tuple(x) for x in morceaux]


def _ressemble_a_un_nom(texte: str) -> bool:
    """Au moins un mot avec une majuscule initiale et le reste en minuscules ("Bob", "Smith") : pas "DIE", pas "you"."""
    return any(w[:1].isupper() and not w.isupper() for w in re.findall(r"[^\W\d_]+", texte))


def _a_ignorer(texte: str, type_spacy: str) -> bool:
    """Vrai si l'entité détectée ne doit pas être masquée (mot toxique, jargon, personnalité publique, mot courant)."""
    mots = _mots(texte)
    if not mots:
        return True
    # 1. sécurité : un mot toxique ne doit jamais être masqué (les insultes sont retirées avant, dans find_ner_spans)
    if any(_est_toxique(m) for m in mots):
        return True
    # 2. un mot courant, ou un seul mot tout en minuscules (très probablement une erreur du NER : "hi", "moron")
    if all(m in MOTS_COURANTS for m in mots) or (len(mots) == 1 and texte.strip().islower()):
        return True
    # 3. jargon Wikipédia (PERSON comme ORG) : "Wiki", "Wikipedia", "UTC", "POV", "Wikipedia:Questions"...
    if any(m in JARGON_WIKI or m.startswith("wiki") for m in mots) and (
            type_spacy == "ORG" or all(m in JARGON_WIKI or m.startswith("wiki") for m in mots)):
        return True
    # 4. personnalité publique (PERSON ou ORG : "Mitt Romney", "George W. Bush", "Jesus", "pro-Assad")
    if any(m in PERSONNALITES_PUBLIQUES for m in mots):
        return True
    # 5. code couleur hexadécimal pris pour un nom ("ffffff")
    if len(mots) == 1 and re.fullmatch(r"[0-9a-f]{6}", mots[0]):
        return True
    return False


def find_ner_spans(doc) -> list[Span]:
    """Retourne les spans (début, fin, étiquette) des entités PERSON et ORG d'un Doc spaCy.

    - les ORG de moins de 3 caractères sont ignorées (souvent du bruit : "FA", "UN"...)
    - NORP, GPE, LOC ne sont jamais masqués
    - les mots toxiques sont retirés de l'entité (seul le reste est masqué : "Stupid Bob" -> "Stupid [PERSONNE]")
    - le jargon Wikipédia, les personnalités publiques et les mots courants sont ignorés (voir _a_ignorer)
    """
    spans: list[Span] = []
    for ent in doc.ents:
        etiquette = NER_VERS_ETIQUETTE.get(ent.label_)
        if etiquette is None:
            continue
        # on retire les mots toxiques de l'entité : "dick faggot" -> rien, "Stupid Bob" -> "Bob"
        avait_insulte = any(_est_toxique(w) for w in _mots(ent.text))
        for d, f in _morceaux_sans_insulte(ent.text, ent.start_char):
            morceau = doc.text[d:f]
            # reste d'une entité insultante : masqué seulement s'il ressemble à un nom ("DIE FAG DIE" -> rien)
            if avait_insulte and not _ressemble_a_un_nom(morceau):
                continue
            if ent.label_ == "ORG" and len(morceau.strip()) < 3:
                continue
            if _a_ignorer(morceau, ent.label_):
                continue
            spans.append((d, f, etiquette))
    return spans

# =============================================================================
# 3. Fusion et remplacement (notebooks/anonyme_2.ipynb, cellule « Fusion »)
# =============================================================================
def fusionner_spans(spans_regex: list[Span], spans_ner: list[Span]) -> list[Span]:
    """Fusionne regex + NER sans chevauchement. Le regex est prioritaire sur le NER.

    À priorité égale, on garde le span le plus long, puis le plus tôt dans le texte.
    """
    candidats = [(0, s) for s in spans_regex] + [(1, s) for s in spans_ner]
    candidats.sort(key=lambda c: (c[0], -(c[1][1] - c[1][0]), c[1][0]))
    retenus: list[Span] = []
    for _, (d, f, e) in candidats:
        if all(f <= d2 or d >= f2 for d2, f2, _ in retenus):   # aucun chevauchement
            retenus.append((d, f, e))
    return sorted(retenus)


def appliquer_spans(text: str, spans: list[Span]) -> str:
    """Remplace chaque span par sa balise (voir BALISES) en un seul passage sur le texte original."""
    morceaux, curseur = [], 0
    for d, f, e in spans:
        morceaux.append(text[curseur:d])
        morceaux.append(BALISES[e])
        curseur = f
    morceaux.append(text[curseur:])
    return "".join(morceaux)


def anonymize_many(texts: list[str], batch_size: int = 256) -> list[str]:
    """Anonymise une liste de textes (regex + NER spaCy), par lots. Remplace anonymize_A des notebooks."""
    texts = ["" if t is None else str(t) for t in texts]
    return [appliquer_spans(t, fusionner_spans(find_regex_spans(t), find_ner_spans(doc)))
            for t, doc in zip(texts, nlp.pipe(texts, batch_size=batch_size))]


def anonymize(text: str) -> str:
    """Anonymise un seul texte : usage API."""
    return anonymize_many([text])[0]


# =============================================================================
# 4. Nettoyage (notebooks/clean_text.ipynb)
# =============================================================================
# Emojis et pictogrammes (plages Unicode courantes : symboles, dingbats, drapeaux, émojis récents)
RE_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF"   # émojis, pictogrammes, drapeaux
    "\U00002600-\U000027BF"    # symboles divers et dingbats
    "\U00002B00-\U00002BFF"    # flèches et symboles divers
    "\u200d\ufe0f]+",          # liant d'émojis et sélecteur de variation
    flags=re.UNICODE)


def clean_text(text: str) -> str:
    """Nettoie un commentaire déjà anonymisé."""
    text = text.lower()                          # 1. minuscules
    text = RE_EMOJI.sub(" ", text)               # 2. retire les emojis
    text = re.sub(r"[^\w\s]", " ", text)         # 3. retire la ponctuation ("_" conservé -> balises intactes)
    return re.sub(r"\s+", " ", text).strip()     # 4. espaces multiples et retours à la ligne -> un espace


def preprocess(text: str) -> str:
    """Chaîne complète appliquée à chaque requête de l'API : anonymisation puis nettoyage."""
    return clean_text(anonymize(text))
