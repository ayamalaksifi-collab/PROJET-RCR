import json, re, math, unicodedata, numpy as np
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

def norm(s):
    s=unicodedata.normalize('NFKD',s.lower()); s=''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9 ]',' ',s)
STOP=set('de la le les des du et en un une au aux ou pour par sur dans que qui est a d l the of and to in for or with is are be'.split())
tok=lambda s:[w for w in norm(s).split() if w not in STOP and len(w)>1]

class BM25:
    def __init__(s,docs,k1=1.5,b=0.75):
        s.d=[Counter(tok(x)) for x in docs]; s.len=np.array([sum(c.values()) for c in s.d]); s.avg=s.len.mean()
        df=Counter(w for c in s.d for w in c); N=len(docs)
        s.idf={w:math.log(1+(N-n+.5)/(n+.5)) for w,n in df.items()}; s.k1,s.b=k1,b
    def score(s,q):
        out=np.zeros(len(s.d))
        for w in set(tok(q)):
            if w not in s.idf: continue
            for i,c in enumerate(s.d):
                f=c.get(w,0)
                if f: out[i]+=s.idf[w]*f*(s.k1+1)/(f+s.k1*(1-s.b+s.b*s.len[i]/s.avg))
        return out

class Embedder:
    """Interface unique : encode(list[str]) -> matrice normalisée.
    Ici : TF-IDF (mots + trigrammes de caractères) + LSA, faute de modèle neuronal hors-ligne.
    Sur votre machine : remplacer par SentenceTransformerEmbedder (voir plus bas)."""
    def __init__(s,texts,dim=256):
        s.v=TfidfVectorizer(preprocessor=norm,analyzer='char_wb',ngram_range=(3,5),sublinear_tf=True,min_df=2,max_features=200000)
        X=s.v.fit_transform(texts); s.svd=TruncatedSVD(dim,random_state=0); s.svd.fit(X)
    def encode(s,texts): return normalize(s.svd.transform(s.v.transform(texts)))

class SentenceTransformerEmbedder:  # à utiliser chez vous (pip install sentence-transformers)
    def __init__(s,name='intfloat/multilingual-e5-small'):
        from sentence_transformers import SentenceTransformer; s.m=SentenceTransformer(name); s.name=name
    def encode(s,texts,query=False):
        pre='query: ' if query else 'passage: '
        return s.m.encode([pre+t for t in texts],normalize_embeddings=True,batch_size=32,show_progress_bar=True)

def load():
    return json.load(open('chunks.json',encoding='utf-8'))
