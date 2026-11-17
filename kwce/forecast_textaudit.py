"""Local text audit for the Forecast channel: supply-string coverage + glyph coverage.

Per the standing decision, the channel does NOT convert WiiLink live-supply strings itself (the
dropped v104/v105).  On the emulator those strings are localized PC-side into the cache by
kwce.forecast_data.localize_forecast, which only rewrites strings present in forecast_mapping().

This module audits, with no Dolphin and no new build:
  * supply coverage - every string the real downloaded payload references (conditions, UV levels,
    place/country names) that is NOT in forecast_mapping would stay English even on the emulator;
  * glyph coverage - every Korean character the mapping produces must exist in the build-v103
    fonts that draw it (place fonts carry the place glyphs, every weather font carries the rest),
    otherwise it would tofu.
The channel's own error-window / banner / label strings live in the WAD and are already localized
(build-v103 remaining_english_panes == 0); their on-screen behaviour/transitions are a lead check.
"""
import json
import struct

from .channels import ROOT, ChannelArchive, load_library
from .channel_font import font_data
from .forecast_data import forecast_mapping

PLACE_FONTS = {'arc/font/font_weather.brfnt', 'font_weather_city.brfnt.LZ'}
BUILD = ROOT / 'workspace/channels/forecast/build-v103'
REFERENCES = ROOT / 'workspace/channels/forecast/references'
# The same string-pointer tables localize_forecast walks (count_at, offset_at, stride, fields).
TABLES = [(48, 52, 8, [4]), (56, 60, 8, [4]), (80, 84, 24, [4, 8, 12])]


def referenced_strings(data):
    """Every UTF-16 string the forecast payload's pointer tables reference (like localize_forecast)."""
    if len(data) < 88 or struct.unpack_from('>II', data, 0) != (0, len(data)):
        raise ValueError('Unexpected forecast payload header')
    positions = set()
    for count_at, offset_at, stride, fields in TABLES:
        count = struct.unpack_from('>I', data, count_at)[0]
        offset = struct.unpack_from('>I', data, offset_at)[0]
        if count == 0 and offset == 0:
            continue
        if count > 10000 or offset < 88 or offset + count * stride > len(data):
            raise ValueError('Forecast table bounds')
        for index in range(count):
            for field in fields:
                positions.add(struct.unpack_from('>I', data, offset + index * stride + field)[0])
    out = []
    for at in sorted(positions):
        if at == 0 or at < 88 or at % 2 or at >= len(data):
            continue
        end = at
        while end + 2 <= len(data) and data[end:end + 2] != b'\0\0' and end - at < 4096:
            end += 2
        out.append(data[at:end].decode('utf-16-be'))
    return out


def _decompress(payload):
    load_library()
    from libWiiPy.archive import decompress_lz77
    return decompress_lz77(payload)


def payloads():
    """{country: decoded payload bytes} for the pinned real forecast downloads."""
    out = {}
    dec136 = REFERENCES / 'public-forecast-136-dec.bin'
    if dec136.exists():
        out[136] = dec136.read_bytes()
    comp49 = REFERENCES / 'http-public-forecast-49.bin'
    if comp49.exists():
        try:
            data = _decompress(comp49.read_bytes())
            if struct.unpack_from('>II', data, 0) == (0, len(data)):
                out[49] = data
        except Exception:
            pass
    return out


def supply_coverage():
    """For each real payload, the referenced strings not covered by forecast_mapping (-> stay English)."""
    mapping = forecast_mapping()
    weekdays = json.loads((ROOT / 'configs/forecast-dynamic-ko.json').read_text(encoding='utf-8')).get('weekdays', {})
    covered_keys = set(mapping) | set(weekdays.values()) | set(weekdays)
    result = {}
    for country, data in payloads().items():
        refs = referenced_strings(data)
        uncovered = sorted({s for s in refs if s and s not in covered_keys and ' '.join(s.split()) not in covered_keys})
        result[country] = dict(referenced=len(refs), unique=len(set(refs)),
                               covered=len([s for s in set(refs) if s in covered_keys or ' '.join(s.split()) in covered_keys]),
                               uncovered=uncovered)
    return result


def _font_glyphs(name, data):
    blocks, mapping, widths = font_data(b'RFNT' + data[4:] if data[:4] != b'RFNT' else data)
    return set(mapping)


def build_fonts():
    """{font name: set of codepoints} for the build-v103 weather/place fonts."""
    lib = load_library()
    t = lib.title.Title()
    t.load_wad((BUILD / 'forecast-ko-personal-test.wad').read_bytes())
    content = ChannelArchive(t.get_content_by_index(9))
    fonts = {}
    layout = ChannelArchive(_decompress(content.get('weather_layout.arc.LZ')))
    for name in layout.files:
        if name.endswith('.brfnt'):
            fonts[name] = _font_glyphs(name, layout.get(name))
    for name in ['font_weather_city.brfnt.LZ', 'font_weather_time.brfnt.LZ', 'font_weather_timeWW.brfnt.LZ']:
        if name in content.files:
            fonts[name] = _font_glyphs(name, _decompress(content.get(name)))
    return fonts


def glyph_coverage():
    """Missing glyphs per font: place names need the place fonts; conditions/UV/dynamic need every font."""
    dynamic = json.loads((ROOT / 'configs/forecast-dynamic-ko.json').read_text(encoding='utf-8'))
    places = json.loads((ROOT / 'configs/forecast-places-ko.json').read_text(encoding='utf-8'))['strings']
    non_place = set()
    for v in list(dynamic['strings'].values()) + list(dynamic.get('weekdays', {}).values()):
        non_place |= {ord(c) for c in v if c not in '\n\r'}
    place = {ord(c) for v in places.values() for c in v if c not in '\n\r'}
    fonts = build_fonts()
    gaps = {}
    for name, glyphs in fonts.items():
        need = (non_place | place) if name in PLACE_FONTS else non_place
        miss = sorted(need - glyphs)
        if miss:
            gaps[name] = ''.join(chr(c) for c in miss)
    return dict(fonts=sorted(fonts), place_fonts=sorted(PLACE_FONTS), gaps=gaps)


def channel_text_status():
    """The build-v103 channel-resource localization facts (error windows, banner, panes)."""
    m = json.loads((BUILD / 'build-manifest.json').read_text(encoding='utf-8'))
    val = m.get('localization_validation', {})
    return dict(
        remaining_english_panes=m.get('remaining_english_panes'),
        translated_textboxes=m.get('translated_textboxes'),
        native_error_text_styles=val.get('native_error_text_styles'),
        banner_language_groups=len(m.get('banner_language_groups', [])),
        behaviour_unverified=m.get('incomplete', []),
    )
