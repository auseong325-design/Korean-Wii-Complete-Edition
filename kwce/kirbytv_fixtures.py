"""Synthetic Kirby TV service data for local internal-screen review.

Everything here is fabricated: fictional episode titles/synopses and a single
self-made test video. No real Kirby episodes, synopses or copyrighted footage
is reproduced. The XML follows the public gb_config structure (code HCMP) so
the channel reaches its list, timetable, settings and player screens.
"""
import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
UI_TABLE = ROOT / 'configs/kirbytv-ui-v1-ko.json'
VIDEO = 'test/sample.mo'            # served for every episode
EPISODE_COUNT = 6


def _ui_locale():
    """locale trans_units with the English source strings the SWF overlay maps."""
    ui = json.loads(UI_TABLE.read_text(encoding='utf-8'))
    locale, help_items = [], {}
    for row in ui['entries']:
        uid, field, source = row['id'], row['field'], row['source']
        if uid.startswith('help/'):
            _, item, key = uid.split('/', 2)
            help_items.setdefault(item, []).append((key, field, source))
            continue
        attr = ' type="btn"' if field == 'label' else (' type="dialog"' if field == 'message' else '')
        locale.append(f'    <trans_unit id="{uid}"{attr}>\n      <{field} size="">\n'
                      f'        <target xml:lang="en-UK">{escape(source)}</target>\n      </{field}>\n    </trans_unit>')
    return '\n'.join(locale), help_items


def _episodes():
    # Fabricated titles/synopses (not the real series). Dates centre on a fixed
    # reference day so the lead sees current, upcoming and expired rows.
    titles = [
        ('별가루 마을의 아침', '커비가 별가루 마을에서 새로운 하루를 맞이합니다. (가상의 시험용 줄거리입니다.)'),
        ('데굴데굴 언덕 대회', '친구들과 함께 언덕을 굴러 내려가는 가상의 시험 에피소드입니다.'),
        ('하늘 위의 연날리기', '바람을 타고 연을 날리는 이야기. 실제 방송분이 아닌 시험 데이터입니다.'),
        ('달빛 호수의 노래', '고요한 호수에서 울려 퍼지는 노래. 내부 화면 검수용 가상 줄거리.'),
        ('용기의 작은 열쇠', '잠긴 문을 여는 작은 열쇠를 찾는 가상의 모험 이야기입니다.'),
        ('다시 만난 친구들', '오랜만에 모인 친구들의 하루. 저작권 없는 자작 시험 줄거리입니다.'),
    ]
    rows = []
    for i, (title, synopsis) in enumerate(titles[:EPISODE_COUNT], 1):
        # Day offsets from the reference: already-showing, new today, upcoming, expired.
        start = ['2026 10 24 09 00 00', '2026 10 27 09 00 00', '2026 10 28 09 00 00',
                 '2026 10 31 09 00 00', '2026 11 03 09 00 00', '2026 10 10 09 00 00'][i - 1]
        end = ['2026 11 05 09 00 00', '2026 11 08 09 00 00', '2026 11 09 09 00 00',
               '2026 11 12 09 00 00', '2026 11 15 09 00 00', '2026 10 22 09 00 00'][i - 1]
        rows.append((i, title, synopsis, start, end))
    return rows


def _episode_xml(num, title, synopsis, start, end, video=VIDEO, power=None):
    return (f'    <item id="{num}" type="" start_date="{start}" end_date="{end}">\n'
            f'      <episode_number>{num}</episode_number>\n      <kirby_power>{num if power is None else power}</kirby_power>\n'
            f'      <trans_unit>\n        <title size=""><target xml:lang="ko-KR">{escape(title)}</target></title>\n'
            f'        <title_message><target>{num:02d}</target></title_message>\n'
            f'        <synopsis size=""><target xml:lang="ko-KR">{escape(synopsis)}</target></synopsis>\n      </trans_unit>\n'
            f'      <video path="{video}"/>\n    </item>')


