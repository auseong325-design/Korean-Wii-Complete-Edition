"""Animate the restored DVD model of the 43K disc channel (resource-only).

The menu binds the disc animations to the groups G_Comment0, G_Wii, G_GC and
G_DiskIn only ("G_DVD" is never bound), so the DVD panes stood still and were
hidden only together with the whole layout, overlapping the next banner.

Fix without touching menu code:
* add the DVD panes to G_Wii and G_GC. nw4r applies enabled animations in bind
  order (Wii group first, GC group second) and the menu disables an animation
  when it stops, so the DVD follows the losing disc: GC_LOST when a Wii disc
  wins, Wii_LOST when a GC disc wins, both LOST tracks for a bad disc;
* DiskLoop keeps only the DVD rotation tracks; the other DVD tracks are
  disabled in place (unknown tag kinds are skipped by AnimTransformBasic), so a
  still-looping group cannot undo a fade;
* DiskIn holds every DVD track at the final DiskLost value, so the DVD stays
  hidden while the matching disc is inserted.
Byte sizes of both BRLANs are unchanged; only the two group blocks grow.
"""
import hashlib,struct
from .formats import U8,ash_decompress,ash_compress
from .channels import layout_sections,rebuild_layout

ASH_PATH='layout/common/diskBann2.ash'
LAYOUT='arc/blyt/my_DiskCh_a_R.brlyt'
ANIM='arc/anim/my_DiskCh_a_R_{}.brlan'
DVD_PANES=['W_DVD','RefDVD','N_RefDVD','DVDDisk','N_DVD0','SahdeDVD']
JOIN_GROUPS=['G_Wii','G_GC']
DISABLED=b'RLxx'
# (entry name, is material, tag) kept in DiskLoop: the spin of the disc and its reflection.
LOOP_KEEP={('DVDDisk',0,b'RLPA'),('RefDVD',1,b'RLTS')}


def _contents(data):
    """Yield (name, is_material, [(tag_offset, magic, [(track_offset, target, curve, [key offsets])])])."""
    if data[:4]!=b'RLAN':raise ValueError('Not a BRLAN')
    pos=0x10
    for _ in range(struct.unpack_from('>H',data,0xe)[0]):
        kind=data[pos:pos+4];size=struct.unpack_from('>I',data,pos+4)[0]
        if kind==b'pai1':
            count,offsets=struct.unpack_from('>HI',data,pos+0xe)
            for i in range(count):
                e=pos+struct.unpack_from('>I',data,pos+offsets+4*i)[0]
                name=data[e:e+20].split(b'\0')[0].decode('ascii');tags=[]
                for t in range(data[e+0x14]):
                    to=e+struct.unpack_from('>I',data,e+0x18+4*t)[0];tracks=[]
                    for k in range(data[to+4]):
                        te=to+struct.unpack_from('>I',data,to+8+4*k)[0]
                        _,target,curve,_,keys,_,koff=struct.unpack_from('>BBBBHHI',data,te)
                        step=12 if curve==2 else 8
                        tracks.append((te,target,curve,[te+koff+step*j for j in range(keys)]))
                    tags.append((to,data[to:to+4],tracks))
                yield name,data[e+0x15],tags
        pos+=size


def _value(data,curve,keys,frame):
    """Evaluate a BRLAN track like nw4r (hermite: frame,value,slope; step: frame,u16)."""
    if curve!=2:
        value=struct.unpack_from('>H',data,keys[0]+4)[0]
        for k in keys:
            f,v=struct.unpack_from('>fH',data,k)
            if f<=frame:value=v
        return value
    points=[struct.unpack_from('>fff',data,k)for k in keys]
    if frame<=points[0][0]:return points[0][1]
    if frame>=points[-1][0]:return points[-1][1]
    for (f0,v0,s0),(f1,v1,s1) in zip(points,points[1:]):
        if f0<=frame<=f1:
            if f1==f0:return v1
            t=(frame-f0)/(f1-f0);span=f1-f0
            return (2*t**3-3*t**2+1)*v0+(t**3-2*t**2+t)*span*s0+(-2*t**3+3*t**2)*v1+(t**3-t**2)*span*s1
    return points[-1][1]


