# Synthèse automatique des vagues (chiffres bruts)

## v1_reconnaissance — 5 écart(s)

- GET /docs : 429 (attendu 404)
- POST /model : 429 (attendu 404)
- POST /predire : 429 (attendu 404)
- GET /.env : 429 (attendu 404)
- GET /phpinfo.php : 429 (attendu 404)

## v2_sondes_web — 4 écart(s)

- 200 /health : en-têtes manquants ['x-frame-options']
- 404 /inconnu : en-têtes manquants ['x-frame-options']
- 401 /score sans clé : en-têtes manquants ['x-frame-options']
- pas de pare-feu applicatif (WAF) : charges XSS / SQLi transmises à l'API (risque connu, accepté)

## v3_authentification — conforme


## v4_fuite_information — 1 écart(s)

- JSON imbriqué 5 000 niveaux : erreur serveur 500

## v5_extraction

- 15/400 réponses exploitables en 13.8 s, soit 65/min ; codes {'200': 15, '429': 383, '503': 2} ; premier 429 à 0.0 s

## v6_evasion_sondes_ia

| Attaque | Résultat |
|---|---|
| sans attaque | {'rappel': 0.9, 'faux_positifs': 1} |
| leetspeak | {'evasions': '0/18', 'taux_evasion': 0.0} |
| lettres espacées | {'evasions': '2/18', 'taux_evasion': 0.111} |
| homoglyphes | {'evasions': '0/18', 'taux_evasion': 0.0} |
| invisibles | {'evasions': '0/18', 'taux_evasion': 0.0} |
| point entre lettres | {'evasions': '6/18', 'taux_evasion': 0.333} |
| noyage 1000 car. | {'evasions': '1/18', 'taux_evasion': 0.056} |
| noyage 3000 car. | {'evasions': '1/18', 'taux_evasion': 0.056} |

Sondes IA ratées : emoji seulement, négation, citation d'insulte (méta)

## v7_deni_service

- Attaque : 21542 requêtes, 19 acceptées (200)
- Légitime pendant l'attaque : {'requetes': 55, 'reussies': 55, 'taux_succes': 1.0, 'codes': {'200': 55}, 'p50_ms': 176, 'p95_ms': 208, 'max_ms': 264}
- Légitime référence : {'requetes': 28, 'reussies': 28, 'taux_succes': 1.0, 'codes': {'200': 28}, 'p50_ms': 172, 'p95_ms': 219, 'max_ms': 281} ; multiplicateur P95 : ×0.9
- Alertes déclenchées : {'DssDebitAnormal': 75, 'DssRefusEnHausse': 135}

## v8_multi_adresses

- Attaque : 21600 requêtes, 46 acceptées (200)
- Légitime pendant l'attaque : {'requetes': 54, 'reussies': 53, 'taux_succes': 0.981, 'codes': {'200': 53, '503': 1}, 'p50_ms': 173, 'p95_ms': 217, 'max_ms': 506}
- Légitime référence : {'requetes': 28, 'reussies': 28, 'taux_succes': 1.0, 'codes': {'200': 28}, 'p50_ms': 165, 'p95_ms': 204, 'max_ms': 213} ; multiplicateur P95 : ×1.1
- Alertes déclenchées : {'DssDebitAnormal': 105, 'DssRefusEnHausse': 135}

![Déni de service](deni_service.png)
