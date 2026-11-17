"""Protection de l'API en entrée (couche « application »).

Leçons de l'attaque du 16 novembre 2026 (supervision/INCIDENTS.md) et du bilan de la promotion : la plupart des API ont
été mises à genoux par un simple flot de requêtes, ou ont laissé extraire leur modèle à 2 000 requêtes par minute.
Ce module, placé AVANT l'authentification et le modèle, refuse vite et à peu de frais :

- limite par adresse IP, toutes routes (429) ;
- débit lissé par adresse IP sur /score, la route qui coûte du calcul : rafale de 10 puis 1 par seconde (429),
  un texte long coûtant plus de jetons qu'un court (1 par tranche de 500 octets) ;
- sanction progressive d'une adresse qui insiste après ses refus : bloquée 30 s, 60 s, 120 s... jusqu'à 15 min (429) ;
- blocage temporaire d'une adresse qui présente trop de clés fausses (429) : brute-force de la clé ;
- corps de requête plafonné (413) ;
- en-têtes de sécurité sur toutes les réponses.

L'adresse du client vient de X-Forwarded-For : le load balancer Google ajoute l'adresse réelle du client puis la sienne,
donc l'avant-dernière valeur est fiable ; les valeurs plus à gauche peuvent être inventées par le client.
Les limites sont PAR POD (mémoire locale) : avec N pods derrière le load balancer, la limite réelle est environ N fois
plus haute. Une limite globale demanderait Cloud Armor, refusé par le quota du projet (voir livrables/TP2_LIVRABLE.md, § 4.3).
RGPD : une adresse IP est une donnée personnelle. Les journaux ne la contiennent jamais en clair : seulement une
empreinte HMAC (clé secrète), stable d'un pod à l'autre, qui permet de reconnaître un client sans le nommer.
"""
import hashlib
import hmac
import json
import logging
import os
import time

from prometheus_client import Counter

from limiteur_debit import LimiteurDebit, Sanctions, SeauJetons

log = logging.getLogger("dss.protection")

REFUS = Counter("dss_refus", "Requêtes refusées par la protection de l'API", ["motif"])


def _entier(nom: str, defaut: int) -> int:
    return int(os.environ.get(nom, defaut))


# Valeurs par défaut choisies d'après les mesures de l'étape 5 (≈ 4 requêtes/s de calcul par pod) et le bilan de
# l'attaque (191 à 225 requêtes/s sur /docs). Réglables par variable d'environnement sans reconstruire l'image.
LIMITE_IP_PAR_MIN = _entier("LIMITE_IP_PAR_MIN", 300)        # toutes routes, par IP et par pod
LIMITE_SCORE_PAR_MIN = _entier("LIMITE_SCORE_PAR_MIN", 60)   # /score, par IP et par pod : débit moyen du seau
RAFALE_SCORE = _entier("RAFALE_SCORE", 10)                    # /score : requêtes permises d'un coup
# Coût d'une requête /score en jetons : 1 + 1 par tranche de OCTETS_PAR_JETON octets. Un texte long coûte bien plus
# de calcul (mesuré sur le pod : ~0,1 s pour un texte court, 5 à 7 s pour 5 000 caractères avec la défense
# anti-noyage) : sans cela, un seul client enverrait des textes longs à 1/s et occuperait tout le service.
OCTETS_PAR_JETON = _entier("OCTETS_PAR_JETON", 500)
LIMITE_ECHECS_PAR_MIN = _entier("LIMITE_ECHECS_PAR_MIN", 10)  # clés fausses, par IP et par pod
MAX_OCTETS = _entier("MAX_BODY_BYTES", 40_000)                # 5 000 caractères accentués = 10 Ko ; marge pour le JSON