def _frames(data):
    pos=0x10
    while data[pos:pos+4]!=b'pai1':pos+=struct.unpack_from('>I',data,pos+4)[0]
    return struct.unpack_from('>H',data,pos+8)[0]


def patch_layout_groups(layout):
    sections=layout_sections(layout);seen=set()
    for i,s in enumerate(sections):
        if s[:4]!=b'grp1':continue
        name=s[8:24].split(b'\0')[0].decode('ascii');count=struct.unpack_from('>H',s,24)[0]
        members=[s[28+16*j:44+16*j].split(b'\0')[0].decode('ascii')for j in range(count)]
        if name=='G_DVD' and members and set(members)!=set(DVD_PANES):raise ValueError('Unexpected G_DVD members')
        if name not in JOIN_GROUPS:continue
        if set(DVD_PANES)&set(members):raise ValueError('DVD panes already grouped')
        members+=DVD_PANES
        block=bytearray(s[:28])+b''.join(m.encode('ascii').ljust(16,b'\0')for m in members)
        struct.pack_into('>I',block,4,len(block));struct.pack_into('>H',block,24,len(members))
        sections[i]=bytes(block);seen.add(name)
    if seen!=set(JOIN_GROUPS):raise ValueError('Disc groups not found')
    return rebuild_layout(layout,sections)


def patch_loop(loop):
    out=bytearray(loop);disabled=0
    for name,material,tags in _contents(loop):
        if name not in DVD_PANES:continue
        for to,magic,_ in tags:
            if (name,material,magic) in LOOP_KEEP:continue
            out[to:to+4]=DISABLED;disabled+=1
    return bytes(out),disabled


def patch_disk_in(disk_in,lost):
    """Hold every DVD track of DiskIn at the last DiskLost frame (in place, same size)."""
    final={};end=_frames(lost)-1
    for name,material,tags in _contents(lost):
        if name in DVD_PANES:
            for _,magic,tracks in tags:
                for te,target,curve,keys in tracks:final[(name,material,magic,target)]=(curve,_value(lost,curve,keys,end))
    out=bytearray(disk_in);held=0
    for name,material,tags in _contents(disk_in):
        if name not in DVD_PANES:continue
        for _,magic,tracks in tags:
            for te,target,curve,keys in tracks:
                lost_curve,value=final[(name,material,magic,target)]
                if lost_curve!=curve:raise ValueError('Curve type differs between DiskLost and DiskIn')
                for k in keys:
                    if curve==2:struct.pack_into('>ff',out,k+4,value,0.0)
                    else:struct.pack_into('>H',out,k+4,value)
                held+=1
    return bytes(out),held


def patch_dvd_animation(resource):
    outer=U8(resource);inner=U8(ash_decompress(outer.get(ASH_PATH)))
    layout=patch_layout_groups(inner.get(LAYOUT))
    loop,disabled=patch_loop(inner.get(ANIM.format('DiskLoop')))
    disk_in,held=patch_disk_in(inner.get(ANIM.format('DiskIn')),inner.get(ANIM.format('DiskLost')))
    patched=inner.replace(LAYOUT,layout)
    for path,data in [(ANIM.format('DiskLoop'),loop),(ANIM.format('DiskIn'),disk_in)]:patched=U8(patched).replace(path,data)
    ash=ash_compress(patched)
    if ash_decompress(ash)!=patched:raise ValueError('ASH round-trip failed')
    result=outer.replace(ASH_PATH,ash)
    check=U8(ash_decompress(U8(result).get(ASH_PATH)))
    for path,data in [(LAYOUT,layout),(ANIM.format('DiskLoop'),loop),(ANIM.format('DiskIn'),disk_in)]:
        if check.get(path)!=data:raise ValueError('Nested resource verification failed')
    changed=sorted(n for n in check.files if check.get(n)!=inner.get(n))
    return result,dict(feature='DVD model follows the losing disc',groups=JOIN_GROUPS,dvd_panes=DVD_PANES,
                       loop_tags_disabled=disabled,disk_in_tracks_held=held,inner_files_changed=changed,
                       resource_sha1=hashlib.sha1(result).hexdigest())
