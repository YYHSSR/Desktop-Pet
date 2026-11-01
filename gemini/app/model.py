"""Gemini's local companion state: no account or service usage is invented."""
from share.desktop.companion_state import (
    normalized, atomic_json, load_settings, extended, week_key,
    FocusClock, FocusLedger, ActionDirector)


GREETINGS = (
    (5, '夜深了，星星都困了，你也早点睡喵。'),
    (9, '早安喵～今天也一起慢慢来。'),
    (12, '上午好喵，先挑一件小事开始吧。'),
    (14, '午后有点困？伸个懒腰再继续喵。'),
    (18, '下午好喵，我在旁边陪着你。'),
    (23, '傍晚啦，星星快出来了喵～'),
    (24, '夜深了，星星都困了，你也早点睡喵。'),
)

CONSTELLATION = 7  # Gemini: a week of stars joins into the twins.
ACTIONS = ('stretch', 'greeting', 'curious', 'pout', 'glance', 'meow', 'hop', 'chase', 'pounce', 'catch', 'lift', 'drag')
MENU_ORDER = ('idle','greeting','curious','glance','meow','stretch','hop','pout','chase','pounce','catch','lift','drag')
# How often each action turns up on its own: small cat moments are common,
# the big chase and pounce are rare treats, catching a star is kept for
# manual interaction.
ACTION_WEIGHTS = dict(glance=3., curious=2.8, meow=2.5, greeting=1.4, stretch=1.6,
                      hop=1.1, pout=.35, chase=.25, pounce=.12, catch=0., lift=0., drag=0.)
SCHEMA = extended(
    poke_action=('choice', 'curious', ACTIONS),
    double_action=('choice', 'meow', ACTIONS),
    ear_meow=('bool', True),
    hop_after_drag=('bool', True),
    sparkles=('bool', True),
    paw_prints=('bool', True),
)


def action_weight(key, hour):
    weight = ACTION_WEIGHTS.get(key, 0.)
    if key == 'stretch' and (6 <= hour < 10 or 13 <= hour < 15):
        weight *= 2.5      # waking up, and the after-lunch slump
    elif key == 'greeting' and 6 <= hour < 11:
        weight *= 2        # morning hellos
    elif key in ('chase', 'pounce') and 19 <= hour < 23:
        weight *= 1.8      # evening zoomies
    elif key in ('chase', 'pounce', 'hop') and (hour >= 23 or hour < 6):
        weight *= .3       # calmer late at night
    return weight


def time_greeting(hour, nickname=''):
    """A cat-voiced greeting for the local hour (0-23)."""
    hour = int(hour) % 24
    line = next(text for limit, text in GREETINGS if hour < limit)
    return f'{nickname}，{line}' if nickname else line


def load_focus_record(path, today):
    """Return (sessions_today, minutes_today, week_stars) without trusting the file."""
    ledger = FocusLedger.load(path)
    return (*ledger.today(today), ledger.week_total(today))
