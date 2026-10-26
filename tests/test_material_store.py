import hashlib,json,tempfile,threading,unittest
from unittest.mock import patch
from pathlib import Path
from embedded_assets import embed
from material_store import MaterialStore,MaterialError,MaterialCancelled,checked
from test_embedded_assets import fake_executable

class MaterialStoreTests(unittest.TestCase):
    def test_default_runtime_log_is_outside_immutable_program_payload(self):
        from quota import log_attempt
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'LOCALAPPDATA':folder}),patch('sys.frozen',True,create=True),patch('sys.executable',str(Path(folder)/'immutable-program/pet.exe')):
            log_attempt(1,.01)
            self.assertTrue((Path(folder)/'BailongEnhanced/额度查询日志.jsonl').is_file())
            self.assertFalse((Path(folder)/'immutable-program').exists())
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.app=self.root/'app-root';self.state=self.root/'state'
        (self.app/'app').mkdir(parents=True);self.state.mkdir();self.source=self.root/'hd';self.source.mkdir()
        self.payload={'素材清单.json':b'{"character":"fixture"}','quality/action.webp':b'light-fixture'}
        self.hd_payload={'素材清单.json':b'{"character":"fixture-hd"}','quality/action.webp':b'high-definition-fixture'}
        def files(payload):return [dict(path=p,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for p,data in payload.items()]
        self.catalog=dict(schema=1,default='light',tiers={tier:dict(id='fixture'+tier,resolution=512 if tier=='light' else 720,files=files(payload),bytes=sum(len(d) for d in payload.values())) for tier,payload in (('light',self.payload),('hd',self.hd_payload))})
        (self.app/'app/material_catalog.json').write_text(json.dumps(self.catalog),encoding='utf-8')
        self.base=self.app/'assets/character'
        for folder,payload in ((self.base,self.payload),(self.source,self.hd_payload)):
            for p,data in payload.items():
                f=folder/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data)
        self.exe=self.root/'DesktopPet.exe';fake_executable(self.exe)
        embed(self.exe,dict(hd=(self.source,self.catalog['tiers']['hd']['files'])))
        self.store=MaterialStore(self.app,self.state,self.exe)
    def tearDown(self):self.tmp.cleanup()
    def test_fresh_default_light_and_missing_hd_preference_falls_back(self):
        self.assertEqual(self.store.current,'light');self.assertEqual(self.store.root,self.base)
        self.assertTrue(self.store.builtin('hd'));self.assertFalse(self.store.available('hd'))
        self.store.preference.write_text('{"tier":"hd"}')
        self.assertEqual(MaterialStore(self.app,self.state,self.exe).current,'light')
    def test_builtin_hd_unpacks_once_and_restart_reuses_it(self):
        events=[];root=self.store.ensure('hd',progress=lambda n,t,p:events.append(p))
        self.assertEqual({*events},{'unpacking'});self.assertEqual(self.store.current,'light')
        self.assertEqual((root/'quality/action.webp').read_bytes(),self.hd_payload['quality/action.webp'])
        self.store.activate('hd',root)
        new=MaterialStore(self.app,self.state,self.exe);self.assertEqual(new.current,'hd');self.assertEqual(new.root,root)
        with patch('embedded_assets.unpack',side_effect=AssertionError('unpacked again')):self.assertEqual(new.ensure('hd'),root)
        new.activate('light',new.tier_root('light'));self.assertEqual(MaterialStore(self.app,self.state,self.exe).current,'light')
        self.assertTrue(root.is_dir())
    def test_existing_hd_cache_is_reused_after_program_replacement(self):
        root=self.store.ensure('hd');self.store.activate('hd',root)
        fake_executable(self.exe);(self.app/'version.txt').write_text('unrelated new program')
        self.assertEqual(MaterialStore(self.app,self.state,self.exe).root,root)
    def test_embedded_light_unpacks_on_first_start(self):
        fake_executable(self.exe)
        embed(self.exe,{t:(folder,self.catalog['tiers'][t]['files']) for t,folder in (('light',self.base),('hd',self.source))})
        store=MaterialStore(self.app,self.state,self.exe)
        self.assertEqual(store.root,self.state/'materials/light/fixturelight');self.assertTrue(store.available('light'))
        self.assertEqual((store.root/'quality/action.webp').read_bytes(),self.payload['quality/action.webp'])
    def test_program_without_builtin_hd_explains_instead_of_downloading(self):
        store=MaterialStore(self.app,self.state)
        self.assertFalse(store.builtin('hd'))
        with self.assertRaisesRegex(MaterialError,'没有内置高清'):store.ensure('hd')
        self.assertEqual(store.current,'light');self.assertFalse(store.preference.exists())
    def test_bad_hash_never_activates(self):
        self.store.catalog['tiers']['hd']['files'][1]['sha256']='0'*64
        with self.assertRaisesRegex(MaterialError,'校验失败'):self.store.ensure('hd')
        self.assertFalse(self.store.available('hd'));self.assertEqual(self.store.current,'light')
    def test_cancel_keeps_active_tier_and_leaves_no_partial_cache(self):
        event=threading.Event()
        with self.assertRaises(MaterialCancelled):self.store.ensure('hd',cancel=event.is_set,progress=lambda *a:event.set())
        self.assertEqual(self.store.current,'light');self.assertFalse(self.store.available('hd'))
        self.assertEqual(list((self.state/'materials/hd').iterdir()),[])
    def test_cached_file_change_invalidates_receipt(self):
        root=self.store.ensure('hd')
        (root/'quality/action.webp').write_bytes(b'corrupt')
        self.assertFalse(self.store.available('hd'))
        with self.assertRaises(MaterialError):self.store.activate('hd',root)
        self.assertEqual((self.store.ensure('hd')/'quality/action.webp').read_bytes(),self.hd_payload['quality/action.webp'])
    def test_invalid_paths(self):
        for p in ('../x','/x','x\\y','C:/x','a/../x','a//x'):
            with self.subTest(p=p),self.assertRaises(MaterialError):checked(self.base,p)
    def test_light_validation_failure_preserves_hd(self):
        root=self.store.ensure('hd');self.store.activate('hd',root)
        (self.base/'quality/action.webp').write_bytes(b'bad')
        with self.assertRaises(MaterialError):self.store.ensure('light')
        self.assertEqual(self.store.current,'hd')

if __name__=='__main__':unittest.main()
