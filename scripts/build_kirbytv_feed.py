"""Build workspace/channels/kirbytv/local-feed-vN: synthetic Kirby TV feed.

Writes the fabricated gb_config_en.xml and route table, then encodes a
self-made short test clip to sample.mo with the pinned mobipeg encoder inside
a capability-zero AppContainer. Fictional data only; no network inputs, no
order/upload acceptance. Create-once per revision.

Revision 1: 320x240, 25 fps, PCM audio ('AP' tag). The channel's Mobiclip SDK
header switch has no 'AP' case (only FastAudio A2/A3, ADPCM A8/A9, Vorbis AV,
multitrack AM), so that clip had no usable audio track and did not start
(v2 review, 2026-10-28). Revision 2: 624x352 (the common retail size), 30 fps,
IMA-ADPCM stereo ('A9'), motion vectors capped at 32 px.
Revisions 3-4: the revision-2 clip byte for byte, plus a pinned channel clock
(settings/override/server_date) and settings/expiry_date with a 9-episode
schedule that holds every timetable state; 4 is the same schedule in the final
two weeks before expiry. See kwce.kirbytv_fixtures.SCENARIOS.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import kirbytv_fixtures as F
from kwce.channels import load_library

PROFILES = {
    1: dict(frames=125, fps=25, width=320, height=240, audio='pcm', runner='v1',
            audio_args='-c:a pcm_s16le -ac 2 -ar 32000 -mo_audio pcm', x264='asm=0:threads=1:rc-lookahead=0',
            audio_tag=b'AP', audio_label='stereo PCM 32000Hz'),
    2: dict(frames=240, fps=30, width=624, height=352, audio='adpcm', runner='v2',
            audio_args='-c:a pcm_s16le -ac 2 -ar 32000 -mo_audio adpcm', x264='asm=0:threads=1:rc-lookahead=0:mvrange=32',
            audio_tag=b'A9', audio_label='stereo IMA-ADPCM 32000Hz'),
    # Revisions 3+: pinned schedule scenarios (kwce.kirbytv_fixtures.SCENARIOS); the clip
    # that played in the v3 review is reused byte for byte instead of re-encoded.
    3: dict(video_from=2, scenario=3),
    4: dict(video_from=2, scenario=4),
}
SDK_AUDIO_TAGS = (b'A2', b'A3', b'A8', b'A9', b'AV', b'AM')   # cases in the channel's header switch


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def header_tags(data):
    if data[:4] != b'MOC5':
        raise ValueError('Not a MOC5 file')
    size = struct.unpack_from('<I', data, 4)[0]
    pos, tags = 8, []
    while pos < 8 + size:
        tag = data[pos:pos + 2]
        words = struct.unpack_from('<H', data, pos + 2)[0]
        tags.append((tag, data[pos + 4:pos + 4 + 4 * words]))
        pos += 4 + 4 * words
    if pos != 8 + size or not tags or tags[-1][0] != b'HE':
        raise ValueError('MOC5 header does not end with HE')
    return tags


def write_frames(work, profile):
    load_library()
    from PIL import Image, ImageDraw
    from kwce.wiiroom_visual import _font
    w, h, fps, frames = profile['width'], profile['height'], profile['fps'], profile['frames']
    scale = h / 240
    video = bytearray()
    for n in range(frames):
        im = Image.new('RGB', (w, h), (14, 40, 70))
        d = ImageDraw.Draw(im)
        x = round(18 * scale)
        d.text((x, round(20 * scale)), '커비 TV 채널', font=_font(round(30 * scale)), fill=(255, 255, 255))
        d.text((x, round(72 * scale)), '자체 제작 시험 영상', font=_font(round(20 * scale)), fill=(185, 225, 245))
        d.text((x, round(110 * scale)), f'{n // fps:02d}초 / {frames // fps}초', font=_font(round(19 * scale)), fill=(255, 255, 255))
        top, bottom = round(168 * scale), round(188 * scale)
        d.rectangle((x, top, w - x, bottom), fill=(40, 80, 100))
        d.rectangle((x, top, x + (w - 2 * x) * n // (frames - 1), bottom), fill=(60, 200, 235))
        d.text((x, round(206 * scale)), '실제 에피소드 아님', font=_font(round(14 * scale)), fill=(185, 225, 245))
        y, cb, cr = im.convert('YCbCr').split()
        video += y.tobytes()
        video += cb.resize((w // 2, h // 2), Image.Resampling.BOX).tobytes()
        video += cr.resize((w // 2, h // 2), Image.Resampling.BOX).tobytes()
    (work / 'frames.yuv').write_bytes(video)


def encode_video(feed, revision):
    """Self-made MOC5 clip via the pinned encoder in a capability-0 sandbox."""
    profile = PROFILES[revision]
    cfg = json.loads((ROOT / 'configs/mobipeg-runtime.lock.json').read_text(encoding='utf-8'))
    for row in cfg['files']:
        if digest(ROOT / row['path']) != row['sha256']:
            raise ValueError('Pinned encoder differs')
    work = feed / 'encode'
    work.mkdir()
    write_frames(work, profile)
    src = ROOT / f"tools/kirbytv-sandbox/{profile['runner']}/src/KirbyMediaRunner.cs"
    runner = work / 'KirbyMediaRunner.exe'
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    build = subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64', '/out:' + str(runner), str(src)], capture_output=True)
    if build.returncode:
        raise ValueError('Media runner compile failed: ' + build.stderr.decode('ascii', 'replace'))
    w, h, fps, frames = profile['width'], profile['height'], profile['fps'], profile['frames']
    seconds = frames // fps
    encode = (f'-hide_banner -nostdin -f rawvideo -pixel_format yuv420p -video_size {w}x{h} -framerate {fps} '
              f'-i frames.yuv -f lavfi -i sine=frequency=440:sample_rate=32000 -t {seconds} -c:v mobiclip -pix_fmt yuv420p '
              f"-threads 1 -x264-params {profile['x264']} {profile['audio_args']} -f mobiclip_mo sample.mo")
    decode = '-hide_banner -nostdin -i sample.mo -f null -'
    for label, line in (('encode', encode), ('decode', decode)):
        (work / f'{label}.txt').write_text(line, encoding='ascii')
        proc = subprocess.run([str(runner), f'{label}.txt'], cwd=work, capture_output=True, timeout=330)
        (work / f'{label}.log').write_bytes(proc.stdout + proc.stderr)
        if proc.returncode:
            raise ValueError(f'MOC5 {label} failed; see {label}.log')
    data = (work / 'sample.mo').read_bytes()
    tags = header_tags(data)
    names = [t for t, _ in tags]
    if b'KI' not in names or b'pc' not in names or profile['audio_tag'] not in names:
        raise ValueError(f'sample.mo header tags differ: {names}')
    if revision >= 2 and not any(t in SDK_AUDIO_TAGS for t in names):
        raise ValueError('sample.mo has no audio track the channel SDK understands')
    timeline = dict(tags)[b'TL']
    v2 = dict(tags)[b'V2']
    (feed / 'sample.mo').write_bytes(data)
    record = dict(container='MOC5 (mobiclip_mo)', encoder_version='2.3', encoder_asm=False, frames=frames, fps=fps,
                  width=w, height=h, seconds=seconds, audio=profile['audio_label'],
                  header_tags=[t.decode('latin-1') for t in names],
                  header_timeline=list(struct.unpack('<3I', timeline[:12])), header_video=list(struct.unpack('<2I', v2[:8])),
                  sdk_audio_tag_supported=any(t in SDK_AUDIO_TAGS for t in names),
                  decode_completed=True, channel_playback_verified=False, sha256=digest(feed / 'sample.mo'),
                  runner_source=src.relative_to(ROOT).as_posix(), runner_source_sha256=digest(src))
    shutil.rmtree(work)
    return record


def reuse_video(feed, revision):
    """Copy sample.mo from an earlier numbered feed after checking its manifest hash."""
    source_revision = PROFILES[revision]['video_from']
    source = ROOT / f'workspace/channels/kirbytv/local-feed-v{source_revision}'
    manifest = json.loads((source / 'fixture-manifest.json').read_text(encoding='utf-8'))
    row = next(r for r in manifest['files'] if r['path'] == 'sample.mo')
    if digest(source / 'sample.mo') != row['sha256'] or manifest['video']['sha256'] != row['sha256']:
        raise ValueError(f'local-feed-v{source_revision} sample.mo differs from its manifest')
    tags = [t for t, _ in header_tags((source / 'sample.mo').read_bytes())]
    if not set(tags) & set(SDK_AUDIO_TAGS):
        raise ValueError('Reused clip has no audio track the channel SDK understands')
    shutil.copy2(source / 'sample.mo', feed / 'sample.mo')
    if digest(feed / 'sample.mo') != row['sha256']:
        raise ValueError('Reused clip copy differs')
    video = dict(manifest['video'])
    video.update(reused_from=f'local-feed-v{source_revision}', channel_playback_verified=True,
                 channel_playback_evidence='same bytes played in the lead Dolphin review of build-v3 + local-feed-v2 '
                                           '(2026-10-28 12:47-12:52); not yet seen with build-v4')
    return video


def schedule_record(revision):
    plan = F.scenario(revision)
    return dict(
        purpose=plan['purpose'], server_date_override=F.http_date_text(plan['server_date']),
        expiry_date=F.service_date_text(plan['expiry_date']), times='service UTC (build-v4 shows them in KST, +9)',
        episodes=[dict(number=e['number'], start=F.service_date_text(e['start']), end=F.service_date_text(e['end']),
                       video=bool(e['video']), expected_state=e['expected_state']) for e in plan['episodes']])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', type=int, choices=sorted(PROFILES), default=2)
    args = parser.parse_args()
    feed = ROOT / f'workspace/channels/kirbytv/local-feed-v{args.revision}'
    if feed.exists():
        raise SystemExit('Existing local feed preserved')
    profile = PROFILES[args.revision]
    scenario = profile.get('scenario')
    feed.mkdir(parents=True)
    try:
        (feed / 'gb_config_en.xml').write_bytes(F.gb_config_xml(scenario))
        (feed / 'routes.tsv').write_bytes(F.routes())
        video = reuse_video(feed, args.revision) if 'video_from' in profile else encode_video(feed, args.revision)
    except BaseException:
        shutil.rmtree(feed)   # an unfinished feed is not a numbered artifact
        raise
    files = ['gb_config_en.xml', 'routes.tsv', 'sample.mo']
    count = len(F.SCENARIO_EPISODES) if scenario else F.EPISODE_COUNT
    manifest = dict(
        revision=args.revision, channel='kirbytv', local_only=True, synthetic=True,
        real_episodes=False, order_or_upload_accepted=False,
        service_path_scheme='/kctv2/xml/gb_config_en.xml and /kctv2/test/sample.mo (query stripped)',
        config_episodes=count, ui_sources='English (SWF overlay renders Korean)',
        video=video, files=[dict(path=p, sha256=digest(feed / p)) for p in files])
    if scenario:
        manifest['schedule'] = schedule_record(scenario)
    (feed / 'fixture-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'Built Kirby TV local-feed-v{args.revision}:', count, 'fictional episodes, self-made',
          video['container'], video['audio'], f"{video['width']}x{video['height']}@{video['fps']}", 'tags', video['header_tags'],
          ('pinned ' + manifest['schedule']['server_date_override']) if scenario else '(playback pending)')


if __name__ == '__main__':
    main()
