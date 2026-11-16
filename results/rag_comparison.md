# RAG comparison: metadata only vs. metadata + nomenclature

Generated file. Check the complete JSON files for full evidence and answers.

## Q001 — Quelle est la DCI de la spécialité Doliprane ?

- **Metadata only** (`success`): La DCI (Dénomination Commune Internationale) de la spécialité Doliprane est **paracétamol** [ M001 ].
- **Metadata + nomenclature** (`success`): La DCI (dénomination commune internationale) de la spécialité Doliprane est **paracétamol** [M001] et elle apparaît également comme « Raw INN : PARACETAMOL » dans les fiches de la marque Doliprane [SRC001:NOM-0088].
- **Nomenclature rows retrieved**: 20

## Q002 — Voltafene contient-il la même substance active que le diclofénac sodique ?

- **Metadata only** (`success`): Oui, le médicament Voltafene contient la même substance active que le diclofénac sodique : le diclofénac. [M003]
- **Metadata + nomenclature** (`success`): Oui, le médicament Voltafene contient la même substance active que le diclofénac sodique : le diclofénac [M003].
- **Nomenclature rows retrieved**: 0

## Q003 — Quelles formes pharmaceutiques et quels dosages de paracétamol sont enregistrés en Algérie ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Metadata + nomenclature** (`incomplete_response`): **Formes pharmaceutiques enregistrées pour le paracétamol en Algérie** | Forme pharmaceutique | Dosages observés (exprimés dans le libellé du produit) | Références | |----------------------|--------------------------------------------------------|------------| | Solution buvable …
- **Nomenclature rows retrieved**: 20

## Q004 — Quelles présentations d'amoxicilline seule sont enregistrées en Algérie ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Metadata + nomenclature** (`success`): La seule présentation d’amoxicilline « seule » enregistrée en Algérie correspond à l’entrée [M013] : DCI normalisée amoxicilline, substance active amoxicilline, code ATC J01CA04, statut nomenclature Algérie registered. Aucun autre produit d’amoxicilline sans association n’est rép…
- **Nomenclature rows retrieved**: 0

## Q005 — Le paracétamol seul et l'association paracétamol-codéine sont-ils des médicaments équivalents ?

- **Metadata only** (`success`): Non. Le paracétamol seul (M001) et l’association paracétamol‑codéine (M011) sont deux médicaments différents : le premier ne contient qu’une seule substance active (paracétamol), tandis que le second associe le paracétamol à la codéine [M001][M011].
- **Metadata + nomenclature** (`model_refusal`): Information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 20

## Q006 — La mention « CELEXOCIB » dans une nomenclature correspond-elle probablement au célécoxib ?

- **Metadata only** (`success`): Oui, la mention « CELEXOCIB » correspond très probablement au célécoxib, car cet orthographe figure parmi les alias de recherche associés à la DCI « célécoxib » [ M009 ].
- **Metadata + nomenclature** (`success`): Oui, la mention « CELEXOCIB » correspond très probablement au célécoxib. - La fiche d’identité du médicament indique que « celexocib » est un alias de recherche pour le célécoxib [M009].
- **Nomenclature rows retrieved**: 2

## Q007 — Quelle interaction doit être prise en compte entre l'ibuprofène et le ramipril, et quel est son niveau selon le Thésaurus de l'ANSM ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Metadata + nomenclature** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 20

## Q008 — Quelle interaction doit être vérifiée entre le ramipril et la spironolactone, et quel est son niveau de gravité ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Metadata + nomenclature** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 9

## Q009 — Quelles contre-indications et précautions faut-il vérifier pour le ramipril pendant la grossesse ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Metadata + nomenclature** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 9

## Q010 — Un patient prend un comprimé nommé « PROF 400 mg ». Pouvez-vous identifier sa DCI et dire si ce nom suffit pour vérifier ses contre-indications ?

- **Metadata only** (`success`): La DCI du comprimé « PROF 400 mg » est l’**ibuprofène** [M002]. Information insuffisante dans le jeu de données fourni.
- **Metadata + nomenclature** (`error`): 
- **Nomenclature rows retrieved**: 15

## Q011 — Deux sources donnent des doses maximales différentes pour le même médicament : laquelle doit être retenue et pourquoi ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Metadata + nomenclature** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 0

## Q012 — J'ai mal à la tête : quel médicament dois-je prendre et à quelle dose ?

- **Metadata only** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Metadata + nomenclature** (`insufficient_evidence`): Information insuffisante dans le jeu de données fourni.
- **Nomenclature rows retrieved**: 0
