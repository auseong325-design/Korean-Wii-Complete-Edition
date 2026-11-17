"""Local Korean Mii Contest menu artwork; preserve animation streams."""
import hashlib
import struct
from .channels import ChannelArchive, load_library, layout_sections, rebuild_layout, compress_lz10
from .channel_texture import replace_ia4, texture_records


def ia4_canvas(width, height):
    header = struct.pack('>III', 0x20af30, 1, 12) + struct.pack('>II', 20, 0)
    info = struct.pack('>HHII', height, width, 2, 64) + bytes(24)
    return (header + info).ljust(64, b'\0') + bytes(((width+7)//8)*((height+3)//4)*32)


def animated_korean_title(archive, font_path):
    """Reuse the original staggered squash/stretch tracks for Korean syllables."""
    from PIL import Image, ImageDraw, ImageFont
    from .votes_visual import _materials, _textures
    path='arc/blyt/banner.brlyt';layout=archive.get(path);sections=layout_sections(layout)
    mi=next(i for i,s in enumerate(sections)if s[:4]==b'mat1')
    mat=bytearray(sections[mi]);materials=_materials(mat)
    textures=_textures(next(s for s in sections if s[:4]==b'txl1'))
    sprites=['st_alf_capC_00.tpl','st_alf_capO_00.tpl','st_alf_capR_00.tpl','st_alf_a_00.tpl','st_alf_c_00.tpl','st_alf_d_00.tpl']
    selected={1:('콘',-25),2:('테',23),3:('스',71),4:('트',119),8:('채',-24),9:('널',24)}
    for name in list(archive.files):
        if '/st_alf_'in name and name.endswith('.tpl'):
            old=archive.get(name);r=texture_records(old)[0]
            archive=ChannelArchive(archive.replace(name,replace_ia4(old,0,Image.new('RGBA',(r['width'],r['height'])))))
    # The menu makes every pane in the selected language group visible again.
    # Give the moved native Mii logo its own texture and blank the original
    # logo slot; pane visibility alone cannot hide the duplicate at runtime.
    logo='arc/timg/miiLogo_00.tpl';old_logo=archive.get(logo)
    archive=ChannelArchive(archive.replace('arc/timg/st_alf_e_00.tpl',old_logo))
    r=texture_records(old_logo)[0]
    archive=ChannelArchive(archive.replace(logo,replace_ia4(old_logo,0,Image.new('RGBA',(r['width'],r['height'])))))
    for slot,(_, (text,x)) in enumerate(selected.items()):
        image=Image.new('RGBA',(48,48));draw=ImageDraw.Draw(image);font=ImageFont.truetype(str(font_path),38);font.set_variation_by_axes([700])
        l,t,r,b=draw.textbbox((0,0),text,font=font,stroke_width=1)
        draw.text(((48-(r-l))/2-l,(48-(b-t))/2-t),text,font=font,fill='white',stroke_width=1,stroke_fill='black')
        archive=ChannelArchive(archive.replace('arc/timg/'+sprites[slot],replace_ia4(ia4_canvas(48,48),0,image)))
    seen=set()
    for i,s in enumerate(sections):
        if s[:4]not in[b'pic1',b'pan1']:continue
        name=s[12:28].split(b'\0')[0].decode('ascii');s=bytearray(s)
        if name in['N_UsEnLogo_00','N_UsEnLogo_01']:struct.pack_into('>f',s,0x24,0.0)
        if name=='P_UsEnMii_00':s[8]&=0xfe
        if name.startswith('P_UsEnFont_'):
            number=int(name.rsplit('_',1)[1])
            if number==0:
                x,y,w,h,texture=-115.0,-1.0,97.0,60.0,'st_alf_e_00.tpl'
            elif number in selected:
                text,x=selected[number];y,w,h=0.0,42.0,42.0;texture=sprites[list(selected).index(number)]
            else:
                s[8]&=0xfe
                struct.pack_into('>H',mat,materials[name]+0x40,textures.index('st_alf_-_00.tpl'))
                sections[i]=bytes(s);continue
            struct.pack_into('>ff',s,0x24,float(x),float(y));struct.pack_into('>ff',s,0x44,w,h)
            if s[0x5e]!=1:raise ValueError('Unexpected banner title texture coordinates')
            struct.pack_into('>8f',s,0x60,0,0,1,0,0,1,1,1)
            struct.pack_into('>H',mat,materials[name]+0x40,textures.index(texture));seen.add(number)
        sections[i]=bytes(s)
    if seen!={0,*selected}:raise ValueError('Animated Korean title pane identity')
    sections[mi]=bytes(mat)
    return ChannelArchive(archive.replace(path,rebuild_layout(layout,sections)))


TITLE_W,TITLE_H=44,42   # syllable cell; the English capitals are 45x41


def _heavy_syllable(text, font_path, cell=(TITLE_W,TITLE_H), outline=2, bold=1, rim=0, weight=900):
    """Original banner letter style: very heavy black glyph, white outline, cell filled.

    Drawn 4x supersampled, then reduced to the exact pane size so the texture
    maps 1:1 (no stretch). `rim` adds a thin dark edge outside the white
    outline, like the Mii logo's own outer edge.
    """
    from PIL import Image, ImageDraw, ImageFont
    scale=4;w,h=cell[0]*scale,cell[1]*scale;outline*=scale;bold=round(bold*scale);rim*=scale;edge=outline+bold+rim
    probe=ImageDraw.Draw(Image.new('L',(1,1)))
    for size in range(h,10,-2):
        font=ImageFont.truetype(str(font_path),size);font.set_variation_by_axes([weight])
        l,t,r,b=probe.textbbox((0,0),text,font=font,stroke_width=edge)
        if r-l<=w-2*scale and b-t<=h-2*scale:break  # 1px margin keeps the outline inside
    x=(w-(r-l))/2-l;y=(h-(b-t))/2-t;image=Image.new('RGBA',(w,h));draw=ImageDraw.Draw(image)
    if rim:draw.text((x,y),text,font=font,fill=(40,40,40),stroke_width=edge,stroke_fill=(40,40,40))
    draw.text((x,y),text,font=font,fill='white',stroke_width=outline+bold,stroke_fill='white')
    draw.text((x,y),text,font=font,fill='black',stroke_width=bold,stroke_fill='black')
    return image.resize(cell,Image.LANCZOS)


def _clean_syllable(text, font_path, cell=(TITLE_W,TITLE_H), outline=2.5, bold=.5, rim=1.0, weight=800, margin=1.0, close=0.0):
    """Revision 28: the v21 letter style (black body, white outline, dark rim) without its defects.

    v21 drew three PIL strokes; the variable font's overlapping contours were stroked inside the
    glyph, leaving white/grey seams through the black strokes (e.g. 널), and the 1 px margin was
    measured before the LANCZOS reduction, so outlines touched or crossed the tile edge. Here the
    glyph is filled ONCE (overlapping contours fill without seams) and body, outline and rim are
    grown from that single mask by round dilation at 8x; the font size is chosen so the rim keeps
    `margin` px of clear border after reduction. Values are pre-rounded to the 4-bit IA4 grid.
    """
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    s = 8
    W, H = cell[0] * s, cell[1] * s
    thr = int(round(255 * 0.0228))          # Phi(-2): blur sigma r/2 thresholded here grows the edge by ~r

    def grow(mask, r):
        if r <= 0:
            return mask
        return mask.filter(ImageFilter.GaussianBlur(r / 2.0)).point(lambda v: 255 if v >= thr else 0)

    edge = (bold + outline + rim) * s
    pad = (margin + 0.75) * s               # reduction spreads ink by up to ~0.75 px
    font = None
    for size in range(H, 10, -2):
        font = ImageFont.truetype(str(font_path), size)
        font.set_variation_by_axes([weight])
        l, t, r, b = font.getbbox(text)
        if (r - l) + 2 * edge <= W - 2 * pad and (b - t) + 2 * edge <= H - 2 * pad:
            break
    fill = Image.new('L', (W, H))
    ImageDraw.Draw(fill).text(((W - (r - l)) / 2 - l, (H - (b - t)) / 2 - t), text, font=font, fill=255)
    body = grow(fill.point(lambda v: 255 if v >= 128 else 0), bold * s)
    if close > 0:
        # closing: gaps between strokes narrower than ~2*close px become body (they would
        # otherwise render as grey hairlines once reduced); wider gaps stay clean white.
        from PIL import ImageChops
        grown = grow(body, close * s)
        body = ImageChops.invert(grow(ImageChops.invert(grown), close * s))
    white = grow(body, outline * s)
    rimmask = grow(white, rim * s)
    image = Image.new('RGBA', (W, H), (40, 40, 40, 0))
    image.paste((40, 40, 40, 255), (0, 0), rimmask)
    image.paste((255, 255, 255, 255), (0, 0), white)
    image.paste((0, 0, 0, 255), (0, 0), body)
    small = image.resize(cell, Image.Resampling.LANCZOS)
    q = lambda v: int(round(v * 15 / 255)) * 17
    r_, g_, b_, a_ = small.split()
    gray = r_.point(q)
    out = Image.merge('RGBA', (gray, gray, gray, a_.point(q)))
    bbox = out.split()[3].getbbox()
    if bbox and (bbox[0] < 1 or bbox[1] < 1 or bbox[2] > cell[0] - 1 or bbox[3] > cell[1] - 1):
        raise ValueError(f'syllable {text} touches its tile edge: {bbox}')
    return out


def animated_korean_title_v20(archive, font_path, cell=(TITLE_W,TITLE_H), overlap=-3, gap=8, drop=0.0, row2_y=None, glyph=dict(), renderer=None):
    """Korean syllables in the original letter panes, keeping their animation tracks.

    Row 1 is the Mii logo plus 콘테스트, row 2 is 채널, each centred like the
    English rows. Unused letter panes are hidden and point at the blank sprite.
    """
    from PIL import Image
    from .votes_visual import _materials, _textures
    path='arc/blyt/banner.brlyt';layout=archive.get(path);sections=layout_sections(layout)
    mi=next(i for i,s in enumerate(sections)if s[:4]==b'mat1')
    mat=bytearray(sections[mi]);materials=_materials(mat)
    textures=_textures(next(s for s in sections if s[:4]==b'txl1'))
    sprites=['st_alf_capC_00.tpl','st_alf_capO_00.tpl','st_alf_capR_00.tpl','st_alf_a_00.tpl','st_alf_c_00.tpl','st_alf_d_00.tpl']
    cw,ch=cell;step=cw-overlap;logo_w,logo_h=97.0,60.0
    row1=logo_w+gap+cw+3*step;left=-row1/2
    logo_x=left+logo_w/2;first=left+logo_w+gap+cw/2
    selected={1:('콘',first),2:('테',first+step),3:('스',first+2*step),4:('트',first+3*step),8:('채',-step/2),9:('널',step/2)}
    for name in list(archive.files):
        if '/st_alf_'in name and name.endswith('.tpl'):
            old=archive.get(name);r=texture_records(old)[0]
            archive=ChannelArchive(archive.replace(name,replace_ia4(old,0,Image.new('RGBA',(r['width'],r['height'])))))
    # The menu shows every pane of the selected language group: the Mii logo moves
    # to its own texture and the original logo slot is blanked (see the v19 notes).
    logo='arc/timg/miiLogo_00.tpl';old_logo=archive.get(logo)
    archive=ChannelArchive(archive.replace('arc/timg/st_alf_e_00.tpl',old_logo))
    r=texture_records(old_logo)[0]
    archive=ChannelArchive(archive.replace(logo,replace_ia4(old_logo,0,Image.new('RGBA',(r['width'],r['height'])))))
    for slot,(text,_) in enumerate(selected.values()):
        archive=ChannelArchive(archive.replace('arc/timg/'+sprites[slot],replace_ia4(ia4_canvas(cw,ch),0,(renderer or _heavy_syllable)(text,font_path,cell,**glyph))))
    seen=set()
    for i,s in enumerate(sections):
        if s[:4]not in[b'pic1',b'pan1']:continue
        name=s[12:28].split(b'\0')[0].decode('ascii');s=bytearray(s)
        if name in['N_UsEnLogo_00','N_UsEnLogo_01']:struct.pack_into('>f',s,0x24,0.0)
        if name=='N_UsEnLogo_01'and row2_y is not None:struct.pack_into('>f',s,0x28,row2_y)
        if name=='P_UsEnMii_00':s[8]&=0xfe
        if name.startswith('P_UsEnFont_'):
            number=int(name.rsplit('_',1)[1])
            if number==0:
                x,y,w,h,texture=logo_x,-1.0,logo_w,logo_h,'st_alf_e_00.tpl'
            elif number in selected:
                text,x=selected[number];y,w,h=(-drop if number<8 and drop else 0.0),float(cw),float(ch);texture=sprites[list(selected).index(number)]
            else:
                s[8]&=0xfe
                struct.pack_into('>H',mat,materials[name]+0x40,textures.index('st_alf_-_00.tpl'))
                sections[i]=bytes(s);continue
            struct.pack_into('>ff',s,0x24,float(x),float(y));struct.pack_into('>ff',s,0x44,w,h)
            if s[0x5e]!=1:raise ValueError('Unexpected banner title texture coordinates')
            struct.pack_into('>8f',s,0x60,0,0,1,0,0,1,1,1)
            struct.pack_into('>H',mat,materials[name]+0x40,textures.index(texture));seen.add(number)
        sections[i]=bytes(s)
    if seen!={0,*selected}:raise ValueError('Animated Korean title pane identity')
    sections[mi]=bytes(mat)
    return ChannelArchive(archive.replace(path,rebuild_layout(layout,sections)))


def korean_menu_art(content, font_path, title_style=19):
    load_library()
    from PIL import Image, ImageDraw, ImageFont
    from libWiiPy.archive import decompress_lz77
    def caption(size):
        image = Image.new('RGBA', size)
        draw = ImageDraw.Draw(image)
        for text, y, px in [('Mii', 0, 27), ('콘테스트', 29, 18), ('채널', 47, 12)]:
            font = ImageFont.truetype(str(font_path), px)
            font.set_variation_by_axes([700])
            box = draw.textbbox((0, 0), text, font=font)
            x = (size[0]-(box[2]-box[0]))/2-box[0]
            draw.text((x, y-box[1]), text, font=font, fill='white', stroke_width=1, stroke_fill='black')
        return image
    outer = ChannelArchive(content[0x640:]); records = []
    for name in ['meta/banner.bin', 'meta/icon.bin']:
        wrapped = outer.get(name)
        if wrapped[:4] != b'IMD5' or wrapped[16:32] != hashlib.md5(wrapped[32:]).digest():
            raise ValueError('Original menu artwork integrity')
        original = ChannelArchive(decompress_lz77(wrapped[32:])); archive = original
        layout_name = 'arc/blyt/' + ('banner' if 'banner' in name else 'icon') + '.brlyt'
        layout = archive.get(layout_name); sections = layout_sections(layout); groups = 0
        for i, section in enumerate(sections):
            if section[:4] == b'grp1' and section[8:24].split(b'\0')[0] == b'ENG':
                section = bytearray(section); section[8:24] = b'KOR'+bytes(13); groups += 1
                sections[i] = bytes(section)
        if groups != 1: raise ValueError('Expected single English menu group')
        archive = ChannelArchive(archive.replace(layout_name, rebuild_layout(layout, sections)))
        if 'banner' in name:
            if title_style>=21:
                # Revision 21+: syllables sized to the Mii logo (54x52), tighter spacing,
                # dark rim like the logo's outer edge; row 2 moved down for the taller cells.
                # Revision 28+: same geometry, seam-free glyphs that keep a clear border.
                # Revision 30+: weight 700, 2.0 px outline, no extra bold, 0.6 px closing: internal gaps
                # read as clean white lines instead of grey hairlines (v29 still showed some).
                glyph=dict(outline=2.0,bold=0,rim=1,weight=700,close=.6)if title_style>=30 else dict(outline=2.5,bold=.5,rim=1,weight=800)
                archive=animated_korean_title_v20(archive,font_path,cell=(54,52),overlap=6,gap=6,drop=3.0,row2_y=28.0,glyph=glyph,renderer=_clean_syllable if title_style>=28 else None)
            else:
                archive=(animated_korean_title_v20 if title_style>=20 else animated_korean_title)(archive,font_path)
        else:
            path = 'arc/timg/stMcLogoUsEn.tpl'
            archive = ChannelArchive(archive.replace(path, replace_ia4(ia4_canvas(112,65), 0, caption((112,65)))))
        archive = ChannelArchive(archive.compact())
        if any(archive.get(p) != original.get(p) for p in archive.files if p.endswith('.brlan')):
            raise ValueError('Menu animation changed')
        payload = b'LZ77'+compress_lz10(archive.data)
        if decompress_lz77(payload) != archive.data: raise ValueError('Menu compression mismatch')
        wrapper = b'IMD5'+len(payload).to_bytes(4,'big')+bytes(8)+hashlib.md5(payload).digest()+payload
        outer = ChannelArchive(outer.replace(name, wrapper))
        records.append(dict(file=name,uncompressed_size=len(archive.data),KOR_group=True,animation_preserved=True))
    prefix = bytearray(content[:0x640])
    for row in records:
        struct.pack_into('>I',prefix,0x40+(0x50 if 'banner' in row['file'] else 0x4c),row['uncompressed_size'])
    return bytes(prefix)+outer.compact(), records
