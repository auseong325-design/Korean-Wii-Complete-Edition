/* Read-only, anonymous News/Forecast network comparison. No console IDs or data. */
#include <gccore.h>
#include <ogc/system.h>
#include <ogc/isfs.h>
#include <fat.h>
#include <network.h>
#include <errno.h>
#include <malloc.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include "cache.h"

/* IOS socket fcntl uses bit 2, unlike newlib's file O_NONBLOCK. */
#define KWCE_IOS_NONBLOCK 0x04

static volatile int init_done;
static volatile s32 init_result;

/* Read only: 0x14 is NWC24iGetUniversalTime, not either time-setting ioctl. */
static uint32_t read_kd_time(FILE *out) {
    s32 fd=IOS_Open("/dev/net/kd/time",0);
    fprintf(out,"kd_time_open=%d\n",fd<0?(int)fd:0);fflush(out);
    if(fd<0)return 0;
    u32 *words=memalign(32,32);uint32_t unix_time=0;
    if(words) {
        memset(words,0,32);
        s32 rc=IOS_Ioctl(fd,0x14,NULL,0,words,32);
        fprintf(out,"kd_time_ioctl=%d\n",(int)rc);
        if(rc>=0) {
            fprintf(out,"kd_time_result=%d\n",(int)(s32)words[0]);
            if((s32)words[0]==0) {
                uint64_t seconds=((uint64_t)words[1]<<32)|words[2];
                fprintf(out,"kd_time_seconds=%llu\n",(unsigned long long)seconds);
                if(seconds>=946684800ULL && seconds<4102444800ULL) unix_time=(uint32_t)seconds;
                else if(seconds<946684800ULL && seconds+946684800ULL<4102444800ULL)
                    unix_time=(uint32_t)(seconds+946684800ULL);
            }
        }
        fflush(out);free(words);
    }
    IOS_Close(fd);return unix_time;
}

static uint32_t read_kd_difference(FILE *out,const char *stage) {
    s32 fd=IOS_Open("/dev/net/kd/time",0);
    if(fd<0){fprintf(out,"kd_diff_%s=%d\n",stage,(int)fd);fflush(out);return 0;}
    uint32_t derived=0;
    u32 *words=memalign(32,32);
    if(words) {
        memset(words,0,32);
        s32 rc=IOS_Ioctl(fd,0x18,NULL,0,words,32);
        fprintf(out,"kd_diff_%s=%d\n",stage,rc<0?(int)rc:(int)(s32)words[0]);
        fflush(out);free(words);
    }
    IOS_Close(fd);return derived;
}

static void inspect_cache(FILE *out, uint32_t kd_unix) {
    s32 rc=ISFS_Initialize();fprintf(out,"cache_isfs_init=%d\n",(int)rc);fflush(out);
    if(rc<0)return;
    s32 fd=ISFS_Open("/title/00010002/48414745/data/wc24dl.vff",ISFS_OPEN_READ);
    fprintf(out,"cache_open=%d\n",fd<0?(int)fd:0);fflush(out);
    if(fd>=0) {
        fstats *st=memalign(32,sizeof(fstats));
        if(st) {
            rc=ISFS_GetFileStats(fd,st);fprintf(out,"cache_stat=%d\n",(int)rc);fflush(out);
            if(rc>=0 && st->file_length>0 && st->file_length<=8u*1024u*1024u) {
                u32 n=st->file_length;u32 aligned=(n+31u)&~31u;unsigned char *buffer=memalign(32,aligned);
                if(buffer) {
                    rc=ISFS_Read(fd,buffer,n);fprintf(out,"cache_read=%d\n",(int)rc);fflush(out);
                    if(rc==(s32)n) {
                        news_cache_summary summary;time_t now=time(NULL);
                        uint32_t reference=kd_unix?kd_unix:(now>0?(uint32_t)now:0);
                        int result=news_cache_inspect(buffer,n,reference,&summary);
                        fprintf(out,"cache_parse=%d\ncache_entries=%u\ncache_parsed=%u\n"
                            "cache_fresh=%u\ncache_expired=%u\ncache_future=%u\n"
                            "cache_country_49=%u\ncache_country_136=%u\ncache_english=%u\n"
                            "cache_unrecognized=%u\ncache_crc_ok=%u\ncache_crc_bad=%u\n"
                            "cache_structural_bad=%u\ncache_language_empty=%u\ncache_expired_utc9=%u\n"
                            "cache_topic_bad=%u\ncache_source_bad=%u\ncache_location_bad=%u\ncache_image_bad=%u\nclock_unix=%lld\ncache_clock_is_kd=%d\n",result,summary.entries,summary.parsed,
                            summary.fresh,summary.expired,summary.future,summary.country_49,summary.country_136,
                            summary.language_english,summary.unsupported_or_invalid,summary.crc_ok,summary.crc_bad,summary.structural_bad,summary.language_empty,summary.expired_utc9,summary.topic_bad,summary.source_bad,summary.location_bad,summary.image_bad,(long long)now,kd_unix!=0);
                        fflush(out);
                    }
                    memset(buffer,0,aligned);free(buffer);
                } else { fprintf(out,"cache_allocation_failed=1\n");fflush(out); }
            } else if(rc>=0) { fprintf(out,"cache_size_unsupported=1\n");fflush(out); }
            free(st);
        }
        ISFS_Close(fd);
    }
    ISFS_Deinitialize();
}