# ---------------------------------------------------------- schedule scenarios
#
# Feed revisions 3+ pin the channel clock: DataController.setChannelDate reads
# settings/override/server_date before the HTTP Date header (the local server
# sends none, so revisions 1-2 fell back to the first episode's start date),
# and settings/expiry_date drives isExpired / isFinalWeek. Episode dates are
# chosen so that, at the pinned instant, the timetable holds every state the
# EpisodeStateMachine can produce. Times are the service's UTC; the Korean
# build-v4 shows them in KST (+9), which moves two of the shown dates.

SCENARIO_EPISODES = [
    # (number, title, synopsis, start, end, has_video, expected state at the pinned instant)
    (1, '별가루 마을의 아침', '커비가 별가루 마을에서 새로운 하루를 맞이합니다. (가상의 시험용 줄거리입니다.)',
     (2026, 10, 10, 0), (2026, 10, 22, 0), True, 'UNLOCKED'),       # episode 1 is always unlocked
    (2, '데굴데굴 언덕 대회', '친구들과 함께 언덕을 굴러 내려가는 가상의 시험 에피소드입니다.',
     (2026, 10, 12, 0), (2026, 10, 24, 0), True, 'LOCKED_EXPIRED'),
    (3, '하늘 위의 연날리기', '바람을 타고 연을 날리는 이야기. 실제 방송분이 아닌 시험 데이터입니다.',
     (2026, 10, 16, 15), (2026, 10, 28, 15), True, 'LIMITED_24'),
    (4, '달빛 호수의 노래', '고요한 호수에서 울려 퍼지는 노래. 내부 화면 검수용 가상 줄거리.',
     (2026, 10, 18, 0), (2026, 10, 30, 0), True, 'LIMITED_TIME'),
    (5, '용기의 작은 열쇠', '잠긴 문을 여는 작은 열쇠를 찾는 가상의 모험 이야기입니다.',
     (2026, 10, 25, 0), (2026, 11, 5, 18), True, 'UNLOCKED'),
    (6, '다시 만난 친구들', '오랜만에 모인 친구들의 하루. 저작권 없는 자작 시험 줄거리입니다.',
     (2026, 10, 28, 0), (2026, 11, 9, 0), True, 'NEW'),
    (7, '반짝반짝 별똥별', '밤하늘의 별똥별을 쫓아가는 가상의 이야기. 시험용 줄거리입니다.',
     (2026, 10, 30, 20), (2026, 11, 11, 20), True, 'LOCKED_FUTURE'),
    (8, '바람개비 경주', '바람개비를 들고 달리는 가상의 경주 이야기입니다. (시험 데이터)',
     (2026, 11, 3, 0), (2026, 11, 15, 0), True, 'LOCKED_FUTURE'),
    (9, '영상 없는 시험 에피소드', '영상 경로가 비어 있는 시험 항목입니다. 볼 수 없는 에피소드 화면 확인용입니다.',
     (2026, 10, 26, 0), (2026, 11, 7, 0), False, 'UNAVAILABLE'),
]

SCENARIOS = {
    3: dict(server_date=(2026, 10, 28, 3), expiry_date=(2026, 12, 3, 0), shift_days=0,
            purpose='every timetable state at a pinned instant; late start on a fresh save; not the final weeks'),
    4: dict(server_date=(2026, 11, 24, 3), expiry_date=(2026, 12, 3, 0), shift_days=27,
            purpose='same schedule 27 days later: final two weeks before expiry (txt_intro_4 + [number_days])'),
}


def _scenario_time(parts, shift_days=0):
    from datetime import datetime, timedelta
    return datetime(*parts) + timedelta(days=shift_days)


def service_date_text(value):
    """'YYYY MM DD HH MM SS' as DateManager.getDateFromString slices it."""
    return value.strftime('%Y %m %d %H %M %S')


def http_date_text(value):
    """RFC 1123 date as DateManager.__set__serverDate splits it (', ', ' ', ':')."""
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    return f'{days[value.weekday()]}, {value.day:02d} {months[value.month - 1]} {value.year} {value:%H:%M:%S} GMT'


