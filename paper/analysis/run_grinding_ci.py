import numpy as np, json, sys

gamma=15; slot_gap=0; fa=0.5; fb=0.05; k_settle=6; total_forks=200; total_slots=50000

def f_static(d): return fb
def f_snow(d):
    if d<=slot_gap: return 0.0
    elif d<=gamma: return min(1.0, fa*(d-slot_gap)/(gamma-slot_gap))
    else: return fb

def _mean_gap():
    acc=1.0; pi_raw=[]
    for g in range(1,5000):
        pi_raw.append(acc); acc*=(1-f_snow(g))
        if acc<1e-14: break
    p=np.array(pi_raw); p/=p.sum()
    return np.dot(np.arange(1,len(p)+1),p)

MEAN_GAP=_mean_gap()
print(f'MEAN_GAP={MEAN_GAP:.4f}', flush=True)

def phi(d,a,f): return 1-(1-f(d))**a
def w_count(g): return 1.0
def w_ramp(g): return g/MEAN_GAP

class Challenger:
    def __init__(self,stake,f_fn):
        self.stake=stake; self.f_fn=f_fn
        self.ys=np.random.rand(total_slots)
        self._c={}
    def threshold(self,d):
        if d not in self._c: self._c[d]=phi(d,self.stake,self.f_fn)
        return self._c[d]
    def test(self,slot,parent):
        return self.ys[slot%total_slots]<self.threshold(slot-parent)

def grinding_sim_scheme(num_challenger,num_adversary,f_fn,weight_fn):
    branch_depth=2
    challengers=[Challenger(1.0/num_challenger,f_fn) for _ in range(num_challenger)]
    branches=np.zeros((1,6)); forked=False; last_fork=0; fork_intervals=[]; slot=0
    use_weight=(weight_fn is not w_count)
    while len(fork_intervals)<total_forks:
        new_branches=[]
        np.random.shuffle(challengers)
        honest=challengers[num_adversary:]
        adv=challengers[:num_adversary]
        for b in branches:
            for c in honest:
                if c.test(slot,int(b[0])):
                    gap=slot-b[0]; wt=weight_fn(gap)
                    nb=b.copy(); nb[0]=slot; nb[1]+=1; nb[4]+=wt
                    if use_weight:
                        lead=max(branches[:,4]-branches[:,5])
                        my_hw=nb[4]-nb[5]; nb[3]=lead-my_hw
                    else:
                        lead=max(branches[:,1]-branches[:,2])
                        my_bn=nb[1]-nb[2]; nb[3]=lead-my_bn
                    if nb[3]<branch_depth: new_branches.append(nb)
            for c in adv:
                for bb in list(branches):
                    if c.test(slot,int(bb[0])):
                        gap=slot-bb[0]; wt=weight_fn(gap)
                        nb=bb.copy(); nb[0]=slot; nb[1]+=1; nb[2]+=1; nb[4]+=wt; nb[5]+=wt
                        if use_weight:
                            lead=max(branches[:,4]-branches[:,5])
                            my_hw=nb[4]-nb[5]; nb[3]=lead-my_hw
                        else:
                            lead=max(branches[:,1]-branches[:,2])
                            my_bn=nb[1]-nb[2]; nb[3]=lead-my_bn
                        if nb[3]<branch_depth: new_branches.append(nb)
        if new_branches: branches=np.array(new_branches)
        else: branches=np.zeros((1,6)); branches[0,0]=slot
        best=branches[np.argmax(branches[:,1]-branches[:,2])]
        if best[2]>0 and not forked: forked=True; last_fork=slot
        elif best[2]==0 and forked:
            fork_intervals.append(slot-last_fork); forked=False
        slot+=1
        if slot>5000000: break
    if not fork_intervals: return 0.0
    avg_interval=np.mean(fork_intervals)
    settle_prob=1-(1-1/max(avg_interval,1))**k_settle
    return min(settle_prob,1.0)

N_TRIALS=20
data_points=list(range(0,51,5))
schemes=[('static',f_static,w_count),('ldd',f_snow,w_count),('ramp',f_snow,w_ramp)]
results={'adv_stake':data_points}

for name,f_fn,w_fn in schemes:
    means=[]; cis=[]
    for stake_pct in data_points:
        num_c=100; num_a=stake_pct
        trials=[]
        for t in range(N_TRIALS):
            np.random.seed(t*100+stake_pct)
            v=grinding_sim_scheme(num_c,num_a,f_fn,w_fn)
            trials.append(v)
        m=np.mean(trials); ci=1.96*np.std(trials)/np.sqrt(N_TRIALS)
        means.append(round(float(m),4)); cis.append(round(float(ci),4))
        print(f'{name} stake={stake_pct}%: mean={m:.3f} ci={ci:.3f}', flush=True)
    results[name]={'mean':means,'ci95':cis}
    print(f'=== Done {name} ===', flush=True)

with open('grinding_results_ci.json','w') as f: json.dump(results,f,indent=2)
print('Saved grinding_results_ci.json', flush=True)