static s32 initialized(s32 result, void *unused) {
    (void)unused;
    init_result=result; init_done=1;
    return 0;
}

static int lookup(const char *host, struct in_addr *out) {
    struct hostent *result=net_gethostbyname(host);
    if (!result || result->h_addrtype!=AF_INET || result->h_length!=4 ||
        !result->h_addr_list || !result->h_addr_list[0]) return 0;
    memcpy(out,result->h_addr_list[0],4);
    return 1;
}

static int poll_socket(s32 fd, int events) {
    struct pollsd p;
    memset(&p,0,sizeof(p));p.socket=fd;p.events=(u32)events;
    s32 n=net_poll(&p,1,10000);
    if (n<=0) return n==0 ? -1000 : (int)n;
    if (p.revents & (u32)events) return 0;
    if (p.revents & (POLLERR | POLLHUP | POLLNVAL)) return -1001;
    return -1002;
}

static void probe(FILE *out, const char *label, const char *host,
                  const char *path, struct in_addr addr) {
    s32 fd=net_socket(AF_INET,SOCK_STREAM,IPPROTO_IP);
    fprintf(out,"%s_socket=%d\n",label,fd<0?(int)fd:0);fflush(out);
    if (fd<0) return;
    s32 flags=net_fcntl(fd,F_GETFL,0);
    s32 mode=flags<0?flags:net_fcntl(fd,F_SETFL,(u32)flags|KWCE_IOS_NONBLOCK);
    fprintf(out,"%s_nonblocking=%d\n",label,(int)mode);fflush(out);
    if (mode<0) { net_close(fd);return; }
    struct sockaddr_in target;memset(&target,0,sizeof(target));
    target.sin_len=sizeof(target);target.sin_family=AF_INET;target.sin_port=htons(80);target.sin_addr=addr;
    s32 rc=-1000;
    for(int i=0;i<200;i++) {
        rc=net_connect(fd,(struct sockaddr *)&target,sizeof(target));
        if(rc==0 || rc==-EISCONN) { rc=0;break; }
        usleep(50000);
    }
    fprintf(out,"%s_connect=%d\n",label,(int)rc);fflush(out);
    if (rc<0) { net_close(fd);return; }
    char request[256];int length=snprintf(request,sizeof(request),
        "HEAD %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: KWCE-News-Diagnostic/1\r\nConnection: close\r\n\r\n",path,host);
    if (length<=0 || length>=(int)sizeof(request)) { net_close(fd);return; }
    int sent=0;
    while(sent<length) {
        rc=poll_socket(fd,POLLOUT);if (rc<0) break;
        s32 n=net_send(fd,request+sent,(u32)(length-sent),0);
        if (n<=0) { rc=n?n:-1003;break; } sent+=(int)n;
    }
    fprintf(out,"%s_request=%d\n",label,(int)rc);fflush(out);
    if (rc==0) {
        char response[128];int used=0,status=0;
        while(used<(int)sizeof(response)-1) {
            rc=poll_socket(fd,POLLIN);if(rc<0)break;
            s32 n=net_recv(fd,response+used,(u32)(sizeof(response)-1-used),0);
            if(n<=0) { rc=n?n:-1004;break; }used+=(int)n;response[used]=0;
            if(strchr(response,'\n')) break;
        }
        if (used>0 && sscanf(response,"HTTP/%*d.%*d %d",&status)==1 && status>=100 && status<=599)
            fprintf(out,"%s_http_status=%d\n",label,status);
        else fprintf(out,"%s_response_result=%d\n",label,(int)rc);
        fflush(out);
    }
    net_close(fd);
}

