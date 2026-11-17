"""KWCE DVD player = WiiMC 3.0.0 (dborth/wiimc fae733f, GPLv3) + these changes.

Every edit is a guarded exact replacement (must match once), applied to a fresh
copy of external/other-tools/wiimc; new files come from homebrew/kwce-dvd.
Revision gates keep earlier builds reproducible.
"""
from pathlib import Path

SOURCE_COMMIT='fae733f1ee51db8f8c9e3560cdb8b65835174f00'

def patches(revision,css=False):
    p=[]
    def add(path,old,new):p.append((path,old,new))
    if revision>=47:
        # The inset HOME layout leaves a thin movie strip at the outer edge.
        # These opaque bands are now safe with the explicit rectangle VCD.
        add('source/kwce/kwce_home.cpp',
            '\tMenu_DrawRectangle(0,0,screenwidth,screenheight,(GXColor){0,0,0,85},1);',
            '\tMenu_DrawRectangle(0,0,screenwidth,screenheight,(GXColor){0,0,0,85},1);\n'
            '\tMenu_DrawRectangle(0,0,screenwidth,screenheight * 0.08f,(GXColor){0,0,0,255},1);\n'
            '\tMenu_DrawRectangle(0,screenheight * 0.92f,screenwidth,screenheight * 0.08f,(GXColor){0,0,0,255},1);')
    if revision>=45:
        # A HOME backdrop/layout or movie leaves a different vertex descriptor.
        # Every libwiigui primitive must declare exactly the bytes it emits;
        # otherwise texcoord/position bytes are decoded as FIFO opcodes.
        plain=('\tGX_ClearVtxDesc();\n'
               '\tGX_SetVtxDesc(GX_VA_POS, GX_DIRECT);\n'
               '\tGX_SetVtxDesc(GX_VA_CLR0, GX_DIRECT);\n'
               '\tGX_SetVtxAttrFmt(GX_VTXFMT0, GX_VA_POS, GX_POS_XYZ, GX_F32, 0);\n'
               '\tGX_SetVtxAttrFmt(GX_VTXFMT0, GX_VA_CLR0, GX_CLR_RGBA, GX_RGBA8, 0);\n')
        add('source/video.cpp','\tGX_Begin(fmt, GX_VTXFMT0, n);',
            plain+('\tGX_SetBlendMode(GX_BM_BLEND, GX_BL_SRCALPHA, GX_BL_INVSRCALPHA, GX_LO_CLEAR);\n' if revision>=46 else '')+
            '\tGX_SetTevOp(GX_TEVSTAGE0, GX_PASSCLR);\n\tGX_Begin(fmt, GX_VTXFMT0, n);')
        add('source/video.cpp','\tGX_Begin(GX_QUADS, GX_VTXFMT0,4);',
            plain+'\tGX_SetVtxDesc(GX_VA_TEX0, GX_DIRECT);\n'
            '\tGX_SetVtxAttrFmt(GX_VTXFMT0, GX_VA_TEX0, GX_TEX_ST, GX_F32, 0);\n'
            '\tGX_Begin(GX_QUADS, GX_VTXFMT0,4);')
        font=('\tGX_ClearVtxDesc();\n'
              '\tGX_SetVtxDesc(GX_VA_POS, GX_DIRECT);\n'
              '\tGX_SetVtxDesc(GX_VA_CLR0, GX_DIRECT);\n'
              '\tthis->setVertexFormat(this->vertexIndex);\n')
        add('source/utils/FreeTypeGX.cpp','\tGX_SetTevOp (GX_TEVSTAGE0, GX_MODULATE);\n\tGX_SetVtxDesc (GX_VA_TEX0, GX_DIRECT);',
            font+'\tGX_SetTevOp (GX_TEVSTAGE0, GX_MODULATE);\n\tGX_SetVtxDesc (GX_VA_TEX0, GX_DIRECT);')
        add('source/utils/FreeTypeGX.cpp','\tGX_SetTevOp (GX_TEVSTAGE0, GX_PASSCLR);\n\tGX_SetVtxDesc (GX_VA_TEX0, GX_NONE);',
            font+'\tGX_SetTevOp (GX_TEVSTAGE0, GX_PASSCLR);\n\tGX_SetVtxDesc (GX_VA_TEX0, GX_NONE);')
    if revision>=43:
        # A DVD still must reuse the decoded image. Refeeding its final P/B
        # packet repeatedly changes prediction references and damages the image.
        add('source/mplayer/mplayer.c','if (mpctx->nav_smpi && !mpctx->nav_buffer)',
            'if (mpctx->nav_smpi)')
        add('source/mplayer/mplayer.c','        if (mpctx->nav_buffer) {\n            *start',
            '        if (mpctx->nav_buffer && !decoded_frame) {\n            *start')
        # Decoder planes include padding (e.g. width736, visible width720).
        # Allocate that layout before copy_mpi copies its chroma_width columns.
        add('source/mplayer/mplayer.c','        to_mpi->imgfmt == from_mpi->imgfmt)',
            '        to_mpi->imgfmt == from_mpi->imgfmt &&\n'
            '        to_mpi->width == from_mpi->width && to_mpi->height == from_mpi->height)')
        add('source/mplayer/mplayer.c','        mpi = alloc_mpi(from_mpi->w, from_mpi->h, from_mpi->imgfmt);',
            '        mpi = alloc_mpi(from_mpi->width, from_mpi->height, from_mpi->imgfmt);\n'
            '        if (!mpi) return NULL;\n'
            '        mpi->w = from_mpi->w; mpi->h = from_mpi->h;')
        add('source/kwce/kwce_dvd.cpp',
            'DVD에 접근할 수 없습니다.\\nDVD 플레이어 채널을 다시 설치해 주십시오.',
            'DVD 드라이브에 접근할 수 없습니다.\\n전원을 끈 뒤 다시 시도해 주십시오.')
    if revision==42:
        add('source/mplayer/mplayer.c',
            'static mp_image_t *mp_dvdnav_copy_mpi(mp_image_t *to_mpi,',
            'static void kwce_frame_probe(mp_image_t *m,const char *kind,int id) {\n'
            ' char path[96];sprintf(path,"sd1:/kwce/dvd/%s-%d.yuv",kind,id);FILE *f=fopen(path,"wb");if(!f)return;\n'
            ' fwrite(&m->w,4,1,f);fwrite(&m->h,4,1,f);\n'
            ' for(int p=0;p<3;p++){int w=p?m->chroma_width:m->w,h=p?m->chroma_height:m->h;for(int y=0;y<h;y++)fwrite(m->planes[p]+y*m->stride[p],1,w,f);}fclose(f);\n'
            '}\nstatic mp_image_t *mp_dvdnav_copy_mpi(mp_image_t *to_mpi,')
        add('source/mplayer/mplayer.c','    copy_mpi(mpi, from_mpi);\n    return mpi;',
            '    copy_mpi(mpi, from_mpi);\n'
            '    static int kwceN=0;if(kwceN<4){kwce_frame_probe(from_mpi,"from",kwceN);kwce_frame_probe(mpi,"snapshot",kwceN++);}\n'
            '    return mpi;')
    if revision==40:
        add('source/kwce/kwce_dvd.cpp','"%s/test-disc.iso"','"%s/test-file.mpg"')
    if revision==41:
        add('source/mplayer/libmpcodecs/dec_video.c',
            '    mpi = mpvdec->decode(sh_video, start, in_size, drop_frame);',
            '    static int kwceProbe=0;\n'
            '    if(kwceProbe<4 && in_size>0){char p[96];sprintf(p,"sd1:/kwce/dvd/probe-%d.m2v",kwceProbe++);FILE *f=fopen(p,"wb");if(f){fwrite(start,1,in_size,f);fclose(f);}}\n'
            '    mpi = mpvdec->decode(sh_video, start, in_size, drop_frame);')
    if 39<=revision<=41:
        add('source/mplayer/config.mak','LIBMPEG2 = no\nLIBMPEG2_INTERNAL = no',
            'LIBMPEG2 = yes\nLIBMPEG2_INTERNAL = yes')
        add('source/mplayer/config.h','#undef CONFIG_LIBMPEG2\n#undef CONFIG_LIBMPEG2_INTERNAL',
            '#define CONFIG_LIBMPEG2 1\n#define CONFIG_LIBMPEG2_INTERNAL 1')
        add('source/mplayer/mplayer.c','m_config_set_option(mconfig,"vo","gekko");',
            'm_config_set_option(mconfig,"vo","gekko");\nm_config_set_option(mconfig,"vc","mpeg12,");')
    if 38<=revision<=41:
        add('source/mplayer/config.mak','CFLAGS   = -Wundef',
            'CFLAGS   = -fno-strict-aliasing -fwrapv -Wundef')
    if revision==37:
        add('source/mplayer/osdep/gx_supp.c','void GX_FillTextureYUV(u8 *buffer[3], int stride[3])\n{',
            'volatile unsigned KwceVideoPlanes[6];\nvoid GX_FillTextureYUV(u8 *buffer[3], int stride[3])\n{\n'
            '\tfor(int i=0;i<3;i++){KwceVideoPlanes[i]=(unsigned)buffer[i];KwceVideoPlanes[i+3]=stride[i];}\n')
    if 35<=revision<=41:
        # Legacy IDCT reads one coefficient array through both int16_t and
        # uint32_t pointers. Modern GCC otherwise assumes these cannot alias.
        add('source/mplayer/ffmpeg/libavcodec/simple_idct.c',
            '#include "avcodec.h"',
            '#pragma GCC optimize ("no-strict-aliasing")\n#include "avcodec.h"')
    # --- build -------------------------------------------------------------------------------
    add('Makefile','SOURCES\t\t:=\tsource source/libwiigui source/utils source/utils/unzip',
        'SOURCES\t\t:=\tsource source/libwiigui source/utils source/utils/unzip source/kwce'+(' source/kwce/lyt' if revision>=2 else ''))
    if revision>=34:
        add('source/wiimc.cpp','int main(int argc, char *argv[])\n{\n',
            'int main(int argc, char *argv[])\n{\n'
            '\t// Native menu entry retains IOS80. Recreate the normal IOS58 player environment.\n'
            + ('\tif(IOS_GetVersion()!=58) { cIOS_access(); if(IOS_ReloadIOS(58)<0 || IOS_GetVersion()!=58) { SYS_ResetSystem(SYS_RETURNTOMENU,0,0); return 1; } }\n'
               if revision>=42 else '\tif(IOS_GetVersion()!=58 && IOS_ReloadIOS(58)<0) { SYS_ResetSystem(SYS_RETURNTOMENU,0,0); return 1; }\n'))
    if revision>=31:
        # Link the otherwise unchanged pinned libogc2 wpad.o with its device
        # table exported, so HOME can request an asynchronous battery status.
        add('Makefile', 'LIBS    := -lmplayerwii',
            'LIBS    := $(dir $(OUTPUT))../kwce_wpad.o -lmplayerwii')
        # WiiMC polls channel 1 only; HOME also handles status replies for 2P-4P.
        add('source/input.cpp', '#include "input.h"\n', '#include "input.h"\n#include "kwce/kwce_home.h"\n')
        add('source/input.cpp', 'WPAD_ReadPending(0, NULL); // only wiimote 1',
            'if(KwceHomeActive()) { for(int p=0;p<4;p++) WPAD_ReadPending(p, NULL); }\n\telse WPAD_ReadPending(0, NULL); // playback retains WiiMC input handling')
    # --- startup: DVD only, no network, works without an SD card -----------------------------
    add('source/wiimc.cpp','#include "settings.h"\n','#include "settings.h"\n#include "kwce/kwce_dvd.h"\n')
    add('source/wiimc.cpp','\tFindAppPath(); // Initialize SD and USB devices and look for apps/wiimc\n',
        '\tFindAppPath(); // Initialize SD and USB devices and look for apps/wiimc\n'
        '\tKwceDvdSetupPaths(); // KWCE: settings in sd1:/kwce/dvd when present\n'
        '\tAutobootExit = true; // KWCE: the player returns to the Wii Menu after the disc\n')
    add('source/wiimc.cpp','\tStartNetworkThread(); //to set net heap aside MEM2 area\n\tusleep(100); //force network thread execution\n',
        '\t// KWCE: no network in the DVD player\n')
    add('source/wiimc.cpp','\tif(!InitFreeType((u8*)font_ttf, font_ttf_size)) // Initialize font system\n',
        '\tKwceDvdLoadFont(); // KWCE: Wii system font (wbf1) for all UI text\n'
        '\tif(!InitFreeType((u8*)font_ttf, font_ttf_size)) // Initialize font system\n')
    add('source/wiimc.cpp','\tif(appPath[0] == 0)\n\t{\n\t\tInfoPrompt("Unable to Initialize MPlayer", "Unable to find a valid working path");\n\t\treturn false;\n\t}\n\n\tif(chdir(appPath) != 0)',
        '\tif(appPath[0] != 0 && chdir(appPath) != 0) // KWCE: a working path is optional')
    add('source/wiimc.cpp','\tsprintf(MPLAYER_CSSDIR,"%s/css",appPath);\n\tDIR *dir = opendir(MPLAYER_CSSDIR);\n\n\tif(!dir && mkdir(MPLAYER_CSSDIR, 0777) != 0)\n\t\tsprintf(MPLAYER_CSSDIR, "off");\n\telse\n\t\tclosedir(dir);\n',
        '\tsprintf(MPLAYER_CSSDIR, "off"); // KWCE: no CSS key cache\n')
    # --- settings defaults --------------------------------------------------------------------
    add('source/settings.cpp','\tWiiSettings.language = CONF_GetLanguage() == 4 ? LANG_SPANISH : LANG_ENGLISH;\n',
        '\tWiiSettings.language = LANG_KOREAN; // KWCE\n')
    add('source/settings.cpp','\tWiiSettings.hideExtensions = 1;\n\tWiiSettings.exitAction = EXIT_AUTO;\n',
        '\tWiiSettings.hideExtensions = 1;\n\tWiiSettings.exitAction = EXIT_WIIMENU; // KWCE\n')
    # --- font: wbf1 glyphs through FreeTypeGX ------------------------------------------------
    add('source/utils/FreeTypeGX.cpp','#include "FreeTypeGX.h"\n','#include "FreeTypeGX.h"\n#include "../kwce/kwce_font.h"\n')
    add('source/utils/FreeTypeGX.cpp','''	FT_UInt gIndex;
	uint16_t textureWidth = 0, textureHeight = 0;

	gIndex = FT_Get_Char_Index( ftFace, charCode );''','''	FT_UInt gIndex;
	uint16_t textureWidth = 0, textureHeight = 0;

	KwceGlyph kg;  // KWCE: Wii system font first, FreeType only for missing characters
	if(KwceFontReady() && KwceFontGlyph(charCode, this->ftPointSize, &kg))
	{
		FT_Bitmap bmp;
		memset(&bmp, 0, sizeof(bmp));
		bmp.width = kg.width; bmp.rows = kg.rows; bmp.pitch = kg.width; bmp.buffer = kg.buffer;
		textureWidth = adjustTextureWidth(kg.width);
		textureHeight = adjustTextureHeight(kg.rows);
		this->fontData[charCode] = (ftgxCharData){ (int16_t)kg.left, (uint16_t)kg.advance, 0, textureWidth, textureHeight,
			(int16_t)kg.top, (int16_t)kg.top, (int16_t)(kg.rows - kg.top), NULL };
		this->loadGlyphData(&bmp, &this->fontData[charCode]);
		KwceFontFreeGlyph(&kg);
		return &this->fontData[charCode];
	}

	gIndex = FT_Get_Char_Index( ftFace, charCode );''')
    add('source/utils/FreeTypeGX.cpp','\toffset->ascender = ftFace->size->metrics.ascender>>6;\n\toffset->descender = ftFace->size->metrics.descender>>6;\n',
        '\toffset->ascender = ftFace->size->metrics.ascender>>6;\n\toffset->descender = ftFace->size->metrics.descender>>6;\n'
        '\tif(KwceFontReady())\n\t{\n\t\tint a, d;\n\t\tKwceFontMetrics(this->ftPointSize, &a, &d);\n\t\toffset->ascender = a; offset->descender = -d;\n\t}\n')
    # --- menu: straight to the disc; Korean errors end at the Wii Menu ------------------------
    add('source/menu.cpp','#include "filelist.h"\n','#include "filelist.h"\n#include "kwce/kwce_dvd.h"\n#include "kwce/kwce_font.h"\n')
    add('source/menu.cpp','''	if(!LoadSettings())
	{
		if(!SaveSettings(NOTSILENT))
		{
			ExitRequested = true;
			return;
		}
	}
''','''	if(!LoadSettings())
		SaveSettings(SILENT); // KWCE: the player also runs without an SD card
	static bool kwceLanguage = true;
	if(kwceLanguage) { kwceLanguage = false; ChangeLanguage(); }
''')
    add('source/menu.cpp','''		if(loadedFile[0] != 0)
		{
			guiShutdown = true;
			sleep(2); // USB mount delay

			LoadNewFile();

			SuspendParseThread();
			SuspendGui();
		}
''','''		char kwceTest[MAXPATHLEN];
		if(loadedFile[0] == 0 && KwceDvdTestDisc(kwceTest, sizeof(kwceTest)))
			strcpy(loadedFile, kwceTest); // KWCE emulator test bed: SD image played like the disc
		if(loadedFile[0] != 0)
		{
			guiShutdown = true;
			sleep(2); // USB mount delay

			LoadNewFile();

			SuspendParseThread();
			SuspendGui();
		}
		else
			menuCurrent = MENU_DVD; // KWCE: the player starts with the inserted disc
''')
    add('source/menu.cpp','''	checkIOS = false;

	while(!guiShutdown)''','''	checkIOS = false;

	if(kwce_css_scrambled) // KWCE: no CSS decryption in this build
	{
		ErrorPrompt(kwce::msgCss);
		ExitRequested = true;
		guiShutdown = true;
	}

	while(!guiShutdown)''')
    add('source/menu.cpp','''	if (device == -1)
	{
		if(menuPrevious == MENU_DVD)
			menuPrevious = MENU_BROWSE_VIDEOS;
		UndoChangeMenu(); // go back to last menu
		return;
	}

	if(!wiiPlayingDVD())''','''	if (device == -1) // KWCE: the reason was shown; return to the Wii Menu
	{
		ExitRequested = true;
		guiShutdown = true;
		return;
	}

	if(!wiiPlayingDVD())''')
    add('source/menu.cpp','''		if(!guiShutdown) // load failed
		{
			if(menuPrevious == MENU_DVD)
				menuPrevious = MENU_BROWSE_VIDEOS;
			UndoChangeMenu(); // go back to last menu
			mainWindow->Remove(disabled);
			mainWindow->SetState(STATE_DEFAULT);
			ErrorPrompt("Unrecognized DVD format!");
		}''','''		if(!guiShutdown) // load failed
		{
			mainWindow->Remove(disabled);
			mainWindow->SetState(STATE_DEFAULT);
			ErrorPrompt(kwce::msgNotVideo); // KWCE
			ExitRequested = true;
			guiShutdown = true;
		}''')
    add('source/menu.cpp','\t\tShowAction("Loading...");\n\t\tResetVideos();\n\t\tDisableVideoImg();\n\t\tLoadMPlayerFile();\n\n\t\t// wait until MPlayer is ready to take or return control',
        '\t\tShowAction(kwce::msgLoading); // KWCE\n\t\tResetVideos();\n\t\tDisableVideoImg();\n\t\tLoadMPlayerFile();\n\n\t\t// wait until MPlayer is ready to take or return control')
    add('source/menu.cpp','''	while(controlledbygui == 0)
	{
		CheckSleepTimer();
		usleep(500000);
''','''	while(controlledbygui == 0)
	{
		CheckSleepTimer();
		usleep(500000);

		if(kwce_css_scrambled) // KWCE: stop at the first scrambled sector
			StopMPlayerFile();
''')
    add('source/menu.cpp','''void ChangeLanguage()
{
	char error[128] = {0};
''','''void ChangeLanguage()
{
	char error[128] = {0};

	if(KwceFontReady()) // KWCE: the Wii system font covers Korean; no external .ttf
	{
		SuspendGui();
		ResetText();
		ResumeGui();
		return;
	}
''')
    # --- DVD mount messages -------------------------------------------------------------------
    add('source/fileop.cpp','#include "fileop.h"\n','#include "fileop.h"\n#include "kwce/kwce_dvd.h"\n')
    for old,new in [('ErrorPrompt("WiiMC does not have DVD access.");','ErrorPrompt(kwce::msgNoAccess);'),
                    ('ErrorPrompt("DVD playback is not supported on this Wii.");','ErrorPrompt(kwce::msgUnsupportedDrive);'),
                    ('ShowAction("Loading DVD...");','ShowAction(kwce::msgLoading);'),
                    ('retry = ErrorPromptRetry("Unsupported DVD.");','retry = ErrorPromptRetry(kwce::msgNotVideo);')]:
        add('source/fileop.cpp',old,new)
    if revision>=2:p.extend(_home_menu_patches(revision))
    if revision>=5:
        # dvdnav STOP closes the VM's IFO handles. MPlayer can ask for another
        # buffer after that event; EOF must stay terminal until an explicit reset.
        add('source/mplayer/stream/stream_dvdnav.c','    dvdnav_priv_t* priv=s->priv;\n    if (priv->state & NAV_FLAG_WAIT_READ)',
            '    dvdnav_priv_t* priv=s->priv;\n    if (priv->state & NAV_FLAG_EOF) /* KWCE: never restart a stopped DVD VM */\n      return 0;\n    if (priv->state & NAV_FLAG_WAIT_READ)')
        add('source/mplayer/libdvdnav/vm/vm.c','int vm_start(vm_t *vm) {\n  /* Set pgc to FP (First Play) pgc */\n  set_FP_PGC(vm);',
            'int vm_start(vm_t *vm) {\n  /* KWCE: vm_stop has closed the reader and IFOs; reset before starting. */\n  if (!vm || !vm->vmgi || !vm->dvd)\n    return 0;\n  /* Set pgc to FP (First Play) pgc */\n  if (!set_FP_PGC(vm))\n    return 0;')
    if revision>=7:
        add('source/mplayer/mplayer.c','  while ( (cmd = mp_input_get_cmd(20, 1, 1)) == NULL || cmd->pausing == 4)',
            '  while ( (cmd = mp_input_get_cmd(1, 1, 1)) == NULL || cmd->pausing == 4) /* KWCE: HOME redraw at VI cadence */')
    if revision>=9:
        add('source/video.cpp','#include "menu.h"\n','#include "menu.h"\n#include "kwce/kwce_home.h"\n')
        add('source/video.cpp','\tUpdatePads();\n\tif(safe_gc)',
            '\tUpdatePads();\n\tif(KwceHomeActive()) { MPlayerInput(); ResetVideo_Menu(); DoMPlayerGuiDraw(); return 1; } // KWCE: independent of IR/tiled gates\n\tif(safe_gc)')
        add('source/mplayer/mplayer.c','     // DrawMPlayer(); // Output 60FPS on pause.',
            '      DrawMPlayer(); // KWCE: refresh the paused UI at VI cadence (upstream 60FPS path)')
    if revision>=12:
        add('source/mplayer/mplayer.c','static void pause_loop(void)\n{',
            'extern int KwceHomeFrame(void);\nextern void KwceRestoreMovieGX(void);\nstatic void pause_loop(void)\n{')
        add('source/mplayer/mplayer.c','    if (mpctx->sh_video && mpctx->video_out && vo_config_count)\n      mpctx->video_out->check_events();',
            '    if (KwceHomeFrame()) continue; /* KWCE: HOME has its own 60Hz snapshot renderer */\n    KwceRestoreMovieGX();\n    if (mpctx->sh_video && mpctx->video_out && vo_config_count)\n      mpctx->video_out->check_events();')
        add('source/mplayer/osdep/gx_supp.c','void GX_RenderTexture()\n{',
            'void KwceRestoreMovieGX(void) {\n  Mtx44 p; draw_initYUV(); draw_scaling();\n  guOrtho(p,mplayerheight/2,-(mplayerheight/2),-(mplayerwidth/2),mplayerwidth/2,10,1000);\n  GX_LoadProjectionMtx(p,GX_ORTHOGRAPHIC);\n}\n\nvoid GX_RenderTexture()\n{')
    if 14<=revision<=15:
        add('source/video.cpp','void Menu_Render()\n{',
            'extern "C" void KwcePresentHome()\n{\n  while(flip_pending) VIDEO_WaitVSync();\n  GX_SetZMode(GX_TRUE,GX_LEQUAL,GX_TRUE);GX_SetColorUpdate(GX_TRUE);\n  GX_CopyDisp(xfb[whichfb],GX_TRUE);GX_SetDrawDone();\n  VIDEO_WaitVSync(); ++FrameTimer;\n}\n\nvoid Menu_Render()\n{')
    if revision==16:
        add('source/video.cpp','void Menu_Render()\n{',
            'void Draw_VIDEO();\nstatic volatile bool kwceHomeDone=false;\nstatic void KwceHomeDone() { kwceHomeDone=true; }\nextern "C" void KwcePresentHome()\n{\n  while(flip_pending) VIDEO_WaitVSync();\n  kwceHomeDone=false;GX_SetDrawDoneCallback(KwceHomeDone);\n  GX_SetZMode(GX_TRUE,GX_LEQUAL,GX_TRUE);GX_SetColorUpdate(GX_TRUE);\n  GX_CopyDisp(xfb[whichfb],GX_TRUE);GX_SetDrawDone();GX_Flush();\n  while(!kwceHomeDone) usleep(50);\n  GX_SetDrawDoneCallback(Draw_VIDEO);\n  VIDEO_SetNextFramebuffer(xfb[whichfb]);VIDEO_Flush();whichfb^=1;\n  VIDEO_WaitVSync();++FrameTimer;\n}\n\nvoid Menu_Render()\n{')
    if 17<=revision<=18:
        add('source/video.cpp','void Menu_Render()\n{',
            'void Draw_VIDEO();\nstatic volatile bool kwceHomeDone=false;\nstatic void KwceHomeDone() { kwceHomeDone=true; }\nextern "C" void KwcePresentHome()\n{\n  while(flip_pending) VIDEO_WaitVSync();\n  VIDEO_WaitVSync();\n  kwceHomeDone=false;GX_SetDrawDoneCallback(KwceHomeDone);\n  GX_SetZMode(GX_TRUE,GX_LEQUAL,GX_TRUE);GX_SetColorUpdate(GX_TRUE);\n  GX_CopyDisp(xfb[whichfb],GX_TRUE);GX_SetDrawDone();GX_Flush();\n  while(!kwceHomeDone) usleep(50);\n  GX_SetDrawDoneCallback(Draw_VIDEO);\n  VIDEO_SetNextFramebuffer(xfb[whichfb]);VIDEO_Flush();whichfb^=1;\n  ++FrameTimer;\n}\n\nvoid Menu_Render()\n{')
    if revision>=19:
        add('source/video.cpp','#include <unistd.h>\n','#include <unistd.h>\n#include <ogc/lwp_watchdog.h>\n')
        add('source/video.cpp','void Menu_Render()\n{',
            'void Draw_VIDEO();\nstatic volatile bool kwceHomeDone=false;\nstatic void KwceHomeDone() { kwceHomeDone=true; }\nextern "C" void KwcePresentHome()\n{\n  while(flip_pending) VIDEO_WaitVSync();\n  static u64 last=0;u64 now=gettime();\n  while(last && diff_usec(last,now)<16667) { usleep(100);now=gettime(); }\n  last=now;\n  kwceHomeDone=false;GX_SetDrawDoneCallback(KwceHomeDone);\n  GX_SetZMode(GX_TRUE,GX_LEQUAL,GX_TRUE);GX_SetColorUpdate(GX_TRUE);\n  GX_CopyDisp(xfb[whichfb],GX_TRUE);GX_SetDrawDone();GX_Flush();\n  while(!kwceHomeDone) usleep(50);\n  GX_SetDrawDoneCallback(Draw_VIDEO);\n  VIDEO_SetNextFramebuffer(xfb[whichfb]);VIDEO_Flush();whichfb^=1;\n  ++FrameTimer;\n}\n\nvoid Menu_Render()\n{')
    if revision>=20:
        # Do not inherit another WiiMC installation's video/restore settings.
        add('source/wiimc.h','#define APPFOLDER\t\t"wiimc"','#define APPFOLDER\t\t"kwce-dvd"')
        add('source/wiimc.cpp','\tKwceDvdSetupPaths(); // KWCE: settings in sd1:/kwce/dvd when present\n',
            '\tKwceDvdSetupPaths(); // KWCE: settings in sd1:/kwce/dvd when present\n\tKwceDvdTrace("startup",20,0);\n')
        add('source/wiimc.cpp','#include "kwce/kwce_home.h"\n','#include "kwce/kwce_home.h"\n#include "kwce/kwce_trace.h"\n')
        add('source/menu.cpp','\tWiiSettings.dvdMenu = 0; // KWCE: settings saved by R1 asked for the main title only\n',
            '\tWiiSettings.dvdMenu = 0; // KWCE: settings saved by R1 asked for the main title only\n\tWiiSettings.tiledRender=0; wiiSetTiledOFF(); // R20: native single-frame video path\n')
        for path in ['source/mplayer/stream/stream_dvdnav.c','source/mplayer/osdep/gx_supp.c','source/mplayer/libao2/ao_gekko.c']:
            add(path,'#include <stdio.h>\n','#include <stdio.h>\n#include "../../kwce/kwce_trace.h"\n')
        add('source/mplayer/stream/stream_dvdnav.c','        if (dvdnav_is_domain_vts(priv->dvdnav)) {',
            '        KwceDvdTrace("domain",dvdnav_is_domain_vts(priv->dvdnav)?1:0,0);\n        if (dvdnav_is_domain_vts(priv->dvdnav)) {')
        add('source/mplayer/libao2/ao_gekko.c','static int init(int rate, int channels, int format, int flags)\n{',
            'static int init(int rate, int channels, int format, int flags)\n{\n\tKwceDvdTrace("audio-init",rate,channels);')
        add('source/mplayer/osdep/gx_supp.c','extern int sync_interlace;\n',
            'extern int sync_interlace;\nstatic int kwceTraceFrames=0;\n')
        add('source/mplayer/osdep/gx_supp.c','void GX_StartYUV(u16 width, u16 height, u16 haspect, u16 vaspect)\n{',
            'void GX_StartYUV(u16 width, u16 height, u16 haspect, u16 vaspect)\n{\n\tkwceTraceFrames=3;KwceDvdTrace("video-config",width,height);')
        add('source/mplayer/osdep/gx_supp.c','void GX_FillTextureYUV(u8 *buffer[3], int stride[3])\n{',
            'void GX_FillTextureYUV(u8 *buffer[3], int stride[3])\n{\n\tif(kwceTraceFrames)KwceDvdTrace("fill-enter",need_wait,sync_interlace);')
        add('source/mplayer/osdep/gx_supp.c','inline void DrawMPlayer()\n{',
            'inline void DrawMPlayer()\n{\n\tint kwceTraceThis=kwceTraceFrames>0;\n\tif(kwceTraceThis)KwceDvdTrace("frame-enter",need_wait,sync_interlace);')
        add('source/mplayer/osdep/gx_supp.c','\tneed_wait=true;\n}',
            '\tneed_wait=true;\n\tif(kwceTraceThis){KwceDvdTrace("frame-submit",sync_interlace,wiiTiledRender);--kwceTraceFrames;}\n}')
        if not css:
            # The zero-title-key branch bypasses _dvdcss_unscramble upstream.
            # Reject at that branch, before protected PES bytes reach a decoder.
            add('source/mplayer/libdvdcss/libdvdcss.c','#include "config.h"\n',
                '#include "config.h"\n#include "../../kwce/kwce_dvd.h"\n')
            add('source/mplayer/libdvdcss/libdvdcss.c','            if( ((uint8_t*)p_buffer)[0x14] & 0x30 )',
                '            _dvdcss_unscramble(NULL,(uint8_t*)p_buffer);\n            if( kwce_css_scrambled )')
            add('source/mplayer/libdvdcss/libdvdcss.c','                break;\n            }\n            p_buffer = (void *) ((uint8_t *)p_buffer + DVDCSS_BLOCK_SIZE);',
                '                return -1; /* R20: no protected payload is returned */\n            }\n            p_buffer = (void *) ((uint8_t *)p_buffer + DVDCSS_BLOCK_SIZE);')
            add('source/mplayer/libdvdcss/libdvdcss.c','        _dvdcss_unscramble( dvdcss->css.p_title_key, iov_base );\n        ((uint8_t*)iov_base)[0x14] &= 0x8f;',
                '        _dvdcss_unscramble( dvdcss->css.p_title_key, iov_base );\n        if(kwce_css_scrambled)return -1; /* detector only: never clear the flags */')
    if revision>=21:
        add('source/wiimc.cpp','KwceDvdTrace("startup",20,0);','KwceDvdTrace("startup",21,0);')
        add('source/video.cpp','#include "kwce/kwce_home.h"\n',
            '#include "kwce/kwce_home.h"\n#include "kwce/kwce_trace.h"\n#include "kwce/kwce_present.h"\n')
        # GX/VI callbacks share these with the main drawing thread.
        add('source/video.cpp','bool need_wait=false;\nbool flip_pending=false;',
            'volatile bool need_wait=false;\nvolatile bool flip_pending=false;\nstatic volatile unsigned kwceFlips=0;')
        add('source/menu.cpp','extern bool flip_pending;','extern volatile bool flip_pending;')
        for name in ['need_wait','flip_pending']:
            add('source/mplayer/osdep/gx_supp.c',f'extern bool {name};',f'extern volatile bool {name};')
        old='''static void vblank_cb(u32 retraceCnt)
{
	if (flip_pending) {
		if(sync_interlace == 1) {
			if(!VIDEO_GetNextField()) {
				VIDEO_SetNextFramebuffer(xfb[whichfb]);
				VIDEO_Flush();
				whichfb ^= 1;
				flip_pending = false;
			}
		} else if(sync_interlace == 2) {
			if(VIDEO_GetNextField()) {
				VIDEO_SetNextFramebuffer(xfb[whichfb]);
				VIDEO_Flush();
				whichfb ^= 1;
				flip_pending = false;
			}
		} else {
			VIDEO_SetNextFramebuffer(xfb[whichfb]);
			VIDEO_Flush();
			whichfb ^= 1;
			flip_pending = false;
		}
	}
}'''
        new='''static void vblank_cb(u32 retraceCnt)
{
    static unsigned missed=0;
    if (!flip_pending) { missed=0; return; }
    /* MPEG field order describes the input. Only an interlaced VI output
       has alternating fields. HOME must never wait for a movie field. */
    if (!KwceShouldPresent(vmode->viTVMode & 3, sync_interlace,
                          VIDEO_GetNextField(), KwceHomeActive(), missed++)) return;
    VIDEO_SetNextFramebuffer(xfb[whichfb]);
    VIDEO_Flush(); whichfb^=1; flip_pending=false; missed=0; ++kwceFlips;
}'''
        add('source/video.cpp',old,new)
        add('source/video.cpp','\tGX_SetDrawDoneCallback(Draw_VIDEO);\n\tGX_Flush();',
            '\tGX_SetDrawDoneCallback(Draw_VIDEO);\n\tGX_Flush();\n\tKwceDvdTrace("video-output",vmode->viTVMode,VIDEO_GetNextField());\n\tKwceDvdTrace("present-selftest",KwcePresentSelfTest(),0);')
        add('source/mplayer/osdep/gx_supp.c','\tint kwceTraceThis=kwceTraceFrames>0;',
            '\tstatic unsigned frames=0;static int lastSync=-1;\n\tif(lastSync!=sync_interlace || (++frames%120)==0){KwceDvdTrace("field-sync",sync_interlace,vmode->viTVMode);lastSync=sync_interlace;}\n\tint kwceTraceThis=kwceTraceFrames>0;')
        # Keep callback counters available without doing FAT I/O inside an IRQ.
        add('source/video.cpp','int DrawMPlayerGui()\n{',
            'int DrawMPlayerGui()\n{\n\tstatic unsigned calls=0;if((++calls%120)==0)KwceDvdTrace("present-count",kwceFlips,flip_pending);')
    if revision>=29:
        # KWCE(5): hide WiiMC's own libwiigui UI during boot->playback so the channel
        # launches like a native Wii disc -- black until the movie's first frame -- while
        # the Korean error prompts still appear. Anchors verified unique in the pristine tree.
        add('source/menu.cpp','\t\tVIDEO_SetBlack(FALSE);\n',
            '\t\t// KWCE(5): stay black here; the movie un-blanks in GX_StartYUV\n')
        add('source/menu.cpp','\tmainWindow = menuWindow;\n',
            '\tstatic GuiWindow kwceBlank(screenwidth, screenheight); // KWCE(5): empty window; WiiMC menu chrome is never drawn\n\tmainWindow = &kwceBlank;\n')
        add('source/menu.cpp','\tmainWindow->Append(&promptWindow);\n\tResumeGui();\n\n\twhile(choice == -1)',
            '\tmainWindow->Append(&promptWindow);\n\tVIDEO_SetBlack(FALSE); // KWCE(5): a Korean error prompt must stay visible after the black transition\n\tResumeGui();\n\n\twhile(choice == -1)')
        add('source/mplayer/osdep/gx_supp.c','#include "../../video.h"\n',
            '#include "../../video.h"\n#include <ogc/video.h> // KWCE(5): VIDEO_SetBlack for the native-launch un-blank\n')
        add('source/mplayer/osdep/gx_supp.c','\tGX_CopyDisp(xfb[0], GX_TRUE);\n',
            '\tGX_CopyDisp(xfb[0], GX_TRUE);\n\tstatic bool kwceShown=false; if(!kwceShown){kwceShown=true;VIDEO_SetBlack(FALSE);} /* KWCE(5): native-launch un-blank at the first video frame */\n')
    if revision==44:
        add('source/menu.cpp','#include "kwce/kwce_dvd.h"\n',
            '#include "kwce/kwce_dvd.h"\nextern "C" void KwceDvdTrace(const char *,int,int);\n')
        add('source/menu.cpp','\t\tErrorPrompt(kwce::msgCss);\n\t\tExitRequested = true;',
            '\t\tErrorPrompt(kwce::msgCss);\n\t\tKwceDvdTrace("error-ui",5,0);\n\t\tExitRequested = true;')
        add('source/menu.cpp','\t\tif(ExitRequested)\n\t\t{\n\t\t\tif(screensaverThreadHalt)',
            '\t\tif(ExitRequested)\n\t\t{\n\t\t\tif(kwce_css_scrambled) KwceDvdTrace("error-ui",6,0);\n\t\t\tif(screensaverThreadHalt)')
        add('source/menu.cpp','\t\t\t// Turn off dimming on exit',
            '\t\t\tif(kwce_css_scrambled) KwceDvdTrace("error-ui",7,0);\n\t\t\t// Turn off dimming on exit')
    if revision>=49:
        add('source/wiimc.cpp', '#include "kwce/kwce_dvd.h"',
            '#include "kwce/kwce_dvd.h"\n#include <iso9660.h>')
        add('source/fileop.cpp', '#include "kwce/kwce_dvd.h"',
            '#include "kwce/kwce_dvd.h"\n#include "kwce/kwce_trace.h"')
        # DVD navigation reads /dev/di via libdvdread (including UDF).
        # Do not require the file browser's separate ISO9660 mount.
        add('source/fileop.cpp', 'else if(!ISO9660_Mount("dvd", dvd))',
            'else if(!dvd->startup(dvd))')
        add('source/fileop.cpp', '\t\t\tretry = ErrorPromptRetry(kwce::msgNotVideo);',
            '\t\t\tuint32_t driveError=0; int errorResult=DI_GetError(&driveError);\n'
            '\t\t\tKwceDvdTrace("drive-status",DI_GetStatus(),errorResult);\n'
            '\t\t\tKwceDvdTrace("drive-error",(int)driveError,0);\n'
            '\t\t\tretry = ErrorPromptRetry(kwce::msgNotVideo);')
        add('source/fileop.cpp', '\t\t\tmounted = true;\n\t\t\tdvdLastUsed = gettime();',
            '\t\t\tKwceDvdTrace("drive-ready",DI_GetStatus(),0);\n'
            '\t\t\tmounted = true;\n\t\t\tdvdLastUsed = gettime();')
        add('source/wiimc.cpp', '\tStopGX();\n\tUnmountAllDevices();',
            '\tStopGX();\n\tISO9660_Unmount("dvd:");\n\tDI_StopMotor();\n\tDI_Close();\n\tUnmountAllDevices();')
    if revision>=50:
        add('source/menu.cpp','#include "kwce/kwce_dvd.h"',
            '#include "kwce/kwce_dvd.h"\n#include "kwce/kwce_trace.h"')
        # Stage numbers only: never disc titles, paths, sectors or keys.
        add('source/wiimc.cpp', '\t// set new file to load\n\twiiLoadFile(loadedFile, partitionlabel);',
            '\tKwceDvdTrace("load-request",0,0);\n\t// set new file to load\n\twiiLoadFile(loadedFile, partitionlabel);')
        add('source/wiimc.cpp', '\t// application exiting\n',
            '\tKwceDvdTrace("player-exit",ExitRequested,ShutdownRequested);\n\t// application exiting\n')
        add('source/wiimc.cpp', '\t\t\tif(AutobootExit) {\n',
            '\t\t\tif(AutobootExit) {\n\t\t\t\tKwceDvdTrace("autoboot-end",controlledbygui,0);\n')
        add('source/menu.cpp', '\t\tLoadMPlayerFile();\n\n\t\t// wait until MPlayer is ready',
            '\t\tKwceDvdTrace("menu-load",0,0);\n\t\tLoadMPlayerFile();\n\t\tKwceDvdTrace("menu-load",1,0);\n\n\t\t// wait until MPlayer is ready')
        for f in ['source/mplayer/libdvdnav/vm/vm.c']:
            add(f, '#include "config.h"', '#include "config.h"\nextern void KwceDvdTrace(const char *,int,int);')
        add('source/mplayer/libdvdnav/vm/vm.c', '    vm->dvd = DVDOpen(dvdroot);',
            '    KwceDvdTrace("vm-open",0,0);\n    vm->dvd = DVDOpen(dvdroot);\n    KwceDvdTrace("vm-open",1,vm->dvd!=NULL);')
        add('source/mplayer/libdvdnav/vm/vm.c', '    vm->vmgi = ifoOpenVMGI(vm->dvd);',
            '    KwceDvdTrace("vm-ifo",0,0);\n    vm->vmgi = ifoOpenVMGI(vm->dvd);\n    KwceDvdTrace("vm-ifo",1,vm->vmgi!=NULL);')
        add('source/mplayer/stream/stream_dvdnav.c', '  if(dvdnav_open(&(priv->dvdnav),priv->filename)!=DVDNAV_STATUS_OK)',
            '  KwceDvdTrace("nav-open",0,0);\n  if(dvdnav_open(&(priv->dvdnav),priv->filename)!=DVDNAV_STATUS_OK)')
        add('source/mplayer/stream/stream_dvdnav.c', '    free(priv->filename);\n    free(priv);\n    return NULL;',
            '    KwceDvdTrace("nav-open",1,0);\n    free(priv->filename);\n    free(priv);\n    return NULL;')
        add('source/mplayer/stream/stream_dvdnav.c', '    dvdnav_get_next_block(priv->dvdnav,buf,&event,&len);',
            '    KwceDvdTrace("nav-first",0,0);\n    int kwceNavResult=dvdnav_get_next_block(priv->dvdnav,buf,&event,&len);\n    KwceDvdTrace("nav-first",kwceNavResult,event);')
    if revision>=51:
        # Pinned libdi's direct AHB path returns +1 on hardware error;
        # only zero means a completed read. Never copy failed DMA contents.
        f='source/mplayer/libdvdcss/device.c'
        add(f, 'extern bool StartDVDMotor();',
            'extern bool StartDVDMotor();\nextern void KwceDvdTrace(const char *,int,int);')
        for call in ['DI_ReadDVD(bfr, blocks, dvdcss->i_pos)',
                     'DI_ReadDVD(bfr, len / DVDCSS_BLOCK_SIZE, dvdcss->i_pos)']:
            # Match the following check separately in each function.
            old='\tret = '+call+';\n'+ ('\n' if ' blocks,' in call else '')+'\tif (ret < 0) {'
            new='\tret = '+call+';\n\tif (ret != 0) {\n'
            new+='\t\tuint32_t error = 0; int er = DI_GetError(&error);\n'
            new+='\t\tKwceDvdTrace("di-read-fail",ret,DI_GetStatus());\n'
            new+='\t\tKwceDvdTrace("di-read-error",er,(int)error);'
            add(f,old,new)
        f='source/mplayer/libdvdread4/ifo_read.c'
        add(f,'#include <stdio.h>', '#include <stdio.h>\nextern void KwceDvdTrace(const char *,int,int);')
        # Negative DVDReadBytes is not a successful read. Require all bytes
        # before parsing either IFO structure (the old !ret accepts -1).
        add(f,'if(!DVDReadBytes(ifofile->file, vmgi_mat, sizeof(vmgi_mat_t)))',
            'if(DVDReadBytes(ifofile->file, vmgi_mat, sizeof(vmgi_mat_t)) != sizeof(vmgi_mat_t))')
        add(f,'if(!(DVDReadBytes(ifofile->file, vtsi_mat, sizeof(vtsi_mat_t))))',
            'if(DVDReadBytes(ifofile->file, vtsi_mat, sizeof(vtsi_mat_t)) != sizeof(vtsi_mat_t))')
        old='''  ifofile->file = DVDOpenFile(dvd, 0, DVD_READ_INFO_FILE);
  if(!ifofile->file) /* Should really catch any error and try to fallback */
    ifofile->file = DVDOpenFile(dvd, 0, DVD_READ_INFO_BACKUP_FILE);
  if(!ifofile->file) {
    fprintf(stderr, "libdvdread: Can't open file VIDEO_TS.IFO.\\n");
    free(ifofile);
    return NULL;
  }

  if(ifoRead_VMG(ifofile))
    return ifofile;'''
        new='''  /* Try the on-disc backup also when the primary opens but cannot
     be read/validated. Keep the same validation for both copies. */
  int copy;
  for(copy = 0; copy < 2; ++copy) {
    ifofile->file = DVDOpenFile(dvd, 0,
        copy ? DVD_READ_INFO_BACKUP_FILE : DVD_READ_INFO_FILE);
    KwceDvdTrace("ifo-file",copy,ifofile->file != NULL);
    if(!ifofile->file) continue;
    int valid = ifoRead_VMG(ifofile);
    KwceDvdTrace("ifo-valid",copy,valid);
    if(valid) return ifofile;
    DVDCloseFile(ifofile->file);
    ifofile->file = NULL;
  }'''
        add(f,old,new)
        add(f,'  if(strncmp("DVDVIDEO-VMG", vmgi_mat->vmg_identifier, 12) != 0) {',
            '  if(strncmp("DVDVIDEO-VMG", vmgi_mat->vmg_identifier, 12) != 0) {\n    KwceDvdTrace("ifo-header",0,0);')
        f='source/mplayer/libdvdread4/dvd_udf.c'
        add(f,'#include <stdio.h>','#include <stdio.h>\nextern void KwceDvdTrace(const char *,int,int);')
        add(f,'    if( !UDFFindPartition( device, 0, &partition ) ) return 0;',
            '    if( !UDFFindPartition( device, 0, &partition ) ) { KwceDvdTrace("udf-stage",1,0); return 0; }')
        add(f,'    if( TagID != 256 )\n      return 0;',
            '    if( TagID != 256 ) { KwceDvdTrace("udf-stage",2,0); return 0; }')
        add(f,'                       cache_file_info))\n        return 0;',
            '                       cache_file_info)) { KwceDvdTrace("udf-stage",3,0); return 0; }')
        # No filenames, sector addresses, media bytes or identifiers in trace.
        add('source/wiimc.cpp','KwceDvdTrace("startup",21,0);','KwceDvdTrace("startup",51,0);')
    if revision>=52:
        # Observe the first physical reads without logging media addresses or
        # contents. Stop after 32 calls; never add SD I/O to every video frame.
        f='source/mplayer/libdvdcss/device.c'
        add(f, 'static int di_read(dvdcss_t dvdcss, void *buffer, int blocks) {',
            'static unsigned kwce_di_trace_count;\n'
            'static int kwce_di_trace_begin(void) {\n'
            '  if(kwce_di_trace_count >= 32) return 0;\n'
            '  int seq = ++kwce_di_trace_count;\n'
            '  KwceDvdTrace("di-begin",seq,DI_GetStatus());\n'
            '  return seq;\n}\n\n'
            'static int di_read(dvdcss_t dvdcss, void *buffer, int blocks) {')
        for call in ['DI_ReadDVD(bfr, blocks, dvdcss->i_pos)',
                     'DI_ReadDVD(bfr, len / DVDCSS_BLOCK_SIZE, dvdcss->i_pos)']:
            add(f, '\tret = '+call+';',
                '\tint kwceSeq = kwce_di_trace_begin();\n'
                '\tret = '+call+';\n'
                '\tif(kwceSeq) KwceDvdTrace("di-end",kwceSeq,ret);')
        # R51 logged only AFTER the synchronous error query. An IOS wait there
        # otherwise looks exactly like a direct-AHB read that never completed.
        old='\t\tuint32_t error = 0; int er = DI_GetError(&error);'
        # Two distinct functions need distinct anchors for guarded replacement.
        for following in ['\n\t\tKwceDvdTrace("di-read-fail",ret,DI_GetStatus());\n\t\tKwceDvdTrace("di-read-error",er,(int)error);\n\t\tprint_debug(dvdcss,',
                          '\n\t\tKwceDvdTrace("di-read-fail",ret,DI_GetStatus());\n\t\tKwceDvdTrace("di-read-error",er,(int)error);\n\t\tprint_debug( dvdcss,']:
            add(f,old+following,
                '\t\tKwceDvdTrace("di-error-begin",ret,DI_GetStatus());\n'+old+following)
        f='source/mplayer/libdvdread4/dvd_udf.c'
        # Named boundaries only. A missing completion narrows the call tree;
        # it does not itself distinguish a device wait from failed SD logging.
        add(f,'  int i, volvalid;\n  struct avdp_t avdp;\n\n  if(!UDFGetAVDP(device, &avdp))\n    return 0;',
            '  int i, volvalid;\n  struct avdp_t avdp;\n\n'
            '  KwceDvdTrace("udf-anchor",0,0);\n'
            '  int kwceAnchor = UDFGetAVDP(device, &avdp);\n'
            '  KwceDvdTrace("udf-anchor",1,kwceAnchor);\n'
            '  if(!kwceAnchor) return 0;')
        add(f,'    if( !UDFFindPartition( device, 0, &partition ) ) { KwceDvdTrace("udf-stage",1,0); return 0; }',
            '    KwceDvdTrace("udf-partition",0,0);\n'
            '    int kwcePartition = UDFFindPartition(device,0,&partition);\n'
            '    KwceDvdTrace("udf-partition",1,kwcePartition);\n'
            '    if(!kwcePartition) { KwceDvdTrace("udf-stage",1,0); return 0; }')
        add(f,'    /* Find root dir ICB */\n    lbnum = partition.Start;',
            '    KwceDvdTrace("udf-root",0,0);\n'
            '    /* Find root dir ICB */\n    lbnum = partition.Start;')
        add(f,'    /* Sanity checks. */\n    if( TagID != 256 )',
            '    KwceDvdTrace("udf-root",1,TagID==256);\n'
            '    /* Sanity checks. */\n    if( TagID != 256 )')
        add('source/wiimc.cpp','KwceDvdTrace("startup",51,0);',
            'KwceDvdTrace("startup",'+str(revision)+',0);')
    if revision>=54:
        # A diagnostic query must not prevent propagation of a completed read
        # failure. The direct-AHB return value is already sufficient to fail.
        f='source/mplayer/libdvdcss/device.c'
        old=('\t\tKwceDvdTrace("di-error-begin",ret,DI_GetStatus());\n'
             '\t\tuint32_t error = 0; int er = DI_GetError(&error);\n'
             '\t\tKwceDvdTrace("di-read-fail",ret,DI_GetStatus());\n'
             '\t\tKwceDvdTrace("di-read-error",er,(int)error);')
        for suffix in ('\n\t\tprint_debug(dvdcss,','\n\t\tprint_debug( dvdcss,'):
            add(f,old+suffix,'\t\tKwceDvdTrace("di-read-fail",ret,DI_GetStatus());'+suffix)
        # Distinguish shutdown calls without changing command order or claiming
        # that a returned failed read proves every later IOS request is safe.
        add('source/wiimc.cpp','\tDI_StopMotor();\n\tDI_Close();',
            '\tKwceDvdTrace("drive-stop",0,0);\n\tDI_StopMotor();\n'
            '\tKwceDvdTrace("drive-stop",1,0);\n'
            '\tKwceDvdTrace("drive-close",0,0);\n\tDI_Close();\n'
            '\tKwceDvdTrace("drive-close",1,0);')
    if revision>=55:
        # AHB access and DVD-video command permission are independent HW bits.
        # Native entry does not launch the HBC/channel TMD. Establish the DVD
        # bit after IOS reload, before DI owns the drive; preserve other bits.
        helper = """static int kwceDvdVideoBefore = -1;
static int kwceDvdVideoAfter = -1;
static int kwceDvdVideoChanged = 0;
static void KwceEnableDvdVideo(void)
{
    if (*(volatile unsigned *)0xcd800064 != 0xffffffffu) return;
    volatile unsigned *flags = (volatile unsigned *)0xcd800180;
    unsigned old = *flags;
    kwceDvdVideoBefore = (old & 0x00200000u) != 0;
    if (!kwceDvdVideoBefore) {
        *flags = old | 0x00200000u;
        __asm__ volatile("eieio" ::: "memory");
        kwceDvdVideoChanged = 1;
    }
    kwceDvdVideoAfter = (*flags & 0x00200000u) != 0;
}
static void KwceRestoreDvdVideo(void)
{
    if (kwceDvdVideoChanged && *(volatile unsigned *)0xcd800064 == 0xffffffffu) {
        volatile unsigned *flags = (volatile unsigned *)0xcd800180;
        *flags = *flags & ~0x00200000u;
        __asm__ volatile("eieio" ::: "memory");
        kwceDvdVideoChanged = 0;
    }
}
"""
        if revision>=58:
            # HBC main.c clears DI_DISABLEDVD (bit21) after IOS reload.
            # R55-R57 used the inverse polarity; preserve those frozen builds.
            helper=helper.replace('if (!kwceDvdVideoBefore)', 'if (kwceDvdVideoBefore)')
            helper=helper.replace('*flags = old | 0x00200000u;', '*flags = old & ~0x00200000u;')
            helper=helper.replace('*flags = *flags & ~0x00200000u;', '*flags = *flags | 0x00200000u;')
        add('source/wiimc.cpp','#include <iso9660.h>','#include <iso9660.h>\nstatic void KwceRestoreDvdVideo(void);')
        add('source/wiimc.cpp','int main(int argc, char *argv[])',helper+'\nint main(int argc, char *argv[])')
        add('source/wiimc.cpp','\tDI_Init();\n\tWPAD_Init();',
            '\tKwceEnableDvdVideo();\n\tDI_Init();\n\tWPAD_Init();')
        add('source/wiimc.cpp','KwceDvdTrace("startup",'+str(revision)+',0);',
            'KwceDvdTrace("startup",'+str(revision)+',0);\n\tKwceDvdTrace("dvd-video-mode",kwceDvdVideoBefore,kwceDvdVideoAfter);')
        add('source/wiimc.cpp','\tKwceDvdTrace("drive-close",1,0);',
            '\tKwceDvdTrace("drive-close",1,0);\n\tKwceRestoreDvdVideo();')
    if revision>=56:
        # DI_UseCache only controls cache creation at DI_Init. Calling it later
        # leaves the existing 26-sector read-ahead cache active in pinned libdi.
        # R59: the cache-off experiment (R56-58) did not fix the read failure
        # (the cause was the DVD disable bit) and turns every 1-sector request
        # into its own drive command during playback. Restore libdi's default
        # 26-sector read-ahead; frozen R56-58 keep their exact behaviour.
        cache=revision>=59
        if not cache:
            add('source/wiimc.cpp','\tKwceEnableDvdVideo();\n\tDI_Init();',
                '\tKwceEnableDvdVideo();\n\tDI_UseCache(false);\n\tDI_Init();')
        add('source/wiimc.cpp','KwceDvdTrace("dvd-video-mode",kwceDvdVideoBefore,kwceDvdVideoAfter);',
            'KwceDvdTrace("dvd-video-mode",kwceDvdVideoBefore,kwceDvdVideoAfter);\n\tKwceDvdTrace("drive-cache",'+str(int(cache))+',0);')
        f='source/mplayer/libdvdcss/device.c'
        for call,count in [('DI_ReadDVD(bfr, blocks, dvdcss->i_pos)','blocks'),
                           ('DI_ReadDVD(bfr, len / DVDCSS_BLOCK_SIZE, dvdcss->i_pos)','len / DVDCSS_BLOCK_SIZE')]:
            add(f,'\tret = '+call+';',
                '\tif(kwceSeq) KwceDvdTrace("di-size",kwceSeq,'+count+');\n\tret = '+call+';')
    if 57<=revision<=58:  # diagnostic first-read probe; not needed once reads work
        helper=(Path(__file__).resolve().parents[1]/'homebrew/kwce-dvd/r57/source/kwce/kwce_read_probe.h').read_text()
        add('source/fileop.cpp','static bool MountDVD(bool silent)',helper+'\nstatic bool MountDVD(bool silent)')
        add('source/fileop.cpp','\t\t\tKwceDvdTrace("drive-ready",DI_GetStatus(),0);\n\t\t\tmounted = true;',
            '\t\t\tKwceDvdTrace("drive-ready",DI_GetStatus(),0);\n'
            '\t\t\tif(!KwceProbeFirstReads()) break;\n\t\t\tmounted = true;')
    if revision>=60:
        # DVD menu pointer: upstream maps the pointer through vo_dwidth/vo_dheight,
        # which this VO never sets to the drawn rectangle (they come from an
        # aspect() call made with swapped screen dimensions). Positions were
        # scaled about the centre, so buttons near the picture edge (e.g. a
        # next-page arrow) could never be hit. Map through the quad actually drawn.
        add('source/mplayer/osdep/gx_supp.c',
            'void GX_SetScreenPos(int _hor_pos, int _vert_pos, float _hor_zoom, float _vert_zoom)\n{',
            """/* KWCE R60: screen fraction (0..1, y down) -> picture fraction, using the
 * same quad as GX_UpdateScaling(). Returns 0 and (-1,-1) outside the picture. */
int KwceScreenToPicture(double sx, double sy, double *fx, double *fy)
{
	double xscale = (int)(video_haspect * hor_zoom), yscale = (int)(video_vaspect * vert_zoom);
	*fx = *fy = -1.0;
	if (xscale <= 0 || yscale <= 0 || mplayerwidth <= 0 || mplayerheight <= 0) return 0;
	double x = sx * mplayerwidth - mplayerwidth / 2.0 - (video_diffx + hor_pos);
	double y = sy * mplayerheight - mplayerheight / 2.0 - (video_diffy + vert_pos);
	double px = (x + xscale) / (2.0 * xscale), py = (y + yscale) / (2.0 * yscale);
	if (px <= 0.0 || px >= 1.0 || py <= 0.0 || py >= 1.0) return 0;
	*fx = px; *fy = py;
	return 1;
}

void GX_SetScreenPos(int _hor_pos, int _vert_pos, float _hor_zoom, float _vert_zoom)
{""")
        add('source/mplayer/mplayer.c',
            '\tx=(int)x*(double)vo_screenwidth/screenwidth;\n\ty=(int)y*(double)vo_screenheight/screenheight;\n',
            '\t/* KWCE R60: pass screen fractions x10000; command.c maps them to the picture */\n'
            '\tx=(int)(x*10000.0/screenwidth);\n\ty=(int)(y*10000.0/screenheight);\n')
        add('source/mplayer/command.c',
            '                rescale_input_coordinates(pointer_x, pointer_y, &dx, &dy);\n#ifdef CONFIG_DVDNAV',
            '#ifdef GEKKO\n                { extern int KwceScreenToPicture(double, double, double *, double *);\n'
            '                  KwceScreenToPicture(pointer_x / 10000.0, pointer_y / 10000.0, &dx, &dy); }\n'
            '#else\n                rescale_input_coordinates(pointer_x, pointer_y, &dx, &dy);\n#endif\n#ifdef CONFIG_DVDNAV')
    if revision>=61:
        # Upstream gives up a cached read after 80 polls (~0.8 s) and reports
        # end-of-stream; that is its network-reconnect hack. A disc drive needs
        # longer after spin-up or a long seek, and giving up there cuts a DVD
        # menu still mid-picture (corrupt first menu, navigation that only
        # works on a second try). Discs get 15 s; other streams are unchanged.
        add('source/mplayer/stream/cache2.c',
            '\tif(getWeird > 80) { //assume no longer playing audio',
            '\t/* KWCE R61: disc reads may legitimately stall longer than a network poll */\n'
            '\tif(getWeird > ((s->stream && (s->stream->type == STREAMTYPE_DVDNAV || s->stream->type == STREAMTYPE_DVD)) ? 1500 : 80)) { //assume no longer playing audio')
    if revision>=62:
        f='source/mplayer/mplayer.c'
        # --- DVD menu stills -------------------------------------------------
        # The MPEG-2 decoder returns each picture one call late. A menu still is
        # a single I-frame followed by nothing, so the page just entered stayed
        # inside the decoder and the *previous* picture was shown: a corrupt
        # first menu, page changes that only appeared later, and "menu" needing
        # a second press. When the still is reached, hand the decoder one
        # sequence end code; libavcodec then releases the pending picture.
        add(f,'static mp_image_t *mp_dvdnav_restore_smpi(int *in_size,',
            'static int kwce_nav_fed; /* a picture was fed since the decoder was last drained */\n'
            'static mp_image_t *mp_dvdnav_restore_smpi(int *in_size,')
        add(f,'        // display still frame, if any\n        if (mpctx->nav_smpi)\n            decoded_frame = mpctx->nav_smpi;\n',
            '        if (kwce_nav_fed) {\n'
            '            /* KWCE R62: drain the decoder once per still */\n'
            '            static unsigned char kwce_seq_end[4 + 64] = {0x00, 0x00, 0x01, 0xB7};\n'
            '            kwce_nav_fed = 0;\n'
            '            *start   = kwce_seq_end;\n'
            '            *in_size = 4;\n'
            '            return NULL;\n'
            '        }\n'
            '        // display still frame, if any\n        if (mpctx->nav_smpi)\n            decoded_frame = mpctx->nav_smpi;\n')
        add(f,'    if (in_size > 0)\n        mpctx->nav_buffer = malloc(in_size);',
            '    if (in_size > 4)\n        kwce_nav_fed = 1;\n'
            '    if (in_size > 0)\n        mpctx->nav_buffer = malloc(in_size);')
        # A picture whose slices stop before the bottom row is truncated (the
        # first pack is delivered once more when the disc VM restarts a cell).
        # Decoding it only produces concealment streaks; skip it on discs.
        v='source/mplayer/libmpdemux/video.c'
        add(v,'          if(!read_video_packet(d_video)) return -1; // EOF\n          // process headers:\n          switch(i){\n            case 0x1B3: mp_header_process_sequence_header (&picture, &videobuffer[start]);break;',
            '          if(!read_video_packet(d_video)) return -1; // EOF\n'
            '          if(i>=0x101 && i<0x1B0) kwce_last_slice=i-0x100; /* KWCE R62 */\n'
            '          // process headers:\n          switch(i){\n            case 0x1B3: mp_header_process_sequence_header (&picture, &videobuffer[start]);break;')
        add(v,'  if(video_codec == VIDEO_MPEG12){\n        int in_frame=0;',
            '  if(video_codec == VIDEO_MPEG12){\n        int in_frame=0;\n        int kwce_last_slice=0;')
        add(v,'        fps = picture.fps * picture.frame_rate_extension_n / picture.frame_rate_extension_d;\n\n        *start=videobuffer; in_size=videobuf_len;',
            '        if(kwce_last_slice && demuxer->stream &&\n'
            '           (demuxer->stream->type==STREAMTYPE_DVDNAV || demuxer->stream->type==STREAMTYPE_DVD) &&\n'
            '           picture.picture_structure==3 && picture.display_picture_height>=32 &&\n'
            '           kwce_last_slice < picture.display_picture_height/16) {\n'
            '            videobuf_len=0; /* KWCE R62: truncated frame picture */\n'
            '            return video_read_frame(sh_video,frame_time_ptr,start,force_fps);\n'
            '        }\n'
            '        fps = picture.fps * picture.frame_rate_extension_n / picture.frame_rate_extension_d;\n\n        *start=videobuffer; in_size=videobuf_len;')
        # --- No SD writes while playing ---------------------------------------
        # Every trace line reopened and appended the log on SD. The periodic
        # lines did that every ~2 s during menus and playback. Keep lines in RAM
        # once video starts; write them when HOME opens and at exit.
        k='source/kwce/kwce_dvd.cpp'
        add(k,'extern "C" void KwceDvdTrace(const char *event, int a, int b)\n{\n\tif (!appPath[0]) return;\n\tchar path[1100];\n\tsnprintf(path,sizeof path,"%s/playback-r21.log",appPath);\n\tFILE *f=fopen(path,"a");\n\tif (f) { fprintf(f,"%s %d %d\\n",event,a,b); fclose(f); }\n}',
            'static char kwceLog[32768];\nstatic unsigned kwceLogUsed;\nstatic int kwceLogDirect = 1;\n'
            'unsigned long long kwceReadTicks;\nunsigned kwceReadCalls;\n'
            'extern "C" void KwceDvdTraceFlush(void)\n{\n\tif (!kwceLogUsed || !appPath[0]) return;\n\tchar path[1100];\n'
            '\tsnprintf(path,sizeof path,"%s/playback-r21.log",appPath);\n\tFILE *f=fopen(path,"a");\n'
            '\tif (f) { fwrite(kwceLog,1,kwceLogUsed,f); fclose(f); }\n\tkwceLogUsed=0;\n}\n'
            'extern "C" void KwceDvdTrace(const char *event, int a, int b)\n{\n\tif (!appPath[0]) return;\n'
            '\tchar line[64];\n\tint n=snprintf(line,sizeof line,"%s %d %d\\n",event,a,b);\n\tif (n<=0 || n>=(int)sizeof line) return;\n'
            '\tif (!strcmp(event,"player-exit")) kwceLogDirect=1;\n'
            '\tif (kwceLogUsed+n>sizeof kwceLog) { if (!kwceLogDirect) return; KwceDvdTraceFlush(); }\n'
            '\tmemcpy(kwceLog+kwceLogUsed,line,n); kwceLogUsed+=n;\n'
            '\tif (kwceLogDirect) KwceDvdTraceFlush();\n'
            '\tif (!strcmp(event,"video-config")) kwceLogDirect=0;\n}\n'
            'extern "C" int KwcePerfFrames(void);\nextern "C" int KwcePerfDrops(void);\n'
            'extern "C" void KwceDvdPerf(unsigned flips)\n{\n'
            '\tKwceDvdTrace("perf-time",(int)(ticks_to_millisecs(gettime())&0x7fffffff),(int)flips);\n'
            '\tKwceDvdTrace("perf-frames",KwcePerfFrames(),KwcePerfDrops());\n'
            '\tKwceDvdTrace("perf-read",(int)(ticks_to_millisecs(kwceReadTicks)&0x7fffffff),(int)kwceReadCalls);\n}')
        add(k,'#include "kwce_trace.h"','#include "kwce_trace.h"\n#include <ogc/lwp_watchdog.h>')
        add('source/kwce/kwce_trace.h','void KwceDvdTrace(const char *event, int a, int b);',
            'void KwceDvdTrace(const char *event, int a, int b);\nvoid KwceDvdTraceFlush(void);\nvoid KwceDvdPerf(unsigned flips);')
        add(f,'static int drop_frame_cnt; // total number of dropped frames',
            'static int drop_frame_cnt; // total number of dropped frames\n'
            'int KwcePerfFrames(void) { return total_frame_cnt; }\nint KwcePerfDrops(void) { return drop_frame_cnt; }')
        add('source/video.cpp','static unsigned calls=0;if((++calls%120)==0)KwceDvdTrace("present-count",kwceFlips,flip_pending);',
            'static unsigned calls=0;if((++calls%600)==0)KwceDvdPerf(kwceFlips); /* KWCE R62: timing summary, RAM only */')
        add('source/mplayer/osdep/gx_supp.c','if(lastSync!=sync_interlace || (++frames%120)==0){','if(lastSync!=sync_interlace){')
        d='source/mplayer/libdvdcss/device.c'
        for call in ('DI_ReadDVD(bfr, blocks, dvdcss->i_pos)','DI_ReadDVD(bfr, len / DVDCSS_BLOCK_SIZE, dvdcss->i_pos)'):
            add(d,'\tret = '+call+';',
                '\t{ extern unsigned long long gettime(void); extern unsigned long long kwceReadTicks; extern unsigned kwceReadCalls;\n'
                '\t  unsigned long long kwceT0=gettime(); ret = '+call+'; kwceReadTicks+=gettime()-kwceT0; kwceReadCalls++; }')
        h='source/kwce/kwce_home.cpp'
        add(h,'void KwceHomeOpen()\n{\n\tif (!g_home || g_state != H_CLOSED) return;',
            'extern "C" void KwceDvdTraceFlush(void);\nvoid KwceHomeOpen()\n{\n\tif (!g_home || g_state != H_CLOSED) return;\n\tKwceDvdTraceFlush(); /* playback is paused here */')
        # Battery bars: same raw thresholds as the console's own HOME Menu
        # (a remote shown with 2 bars there appeared as 1 red bar here).
        add(h,'bars = raw > 0x82 ? 4 : raw > 0x6A ? 3 : raw > 0x4C ? 2 : raw > 0x30 ? 1 : 0;',
            'bars = raw >= 0x55 ? 4 : raw >= 0x44 ? 3 : raw >= 0x33 ? 2 : raw >= 0x03 ? 1 : 0;')
    if revision>=63:
        # --- Presentation cadence ---------------------------------------------
        # (1) On interlaced output the retrace handler shows a frame only on the
        # matching field, but the draw path waited a single retrace and then
        # drew the next frame over the one still waiting: every other frame was
        # lost (15 shown per second). Wait until the pending frame is shown;
        # the handler's own two-retrace limit bounds this.
        add('source/mplayer/osdep/gx_supp.c','\telse*/ if(flip_pending)\n\t\tVIDEO_WaitVSync();',
            '\telse*/ { int kwceWaits=0; /* KWCE R63: never draw over a frame that was not shown */\n'
            '\t\twhile(flip_pending && kwceWaits++<4) VIDEO_WaitVSync(); }')
        # (2) A DVD still re-presented itself at the last picture's display time
        # (about 51 ms here), so the pointer and menu overlay moved at 19 fps.
        # Stills hold no new picture; refresh them at the display rate and
        # advance the still clock by the same step.
        f='source/mplayer/mplayer.c'
        add(f,'            if (mpctx->stream->type == STREAMTYPE_DVDNAV && in_size < 0) {\n                if (mp_dvdnav_is_eof(mpctx->stream))\n                    return -1;',
            '            if (mpctx->stream->type == STREAMTYPE_DVDNAV && in_size < 0) {\n                if (mp_dvdnav_is_eof(mpctx->stream))\n                    return -1;\n'
            '                frame_time = 1.0f / 60.0f; /* KWCE R63: still refresh step */')
        add(f,'        mpctx->sh_video->pts += 1 / mpctx->sh_video->fps;\n','        mpctx->sh_video->pts += 1.0f / 60.0f; /* KWCE R63: matches the refresh step */\n')
    if revision>=64:
        # Field-parity presentation: show on the matching field, otherwise on
        # the very next retrace. On real interlaced output the next retrace is
        # the matching field anyway; where the reported field never matches
        # (emulator), a frame still takes at most two retraces instead of three.
        h='source/kwce/kwce_present.h'
        add(h,'    if (home || mode!=0 || missed>=2) return 1;','    if (home || mode!=0 || missed>=1) return 1;')
        add(h,'    failed+=!KwceShouldPresent(0,1,1,0,2);','    failed+=!KwceShouldPresent(0,1,1,0,1);\n    failed+=!KwceShouldPresent(0,2,0,0,1);\n    failed+=!KwceShouldPresent(0,1,1,0,2);')
    if revision>=65:
        # --- HOME Menu frame of the console itself ------------------------------
        # 43K iplFramework/iplSystem (NTSC): EFB 640x456 shown on 456 of the
        # 480 lines, projection +-304 (4:3) / +-416 (16:9) by +-228, VI width
        # 670 / 686 of 720. R31's screenheight/500 drew the layout 4% small and
        # showed +-250 units, so the top bar's hidden pose (y 310, lower edge
        # at 228) stayed on screen in the remote settings. Now one layout unit
        # is one line, the horizontal unit follows the original VI width from
        # this player's live VI width, and the HOME is clipped to the original
        # picture with black outside it, as the console's own output is.
        h='source/kwce/kwce_home.cpp'
        add(h,'/* Fit the complete HOME layout within a TV-safe margin in both aspect ratios. */\n'
              'static float scale() { return screenheight / 500.0f; }',
            '/* KWCE R65: the console HOME frame (43K NTSC): one layout unit per line, +-228 visible,\n'
            '   VI width 670 (4:3) / 686 (16:9) for 608 / 832 units. kx() maps that VI width per unit\n'
            '   onto this player\'s live VI width, so proportions match in both aspect ratios. */\n'
            'static float scale() { return screenheight / 480.0f; }\n'
            'static float kx() { return (wide() ? 686.0f / 832.0f : 670.0f / 608.0f) * screenwidth / ((float)vmode->viWidth * scale()); }\n'
            '/* Black outside the original picture; layout and cursors are clipped to it. */\n'
            'static void home_frame(bool on)\n'
            '{\n'
            '\tif (!on) { GX_SetScissor(0, 0, vmode->fbWidth, vmode->efbHeight); return; }\n'
            '\tconst float sw = screenwidth, sh = screenheight, fw = vmode->fbWidth, fh = vmode->efbHeight;\n'
            '\tint x0 = (int)roundf((sw * 0.5f - (wide() ? 416.f : 304.f) * scale() * kx()) * fw / sw);\n'
            '\tint y0 = (int)roundf((sh * 0.5f - 228.f * scale()) * fh / sh);\n'
            '\tif (x0 < 0) x0 = 0;\n'
            '\tif (y0 < 0) y0 = 0;\n'
            '\tconst float vx = x0 * sw / fw, vy = y0 * sh / fh;\n'
            '\tconst GXColor black = {0, 0, 0, 255};\n'
            '\tif (vy > 0) { Menu_DrawRectangle(0, 0, sw, vy, black, 1); Menu_DrawRectangle(0, sh - vy, sw, vy, black, 1); }\n'
            '\tif (vx > 0) { Menu_DrawRectangle(0, 0, vx, sh, black, 1); Menu_DrawRectangle(sw - vx, 0, vx, sh, black, 1); }\n'
            '\tGX_SetScissor(x0, y0, vmode->fbWidth - 2 * x0, vmode->efbHeight - 2 * y0);\n'
            '}')
        add(h,'float lx = (x - screenwidth * 0.5f) / scale(), ly = (screenheight * 0.5f - y) / scale();',
            'float lx = (x - screenwidth * 0.5f) / (scale() * kx()), ly = (screenheight * 0.5f - y) / scale();')
        add(h,'guMtxScaleApply(mv, mv, s * (wide()?1.3684211f:1.f), s, 1.f);',
            'guMtxScaleApply(mv, mv, s * kx() * (wide()?1.3684211f:1.f), s, 1.f);')
        add(h,'translate.x = (x - screenwidth * 0.5f) / (s * (wide()?1.3684211f:1.f));',
            'translate.x = (x - screenwidth * 0.5f) / (s * kx() * (wide()?1.3684211f:1.f));')
        add(h,'\tMenu_DrawRectangle(0,0,screenwidth,screenheight * 0.08f,(GXColor){0,0,0,255},1);\n'
              '\tMenu_DrawRectangle(0,screenheight * 0.92f,screenwidth,screenheight * 0.08f,(GXColor){0,0,0,255},1);',
            '\thome_frame(true);')
        add(h,'\t\tif (w && w->ir.valid) KwceCursorDraw(i, w->ir.x, w->ir.y, w->ir.angle);\n\t}\n',
            '\t\tif (w && w->ir.valid) KwceCursorDraw(i, w->ir.x, w->ir.y, w->ir.angle);\n\t}\n\thome_frame(false);\n')
    if revision>=900:
        # Emulator-only diagnostics (never packaged): keep trace lines in a
        # RAM ring that the host reads from the isolated Dolphin process, and
        # expose the still-frame decode path. Consecutive duplicates collapse.
        add('source/kwce/kwce_dvd.cpp',
            'extern "C" void KwceDvdTrace(const char *event, int a, int b)\n{\n\tif (!appPath[0]) return;',
            """#define KWCE_RING_EVENTS """+("0" if revision>=901 else "1")+"""
static struct { char magic[20]; unsigned used; unsigned repeats; char text[131072]; } kwceRing = {"KWCE-RING-MAGIC!",0,0,{0}};
static char kwceRingLast[64];
extern "C" void KwceDvdTrace(const char *event, int a, int b)
{
	if(KWCE_RING_EVENTS) { char line[64]; int n=snprintf(line,sizeof line,"%s %d %d\\n",event,a,b);
	  if(!strcmp(line,kwceRingLast)) kwceRing.repeats++;
	  else if(n>0 && kwceRing.used+n+24<sizeof kwceRing.text) {
	    if(kwceRing.repeats){kwceRing.used+=snprintf(kwceRing.text+kwceRing.used,24,"x %u 0\\n",kwceRing.repeats);kwceRing.repeats=0;}
	    memcpy(kwceRing.text+kwceRing.used,line,n);kwceRing.used+=n;strcpy(kwceRingLast,line); } }
	if (b!=-12345) return; /* debug build: RAM ring only */
	if (!appPath[0]) return;""")
        add('source/mplayer/mplayer.c',
            "                                       &start, force_fps);\n#ifdef CONFIG_DVDNAV\n            // wait, still frame or EOF",
            "                                       &start, force_fps);\n            KwceDvdTrace(\"vrf\",in_size,mpctx->d_video->eof);\n#ifdef CONFIG_DVDNAV\n            // wait, still frame or EOF")
        add('source/mplayer/mplayer.c',
            "                                         sh_video->pts, &full_frame);\n\n\t\t\tif (flush && !decoded_frame)",
            "                                         sh_video->pts, &full_frame);\n            KwceDvdTrace(\"dec\",in_size,(decoded_frame?1:0)|(full_frame?2:0)|(flush?4:0)|(mpctx->nav_smpi?8:0)|(mpctx->nav_buffer?16:0));\n\n\t\t\tif (flush && !decoded_frame)")
        add('source/mplayer/mplayer.c',
            "        mp_dvdnav_read_wait(mpctx->stream, 1, 1);\n        mp_dvdnav_context_free(mpctx);",
            "        KwceDvdTrace(\"cellchg\",*in_size,0);\n        mp_dvdnav_read_wait(mpctx->stream, 1, 1);\n        mp_dvdnav_context_free(mpctx);")
        add('source/mplayer/mplayer.c',
            "        if (mpctx->nav_buffer && !decoded_frame) {\n            *start   = mpctx->nav_start;",
            "        if (mpctx->nav_buffer && !decoded_frame) {\n            KwceDvdTrace(\"refeed\",mpctx->nav_in_size,0);\n            *start   = mpctx->nav_start;")
        add('source/mplayer/libmpdemux/video.c',
            "            if(i<0x101 || i>=0x1B0){  // not slice code -> end of frame\n              if(!i) return -1; // EOF",
            "            if(i<0x101 || i>=0x1B0){  // not slice code -> end of frame\n              if(!i) { extern void KwceDvdTrace(const char *,int,int); KwceDvdTrace(\"vrf-partial\",videobuf_len,0); return -1; } // EOF")
    if revision>=901:
        # Emulator-only per-frame timing (0.1 ms units) in the RAM ring.
        add('source/kwce/kwce_dvd.cpp','static char kwceRingLast[64];',
            'static char kwceRingLast[64];\n'
            'extern "C" void KwceDbgT(const char *name)\n{\n\tu32 level = IRQ_Disable();\n'
            '\tif (kwceRing.used+24>=sizeof kwceRing.text) kwceRing.used=0;\n'
            '\tkwceRing.used+=snprintf(kwceRing.text+kwceRing.used,24,"%s %u\\n",name,(unsigned)(ticks_to_microsecs(gettime())/100));\n'
            '\tIRQ_Restore(level);\n}')
        add('source/kwce/kwce_trace.h','void KwceDvdPerf(unsigned flips);','void KwceDvdPerf(unsigned flips);\nvoid KwceDbgT(const char *name);')
        g='source/mplayer/osdep/gx_supp.c'
        add(g,'extern int sync_interlace;\nstatic int kwceTraceFrames=0;\n','extern int sync_interlace;\nstatic int kwceTraceFrames=0;\nextern void KwceDbgT(const char *name);\n')
        add(g,'if(kwceTraceFrames)KwceDvdTrace("fill-enter",need_wait,sync_interlace);','if(kwceTraceFrames)KwceDvdTrace("fill-enter",need_wait,sync_interlace);\n\tKwceDbgT("F0");')
        add(g,'\tif (stride[0] & 7)\n\t\tLUMA_COPY(u64)','\tKwceDbgT("F1");\n\tif (stride[0] & 7)\n\t\tLUMA_COPY(u64)')
        add(g,'if(kwceTraceThis)KwceDvdTrace("frame-enter",need_wait,sync_interlace);','if(kwceTraceThis)KwceDvdTrace("frame-enter",need_wait,sync_interlace);\n\tKwceDbgT("D0");')
        add(g,'\tGX_InvVtxCache();\n\tGX_InvalidateTexAll();','\tKwceDbgT("D1");\n\tGX_InvVtxCache();\n\tGX_InvalidateTexAll();')
        add(g,'\t\twhile(flip_pending && kwceWaits++<4) VIDEO_WaitVSync(); }','\t\twhile(flip_pending && kwceWaits++<4) VIDEO_WaitVSync(); }\n\tKwceDbgT("D2");')
        add(g,'\tneed_wait=true;\n\tif(kwceTraceThis){KwceDvdTrace("frame-submit"','\tKwceDbgT("D4");\n\tneed_wait=true;\n\tif(kwceTraceThis){KwceDvdTrace("frame-submit"')
        add('source/mplayer/mplayer.c','                    frame_time_remaining = sleep_until_update(&mpctx->time_frame, &aq_sleep_time);',
            '                    { extern void KwceDbgT(const char *); KwceDbgT("S0");\n'
            '                    frame_time_remaining = sleep_until_update(&mpctx->time_frame, &aq_sleep_time);\n'
            '                    KwceDbgT("S1"); }')
        add('source/video.cpp','VIDEO_Flush(); whichfb^=1; flip_pending=false; missed=0; ++kwceFlips;','VIDEO_Flush(); whichfb^=1; flip_pending=false; missed=0; ++kwceFlips; KwceDbgT("VF");')
        if revision>=902:
            add('source/video.cpp','    if (!flip_pending) { missed=0; return; }','    if (!flip_pending) { missed=0; return; }\n    KwceDbgT(VIDEO_GetNextField()?(sync_interlace==2?"N1s2":sync_interlace==1?"N1s1":"N1s0"):(sync_interlace==2?"N0s2":sync_interlace==1?"N0s1":"N0s0"));')
        add('source/video.cpp','\tneed_wait=false;\n\t//VIDEO_Flush();\n\tflip_pending = true;','\tneed_wait=false;\n\t//VIDEO_Flush();\n\tflip_pending = true; KwceDbgT("GD");')
    if revision>=58:
        add('source/wiimc.cpp','KwceDvdTrace("dvd-video-mode",kwceDvdVideoBefore,kwceDvdVideoAfter);',
            'KwceDvdTrace("dvd-disable-bit",kwceDvdVideoBefore,kwceDvdVideoAfter);')
    return p

