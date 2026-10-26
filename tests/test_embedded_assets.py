import hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from embedded_assets import COOKIE,COOKIE_MARKER,Cancelled,archive_start,embed,embedded_tiers,unpack

def fake_executable(path):
    archive=b'pyinstaller-archive-body'
    cookie=COOKIE.pack(COOKIE_MARKER,len(archive)+COOKIE.size,0,0,313,b'python313.dll')
    path.write_bytes(b'MZ-bootloader'+archive+cookie);return archive+cookie

def write_tier(root,payload,tier_id):
    for name,data in payload.items():
        f=root/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data)
    return dict(id=tier_id,files=[dict(path=p,bytes=len(d),sha256=hashlib.sha256(d).hexdigest()) for p,d in payload.items()])

class EmbeddedAssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.exe=self.root/'DesktopPet.exe';self.archive=fake_executable(self.exe)
        self.payload={'素材清单.json':b'{"idle":{}}','quality-v1/idle.webp':b'RIFF-idle'*50}
        self.hd_payload={'素材清单.json':b'{"idle":{"hd":1}}','quality-v1/idle.webp':b'RIFF-hd'*90}
        self.tier=write_tier(self.root/'light',self.payload,'fixture')
        self.hd=write_tier(self.root/'hd',self.hd_payload,'fixturehd')
    def tearDown(self):self.tmp.cleanup()
    def embed_all(self):
        embed(self.exe,dict(light=(self.root/'light',self.tier['files']),hd=(self.root/'hd',self.hd['files'])))
    def test_archive_stays_at_file_end_and_both_tiers_unpack_verified(self):
        self.embed_all()
        data=self.exe.read_bytes();self.assertTrue(data.startswith(b'MZ-bootloader'));self.assertTrue(data.endswith(self.archive))
        with self.exe.open('rb') as stream:self.assertEqual(archive_start(stream),len(data)-len(self.archive))
        self.assertEqual(embedded_tiers(self.exe),{'light','hd'})
        light=unpack(self.exe,self.root/'cache/light','light',self.tier)
        hd=unpack(self.exe,self.root/'cache/hd','hd',self.hd)
        for name,content in self.payload.items():self.assertEqual((light/name).read_bytes(),content)
        for name,content in self.hd_payload.items():self.assertEqual((hd/name).read_bytes(),content)
    def test_second_launch_reuses_cache_without_reading_executable(self):
        self.embed_all();first=unpack(self.exe,self.root/'cache/light','light',self.tier)
        with patch('embedded_assets.read_index',side_effect=AssertionError('re-extracted')):
            self.assertEqual(unpack(self.exe,self.root/'cache/light','light',self.tier),first)
    def test_tampered_or_stale_cache_is_rebuilt_and_old_tiers_removed(self):
        self.embed_all();old=self.root/'cache/light/previous';old.mkdir(parents=True)
        target=unpack(self.exe,self.root/'cache/light','light',self.tier);(target/'quality-v1/idle.webp').write_bytes(b'x')
        target=unpack(self.exe,self.root/'cache/light','light',self.tier)
        self.assertEqual((target/'quality-v1/idle.webp').read_bytes(),self.payload['quality-v1/idle.webp']);self.assertFalse(old.exists())
    def test_checksum_mismatch_is_rejected(self):
        self.tier['files'][1]['sha256']='0'*64;self.embed_all()
        with self.assertRaises(ValueError):unpack(self.exe,self.root/'cache/light','light',self.tier)
        self.assertFalse((self.root/'cache/light/fixture').exists())
    def test_cancel_leaves_no_partial_tier(self):
        self.embed_all()
        with self.assertRaises(Cancelled):unpack(self.exe,self.root/'cache/hd','hd',self.hd,cancel=lambda:True)
        self.assertEqual(list((self.root/'cache/hd').iterdir()),[])
    def test_executable_without_embedded_files_falls_back(self):
        self.assertEqual(embedded_tiers(self.exe),set())
        self.assertIsNone(unpack(self.exe,self.root/'cache/light','light',self.tier))

if __name__=='__main__':unittest.main()
