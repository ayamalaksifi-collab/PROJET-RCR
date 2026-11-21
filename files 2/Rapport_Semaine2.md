# Semaine 2 — Recherche par le sens (corpus médicaments 12–26)

## 1. Ce qui a été fait
| Étape | Résultat |
|---|---|
| Lecture du corpus | 15 DCI, 45 documents texte (RCP français, labels US en anglais, fiches info) |
| Découpage | **2 360 chunks** (≈ 880 caractères en moyenne, max 1 200, chevauchement 150) |
| Métadonnées par chunk | `dci`, `doc`, `section` (rubrique RCP : 4.2 Posologie, 4.3 Contre-indications…), `lang`, `ocr` |
| Vecteurs | 2 360 × 256 (`vectors.npy`) |
| Recherche mots-clés | BM25 (implémenté à la main, accents et stop-words normalisés) |
| Recherche sémantique | similarité cosinus sur les vecteurs |
| Hybride | fusion BM25 + vecteurs (Reciprocal Rank Fusion) |

**Choix de découpage :** on coupe d'abord aux rubriques numérotées du RCP (« 4.3. Contre-indications »), puis en fenêtres si la rubrique est longue, toujours à une fin de phrase ou de ligne. Une réponse reste ainsi dans la bonne rubrique.

## 2. Limite importante : les embeddings
Cet environnement n'a pas d'accès réseau : impossible de télécharger un modèle d'embeddings neuronal.
Les vecteurs ci-dessus sont donc du **TF-IDF (trigrammes de caractères) + LSA**. C'est un vrai espace vectoriel, mais bien plus faible qu'un modèle comme `multilingual-e5`, surtout pour les paraphrases et le croisement français/anglais.
`index_reel.py` fait la même chose avec `multilingual-e5-small` + ChromaDB : à lancer chez vous, puis à relancer `compare.py` avec ce modèle. **Les chiffres ci-dessous sont à refaire avec lui avant de les citer dans votre rapport.**

## 3. Comparaison mots-clés vs sémantique (10 questions, top-5)
Rang du premier passage correct (– = absent du top-5). Un passage est « correct » s'il vient de la bonne DCI et contient le bon élément.

| Question | Type | BM25 | Sémantique | Hybride |
|---|---|---|---|---|
| Dose maximale de néfopam / 24 h | lexicale | 2 | 3 | 2 |
| Néfopam chez l'enfant ? | paraphrase | – | – | – |
| Antibiotiques et rupture des tendons | paraphrase | 1 | 1 | 1 |
| Cefixime, urétrite gonococcique | lexicale | 3 | – | 2 |
| Gentamicine, insuffisance rénale sévère | paraphrase | – | 4 | 5 |
| Médicament déconseillé avec l'alcool | paraphrase | 2 | 5 | 3 |
| Doxycycline et grossesse | lexicale | 1 | 1 | 1 |
| Clindamycine, diarrhée sévère | paraphrase | 1 | 2 | 1 |
| Ceftriaxone reconstituée, conservation | lexicale | – | 5 | 4 |
| Cotrimoxazole + warfarine | lexicale | – | – | – |
| **Réponse dans le top-5** | | 6/10 | 7/10 | **8/10** |
| **MRR** | | 0,43 | 0,35 | **0,48** |

## 4. Ce qu'on en retient
- **L'hybride est le plus robuste** : il rattrape les échecs de chacune des deux méthodes (cefixime, gentamicine, ceftriaxone).
- **BM25 gagne quand le mot exact est dans la question** (doxycycline, grossesse, clindamycine, tendons) et classe souvent mieux (MRR plus haut).
- **La sémantique aide quand le vocabulaire diffère** (gentamicine : « insuffisance rénale sévère » ↔ « clairance de la créatinine »).
- **Deux échecs instructifs :**
  - *Néfopam/enfant* : la réponse existe (« Enfant de moins de 15 ans » en 4.3) mais la question est trop générique ; ajouter le nom de la rubrique et de la DCI au début de chaque chunk aiderait.
  - *Cotrimoxazole/warfarine* : l'interaction n'apparaît dans le corpus que dans le label américain en anglais (et très peu dans le RCP français), donc une question en français passe à côté. Un modèle multilingue réglerait en partie ce cas.
- **Pièges du corpus** à garder en tête : documents OCR partiels (azithromycine, cefixime : chiffres à vérifier dans les PDF), produit US non identifié (cefixime n°03), mélange français/anglais, plusieurs dosages d'une même DCI qui ne doivent pas être fusionnés.

## 5. À faire de votre côté
1. Remplacer mes 10 questions par **votre question-test de la semaine 1** et vos propres questions.
2. Lancer `index_reel.py`, puis refaire la comparaison avec le vrai modèle.
3. Ajouter un filtre sur la DCI (`where={'dci': ...}`) : c'est l'amélioration la plus rentable dans ce corpus.

Fichiers : `chunking.py` (découpage), `search.py` (BM25 + embeddings), `compare.py` (évaluation), `index_reel.py` (modèle réel), `chunks.json`, `vectors.npy`, `resultats.json`.