def _home_menu_patches(revision=2):
    """R2: the System Menu's HOME Menu over DVD playback (kwce_home), the Wii cursor,
    the disc's own menus (dvdnav) and two dvdnav commands for its buttons."""
    p=[]
    def add(path,old,new):p.append((path,old,new))
    # dvdnav: "top" = DVD title menu, "restart" = play from the first-play program chain
    add('source/mplayer/input/input.h','  MP_CMD_DVDNAV_MOUSECLICK,\n',
        '  MP_CMD_DVDNAV_MOUSECLICK,\n  MP_CMD_DVDNAV_TOPMENU,   // KWCE\n  MP_CMD_DVDNAV_RESTART,   // KWCE\n')
    add('source/mplayer/command.c','  { "mouse",    MP_CMD_DVDNAV_MOUSECLICK      },\n',
        '  { "mouse",    MP_CMD_DVDNAV_MOUSECLICK      },\n  { "top",      MP_CMD_DVDNAV_TOPMENU         },  // KWCE\n  { "restart",  MP_CMD_DVDNAV_RESTART         },  // KWCE\n')
    add('source/mplayer/stream/stream_dvdnav.c','  if(cmd != MP_CMD_DVDNAV_SELECT && !pci)\n',
        '  if(cmd != MP_CMD_DVDNAV_SELECT && cmd != MP_CMD_DVDNAV_TOPMENU && cmd != MP_CMD_DVDNAV_RESTART && !pci)\n')
    add('source/mplayer/stream/stream_dvdnav.c','    case MP_CMD_DVDNAV_SELECT:\n      status = dvdnav_button_activate(nav, pci);\n',
        '    case MP_CMD_DVDNAV_TOPMENU: // KWCE: HOME Menu "타이틀 메뉴"\n'
        '      if((status = dvdnav_menu_call(nav, DVD_MENU_Title)) != DVDNAV_STATUS_OK)\n'
        '        status = dvdnav_menu_call(nav, DVD_MENU_Root);\n'
        '      break;\n'
        '    case MP_CMD_DVDNAV_RESTART: // KWCE: stop dialog "처음부터 재생"\n'
        '      status = dvdnav_reset(nav);\n'
        '      break;\n'
        '    case MP_CMD_DVDNAV_SELECT:\n      status = dvdnav_button_activate(nav, pci);\n')
    add('source/mplayer/mplayer.c','\t\tcase MP_CMD_DVDNAV_MOUSECLICK:\n\t\t\tcmd->args[0].v.s = strdup("mouse"); break;\n',
        '\t\tcase MP_CMD_DVDNAV_MOUSECLICK:\n\t\t\tcmd->args[0].v.s = strdup("mouse"); break;\n'
        '\t\tcase MP_CMD_DVDNAV_TOPMENU:\n\t\t\tcmd->args[0].v.s = strdup("top"); break;  // KWCE\n'
        '\t\tcase MP_CMD_DVDNAV_RESTART:\n\t\t\tcmd->args[0].v.s = strdup("restart"); break;  // KWCE\n')
    # the disc's own menus: dvdnav:// instead of dvd:// (main title only)
    add('source/settings.cpp','\t// DVD\n\tWiiSettings.dvdMenu = 1;\n','\t// DVD\n\tWiiSettings.dvdMenu = 0; // KWCE: the disc\'s own menu\n')
    add('source/menu.cpp','\t\tSaveSettings(SILENT); // KWCE: the player also runs without an SD card\n',
        '\t\tSaveSettings(SILENT); // KWCE: the player also runs without an SD card\n'
        '\tWiiSettings.dvdMenu = 0; // KWCE: settings saved by R1 asked for the main title only\n')
    # HOME Menu archive after the system font
    add('source/wiimc.cpp','#include "kwce/kwce_dvd.h"\n','#include "kwce/kwce_dvd.h"\n#include "kwce/kwce_home.h"\n')
    add('source/wiimc.cpp','\tKwceDvdLoadFont(); // KWCE: Wii system font (wbf1) for all UI text\n',
        '\tKwceDvdLoadFont(); // KWCE: Wii system font (wbf1) for all UI text\n'
        '\tKwceHomeLoad(); // KWCE: Wii HOME Menu (System Menu layout, channel content 3)\n')
    # HOME during playback opens the HOME Menu; it then owns input and drawing
    add('source/input.cpp','#include "input.h"\n','#include "input.h"\n#include "kwce/kwce_home.h"\n')
    add('source/input.cpp','\tbool ir = false;\n\tbool inDVDMenu = wiiInDVDMenu();\n\tstatic bool volumeUpdated = false;\n',
        '\tbool ir = false;\n\tbool inDVDMenu = wiiInDVDMenu();\n\tstatic bool volumeUpdated = false;\n\n'
        '\tif(KwceHomeActive()) // KWCE: the Wii HOME Menu owns input while it is open\n\t{\n\t\tKwceHomeInput();\n\t\tdrawGui = true;\n\t\treturn;\n\t}\n')
    add('source/input.cpp','''			userInput[0].cpad.data.down & CTR_BUTTON_START)) {
		VIDEO_SetBlack (TRUE);
		ExitRequested = true;
	}''','''			userInput[0].cpad.data.down & CTR_BUTTON_START)) {
		if(KwceHomeReady()) // KWCE: HOME opens the Wii HOME Menu
		{
			KwceHomeOpen();
			drawGui = true;
			return;
		}
		VIDEO_SetBlack (TRUE);
		ExitRequested = true;
	}''')
    add('source/menu.cpp','#include "kwce/kwce_font.h"\n','#include "kwce/kwce_font.h"\n#include "kwce/kwce_home.h"\n')
    add('source/menu.cpp','''extern "C" void DoMPlayerGuiDraw()
{
	if(menuMode != 1)
		return;
''','''extern "C" void DoMPlayerGuiDraw()
{
	if(menuMode != 1)
		return;

	if(KwceHomeActive()) // KWCE: Wii HOME Menu over the paused video
	{
		KwceHomeDraw();
		return;
	}
''')
    # the Wii cursor (System Menu P1_Def layout) instead of WiiMC's pointer image
    # R20 returned to WiiMC's pointer as a suspect for the R19 playback freeze,
    # but R20 froze the same way; R21 found the cause (field-sync wait). R66
    # restores the Wii cursor over DVD menus/playback and the GUI screens.
    for indent in (('\t','\t\t') if revision<20 or revision>=66 else ()):
        add('source/menu.cpp',f'''{indent}if(userInput[0].wpad->ir.valid)
{indent}\tMenu_DrawImg(userInput[0].wpad->ir.x-48, userInput[0].wpad->ir.y-48,
{indent}\t\t96, 96, pointer[0]->GetImage(), userInput[0].wpad->ir.angle, 1, 1, 255, GX_TF_RGBA8);
''',f'''{indent}if(userInput[0].wpad->ir.valid && KwceHomeReady()) // KWCE: Wii cursor
{indent}\tKwceCursorDraw(0, userInput[0].wpad->ir.x, userInput[0].wpad->ir.y, userInput[0].wpad->ir.angle);
{indent}else if(userInput[0].wpad->ir.valid)
{indent}\tMenu_DrawImg(userInput[0].wpad->ir.x-48, userInput[0].wpad->ir.y-48,
{indent}\t\t96, 96, pointer[0]->GetImage(), userInput[0].wpad->ir.angle, 1, 1, 255, GX_TF_RGBA8);
''')
    if revision>=22:
        ao='source/mplayer/libao2/ao_gekko.c'
        add(ao,'#include "osdep/ave-rvl.h"\n','#include "osdep/ave-rvl.h"\n#include "../../kwce/kwce_sound.h"\n')
        add(ao,'static void switch_buffers()\n{\n','static void switch_buffers()\n{\n\tint rate = use32kHz ? 32000 : 48000;\n\tif(KwceSoundOwnsAudio()) { KwceSoundDma(NULL,rate); return; }\n')
        add(ao,'static void switch_buffers()','extern bool use32kHz;\nstatic void switch_buffers()')
        add(ao,'\t\tAUDIO_InitDMA((u32)buffers[buffer_play], BUFFER_SIZE);','\t\tif(!KwceSoundDma(buffers[buffer_play],rate)) AUDIO_InitDMA((u32)buffers[buffer_play], BUFFER_SIZE);')
        add(ao,'\t\tAUDIO_InitDMA((u32)silence, BUFFER_SIZE);','\t\tif(!KwceSoundDma(NULL,rate)) AUDIO_InitDMA((u32)silence, BUFFER_SIZE);')
        add(ao,'\tao_data.samplerate = use32kHz ? 32000 : 48000;','\tao_data.samplerate = use32kHz ? 32000 : 48000;\n\tKwceSoundNative(ao_data.samplerate,1);')
        add(ao,'static void uninit(int immed)\n{','static void uninit(int immed)\n{\n\tKwceSoundNative(ao_data.samplerate,0);')
    return p

