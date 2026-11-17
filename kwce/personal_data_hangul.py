"""Reference 2-beolsik (두벌식) Hangul composition for the Korean SPD keyboard.

The C implementation in kwce/personal_data_fork.py (kwce_hangul.c) follows
these functions step by step; tests drive both the tables and this model.
Text is a list of code points; `composing` says whether the last character
may still be extended by the next jamo (typed in this keyboard session).
"""
SBASE,LCOUNT,VCOUNT,TCOUNT=0xAC00,19,21,28
CHO='ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
JUNG='ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'
JONG=' ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ'  # index 0 = no final
VOWEL_PAIRS={('ㅗ','ㅏ'):'ㅘ',('ㅗ','ㅐ'):'ㅙ',('ㅗ','ㅣ'):'ㅚ',('ㅜ','ㅓ'):'ㅝ',('ㅜ','ㅔ'):'ㅞ',('ㅜ','ㅣ'):'ㅟ',('ㅡ','ㅣ'):'ㅢ'}
FINAL_PAIRS={('ㄱ','ㅅ'):'ㄳ',('ㄴ','ㅈ'):'ㄵ',('ㄴ','ㅎ'):'ㄶ',('ㄹ','ㄱ'):'ㄺ',('ㄹ','ㅁ'):'ㄻ',('ㄹ','ㅂ'):'ㄼ',('ㄹ','ㅅ'):'ㄽ',
             ('ㄹ','ㅌ'):'ㄾ',('ㄹ','ㅍ'):'ㄿ',('ㄹ','ㅎ'):'ㅀ',('ㅂ','ㅅ'):'ㅄ'}
SPLIT_VOWEL={v:k for k,v in VOWEL_PAIRS.items()};SPLIT_FINAL={v:k for k,v in FINAL_PAIRS.items()}
# QWERTY row/column -> (jamo, shifted jamo); rows 1-3 of the libwiigui keyboard.
LAYOUT={1:'ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔ',2:'ㅁㄴㅇㄹㅎㅗㅓㅏㅣ',3:'ㅋㅌㅊㅍㅠㅜㅡ'}
SHIFTED={'ㅂ':'ㅃ','ㅈ':'ㅉ','ㄷ':'ㄸ','ㄱ':'ㄲ','ㅅ':'ㅆ','ㅐ':'ㅒ','ㅔ':'ㅖ'}

def is_syllable(c):return SBASE<=ord(c)<SBASE+LCOUNT*VCOUNT*TCOUNT
def key(row,col,shifted=False):
    """Jamo for libwiigui keyboard row/col in Hangul mode, or None (key keeps ASCII)."""
    layout=LAYOUT.get(row,'')
    if not 0<=col<len(layout):return None
    j=layout[col];return SHIFTED.get(j,j)if shifted else j
def decompose(c):
    s=ord(c)-SBASE;return s//(VCOUNT*TCOUNT),(s//TCOUNT)%VCOUNT,s%TCOUNT
def compose(l,v,t=0):return chr(SBASE+(l*VCOUNT+v)*TCOUNT+t)

def type_jamo(text,composing,j,maxlen):
    """Apply one jamo; maxlen counts the terminator like GuiKeyboard (len < max-1)."""
    text=list(text);room=len(text)<maxlen-1
    last=text[-1]if text and composing else None
    if j in CHO or j in JONG[1:]:
        if last and is_syllable(last):
            l,v,t=decompose(last)
            if t==0 and j in JONG[1:]:
                text[-1]=compose(l,v,JONG.index(j));return text,True
            if t and (JONG[t],j)in FINAL_PAIRS:
                text[-1]=compose(l,v,JONG.index(FINAL_PAIRS[JONG[t],j]));return text,True
        if room:text.append(j);return text,True
        return text,composing
    if j not in JUNG:raise ValueError('Not a jamo')
    if last:
        if last in CHO:
            text[-1]=compose(CHO.index(last),JUNG.index(j));return text,True
        if is_syllable(last):
            l,v,t=decompose(last)
            if t==0:
                if (JUNG[v],j)in VOWEL_PAIRS:
                    text[-1]=compose(l,JUNG.index(VOWEL_PAIRS[JUNG[v],j]));return text,True
            elif room:
                final=JONG[t]
                keep,move=SPLIT_FINAL.get(final,('',final))
                text[-1]=compose(l,v,JONG.index(keep)if keep else 0)
                text.append(compose(CHO.index(move),JUNG.index(j)));return text,True
            else:return text,composing
        elif last in JUNG and (last,j)in VOWEL_PAIRS:
            text[-1]=VOWEL_PAIRS[last,j];return text,True
    if room:text.append(j);return text,True
    return text,composing

def backspace(text,composing):
    text=list(text)
    if not text:return text,False
    if not composing:return text[:-1],False
    last=text[-1]
    if is_syllable(last):
        l,v,t=decompose(last)
        if t:
            keep=SPLIT_FINAL.get(JONG[t],('',))[0]
            text[-1]=compose(l,v,JONG.index(keep)if keep else 0)
        elif JUNG[v]in SPLIT_VOWEL:text[-1]=compose(l,JUNG.index(SPLIT_VOWEL[JUNG[v]][0]))
        else:text[-1]=CHO[l]
        return text,True
    if last in SPLIT_VOWEL:text[-1]=SPLIT_VOWEL[last][0];return text,True
    return text[:-1],False

def type_sequence(keys,maxlen=32,start=''):
    """keys: jamo, ' ' (space, commits), '\b' (backspace) or other characters."""
    text,composing=list(start),False
    for k in keys:
        if k=='\b':text,composing=backspace(text,composing)
        elif k in CHO or k in JUNG or k in JONG[1:]:text,composing=type_jamo(text,composing,k,maxlen)
        else:
            if len(text)<maxlen-1:text.append(k)
            composing=False
    return ''.join(text)

def c_tables():
    """C initializers shared with the device keyboard (UTF-16 code units)."""
    def arr(name,chars):return f'static const unsigned short {name}[{len(chars)}] = {{'+', '.join(f'0x{ord(c):04x}'for c in chars)+'};'
    pairs=lambda m:'{'+', '.join(f'{{0x{ord(a):04x}, 0x{ord(b):04x}, 0x{ord(c):04x}}}'for(a,b),c in m.items())+'}'
    rows=[]
    for row in(1,2,3):
        rows.append('{'+', '.join(f'{{0x{ord(c):04x}, 0x{ord(SHIFTED.get(c,c)):04x}}}'for c in LAYOUT[row])+'}')
    return '\n'.join([arr('KWCE_CHO',CHO),arr('KWCE_JUNG',JUNG),arr('KWCE_JONG',JONG.replace(' ','\0')),
        f'static const unsigned short KWCE_VOWEL_PAIRS[{len(VOWEL_PAIRS)}][3] = {pairs(VOWEL_PAIRS)};',
        f'static const unsigned short KWCE_FINAL_PAIRS[{len(FINAL_PAIRS)}][3] = {pairs(FINAL_PAIRS)};',
        'static const unsigned short KWCE_ROW1[10][2] = '+rows[0]+';','static const unsigned short KWCE_ROW2[9][2] = '+rows[1]+';',
        'static const unsigned short KWCE_ROW3[7][2] = '+rows[2]+';'])
