/* Sanitary post-run snapshot. No raw records, URLs, keys, IDs or save data leave NAND. */
#include <gccore.h>
#include <ogc/conf.h>
#include <ogc/isfs.h>
#include <malloc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include "kwce_diagnostics.h"
#include "kwce_diag_builds.h"

#define DL_BYTES 0xf800u
static unsigned int be16(const unsigned char *p) { return ((unsigned)p[0]<<8)|p[1]; }
static unsigned int be32(const unsigned char *p) { return ((unsigned)p[0]<<24)|((unsigned)p[1]<<16)|((unsigned)p[2]<<8)|p[3]; }
static int phase_valid(const char *p) { return !strcmp(p,"before") || !strcmp(p,"after_news") || !strcmp(p,"after_room") || !strcmp(p,"other"); }
static const char *target(unsigned int hi,unsigned int lo) {
    if (hi==0x00010002 && lo==0x48414745) return "news";
    if (hi==0x00010001 && lo==0x4843494a) return "wii_room";
    if (hi==0x00010002 && lo==0x48414645) return "forecast";
    return NULL;
}
static const char *news_route(const unsigned char *p) {
    static const char a[]="http://news.wiilink.ca/v2/1/136/news.bin";
    static const char b[]="http://news.wiilink.ca/v2/1/049/news.bin";
    if (!memcmp(p,a,sizeof a)) return "known_136";
    if (!memcmp(p,b,sizeof b)) return "known_049";
    return "other_or_unrecognized";
}
static void marker(FILE *f,const char *stage) { fprintf(f,"stage=%s\n",stage); fflush(f); }
static const char *installed_build(u64 tid) {
    u32 size=0;if (ES_GetStoredTMDSize(tid,&size)<0 || size<0x1e4 || size>0x10000) return "unavailable";
    signed_blob *blob=memalign(32,(size+63u)&~63u);if (!blob) return "allocation_failed";
    if (ES_GetStoredTMD(tid,blob,size)<0) { free(blob);return "unavailable"; }
    const unsigned char *p=(const unsigned char*)blob;u32 count=be16(p+0x1de);const char *answer="unknown";
    if (count>0 && 0x1e4u+36u*count<=size) {
        for (u32 i=0;i<count;i++) {
            const unsigned char *entry=p+0x1e4+36*i;
            if (be16(entry+4)!=1) continue;
            const unsigned char *digest=entry+16;
            if (tid==0x0001000248414745ULL && !memcmp(digest,kwce_news22_digest,20)) answer="news_r22";
            else if (tid==0x0001000248414745ULL && !memcmp(digest,kwce_news20_digest,20)) answer="news_r20";
            else if (tid==0x000100014843494aULL && !memcmp(digest,kwce_room51_digest,20)) answer="room_r51";
            break;
        }
    }
    free(blob);return answer;
}
static void dir_status(FILE *f,const char *label,const char *path) {
    u32 count=0; s32 rc=ISFS_ReadDir(path,NULL,&count);
    fprintf(f,"%s_dir_result=%d\n",label,rc);
    if (rc>=0) fprintf(f,"%s_dir_entries=%u\n",label,count);
    fflush(f);
}
static void vff_status(FILE *f) {
    const char *path="/title/00010002/48414745/data/wc24dl.vff";
    s32 fd=ISFS_Open(path,ISFS_OPEN_READ);
    fprintf(f,"news_cache_open_result=%d\n",fd<0?fd:0);
    if (fd>=0) {
        fstats *stat=memalign(32,sizeof(fstats));
        if (stat) { s32 rc=ISFS_GetFileStats(fd,stat); fprintf(f,"news_cache_stat_result=%d\n",rc); if (rc>=0) fprintf(f,"news_cache_bytes=%u\n",stat->file_length); free(stat); }
        else fprintf(f,"news_cache_stat_result=allocation_failed\n");
        ISFS_Close(fd);
    }
    fflush(f);
}
static void tasks(FILE *f) {
    unsigned char *data=memalign(32,DL_BYTES);
    if (!data) { fprintf(f,"wc24_list_result=allocation_failed\n");return; }
    s32 fd=ISFS_Open("/shared2/wc24/nwc24dl.bin",ISFS_OPEN_READ);
    fprintf(f,"wc24_list_open_result=%d\n",fd<0?fd:0);fflush(f);
    if (fd<0) { free(data);return; }
    s32 len=ISFS_Read(fd,data,DL_BYTES);ISFS_Close(fd);
    fprintf(f,"wc24_list_read_result=%d\n",len);fflush(f);
    if (len!=(s32)DL_BYTES || be32(data)!=0x5763446c || be32(data+4)!=1) { fprintf(f,"wc24_list_format=invalid_or_short\n"); free(data);return; }
    fprintf(f,"wc24_list_format=recognized_v1\n");
    unsigned n=0;
    for (unsigned i=0;i<120;i++) {
        const unsigned char *e=data+2048+512*i; const char *name=target(be32(e+8),be32(e+12));
        if (!name) continue;
        fprintf(f,"task_%u_channel=%s\n",n,name);
        fprintf(f,"task_%u_flags=%u\n",n,be32(e+4));
        fprintf(f,"task_%u_error_count=%u\n",n,be16(e+26));
        fprintf(f,"task_%u_error_code=%d\n",n,(s32)be32(e+32));
        fprintf(f,"task_%u_remaining_downloads=%u\n",n,be16(e+24));
        fprintf(f,"task_%u_retry_minutes=%u\n",n,be16(e+30));
        fprintf(f,"task_%u_subtask_mask=%u\n",n,be32(e+40));
        fprintf(f,"task_%u_last_download_minutes_2000=%u\n",n,be32(e+48));
        if (!strcmp(name,"news")) fprintf(f,"task_%u_route=%s\n",n,news_route(e+180));
        n++;
    }
    fprintf(f,"matched_task_count=%u\n",n);fflush(f);free(data);
}
int kwce_diagnostic_capture(const char *phase,int (*version_fn)(u64)) {
    if (!phase_valid(phase)) return -1;
    mkdir("sd:/kwce",0777);mkdir("sd:/kwce/diagnostics",0777);
    char path[96];FILE *f=NULL;
    for (unsigned i=1;i<=9999;i++) {
        snprintf(path,sizeof path,"sd:/kwce/diagnostics/diag-%04u.txt",i);
        FILE *old=fopen(path,"rb");if (old) { fclose(old);continue; }
        f=fopen(path,"wb");break;
    }
    if (!f) { printf("  Cannot create SD report.\n");return -1; }
    fprintf(f,"KWCE_DIAGNOSTIC_V1\nphase=%s\n",phase);marker(f,"start");
    fprintf(f,"wii_clock_unix=%lld\nios_version=%u\n",(long long)time(NULL),IOS_GetVersion());fflush(f);
    marker(f,"config");s32 c=CONF_Init();fprintf(f,"conf_init_result=%d\n",c);
    if (c>=0) { fprintf(f,"area=%d\nlanguage=%d\nwc24_enabled=%d\n",CONF_GetArea(),CONF_GetLanguage(),CONF_GetWiiConnect24()); }
    marker(f,"title_versions");
    fprintf(f,"news_installed_tmd_version=%d\n",version_fn(0x0001000248414745ULL));fflush(f);
    fprintf(f,"room_installed_tmd_version=%d\n",version_fn(0x000100014843494aULL));fflush(f);
    fprintf(f,"forecast_installed_tmd_version=%d\n",version_fn(0x0001000248414645ULL));fflush(f);
    marker(f,"installed_builds");
    fprintf(f,"news_installed_build=%s\n",installed_build(0x0001000248414745ULL));fflush(f);
    fprintf(f,"room_installed_build=%s\n",installed_build(0x000100014843494aULL));fflush(f);
    marker(f,"isfs_init");s32 init=ISFS_Initialize();fprintf(f,"isfs_init_result=%d\n",init);fflush(f);
    if (init>=0) {
        marker(f,"wc24_list");tasks(f);
        marker(f,"news_cache");vff_status(f);
        marker(f,"channel_directories");
        dir_status(f,"news","/title/00010002/48414745/data");
        dir_status(f,"room","/title/00010001/4843494a/data");
        ISFS_Deinitialize();
    }
    marker(f,"complete");int flush=fflush(f),error=ferror(f),closed=fclose(f);
    if (flush || error || closed) { printf("\n  SD report write failed; report may be incomplete.\n");return -1; }
    printf("\n  Saved: %s\n",path);
    printf("  Report is a post-run snapshot, not a live HTTP trace.\n");
    return 0;
}