int main(void) {
    VIDEO_Init();GXRModeObj *mode=VIDEO_GetPreferredMode(NULL);
    void *buffer=MEM_K0_TO_K1(SYS_AllocateFramebuffer(mode));
    console_init(buffer,20,20,mode->fbWidth,mode->xfbHeight,mode->fbWidth*VI_DISPLAY_PIX_SZ);
    VIDEO_Configure(mode);VIDEO_SetNextFramebuffer(buffer);VIDEO_SetBlack(FALSE);VIDEO_Flush();VIDEO_WaitVSync();
    printf("KWCE News network diagnostic\n\nRead-only, anonymous HEAD requests.\nStarting automatically...\n");
    if(!fatInitDefault()) { printf("Cannot open SD card.\n");goto wait; }
    mkdir("sd:/kwce-rc",0777);char path[64];FILE *f=NULL;int report_number=0;
    for(int i=1;i<=99;i++) {
        snprintf(path,sizeof(path),"sd:/kwce-rc/news-net-%02d.txt",i);
        FILE *old=fopen(path,"rb");if(old){fclose(old);continue;}f=fopen(path,"wb");report_number=i;break;
    }
    if(!f) { printf("Cannot create report.\n");goto wait; }
    fprintf(f,"KWCE_NEWS_NETWORK_V1\nstage=start\n");fflush(f);
    char snapshot_path[64];snprintf(snapshot_path,sizeof(snapshot_path),"sd:/kwce-rc/news-struct-%02d.txt",report_number);
    FILE *snapshot_old=fopen(snapshot_path,"rb");FILE *snapshot=NULL;
    if(snapshot_old)fclose(snapshot_old);else snapshot=fopen(snapshot_path,"wb");
    if(snapshot){fputs("KWCE_NEWS_STRUCT_V1\n",snapshot);news_cache_set_snapshot(snapshot);}
    uint32_t kd_unix=read_kd_time(f);
    read_kd_difference(f,"before");
    inspect_cache(f,kd_unix);
    if(snapshot){news_cache_set_snapshot(NULL);fputs("DONE\n",snapshot);fclose(snapshot);}
    printf("Testing connection; please wait...\n");
    s32 started=net_init_async(initialized,NULL);
    fprintf(f,"net_init_start=%d\n",(int)started);fflush(f);
    if(started>=0) {
        for(int i=0;i<1500 && !init_done;i++) VIDEO_WaitVSync();
        fprintf(f,"net_init_completed=%d\n",init_done);fflush(f);
        if(init_done) { fprintf(f,"net_init_result=%d\n",(int)init_result);fflush(f); }
        if(init_done && init_result>=0) {
            read_kd_difference(f,"after");
            struct in_addr news,forecast;int n=lookup("news.wiilink.ca",&news);
            int w=lookup("fore.wiilink24.com",&forecast);
            fprintf(f,"news_dns_ok=%d\nforecast_dns_ok=%d\n",n,w);
            if(n && w) fprintf(f,"dns_first_ipv4_equal=%d\n",memcmp(&news,&forecast,4)==0);
            fflush(f);
            if(n) probe(f,"news","news.wiilink.ca","/v2/1/049/news.bin.00",news);
            if(w) probe(f,"forecast","fore.wiilink24.com","/1/136/forecast.bin",forecast);
            net_deinit();
        }
    }
    fprintf(f,"stage=complete\n");int bad=fflush(f)!=0 || ferror(f);if(fclose(f)!=0)bad=1;
    printf(bad?"Report write failed.\n":"Report saved to SD.\n");
    printf("Returning in a few seconds.\n");
wait:
    for(int i=0;i<300;i++) VIDEO_WaitVSync();
    return 0;
}
