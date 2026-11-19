# RAG comparison: metadata only vs. metadata + nomenclature

Generated file. Check the complete JSON files for full evidence and answers.

## Q001 — Quelle est la DCI de la spécialité Doliprane ?

- **Metadata only** (`success`): La DCI (Dénomination Commune Internationale) de la spécialité Doliprane est : **paracétamol** [M001].
- **Selective nomenclature RAG** (`success`, `identity_only`): La DCI (Dénomination Commune Internationale) de la spécialité Doliprane est : **paracétamol** [M001].
- **Nomenclature rows retrieved**: 0

## Q002 — Voltafene contient-il la même substance active que le diclofénac sodique ?

- **Metadata only** (`success`): Oui, le médicament Voltafene contient la même substance active que le diclofénac sodique : le diclofénac. [M003]
- **Selective nomenclature RAG** (`success`, `identity_only`): Oui, Voltafene contient la même substance active que le diclofénac sodique : le diclofénac [M003].
- **Nomenclature rows retrieved**: 0

## Q003 — Quelles formes pharmaceutiques et quels dosages de paracétamol sont enregistrés en Algérie ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Selective nomenclature RAG** (`incomplete_response`, `identity_plus_nomenclature`): En Algérie le paracétamol est enregistré sous les formes suivantes : - **Comprimé (ou comprimé sécable/pelliculé)** : 500 mg ([SRC001:NOM-0014],[SRC001:NOM-0008]) et 1000 mg ([SRC001:NOM-0097],[SRC001:NOM-0088],[SRC001:NOM-0091],[SRC001:NOM-0092]). - **Suspension buvable** : 120 …
- **Nomenclature rows retrieved**: 20

## Q004 — Quelles présentations d'amoxicilline seule sont enregistrées en Algérie ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Selective nomenclature RAG** (`insufficient_evidence`, `identity_plus_nomenclature`): Information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 0

## Q005 — Le paracétamol seul et l'association paracétamol-codéine sont-ils des médicaments équivalents ?

- **Metadata only** (`model_refusal`): Information insuffisante dans le jeu de données fourni.
- **Selective nomenclature RAG** (`model_refusal`, `identity_only`): Information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 0

## Q006 — La mention « CELEXOCIB » dans une nomenclature correspond-elle probablement au célécoxib ?

- **Metadata only** (`success`): Oui, la mention « CELEXOCIB » correspond très probablement au célécoxib, car cet orthographe apparaît parmi les alias de recherche associés à la DCI « célécoxib » dans la nomenclature [M009].
- **Selective nomenclature RAG** (`success`, `identity_only`): Oui, la mention « CELEXOCIB » correspond très probablement au célécoxib, car cet orthographe apparaît parmi les alias de recherche associés à la DCI « célécoxib » dans la nomenclature (voir [M009]).
- **Nomenclature rows retrieved**: 0

## Q007 — Quelle interaction doit être prise en compte entre l'ibuprofène et le ramipril, et quel est son niveau selon le Thésaurus de l'ANSM ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Selective nomenclature RAG** (`insufficient_evidence`, `identity_only`): Information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 0

## Q008 — Quelle interaction doit être vérifiée entre le ramipril et la spironolactone, et quel est son niveau de gravité ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Selective nomenclature RAG** (`insufficient_evidence`, `identity_only`): Information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 0

## Q009 — Quelles contre-indications et précautions faut-il vérifier pour le ramipril pendant la grossesse ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Selective nomenclature RAG** (`insufficient_evidence`, `identity_only`): Information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 0

## Q010 — Un patient prend un comprimé nommé « PROF 400 mg ». Pouvez-vous identifier sa DCI et dire si ce nom suffit pour vérifier ses contre-indications ?

- **Metadata only** (`success`): La DCI du comprimé « PROF 400 mg » est : ibuprofène [M002]. Information insuffisante dans le jeu de données fourni.
- **Selective nomenclature RAG** (`success`, `identity_only`): La DCI du comprimé « PROF 400 mg » est l’ibuprofène [M002]. Le simple libellé « PROF » ne permet pas, avec les données fournies, de confirmer s’il suffit à vérifier les contre‑indications : information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 0

## Q011 — Deux sources donnent des doses maximales différentes pour le même médicament : laquelle doit être retenue et pourquoi ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Selective nomenclature RAG** (`insufficient_evidence`, `identity_only`): Information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 0

## Q012 — J'ai mal à la tête : quel médicament dois-je prendre et à quelle dose ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Selective nomenclature RAG** (`insufficient_evidence`, `identity_only`): Information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 0
