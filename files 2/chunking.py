import re, json, glob, os
ROOT='/home/claude/work/Corpus_Semaine2_Medicaments_12_26/Corpus'
HEAD=re.compile(r'^\s*(\d{1,2}(?:[.,]\d{1,2})?)[.\s]+([A-ZÉÈÀ][A-ZÉÈÀ\' ,/\-]{4,}|[A-ZÉÈ][a-zéèêàîôûç].{3,80})\s*\+?\s*$')
def doc_meta(path):
    rel=os.path.relpath(path,ROOT).split(os.sep)
    dci=rel[0].lower()
    return dci, '/'.join(rel[1:-2]) if len(rel)>3 else os.path.basename(path)
def chunk_text(txt, size=1200, overlap=150):
    # 1) coupe par rubrique RCP si on en trouve, 2) sinon / en plus: fenêtres avec chevauchement
    lines=txt.split('\n'); secs=[]; cur=('0 INTRO',[])
    for l in lines:
        m=HEAD.match(l)
        if m and len(l)<110 and re.match(r'^\s*\d',l):
            secs.append(cur); cur=(l.strip(' +'),[])
        else: cur[1].append(l)
    secs.append(cur)
    out=[]
    for title,body in secs:
        t=re.sub(r'\n{2,}','\n','\n'.join(body)).strip()
        if len(t)<40: continue
        i=0
        while i<len(t):
            j=min(len(t),i+size)
            if j<len(t):
                k=t.rfind('\n',i+size//2,j)
                k2=t.rfind('. ',i+size//2,j)
                j=max(k,k2+1) if max(k,k2)>0 else j
            out.append((title,t[i:j].strip()))
            if j>=len(t): break
            i=max(j-overlap,i+1)
    return out
def all_chunks():
    res=[]
    for p in sorted(glob.glob(ROOT+'/**/Extracted/*.txt',recursive=True)):
        if os.path.basename(p)=='README.txt': continue
        dci,prod=doc_meta(p)
        txt=open(p,encoding='utf-8',errors='replace').read()
        lang='en' if re.search(r'USP|US_|Label_|Product_information',p) else 'fr'
        ocr='OCR partiel' in txt[:800]
        for n,(sec,t) in enumerate(chunk_text(txt)):
            res.append(dict(id=f'{len(res):05d}',dci=dci,doc=os.path.relpath(p,ROOT),section=sec,lang=lang,ocr=ocr,n=n,text=t))
    return res
if __name__=='__main__':
    c=all_chunks()
    json.dump(c,open('chunks.json','w',encoding='utf-8'),ensure_ascii=False)
    import collections
    print(len(c),'chunks;',len({x['doc'] for x in c}),'documents')
    print(collections.Counter(x['dci'] for x in c))
    L=[len(x['text']) for x in c]; print('len min/moy/max',min(L),sum(L)//len(L),max(L))
