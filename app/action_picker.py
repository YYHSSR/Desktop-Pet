"""Varied random action choice: recently played animations wait before repeating."""
import random
from collections import deque


class ActionPicker:
    def __init__(self,rng=None,memory=32):
        self.rng=rng or random.Random();self.history=deque(maxlen=memory)
    def pick(self,pool):
        pool=[item for item in pool if item]
        if not pool:return None
        ids={item.get('id') for item in pool}
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
        weights=[1+last.get(item.get('id'),len(self.history)+len(ids)) for item in fresh]
        item=self.rng.choices(fresh,weights)[0];self.history.append(item.get('id'));return item
    def delay(self,interval):
        return interval*self.rng.uniform(.6,1.25)
