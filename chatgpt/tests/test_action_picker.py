import random
import unittest
from action_picker import ActionPicker
from desktop_core import normalized


def pool(n):return [dict(id=str(i)) for i in range(n)]


class PickerTests(unittest.TestCase):
    def test_large_pool_never_repeats_within_half_its_size(self):
        p=ActionPicker(random.Random(7));items=pool(15);picks=[p.pick(items)['id'] for _ in range(600)]
        for i in range(len(picks)):self.assertNotIn(picks[i],picks[max(0,i-7):i])
        self.assertEqual(set(picks),{item['id'] for item in items})
    def test_every_action_is_reached_quickly_and_evenly(self):
        p=ActionPicker(random.Random(3));items=pool(15);counts={}
        for _ in range(1500):key=p.pick(items)['id'];counts[key]=counts.get(key,0)+1
        self.assertLess(max(counts.values())/min(counts.values()),1.5)
        p=ActionPicker(random.Random(5));first=[p.pick(items)['id'] for _ in range(30)]
        self.assertEqual(len(set(first)),15)
    def test_small_pools_alternate_and_shared_history_spans_pools(self):
        p=ActionPicker(random.Random(1));two=pool(2)
        picks=[p.pick(two)['id'] for _ in range(20)]
        self.assertTrue(all(a!=b for a,b in zip(picks,picks[1:])))
        self.assertEqual(p.pick([dict(id='solo')])['id'],'solo');self.assertIsNone(p.pick([]))
        clicks=[dict(id='0'),dict(id='1'),dict(id='2')];p=ActionPicker(random.Random(2));last=p.pick(pool(15))['id']
        if last in ('0','1','2'):self.assertNotEqual(p.pick(clicks)['id'],last)
    def test_delay_is_jittered_around_interval(self):
        p=ActionPicker(random.Random(9));values=[p.delay(12) for _ in range(500)]
        self.assertTrue(all(7.2<=v<=15 for v in values));self.assertGreater(max(values)-min(values),5)


class SettingsTests(unittest.TestCase):
    def test_old_default_interval_migrates_but_custom_values_stay(self):
        self.assertEqual(normalized({})['random_interval'],12)
        self.assertEqual(normalized({'schema':2,'random_interval':25})['random_interval'],12)
        self.assertEqual(normalized({'schema':2,'random_interval':40})['random_interval'],40)
        self.assertEqual(normalized({'schema':3,'random_interval':25})['random_interval'],25)


if __name__=='__main__':unittest.main()
