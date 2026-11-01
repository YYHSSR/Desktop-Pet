"""Small role-independent resource descriptor for new desktop-pet characters."""
import hashlib
import json
from pathlib import Path


class CharacterPack:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.data = json.loads((self.root / 'character.json').read_text(encoding='utf-8-sig'))
        self.actions = {}
        for item in self.data['actions']:
            key = item['id']
            if not isinstance(key, str) or not key or key in self.actions:
                raise ValueError('动作标识缺失或重复')
            self.path(item)
            if item.get('dragLoopFile'):
                self.path({'file':item['dragLoopFile']})
                if type(item.get('dragLoopFrames')) is not int or not 1 <= item['dragLoopFrames'] <= 2000:
                    raise ValueError('拖拽循环帧数无效')
            self.actions[key] = item
        self.idle = self.data['idle']
        if self.idle not in self.actions or not self.actions[self.idle].get('loop'):
            raise ValueError('角色需要一个循环待机动作')

    def path(self, item):
        path = (self.root / item['file']).resolve()
        if not path.is_relative_to(self.root) or path.suffix.lower() != '.webp':
            raise ValueError('角色素材路径越界或格式不支持')
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def verify(self):
        from PIL import Image, ImageChops, ImageStat
        result = []
        for item in self.actions.values():
            if item.get('dragLoopFile'):
                held=self.path({'file':item['dragLoopFile']})
                with held.open('rb') as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest()!=item['dragLoopSha256'] or held.stat().st_size!=item['dragLoopBytes']:
                        raise ValueError('拖拽循环校验失败')
            path = self.path(item)
            with path.open('rb') as stream:
                checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
            if checksum != item['sha256'] or path.stat().st_size != item['bytes']:
                raise ValueError('角色素材校验失败：' + item['id'])
            with Image.open(path) as image:
                if image.size != (512, 512):
                    raise ValueError('角色画布不是 512 × 512')
                first = image.convert('RGBa')
                for index in range(image.n_frames):
                    image.seek(index)
                    image.load()
                    alpha = image.convert('RGBA').getchannel('A')
                    if alpha.getextrema()[0] != 0 or alpha.getbbox() is None:
                        raise ValueError('角色帧缺少透明背景或内容')
                    # All art must remain within the transparent safety gutter.
                    if alpha.getpixel((0, 0)) or alpha.getpixel((511, 511)):
                        raise ValueError('角色动画进入画布角落')
                if image.n_frames != item['frames']:
                    raise ValueError('角色帧数不匹配')
                if item.get('referencePose'):
                    difference = ImageStat.Stat(ImageChops.difference(first, image.convert('RGBa'))).mean
                    if sum(difference)/4/255 > .012:
                        raise ValueError('动作没有回到共同参考姿势：'+item['id'])
            result.append(item['id'])
        return result