def scenario(revision):
    """Resolved schedule for feed revision 3+: dates, episodes and expected states."""
    spec = SCENARIOS[revision]
    shift = spec['shift_days']
    episodes = []
    for num, title, synopsis, start, end, has_video, state in SCENARIO_EPISODES:
        episodes.append(dict(number=num, title=title, synopsis=synopsis,
                             start=_scenario_time(start, shift), end=_scenario_time(end, shift),
                             video=VIDEO if has_video else '', expected_state=state,
                             power=(num - 1) % EPISODE_COUNT + 1))
    return dict(revision=revision, purpose=spec['purpose'], server_date=_scenario_time(spec['server_date']),
                expiry_date=_scenario_time(spec['expiry_date']), episodes=episodes)


def gb_config_xml(revision=None):
    """Feed XML. revision None (feeds 1-2): original 6-episode set; 3+: a pinned schedule scenario."""
    locale, help_items = _ui_locale()
    episodes = []
    if revision is None:
        settings = '  <settings>\n    <e_vid_path>evideos/</e_vid_path>\n  </settings>\n'
        for num, title, synopsis, start, end in _episodes():
            episodes.append(_episode_xml(num, title, synopsis, start, end))
    else:
        plan = scenario(revision)
        settings = ('  <settings>\n    <e_vid_path>evideos/</e_vid_path>\n'
                    f'    <expiry_date>{service_date_text(plan["expiry_date"])}</expiry_date>\n'
                    f'    <override>\n      <server_date>{http_date_text(plan["server_date"])}</server_date>\n    </override>\n'
                    '  </settings>\n')
        for ep in plan['episodes']:
            episodes.append(_episode_xml(ep['number'], ep['title'], ep['synopsis'], service_date_text(ep['start']),
                                         service_date_text(ep['end']), ep['video'], ep['power']))
    help_xml = []
    for item, entries in help_items.items():
        buttons = [e for e in entries if e[0] in ('label', 'tool_tip')]
        pages = [e for e in entries if e[0] not in ('label', 'tool_tip')]
        page_xml = ''.join(
            f'      <trans_unit id="{key}" type="dialog">\n        <message size=""><target xml:lang="en-UK">{escape(src)}</target></message>\n      </trans_unit>\n'
            for key, field, src in pages)
        label = next(src for key, field, src in buttons if key == 'label')
        tip = next(src for key, field, src in buttons if key == 'tool_tip')
        page_block = f'    <page_data>\n{page_xml}    </page_data>\n' if pages else ''
        help_xml.append(
            f'  <item id="{item}">\n{page_block}'
            f'    <button linkageID="Btn_Settings_{item.capitalize()}">\n      <trans_unit>\n'
            f'        <label><target xml:lang="en-UK">{escape(label)}</target></label>\n'
            f'        <tool_tip y_offset="20"><target xml:lang="en-UK">{escape(tip)}</target></tool_tip>\n'
            f'      </trans_unit>\n    </button>\n  </item>')
    xml = ('<?xml version="1.0" encoding="utf-8" ?>\n<data version="1.0" code="HCMP">\n'
           + settings +
           f'  <locale>\n{locale}\n  </locale>\n'
           f'  <episode_data>\n' + '\n'.join(episodes) + '\n  </episode_data>\n'
           f'  <help_data>\n' + '\n'.join(help_xml) + '\n  </help_data>\n</data>\n')
    return xml.encode('utf-8')


def routes():
    lines = ['GET /kctv2/xml/gb_config_en.xml\tgb_config_en.xml']
    for num, *_ in _episodes():
        lines.append(f'GET /kctv2/{VIDEO}\tsample.mo')
    # De-duplicate while keeping order (all episodes share one test video).
    seen, out = set(), []
    for line in lines:
        if line not in seen:
            seen.add(line)
            out.append(line)
    return ('\n'.join(out) + '\n').encode('ascii')