LYT=['Animator.cpp','Animator.h','BannerTools.h','Layout.cpp','Layout.h','LytSystem.h','Material.cpp','Material.h','Pane.cpp','Pane.h',
     'Picture.cpp','Picture.h','QuadPane.cpp','QuadPane.h','Textbox.cpp','Textbox.h','Texture.cpp','Texture.h','U8Archive.h',
     'WiiFont.cpp','WiiFont.h','Window.cpp','Window.h','gx_addons.c','gx_addons.h']

def overlay(css=False,revision=2):
    """(destination relative to the work tree, source relative to the repo).
    Revision 1 builds from the frozen copy in homebrew/kwce-dvd/r1."""
    base='homebrew/kwce-dvd/r1' if revision==1 else 'homebrew/kwce-dvd/r6' if revision<=6 else 'homebrew/kwce-dvd/r19' if revision<=19 else 'homebrew/kwce-dvd/r20' if revision==20 else 'homebrew/kwce-dvd/r21' if revision==21 else 'homebrew/kwce-dvd/r22' if revision==22 else 'homebrew/kwce-dvd/r23' if revision==23 else 'homebrew/kwce-dvd/r24' if revision==24 else 'homebrew/kwce-dvd/r25' if revision<=27 else 'homebrew/kwce-dvd/r29' if revision<=29 else 'homebrew/kwce-dvd/r30' if revision==30 else 'homebrew/kwce-dvd/r31' if revision==31 else 'homebrew/kwce-dvd/r32' if revision==32 else 'homebrew/kwce-dvd/r33' if revision==33 else 'homebrew/kwce-dvd/r34' if revision==34 else 'homebrew/kwce-dvd/r35' if revision>=36 else 'homebrew/kwce-dvd'
    names=['kwce_font.c','kwce_font.h','kwce_dvd.cpp','kwce_dvd.h']+(['kwce_home.cpp','kwce_home.h'] if revision>=2 else [])+(['kwce_trace.h'] if revision>=20 else [])+(['kwce_present.h']if revision>=21 else [])+(['kwce_sound.cpp','kwce_sound.h']if revision>=22 else [])
    files=[(f'source/kwce/{n}',f'{base}/source/kwce/{n}') for n in names]
    if revision>=2:files+=[(f'source/kwce/lyt/{n}',f'{base}/source/kwce/lyt/{n}') for n in LYT]
    if revision==2:
        frozen={'kwce_home.cpp','lyt/WiiFont.cpp','lyt/WiiFont.h','lyt/Textbox.cpp'}
        files=[(dst,'homebrew/kwce-dvd/r2/'+dst if dst.removeprefix('source/kwce/')in frozen else src)for dst,src in files]
    if revision==3:
        files=[(dst,'homebrew/kwce-dvd/r3/'+dst if dst=='source/kwce/kwce_home.cpp' else src)for dst,src in files]
    if revision==7:
        files=[(dst,'homebrew/kwce-dvd/r6/'+dst if dst=='source/kwce/kwce_home.cpp' else src)for dst,src in files]
    if revision==8:
        files=[(dst,'homebrew/kwce-dvd/r8/'+dst if dst=='source/kwce/kwce_home.cpp' else src)for dst,src in files]
    if revision==9:
        files=[(dst,'homebrew/kwce-dvd/r9/'+dst if dst=='source/kwce/kwce_home.cpp' else src)for dst,src in files]
    if revision==10:
        files=[(dst,'homebrew/kwce-dvd/r10/'+dst if dst=='source/kwce/kwce_home.cpp' else src)for dst,src in files]
    if revision==11:
        files=[(dst,'homebrew/kwce-dvd/r11/'+dst if dst=='source/kwce/kwce_home.cpp' else src)for dst,src in files]
    if revision==12:
        files=[(dst,'homebrew/kwce-dvd/r12/'+dst if dst=='source/kwce/kwce_home.cpp' else src)for dst,src in files]
    if revision==13:
        files=[(dst,'homebrew/kwce-dvd/r13/'+dst if dst=='source/kwce/kwce_home.cpp' else src)for dst,src in files]
    if revision==14:
        files=[(dst,'homebrew/kwce-dvd/r14/'+dst if dst=='source/kwce/kwce_home.cpp' else src)for dst,src in files]
    if revision==15:
        files=[(dst,'homebrew/kwce-dvd/r15/'+dst if dst=='source/kwce/kwce_home.cpp' else src)for dst,src in files]
    if revision==16:
        files=[(dst,'homebrew/kwce-dvd/r16/'+dst if dst=='source/kwce/kwce_home.cpp' else src)for dst,src in files]
    if revision==17:
        files=[(dst,'homebrew/kwce-dvd/r17/'+dst if dst=='source/kwce/kwce_home.cpp' else src)for dst,src in files]
    if revision==18:
        files=[(dst,'homebrew/kwce-dvd/r18/'+dst if dst=='source/kwce/kwce_home.cpp' else src)for dst,src in files]
    if not css:files.append(('source/mplayer/libdvdcss/css.c',f'{base}/mplayer/libdvdcss/css_nocss.c'))
    return files

