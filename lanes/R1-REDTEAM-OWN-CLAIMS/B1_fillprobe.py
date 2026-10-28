"""B1 probe (run after out_B1.json and B1_crosscheck): re-run B1_rederive.beam_decode with the package's fill rule
(no skips once j + s >= K; reports/beam_decoder.md section 1 "one symbol per rune" after the key is used up)
and compare plaintexts with runeforge.beam.decode_batch on the 20 recorded plants plus 20 fresh decoys each.
Usage (repo root): python lanes/R1-REDTEAM-OWN-CLAIMS/B1_fillprobe.py"""
import sys, json, numpy as np
sys.path.insert(0,'lanes/R1-REDTEAM-OWN-CLAIMS'); sys.path.insert(0,'.')
import B1_rederive as mine, inspect
src=inspect.getsource(mine.beam_decode)
src=src.replace("                if s >= 2 and k[(j + s - 1) % K] != kj:", "                if s >= 1 and j + s >= K:\n                    break\n                if s >= 2 and k[(j + s - 1) % K] != kj:")
src=src.replace("def beam_decode(","def beam_decode2(")
ns=dict(mine.__dict__); exec(src, ns); bd2=ns['beam_decode2']
from runeforge.beam import decode_batch
from runeforge.scoring import presets
out=json.load(open('lanes/R1-REDTEAM-OWN-CLAIMS/out_B1.json')); P=out['params']
plains=mine.solved_plains(); sc=mine.Scorer([plains[t] for t in P['train_ids']]); koan=plains['a-koan-1']
ref=presets.get('lp-ngram3-heldout'); model=presets.beam_model('beam-skip')
rng=np.random.default_rng(12345); mm=0; n=0; pm=0; dsd=0
for r in out['plants']:
    plain=koan[r['offset']:r['offset']+240]
    c,_,_=mine.encrypt(plain, mine.random29(r['seed'],960), .19, np.random.default_rng(r['filter_rng_seed']))
    keys=[mine.random29(r['seed'],240)]+[mine.random29(int(s),240) for s in rng.integers(0,2**32,20)]
    res=decode_batch(c,np.stack(keys),ref,model)
    for t,k in enumerate(keys):
        p,_,_=bd2(c,k,sc,8,6,.19); n+=1
        if (p!=res.plain[t]).any(): mm+=1; pm+= (t==0)
print('mismatch with no-skip-in-fill rule:',mm,'of',n,'planted mismatches',pm)
