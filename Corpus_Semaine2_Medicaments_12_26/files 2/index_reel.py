"""Version « vrai modèle » à lancer sur votre machine (internet requis une fois pour télécharger le modèle).
pip install sentence-transformers chromadb
"""
import json, chromadb
from search import SentenceTransformerEmbedder, BM25
C = json.load(open('chunks.json', encoding='utf-8'))
emb = SentenceTransformerEmbedder('intfloat/multilingual-e5-small')   # FR + EN
col = chromadb.PersistentClient('chroma_db').get_or_create_collection('rcp', metadata={'hnsw:space': 'cosine'})
vecs = emb.encode([c['text'] for c in C])
col.add(ids=[c['id'] for c in C], embeddings=vecs.tolist(), documents=[c['text'] for c in C],
        metadatas=[{k: c[k] for k in ('dci', 'doc', 'section', 'lang', 'ocr')} for c in C])
def cherche(q, k=5, dci=None):
    r = col.query(query_embeddings=emb.encode([q], query=True).tolist(), n_results=k, where={'dci': dci} if dci else None)
    return list(zip(r['metadatas'][0], r['documents'][0]))
if __name__ == '__main__':
    for m, t in cherche("Peut-on donner du néfopam à un enfant ?"): print(m['dci'], m['section'], '\n ', t[:150], '\n')
