/* Bounded VFF inspection. Article text is neither interpreted nor exported. */
#include "cache.h"
#include <stdlib.h>
#include <string.h>

static uint32_t be32(const unsigned char *p) {
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static unsigned le16(const unsigned char *p) { return (unsigned)p[0]|((unsigned)p[1]<<8); }
static uint32_t le32(const unsigned char *p) { return (uint32_t)le16(p)|((uint32_t)le16(p+2)<<16); }

static int lz_unpack(const unsigned char *in,size_t n,unsigned char *out,size_t want) {
    if(n<4 || in[0]!=0x10) return 0;
    size_t full=(size_t)in[1]|((size_t)in[2]<<8)|((size_t)in[3]<<16);
    if(full!=want || full>8u*1024u*1024u)return 0;
    size_t i=4,o=0;
    while(o<want) {
        if(i>=n)return 0;
        unsigned flags=in[i++];
        for(unsigned bit=0;bit<8 && o<want;bit++) {
            if(!(flags&(0x80u>>bit))) { if(i>=n)return 0;out[o++]=in[i++]; }
            else {
                if(i+2>n)return 0;
                unsigned a=in[i++],b=in[i++];size_t count=(a>>4)+3,disp=((a&15u)<<8|b)+1;
                if(disp>o)return 0;
                while(count-- && o<want) { out[o]=out[o-disp];o++; }
            }
        }
    }
    return 1;
}


static uint32_t crc32_bytes(const unsigned char *p,size_t n) {
    uint32_t crc=0xffffffffu;
    while(n--) {
        crc^=*p++;
        for(unsigned bit=0;bit<8;bit++)crc=(crc>>1)^((0u-(crc&1u))&0xedb88320u);
    }
    return crc^0xffffffffu;
}


/* Mirrors the channel header checks, excluding article content and cross-hour checks. */
static int bad_structure(const unsigned char *h,size_t n) {
    if(n<104 || be32(h)>>16 || be32(h+0x30)>=n || (be32(h+0x30)&1) || h[0x2d]>=2 || h[0x2e]>=2)return 1;
    unsigned k=0;
    while(k<16 && h[0x1c+k]!=0xff) { if(h[0x1c+k]>=7)return 1;k++; }
    if(k==16)return 1;
    static const unsigned counts[]={0x34,0x3c,0x44,0x4c,0x54};
    static const unsigned widths[]={12,44,28,16,24};
    for(unsigned i=0;i<5;i++) {
        uint32_t count=be32(h+counts[i]),offset=be32(h+counts[i]+4);
        if((offset&3) || (uint64_t)offset+(uint64_t)count*widths[i]>n)return 1;
    }
    return 0;
}


static void check_entries(const unsigned char *h,size_t n,news_cache_summary *o) {
    uint32_t count=be32(h+0x34),off=be32(h+0x38);
    for(uint32_t i=0;i<count;i++) {
        const unsigned char *e=h+off+i*12;uint32_t name=be32(e),items=be32(e+4),table=be32(e+8);
        if((table&3) || (i && !name) || name>=n || (name&1) || (uint64_t)table+(uint64_t)items*8>n){o->topic_bad++;break;}
    }
    count=be32(h+0x44);off=be32(h+0x48);
    for(uint32_t i=0;i<count;i++) {
        const unsigned char *e=h+off+i*28;uint32_t a=be32(e+4),b=be32(e+8),c=be32(e+12),d=be32(e+16),f=be32(e+20),g=be32(e+24);
        if(e[0]>=7 || !e[1] || e[1]>=7 || ((a==0)==(e[0]==0)) || ((b==0)==(e[0]==0)) ||
           (uint64_t)a+b>n || (uint64_t)c+d>n || (d&1) || (!c && d) || (uint64_t)f+g>n || (g&1) || (!f && g)){o->source_bad++;break;}
    }
    count=be32(h+0x4c);off=be32(h+0x50);
    for(uint32_t i=0;i<count;i++){uint32_t p=be32(h+off+i*16);if(!p || p>=n || (p&1)){o->location_bad++;break;}}
    count=be32(h+0x54);off=be32(h+0x58);
    for(uint32_t i=0;i<count;i++) {
        const unsigned char *e=h+off+i*24;uint32_t a=be32(e),b=be32(e+4),c=be32(e+8),d=be32(e+12),f=be32(e+16),g=be32(e+20);
        if((uint64_t)a+b>n || (b&1) || (!a && b) || (uint64_t)c+d>n || (d&1) || (!c && d) || !f || !g || (uint64_t)f+g>n){o->image_bad++;break;}
    }
}


/* Store only numeric metadata, never copy article strings or image bytes. */
FILE *news_snapshot_stream;
void news_cache_set_snapshot(FILE *out) { news_snapshot_stream=out; }
static void snap_char(int c){fputc(c,news_snapshot_stream);}
static void snap_num(uint32_t x){char b[10];unsigned k=0;do {b[k++]=(char)('0'+x%10);x/=10;}while(x);while(k)snap_char(b[--k]);}
static void snap_word(uint32_t x){snap_char(' ');snap_num(x);}
static void snap_segment(const unsigned char *data,uint32_t off,uint32_t length){
    snap_char('S');snap_word(off);snap_word(length);
    for(uint32_t j=0;j<length;j+=4)snap_word(be32(data+off+j));
    snap_char('\n');
}
static void snapshot_header(const unsigned char *data,size_t n,const unsigned char *entry) {
    if(!news_snapshot_stream || entry[8]<'0' || entry[8]>'9' || entry[9]<'0' || entry[9]>'9' || entry[10]!=' ')return;
    uint32_t hour=(entry[8]-'0')*10u+entry[9]-'0';if(hour>=24)return;
    snap_char('F');snap_word(hour);snap_word((uint32_t)n);snap_char('\n');
    snap_segment(data,0,104);
    static const unsigned offs[]={0x34,0x3c,0x44,0x4c,0x54}, widths[]={12,44,28,16,24};
    for(unsigned i=0;i<5;i++)snap_segment(data,be32(data+offs[i]+4),be32(data+offs[i])*widths[i]);
    uint32_t topics=be32(data+0x34),base=be32(data+0x38);
    for(uint32_t i=0;i<topics;i++) {
        uint32_t count=be32(data+base+i*12+4),offset=be32(data+base+i*12+8);
        if(!(offset&3) && (uint64_t)offset+(uint64_t)count*8<=n)snap_segment(data,offset,count*8);
    }
    snap_char('E');snap_char('\n');
}

int news_cache_inspect(const unsigned char *data,size_t bytes,uint32_t now_unix,
                       news_cache_summary *out) {
    if(!data || !out)return -1;
    memset(out,0,sizeof(*out));
    if(bytes<32 || memcmp(data,"VFF ",4) || data[4]!=0xfe || data[5]!=0xff)return -1;
    uint32_t volume=be32(data+8);unsigned cluster=(((unsigned)data[12]<<8)|data[13])*16u;
    if(cluster!=512 || volume%512 || volume>8u*1024u*1024u || volume>bytes)return -1;
    unsigned total=volume/512;if(total<=16 || total>=65525)return -1;
    int fat16=total>=4085;size_t table=((fat16?total*2u:((total+1u)/2u)*3u)+511u)/512u*512u;
    size_t root=32u+2u*table,start=root+4096u;
    if(start>bytes || memcmp(data+32,data+32+table,table))return -1;
    unsigned clusters=total-(1u+(unsigned)(2u*table/512u)+8u)+2u;
    out->valid_vff=1;
    for(size_t at=root;at+32<=start;at+=32) {
        const unsigned char *entry=data+at;
        if(entry[0]==0)break;
        if(entry[0]==0xe5 || (entry[11]&0x18) || entry[11]==15)continue;
        out->entries++;
        unsigned cur=le16(entry+26);uint32_t size=le32(entry+28);
        if(!size || size>4u*1024u*1024u){out->unsupported_or_invalid++;continue;}
        unsigned char *packed=malloc(size);if(!packed)return -2;
        size_t copied=0;unsigned steps=0;int valid=1;
        while(copied<size) {
            if(cur<2 || cur>=clusters || ++steps>clusters){valid=0;break;}
            size_t pos=start+(size_t)(cur-2u)*512u,chunk=size-copied;
            if(chunk>512)chunk=512;
            if(pos+chunk>bytes){valid=0;break;}
            memcpy(packed+copied,data+pos,chunk);copied+=chunk;
            size_t fp=32u+(fat16?2u*cur:(size_t)cur*3u/2u);
            if(fp+2>32u+table){valid=0;break;}
            unsigned value=le16(data+fp);
            cur=fat16?(value>=0xfff8u?0xfffu:value):((cur&1u)?value>>4:value)&0xfffu;
        }
        size_t full=size>=4 ? (size_t)packed[1]|((size_t)packed[2]<<8)|((size_t)packed[3]<<16) : 0;
        unsigned char *unpacked=NULL;
        if(valid && copied==size && cur>=0xff8u && full>=104 && full<=8u*1024u*1024u)
            unpacked=malloc(full);
        if(unpacked && lz_unpack(packed,size,unpacked,full) && be32(unpacked)==512 &&
           be32(unpacked+4)>=104 && be32(unpacked+4)<=8u*1024u*1024u) {
            const unsigned char *hdr=unpacked;
            uint32_t epoch_minutes=now_unix>=946684800u?(now_unix-946684800u)/60u:0;
            uint32_t updated=be32(hdr+12),expires=be32(hdr+16),clock_guard=be32(hdr+24);
            out->parsed++;out->country_49+=hdr[20]==49;out->country_136+=hdr[20]==136;
            out->language_english+=hdr[44]==1;
            if(be32(hdr+4)==full && be32(hdr+8)==crc32_bytes(hdr+12,full-12))out->crc_ok++;
            else out->crc_bad++;
            int invalid_structure=bad_structure(hdr,full);
            out->structural_bad+=invalid_structure;
            if(!invalid_structure) { check_entries(hdr,full,out);snapshot_header(hdr,full,entry); }
            out->language_empty+=hdr[0x1c]==0xff;
            if(epoch_minutes>=540 && expires<epoch_minutes-540)out->expired_utc9++;
            if(expires<epoch_minutes)out->expired++;else out->fresh++;
            if(clock_guard>epoch_minutes+1440u || updated>epoch_minutes+1440u)out->future++;
        } else out->unsupported_or_invalid++;
        free(unpacked);
        free(packed);
    }
    return 0;
}
