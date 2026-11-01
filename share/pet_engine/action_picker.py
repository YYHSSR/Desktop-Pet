"""Varied random action choice: recently played animations wait before repeating."""
import random
from collections import deque


class ActionPicker:
    def __init__(self,rng=None,memory=32):
        self.rng=rng or random.Random();self.history=deque(maxlen=memory)
    def pick(self,pool,weight=None):
        """weight(item) is an optional base likelihood; 0 or less leaves it out."""
        pool=[item for item in pool if item and (weight is None or weight(item)>0)]
        if not pool:return None
        ids={item.get('id') for item in pool}
        if weight is not None:return self._weighted(pool,ids,weight)
        # Block about half of this pool, so a 15-action pool never repeats
        # within 7 picks while small pools still alternate.
        window=min(len(ids)-1,max(1,len(ids)//2))
        recent=[]
        for key in reversed(self.history):
            if len(recent)>=window:break
            if key in ids and key not in recent:recent.append(key)
        fresh=[item for item in pool if item.get('id') not in recent] or pool
        # Long-unplayed actions grow more likely, so none is starved.
        last={}
        for i,key in enumerate(reversed(self.history)):last.setdefault(key,i)
        weights=[(1+last.get(item.get('id'),len(self.history)+len(ids)))*(weight(item) if weight else 1) for item in fresh]
        item=self.rng.choices(fresh,weights)[0];self.history.append(item.get('id'));return item
    def _weighted(self,pool,ids,weight):
        # Weights are the character's taste, so recency only nudges them:
        # never the same action twice running, the two before that damped,
        # and a long-unplayed one at most twice as likely. (Blocking half of
        # a small pool would force the rare treats to come up all the time.)
        recent=[]
        for key in reversed(self.history):
            if key in ids and key not in recent:recent.append(key)
            if len(recent)==3:break
        damp=dict(zip(recent,(0.,.35,.7)))
        if len(ids)==1:damp={}
        gap={}
        for i,key in enumerate(reversed(self.history)):gap.setdefault(key,i)
        def score(item):
            key=item.get('id');stale=min(2.,1+gap.get(key,2*len(ids))/(2*len(ids)))
            return weight(item)*damp.get(key,1.)*stale
        weights=[score(item) for item in pool]
        if not any(weights):weights=[weight(item) for item in pool]
        item=self.rng.choices(pool,weights)[0];self.history.append(item.get('id'));return item
    def delay(self,interval):
        return interval*self.rng.uniform(.6,1.25)
