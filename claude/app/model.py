"""Claude's reading companion state, separate from account usage."""
from share.desktop.companion_state import (
    normalized, atomic_json, load_settings, extended, FocusClock, FocusLedger, ActionDirector)

ACTIONS = ('wave', 'peek', 'idea', 'sparkles', 'wind', 'bow', 'flower', 'drag')
WALKS = ('walk-left', 'walk-right')
MENU_ORDER = ('idle', *ACTIONS, *WALKS)
SCHEMA = extended()

# How often each action turns up on its own. Gentle, reading-flavoured
# moments are common; the big twirl and the wind are treats; the flower is
# rare and stays a manual gift too. Walks only happen when she may wander.
ACTION_WEIGHTS = dict(wave=3.2, peek=2.8, idea=2., sparkles=.65, wind=.25, bow=.35,
                      flower=.12, drag=0., **dict.fromkeys(WALKS, 0.))
WALK_WEIGHT = 2.4                      # a stroll, against the actions above
CLICK_WEIGHTS = dict(peek=3., wave=2., idea=1.)
DOUBLE_WEIGHTS = dict(wave=2., bow=1., sparkles=1.)


def action_weight(key, hour):
    weight = ACTION_WEIGHTS.get(key, 0.)
    if key == 'wave' and 7 <= hour < 10:
        weight *= 1.6      # a morning hello
    elif key == 'sparkles' and 19 <= hour < 23:
        weight *= 1.5      # evening reading lights up a little
    elif key in ('wind', 'bow') and (hour >= 23 or hour < 6):
        weight *= .3
    return weight


def greeting(hour, nickname=''):
    if hour < 5 or hour >= 23:
        line = '书签替你留在这里，也记得早点休息。'
    elif hour < 12:
        line = '早安，今天从哪一页开始？'
    elif hour < 18:
        line = '午后的这一页，我陪你慢慢读。'
    else:
        line = '把今天的心事，轻轻夹进书里。'
    return f'{nickname}，{line}' if nickname else line
