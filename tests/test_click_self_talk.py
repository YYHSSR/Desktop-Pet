"""Click-triggered bubbles remain independent from periodic bubbles."""
from pet import window_alerts

class _Cfg(dict):
    def click_talk_texts_for(self, character_id, click_name):
        return []

class _ClickCfg(_Cfg):
    dir = None

def _click_once(*, click_self_talk: bool, periodic: bool):
    """走真实点击入口：``PetWindow._on_click`` + 最小宿主替身。

    只提供该路径真正用到的属性/方法；``_show_click_self_talk`` 委托到真实 seam
    （``window_alerts.show_click_self_talk``），所以"显示什么、朗读什么"由产品代码决定。
    """
    from pet.window import PetWindow

    class _Pet:
        _just_dragged = False
        clicks = ["click-1"]
        on_restore_fun_windows = None
        _effects_consume_click = None
        _effects_route_click_golden_spin = None

        def __init__(self):
            self.cfg = _ClickCfg({
                "character": "shenshen",
            })
            self.click_show_self_talk = click_self_talk
            self._self_talk_enabled = periodic
            self.shown: list[str] = []
            self.scheduled: list[bool] = []

        def _pick(self, sequence):
            return sequence[0]

        def _cancel_move(self) -> None:
            pass

        def _start_squash(self) -> None:
            pass

        def _switch(self, name) -> None:
            pass


        def _show_click_self_talk(self, click_name):
            return window_alerts.show_click_self_talk(self, click_name)

        def _show_self_talk_text(self, text):
            self.shown.append(text)
            self._last_self_talk_text = text
            return True

        def _show_random_self_talk(self):
            self._last_self_talk_text = "再陪你一会儿。"
            self.shown.append(self._last_self_talk_text)
            return True

        def _schedule_self_talk(self, *, after_display=False):
            self.scheduled.append(bool(after_display))

    pet = _Pet()
    PetWindow._on_click(pet)
    return pet

def test_click_self_talk_shows_without_periodic_bubbles():
    """只开「点击触发自言自语」、关掉「气泡自言自语」也要出气泡并朗读。

    本轮解耦的契约：点击自言自语是**独立开关**，不再依附周期气泡总开关
    （原先 ``_on_click`` 要求两者同时开启，导致只想点击听声的用户无从开启）。
    """
    pet = _click_once(click_self_talk=True, periodic=False)

    assert pet.shown == ["再陪你一会儿。"]
    assert pet.scheduled == [True]

def test_click_self_talk_off_ignores_periodic_setting():
    """反向：只开周期气泡、关掉「点击触发自言自语」时，点击不出气泡也不朗读。"""
    pet = _click_once(click_self_talk=False, periodic=True)

    assert pet.shown == []
    assert pet.scheduled == []
