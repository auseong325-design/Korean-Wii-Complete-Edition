/* KWCE DVD player: startup integration for the WiiMC fork.  See kwce_dvd.h. */
#include <gccore.h>
#include <ogc/es.h>
#include <stdio.h>
#include <stdlib.h>
#include <malloc.h>
#include <string.h>
#include <sys/stat.h>
#include <dirent.h>
#include "kwce_dvd.h"
#include "kwce_font.h"

extern char appPath[1024];

/* Content index of the shared-font copy inside the player channel WAD. */
#define KWCE_FONT_CONTENT 2

namespace kwce {
	const char *msgNoDisc = "디스크를 넣어 주십시오.";
	const char *msgNoAccess = "DVD에 접근할 수 없습니다.\nDVD 플레이어 채널을 다시 설치해 주십시오.";
	const char *msgUnsupportedDrive = "이 Wii 본체는 DVD 비디오 재생을\n지원하지 않습니다.";
	const char *msgNotVideo = "이 디스크는 재생할 수 없습니다.\nDVD 비디오 디스크인지 확인해 주십시오.";
	const char *msgCss = "이 DVD는 저작권 보호(CSS)가 적용되어 있어\n재생할 수 없습니다.";
	const char *msgLoading = "디스크를 읽고 있습니다...";
}

void KwceDvdSetupPaths()
{
	if (appPath[0] != 0) return;
	DIR *dir = opendir("sd1:/");
	if (!dir) return;
	closedir(dir);
	mkdir("sd1:/kwce", 0777);
	mkdir("sd1:/kwce/dvd", 0777);
	dir = opendir("sd1:/kwce/dvd");
	if (dir) { closedir(dir); strcpy(appPath, "sd1:/kwce/dvd"); }
}

static bool load_from_content()
{
	s32 fd = ES_OpenContent(KWCE_FONT_CONTENT);
	if (fd < 0) return false;
	s32 size = ES_SeekContent(fd, 0, SEEK_END);
	if (size <= 0 || ES_SeekContent(fd, 0, SEEK_SET) < 0) { ES_CloseContent(fd); return false; }
	u8 *data = (u8 *)memalign(32, (size + 31) & ~31);
	bool ok = data && ES_ReadContent(fd, data, size) == size;
	ES_CloseContent(fd);
	return ok ? KwceFontLoad(data, size) : (free(data), false);
}

static bool load_from_file(const char *path)
{
	FILE *f = fopen(path, "rb");
	if (!f) return false;
	fseek(f, 0, SEEK_END); long size = ftell(f); fseek(f, 0, SEEK_SET);
	u8 *data = size > 0 ? (u8 *)malloc(size) : NULL;
	bool ok = data && fread(data, 1, size, f) == (size_t)size;
	fclose(f);
	return ok ? KwceFontLoad(data, size) : (free(data), false);
}

bool KwceDvdLoadFont()
{
	if (KwceFontReady()) return true;
	if (load_from_content()) return true;
	char path[1100];
	if (appPath[0]) { snprintf(path, sizeof path, "%s/wbf1.brfna", appPath); if (load_from_file(path)) return true; }
	return false;
}

bool KwceDvdTestDisc(char *path, unsigned size)
{
	if (!appPath[0]) return false;
	snprintf(path, size, "%s/test-disc.iso", appPath);
	struct stat st;
	return stat(path, &st) == 0 && st.st_size > 0;
}