def apply(tree,root,revision,css=False):
    tree=Path(tree);root=Path(root);applied=0
    for dst,src in overlay(css,revision):
        target=tree/dst;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((root/src).read_bytes())
    for path,old,new in patches(revision,css):
        f=tree/path;text=f.read_bytes().decode('utf-8',errors='surrogateescape')
        if text.count(old)==0:old,new=old.replace('\n','\r\n'),new.replace('\n','\r\n')  # upstream mixes LF/CRLF
        if text.count(old)!=1:raise ValueError(f'Patch anchor not unique in {path}: {old[:60]!r}')
        f.write_bytes(text.replace(old,new).encode('utf-8',errors='surrogateescape'));applied+=1
    if revision==44:
        f=tree/'source/menu.cpp';text=f.read_bytes().decode('utf-8',errors='surrogateescape')
        nl='\r\n' if '\r\n' in text else '\n'
        begin=text.index('WindowPrompt(const char *title, wchar_t *msg,')
        end=text.index('int WindowPrompt(const char *title, const char *msg,',begin)
        old=text[begin:end];new=old
        pairs=[('\tint choice = -1;','\tif(kwce_css_scrambled) KwceDvdTrace("error-ui",1,0);\n\tint choice = -1;'),
               ('\tmainWindow->Append(&promptWindow);','\tmainWindow->Append(&promptWindow);\n\tif(kwce_css_scrambled) KwceDvdTrace("error-ui",2,0);'),
               ('\tpromptWindow.SetEffect(EFFECT_FADE, -50);','\tif(kwce_css_scrambled) KwceDvdTrace("error-ui",3,choice);\n\tpromptWindow.SetEffect(EFFECT_FADE, -50);'),
               ('\treturn choice;','\tif(kwce_css_scrambled) KwceDvdTrace("error-ui",4,choice);\n\treturn choice;')]
        for a,b in pairs:
            a=a.replace('\n',nl);b=b.replace('\n',nl)
            if new.count(a)!=1:raise ValueError('R44 prompt diagnostic anchor differs')
            new=new.replace(a,b);applied+=1
        f.write_bytes((text[:begin]+new+text[end:]).encode('utf-8',errors='surrogateescape'))
    if css:  # upstream css.c needs the scrambled flag the UI checks
        f=tree/'source/mplayer/libdvdcss/css.c';text=f.read_text(encoding='utf-8',errors='surrogateescape')
        f.write_text(text+'\nvolatile int kwce_css_scrambled = 0;\n',encoding='utf-8',errors='surrogateescape')
    return applied