EN_TETES_SECURITE = [
    (b"x-content-type-options", b"nosniff"),
    (b"cache-control", b"no-store"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
]


def ip_client(scope) -> str:
    """Adresse du client : avant-dernière valeur de X-Forwarded-For (ajoutée par le load balancer Google)."""
    valeur = dict(scope["headers"]).get(b"x-forwarded-for", b"").decode("latin-1")
    parties = [p.strip() for p in valeur.split(",") if p.strip()]
    if len(parties) >= 2:
        return parties[-2]
    if scope.get("client"):
        return scope["client"][0]
    return parties[0] if parties else "inconnue"


def empreinte(ip: str) -> str:
    """Pseudonyme d'une adresse IP pour les journaux (HMAC, non réversible sans la clé du serveur)."""
    cle = (os.environ.get("API_KEY") or "dev").encode()
    return hmac.new(cle, ip.encode(), hashlib.sha256).hexdigest()[:10]


# (motif, client) -> (instant de la dernière ligne écrite, nombre de refus passés sous silence depuis)
_dernier_journal: dict[tuple[str, str], tuple[float, int]] = {}


def journaliser_refus(motif: str, route: str, ip: str) -> None:
    """Compte chaque refus (métrique) mais n'écrit qu'une ligne par minute et par client et motif : sous 200 requêtes/s,
    une ligne par refus saturerait le CPU du pod et la facture de journalisation."""
    REFUS.labels(motif).inc()
    cle = (motif, empreinte(ip))
    maintenant = time.monotonic()
    if len(_dernier_journal) > 5000:      # garde-fou mémoire : beaucoup d'adresses différentes ne doivent pas la remplir
        _dernier_journal.clear()
    dernier, ignores = _dernier_journal.get(cle, (0.0, 0))
    if maintenant - dernier < 60:
        _dernier_journal[cle] = (dernier, ignores + 1)
        return
    _dernier_journal[cle] = (maintenant, 0)
    log.warning("refus motif=%s route=%s client=%s (+%d refus similaires depuis la dernière ligne)",
                motif, route, cle[1], ignores)


class _TropGros(Exception):
    """Levée quand un corps envoyé en morceaux dépasse la taille permise (sans en-tête Content-Length pour le prévoir)."""


class Protection:
    """Middleware ASGI (sans BaseHTTPMiddleware : moins de copies, donc moins de CPU sous charge)."""

    def __init__(self, app, limite_ip=None, limite_score=None, echecs=None, max_octets=None, sanctions=None):
        self.app = app
        self.limite_ip = limite_ip or LimiteurDebit(LIMITE_IP_PAR_MIN, 60)
        self.limite_score = limite_score or SeauJetons(RAFALE_SCORE, LIMITE_SCORE_PAR_MIN / 60)
        self.sanctions = sanctions or Sanctions()
        self.echecs = echecs or ECHECS
        self.max_octets = max_octets or MAX_OCTETS

    async def _repondre(self, send, code: int, detail: str, attente: float = 0.0):
        """Écrit directement une réponse d'erreur JSON (sans passer par l'application : c'est le but, refuser à peu de frais)."""
        corps = json.dumps({"detail": detail}).encode()
        entetes = [(b"content-type", b"application/json"), (b"content-length", str(len(corps)).encode())]
        if attente:
            # Retry-After est un nombre entier de secondes : on arrondit vers le haut, au moins 1.
            entetes.append((b"retry-after", str(max(1, int(attente + 0.999))).encode()))
        entetes += EN_TETES_SECURITE
        await send({"type": "http.response.start", "status": code, "headers": entetes})
        await send({"type": "http.response.body", "body": corps})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":      # autres types ASGI (démarrage, arrêt) : on laisse passer
            return await self.app(scope, receive, send)

        # Ordre des contrôles, du moins coûteux au plus coûteux : sanction en cours -> trop de clés fausses -> limite par
        # adresse -> débit de /score -> taille du corps. Un client déjà sanctionné est refusé avant tout autre calcul.
        route, methode = scope["path"], scope["method"]
        ip = ip_client(scope)

        if route != "/health":      # sondes Kubernetes et load balancer : jamais limitées
            bloque, attente = self.sanctions.bloque(ip)
            if bloque:
                journaliser_refus("sanction", route, ip)
                return await self._repondre(send, 429, "Trop de requêtes refusées, adresse bloquée temporairement", attente)
            refus = None      # (motif, message) du premier contrôle qui échoue
            bloque, attente = self.echecs.bloque(ip)
            if bloque:
                refus = ("echecs_cle", "Trop de clés refusées, réessayer plus tard")
            if refus is None:
                autorise, attente = self.limite_ip.autoriser(ip)
                if not autorise:
                    refus = ("debit_ip", "Trop de requêtes, réessayer plus tard")
            if refus is None and route == "/score" and methode == "POST":
                # Coût en jetons proportionnel à la taille déclarée du corps (un texte long coûte plus de calcul).
                taille = dict(scope["headers"]).get(b"content-length", b"0")
                cout = 1 + (int(taille) // OCTETS_PAR_JETON if taille.isdigit() else 0)
                autorise, attente = (self.limite_score.autoriser(ip, cout) if isinstance(self.limite_score, SeauJetons)
                                     else self.limite_score.autoriser(ip))
                if not autorise:
                    refus = ("debit_score", "Trop de requêtes sur /score, réessayer plus tard")
            if refus is not None:
                journaliser_refus(refus[0], route, ip)
                duree = self.sanctions.enregistrer_refus(ip)      # chaque refus rapproche le client d'une sanction
                if duree:
                    journaliser_refus("sanction_debut", route, ip)
                return await self._repondre(send, 429, refus[1], max(attente, duree))

        # Corps trop gros : refus immédiat si la taille est annoncée ; sinon, contrôle pendant la réception (recevoir).
        longueur = dict(scope["headers"]).get(b"content-length")
        if longueur and longueur.isdigit() and int(longueur) > self.max_octets:
            journaliser_refus("trop_gros", route, ip)
            return await self._repondre(send, 413, "Requête trop volumineuse")

        recu = 0              # octets reçus jusqu'ici
        commence = False      # la réponse a-t-elle déjà commencé ? Si oui, on ne peut plus la remplacer par un 413

        async def recevoir():
            nonlocal recu
            message = await receive()
            if message["type"] == "http.request":         # corps envoyé en morceaux, sans Content-Length
                recu += len(message.get("body", b""))
                if recu > self.max_octets:
                    raise _TropGros()
            return message

        async def envoyer(message):
            nonlocal commence
            if message["type"] == "http.response.start":      # en-têtes de sécurité ajoutés à TOUTES les réponses
                commence = True
                message = {**message, "headers": list(message.get("headers", [])) + EN_TETES_SECURITE}
            await send(message)

        try:
            await self.app(scope, recevoir, envoyer)
        except _TropGros:
            journaliser_refus("trop_gros", route, ip)
            if not commence:
                await self._repondre(send, 413, "Requête trop volumineuse")


# Compte les clés fausses par adresse : alimenté par verifier_cle (main.py), lu par Protection.
ECHECS = LimiteurDebit(LIMITE_ECHECS_PAR_MIN, 60)
