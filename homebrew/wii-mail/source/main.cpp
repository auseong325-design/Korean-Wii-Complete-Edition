/* Korean front end for the pinned GPL-3.0 WiiLink Mail Patcher.
 * Default view is read-only. The preview build cannot register or write.
 * Upstream registration output is suppressed, including console identifiers.
 */
#include <gccore.h>
#include <wiiuse/wpad.h>
#include <fat.h>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <streambuf>
#include <cstdlib>
#include <malloc.h>
#include "config.h"
#include "patcher.h"
#include "screens.h"

static GXRModeObj* mode;
static void* framebuffer;
struct Quiet:std::streambuf { int overflow(int c)override{return c;} };
static Quiet quiet;

static void screen(int index) {
  const unsigned char* source=screens[index];
  auto* dest=static_cast<u32*>(framebuffer);
  for(unsigned y=0;y<240;y++)for(unsigned x=0;x<160;x++) {
    const unsigned char* p=source+(y*160+x)*4;
    for(unsigned dy=0;dy<2;dy++) {
      u32* q=dest+((y*2+dy)*mode->fbWidth)/2+x*2;
      q[0]=(u32(p[0])<<24)|(u32(p[1])<<16)|(u32(p[0])<<8)|p[3];
      q[1]=(u32(p[2])<<24)|(u32(p[1])<<16)|(u32(p[2])<<8)|p[3];
    }
  }
  DCFlushRange(framebuffer,mode->fbWidth*mode->xfbHeight*2);
  VIDEO_SetNextFramebuffer(framebuffer);VIDEO_Flush();VIDEO_WaitVSync();
}

#ifndef KWCE_PREVIEW_ONLY
static bool backup() {
  if(!fatInitDefault())return false;
  auto* raw=static_cast<unsigned char*>(memalign(32,1024));
  if(!raw)return false;
  s32 fd=ISFS_Open("/shared2/wc24/nwc24msg.cfg",ISFS_OPEN_READ);
  s32 count=fd<0?fd:ISFS_Read(fd,raw,1024);
  if(fd>=0)ISFS_Close(fd);
  if(count!=1024){free(raw);return false;}
  mkdir("sd:/kwce-mail",0777);
  char path[96];unsigned index=1;
  for(;index<10000;index++) {
    snprintf(path,sizeof(path),"sd:/kwce-mail/before-%u.cfg",index);
    FILE* old=fopen(path,"rb");if(!old)break;fclose(old);
  }
  if(index==10000){free(raw);return false;}
  FILE* file=fopen(path,"wb");if(!file){free(raw);return false;}
  bool ok=fwrite(raw,1,1024,file)==1024;
  ok=fclose(file)==0&&ok;
  if(ok){unsigned char verify[1024];file=fopen(path,"rb");ok=file&&fread(verify,1,1024,file)==1024&&!memcmp(raw,verify,1024);if(file)fclose(file);}
  free(raw);return ok;
}

static int restore_mail() {
  if(!backup())return -1;
  NWC24Config config;
  if(!config.ReadConfig()||config.CheckNwc24Config()!=0)return -2;
  if(config.CreationStage()==NWC24CreationStage::Initial) {
    alignas(32) s32 output[8]={};
    s32 fd=IOS_Open("/dev/net/kd/request",IPC_OPEN_READ);
    if(fd<0)return -3;
    s32 result=IOS_Ioctl(fd,0x0f,nullptr,0,output,sizeof(output));IOS_Close(fd);
    if(result<0||output[0]<0)return -4;
  }
  return Patcher();
}
#endif

int main() {
  std::cout.rdbuf(&quiet);
  VIDEO_Init();ISFS_Initialize();WPAD_Init();
  mode=VIDEO_GetPreferredMode(nullptr);
  if(mode->fbWidth!=640||mode->xfbHeight<480)return 1;
  framebuffer=SYS_AllocateFramebuffer(mode);
  VIDEO_ClearFrameBuffer(mode,framebuffer,COLOR_BLACK);
  VIDEO_Configure(mode);VIDEO_SetNextFramebuffer(framebuffer);VIDEO_SetBlack(FALSE);VIDEO_Flush();VIDEO_WaitVSync();
  int page=0;screen(page);
  while(true) {
    WPAD_ScanPads();u32 buttons=WPAD_ButtonsDown(0),held=WPAD_ButtonsHeld(0);
    if(buttons&WPAD_BUTTON_HOME)break;
    if(buttons&WPAD_BUTTON_B){page=0;screen(page);}
    if(buttons&WPAD_BUTTON_A) {
      NWC24Config config;page=config.ReadConfig()&&config.CheckNwc24Config()==0?1:2;screen(page);
    }
    if((held&WPAD_BUTTON_1)&&(held&WPAD_BUTTON_2)) {
      page=3;screen(page);
    }
    if(page==3&&(buttons&WPAD_BUTTON_PLUS)) {
#ifdef KWCE_PREVIEW_ONLY
      page=7;
#else
      screen(4);int result=restore_mail();CONF_Init();WPAD_Init();page=result==0?5:6;
#endif
      screen(page);
    }
    VIDEO_WaitVSync();
  }
  return 0;
}
