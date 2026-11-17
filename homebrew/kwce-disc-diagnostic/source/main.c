/* Read only Priiloader state comparison; writes only a new SD report. */
#include <gccore.h>
#include <ogc/isfs.h>
#include <fat.h>
#include <malloc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define LIMIT (512*1024)
static unsigned char *read_sd(const char *path,unsigned *size) {
    FILE *f=fopen(path,"rb"); if(!f)return NULL;
    if(fseek(f,0,SEEK_END)) {fclose(f);return NULL;}
    long n=ftell(f); if(n<=0 || n>LIMIT || fseek(f,0,SEEK_SET)) {fclose(f);return NULL;}
    unsigned char *p=malloc((size_t)n); if(!p) {fclose(f);return NULL;}
    if(fread(p,1,(size_t)n,f)!=(size_t)n) {free(p);fclose(f);return NULL;}
    fclose(f);*size=(unsigned)n;return p;
}
static unsigned char *read_nand(const char *path,unsigned *size,int *result) {
    s32 fd=ISFS_Open(path,ISFS_OPEN_READ);*result=fd;
    if(fd<0)return NULL;
    fstats *st=memalign(32,32); if(!st) {ISFS_Close(fd);*result=-10000;return NULL;}
    s32 rc=ISFS_GetFileStats(fd,st);unsigned n=st->file_length;free(st);
    if(rc<0 || n==0 || n>LIMIT) {ISFS_Close(fd);*result=rc<0?rc:-10001;return NULL;}
    unsigned aligned=(n+31u)&~31u;unsigned char *p=memalign(32,aligned);
    if(!p) {ISFS_Close(fd);*result=-10000;return NULL;}
    memset(p,0,aligned);rc=ISFS_Read(fd,p,aligned);ISFS_Close(fd);
    if(rc!=(s32)n) {free(p);*result=rc<0?rc:-10002;return NULL;}
    *size=n;*result=0;return p;
}
static int kwce_final_sections(const unsigned char *data,unsigned size) {
    const char *names[]={"[KWCE GC: Wii/GC save menu]","[KWCE GC: Japanese memory card encoding]",
        "[KWCE GC: Japanese save comments (CP932)]","[KWCE DVD: disc channel DVD player]"};
    const char *alternative="[KWCE GC: GC-only disc layout (DVD off)]";
    unsigned starts[4]={0},count=0;
    for(unsigned i=0;i<size;i++)if(data[i]=='[' && (i==0 || data[i-1]=='\n')) {
        starts[0]=starts[1];starts[1]=starts[2];starts[2]=starts[3];starts[3]=i;count++;
    }
    if(count<4)return 0;
    for(unsigned i=0;i<4;i++) {
        const char *s=names[i];unsigned n=(unsigned)strlen(s);unsigned at=starts[i];
        if(at+n<=size && !memcmp(data+at,s,n) && (at+n==size || data[at+n]=='\r' || data[at+n]=='\n'))continue;
        if(i!=3)return 0;
        n=(unsigned)strlen(alternative);
        if(at+n>size || memcmp(data+at,alternative,n) || (at+n<size && data[at+n]!='\r' && data[at+n]!='\n'))return 0;
    }
    return 1;
}
int main(void) {
    VIDEO_Init();void *fb=MEM_K0_TO_K1(SYS_AllocateFramebuffer(VIDEO_GetPreferredMode(NULL)));
    GXRModeObj *mode=VIDEO_GetPreferredMode(NULL);CON_Init(fb,20,20,mode->fbWidth,mode->xfbHeight,mode->fbWidth*VI_DISPLAY_PIX_SZ);
    VIDEO_Configure(mode);VIDEO_SetNextFramebuffer(fb);VIDEO_SetBlack(FALSE);VIDEO_Flush();VIDEO_WaitVSync();
    printf("KWCE Disc Diagnostic\n");
    if(!fatInitDefault()) {printf("SD unavailable.\n");goto wait;}
    mkdir("sd:/kwce-rc",0777);char path[96];FILE *out=NULL;
    for(int i=1;i<100;i++) {snprintf(path,sizeof path,"sd:/kwce-rc/disc-diag-%02d.txt",i);FILE *p=fopen(path,"rb");if(p) {fclose(p);continue;}out=fopen(path,"wb");break;}
    if(!out) {printf("Cannot create report.\n");goto wait;}
    fprintf(out,"format=kwce-disc-diag-v1\nios=%u\n",IOS_GetVersion());
    unsigned sn=0,nn=0,cn=0;int hack_rc=0,state_rc=0;
    unsigned char *sd=read_sd("sd:/apps/Priiloader/hacks_hash.ini",&sn);
    s32 init=ISFS_Initialize();fprintf(out,"isfs_init=%d\nsd_hacks_read=%d\n",(int)init,sd!=NULL);
    unsigned char *nand=NULL,*state=NULL;
    if(init>=0) {
        nand=read_nand("/title/00000001/00000002/data/hackshas.ini",&nn,&hack_rc);
        state=read_nand("/title/00000001/00000002/data/hacksh_s.ini",&cn,&state_rc);
        fprintf(out,"nand_hacks_read=%d\nnand_states_read=%d\n",hack_rc,state_rc);
        int matching=nand && sd && nn==sn && !memcmp(sd,nand,sn);
        if(nand && sd)fprintf(out,"nand_hacks_match_sd=%d\n",matching);
        if(state) {
            fprintf(out,"nand_state_bytes=%u\n",cn);
            unsigned sections=0;
            if(matching)for(unsigned i=0;i<sn;i++)if(sd[i]=='[' && (i==0 || sd[i-1]=='\n'))sections++;
            if(sections>=4 && kwce_final_sections(sd,sn) && (cn==sections || cn==sections*4)) {
                fprintf(out,"state_format=%s\n",cn==sections?"byte":"word_be");
                for(unsigned i=sections-4;i<sections;i++) {
                    unsigned value=cn==sections?state[i]:((unsigned)state[i*4]<<24)|((unsigned)state[i*4+1]<<16)|((unsigned)state[i*4+2]<<8)|state[i*4+3];
                    fprintf(out,"kwce_state_%u=%u\n",i-(sections-4),value);
                }
            } else if(matching)fputs("state_format=unrecognized\n",out);
        }
        ISFS_Deinitialize();
    }
    if(sd) {
        int dvd=0,gc=0; const char *d="[KWCE DVD: disc channel DVD player]",*g="[KWCE GC: GC-only disc layout (DVD off)]";
        for(unsigned i=0;i<sn;i++) {if(i+strlen(d)<=sn && !memcmp(sd+i,d,strlen(d)))dvd++;if(i+strlen(g)<=sn && !memcmp(sd+i,g,strlen(g)))gc++;}
        fprintf(out,"sd_profile_dvd=%d\nsd_profile_gc_only=%d\n",dvd,gc);
    }
    free(sd);free(nand);free(state);fputs("stage=complete\n",out);int bad=fflush(out)!=0 || ferror(out);if(fclose(out))bad=1;
    printf(bad?"Report write failed.\n":"Report saved. Reconnect SD to PC.\n");
wait:
    for(int i=0;i<300;i++)VIDEO_WaitVSync();
    return 0;
}
