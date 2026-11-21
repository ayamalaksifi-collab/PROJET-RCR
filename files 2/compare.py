import re, json, numpy as np
from search import *
C=load(); T=[c['text'] for c in C]
bm=BM25(T); E=Embedder(T); V=E.encode(T)
np.save('vectors.npy',V.astype('float32'))
# (question, dci attendue, regex d'un passage-réponse, type)
Q=[
 ("Quelle est la dose maximale de néfopam par 24 heures ?","nefopam",r"120 mg/24","lexicale"),
 ("Peut-on donner du néfopam à un enfant ?","nefopam",r"moins de 15 ans","paraphrase"),
 ("Quels antibiotiques risquent de provoquer une rupture des tendons ?","ciprofloxacine|levofloxacine",r"tend(i|o)n|tendin","paraphrase"),
 ("Quelle posologie de cefixime pour une urétrite gonococcique ?","cefixime",r"gonococ","lexicale"),
 ("Que faire en cas d'insuffisance rénale sévère avec la gentamicine ?","gentamicine",r"clairance|insuffisance r[ée]nale","paraphrase"),
 ("Quel médicament est déconseillé avec l'alcool pendant le traitement ?","metronidazole",r"alcool|ethanol|disulfiram","paraphrase"),
 ("Peut-on prendre de la doxycycline pendant la grossesse ?","doxycycline",r"grossesse|pregnan","lexicale"),
 ("Risque de diarrhée sévère après un traitement par clindamycine","clindamycine",r"clostridi|colite|pseudomembran","paraphrase"),
 ("À quelle température conserver la ceftriaxone reconstituée ?","ceftriaxone",r"conserv|stor|stabil","lexicale"),
 ("Interaction entre le cotrimoxazole et la warfarine","cotrimoxazole",r"warfarin|antivitamine|AVK","lexicale"),
]
def hit(idx,dci,rx):
    return [i for i in idx if re.search(dci,C[i]['dci']) and re.search(rx,C[i]['text'],re.I)]
rows=[]; K=5
for q,dci,rx,typ in Q:
    s_b=bm.score(q); s_v=V@E.encode([q])[0]
    rb=np.argsort(-s_b)[:K]; rv=np.argsort(-s_v)[:K]
    # hybride RRF
    rr={}
    for r,i in enumerate(np.argsort(-s_b)[:50]): rr[i]=rr.get(i,0)+1/(60+r)
    for r,i in enumerate(np.argsort(-s_v)[:50]): rr[i]=rr.get(i,0)+1/(60+r)
    rh=sorted(rr,key=rr.get,reverse=True)[:K]
    def rank1(idx):
        for r,i in enumerate(idx):
            if re.search(dci,C[i]['dci']) and re.search(rx,C[i]['text'],re.I): return r+1
        return None
    rows.append(dict(q=q,typ=typ,bm25=rank1(rb),sem=rank1(rv),hyb=rank1(rh),
        top_bm25=[(C[i]['dci'],C[i]['section'][:30]) for i in rb[:3]],top_sem=[(C[i]['dci'],C[i]['section'][:30]) for i in rv[:3]]))
for r in rows: print(r['typ'][:5],'|',r['q'][:58],'| BM25',r['bm25'],'| SEM',r['sem'],'| HYB',r['hyb'])
for m in('bm25','sem','hyb'): print(m,'hit@5 =',sum(1 for r in rows if r[m]),'/',len(rows),' MRR=%.2f'%np.mean([1/r[m] if r[m] else 0 for r in rows]))
json.dump(rows,open('resultats.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
