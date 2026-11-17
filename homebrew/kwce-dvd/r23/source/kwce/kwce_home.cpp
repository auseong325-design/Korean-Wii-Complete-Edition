/* KWCE DVD player: the Wii HOME Menu during DVD playback.  See kwce_home.h.
 *
 * Pane and animation names are the System Menu's (layout th_HomeBtn_d); the
 * slot table below binds each original BRLAN once per pane copy, the way the
 * SDK HOME Menu binds one animation to several groups.
 */
#include <gccore.h>
#include <ogc/es.h>
#include <ogc/lwp_watchdog.h>
#include <wiiuse/wpad.h>
#include <malloc.h>
#include <math.h>
#include <stdio.h>
#include <sys/stat.h>
#include <string.h>
#include "lyt/Layout.h"
#include "lyt/LytSystem.h"
#include "kwce_home.h"
#include "kwce_sound.h"
#include "kwce_font.h"
#include "wiimc.h"
#include "video.h"
#include "input.h"
#include "settings.h"
#include <ogc/conf.h>
#include "libwiigui/gui.h"
#include "mplayer/input/input.h"

extern char appPath[1024];
extern int sync_interlace;

#define KWCE_UI_CONTENT 3
#define ANIM(name) "arc/anim/th_HomeBtn_d_" name ".brlan"

/* ---- animation slots ------------------------------------------------------------------ */
enum {
	S_STRT, S_FNSH, S_BAR_IN, S_BAR_OUT, S_BAR_PSH,
	S_BTN_IN, S_BTN_OUT = S_BTN_IN + 4, S_BTN_PSH = S_BTN_OUT + 4,
	S_MSG_IN = S_BTN_PSH + 4, S_MSG_OUT, S_MSG_RTRN,
	S_MBTN_IN, S_MBTN_OUT = S_MBTN_IN + 2, S_MBTN_PSH = S_MBTN_OUT + 2,
	S_BTRY_WHT = S_MBTN_PSH + 2, S_BTRY_GRY = S_BTRY_WHT + 4, S_BTRY_RED = S_BTRY_GRY + 4,
	S_OPT_OPEN = S_BTRY_RED + 4, S_OPT_WINDOW, S_OPT_CLOSE, S_OPT_HOVER, S_OPT_OUT, S_VIB_ON, S_VIB_OFF, S_CLOSE_HOVER, S_CLOSE_OUT,
	S_VIB_CLEAR, S_VOL_ON, S_VOL_OFF, S_SET_IN, S_SET_OUT=S_SET_IN+5, S_SET_PSH=S_SET_OUT+5, S_COUNT=S_SET_PSH+5
};

static_assert(S_COUNT<=KWCE_LYT_SLOTS,"HOME animation slots exceed the layout limit");

struct Slot { float length, frame; bool playing; };

static u8 *g_arc;
static u32 g_arcSize;
static Layout *g_home;
static Layout *g_cursor[4];
static Slot g_slot[S_COUNT];
static WiiFont *g_font;

/* ---- buttons, dialogs, states --------------------------------------------------------- */
enum { BTN_WIIMENU = 0, BTN_TOPMENU = 1, BTN_MENU = 2, BTN_STOP = 3, BTN_COUNT = 4 };
enum { HIT_NONE = -1, HIT_BAR = 10, HIT_DLG_A = 20, HIT_DLG_B = 21 };
enum State { H_CLOSED, H_OPENING, H_MENU, H_PRESS_BAR, H_PRESS_BTN, H_CLOSING,
	H_DLG_OPENING, H_DLG, H_DLG_PRESS, H_DLG_CLOSING, H_FADEOUT, H_SETTINGS_OPENING, H_SETTINGS, H_SETTINGS_CLOSING };
enum Dialog { DLG_WIIMENU, DLG_STOP };
enum Pending { P_NONE, P_TOPMENU, P_MENU, P_RESTART };

static State g_state = H_CLOSED;
static Dialog g_dialog;
static Pending g_pending;
static int g_hover = HIT_NONE, g_pressed = HIT_NONE;
static bool g_wasPaused;
static u64 g_lastTick;
static int g_fade;
static bool g_settingsWindow, g_vibration = true;
static int g_savedSync;
static u64 g_rumbleEnd[4],g_rumbleNext[4];
static void rumble_tick() { u64 now=gettime();for(int i=0;i<4;i++)if(g_rumbleEnd[i] && now>=g_rumbleEnd[i]){WPAD_Rumble(i,0);g_rumbleEnd[i]=0;} }
static void rumble(int chan) { if(chan<0 || !g_vibration)return;u64 now=gettime();if(now<g_rumbleNext[chan])return;
    WPAD_Rumble(chan,1);g_rumbleEnd[chan]=now+microsecs_to_ticks(50000);g_rumbleNext[chan]=now+microsecs_to_ticks(200000); }
static void rumble_stop() {for(int i=0;i<4;i++){WPAD_Rumble(i,0);g_rumbleEnd[i]=0;}}
static u8 *g_backdrop;
static GXTexObj g_backdropTex;
static u16 g_settingsNotice[128];
static bool wide() { return CONF_GetAspectRatio() == CONF_ASPECT_16_9; }
/* Local test SD opt-in only; no console identities or media contents. */
static void trace_ui(const char *event, int state, int hover, int buttons)
{
	char path[1100]; struct stat st;
	if (!appPath[0]) return;
	snprintf(path, sizeof path, "%s/uitrace.on", appPath);
	if (stat(path, &st) != 0) return;
	snprintf(path, sizeof path, "%s/uitrace.log", appPath);
	FILE *f = fopen(path, "a");
	if (f) { fprintf(f, "%s state=%d hit=%d buttons=%d\n", event, state, hover, buttons); fclose(f); }
}
static int g_battery[4] = {-2, -2, -2, -2};

static u16 g_msgWiiMenu[64], g_msgStop[64];

/* ---- loading ----------------------------------------------------------------------------- */
static void utf16(const char *s, u16 *out, int max)
{
	int n = 0;
	const u8 *p = (const u8 *)s;
	while (*p && n < max - 1) {
		u32 c = *p++;
		if (c >= 0xE0) { c = ((c & 0x0F) << 12) | ((p[0] & 0x3F) << 6) | (p[1] & 0x3F); p += 2; }
		else if (c >= 0xC0) { c = ((c & 0x1F) << 6) | (p[0] & 0x3F); p += 1; }
		out[n++] = (u16)c;
	}
	out[n] = 0;
}

static u8 *read_content(u32 *size)
{
	s32 fd = ES_OpenContent(KWCE_UI_CONTENT);
	if (fd < 0) return NULL;
	s32 len = ES_SeekContent(fd, 0, SEEK_END);
	u8 *data = NULL;
	if (len > 0 && ES_SeekContent(fd, 0, SEEK_SET) >= 0) {
		data = (u8 *)memalign(32, (len + 31) & ~31);
		if (data && ES_ReadContent(fd, data, len) != len) { free(data); data = NULL; }
	}
	ES_CloseContent(fd);
	*size = len > 0 ? len : 0;
	return data;
}

static u8 *read_file(const char *path, u32 *size)
{
	FILE *f = fopen(path, "rb");
	if (!f) return NULL;
	fseek(f, 0, SEEK_END); long len = ftell(f); fseek(f, 0, SEEK_SET);
	u8 *data = len > 0 ? (u8 *)memalign(32, (len + 31) & ~31) : NULL;
	if (data && fread(data, 1, len, f) != (size_t)len) { free(data); data = NULL; }
	fclose(f);
	*size = len > 0 ? len : 0;
	return data;
}

WiiFont *KwceLytSystemFont()
{
	if (!g_font) {
		u32 len = 0;
		const uint8_t *rfna = KwceFontFile(&len);
		if (!rfna) return NULL;
		g_font = new WiiFont;
		g_font->SetName("wbf1.brfna");
		if (!g_font->Load(rfna)) { delete g_font; g_font = NULL; }
	}
	return g_font;
}

/* Each layout gets its own copy of its BRLYT: panes are animated in place. */
static Layout *load_layout(const U8Archive &arc, const char *name)
{
	u32 len = 0;
	const u8 *file = arc.GetFile(name, &len);
	if (!file) return NULL;
	u8 *copy = (u8 *)memalign(32, (len + 31) & ~31);
	if (!copy) return NULL;
	memcpy(copy, file, len);
	Layout *layout = new Layout;
	if (!layout->Load(copy)) { delete layout; free(copy); return NULL; }
	return layout;
}

static bool bind(const U8Archive &arc, int slot, const char *file, const char *from = 0, const char *to = 0, const char *only = 0)
{
	const u8 *anim = arc.GetFile(file);
	if (!anim) return false;
	u32 frames = Animator::LoadAnimators((const RLAN_Header *)anim, *g_home, slot, from, to, only);
	g_slot[slot].length = frames;
	g_slot[slot].frame = 0;
	g_slot[slot].playing = false;
	return frames > 0;
}

bool KwceHomeLoad()
{
	if (g_home) return true;
	g_arc = read_content(&g_arcSize);
	if (!g_arc && appPath[0]) {
		char path[1100];
		snprintf(path, sizeof path, "%s/home.arc", appPath);
		g_arc = read_file(path, &g_arcSize);
	}
	if (!g_arc) return false;
	DCFlushRange(g_arc, (g_arcSize + 31) & ~31);
	U8Archive arc(g_arc, g_arcSize);
	if (!arc.IsValid() || !KwceLytSystemFont()) return false;

	g_home = load_layout(arc, "arc/blyt/th_HomeBtn_d.brlyt");
	if (!g_home) return false;
	bool ok = bind(arc, S_STRT, ANIM("hmMenu_strt")) && bind(arc, S_FNSH, ANIM("hmMenu_fnsh"))
		&& bind(arc, S_BAR_IN, ANIM("hmMenu_bar_in")) && bind(arc, S_BAR_OUT, ANIM("hmMenu_bar_out"))
		&& bind(arc, S_BAR_PSH, ANIM("hmMenu_bar_psh"))
		&& bind(arc, S_MSG_IN, ANIM("cmn_msg_in")) && bind(arc, S_MSG_OUT, ANIM("cmn_msg_out"))
		&& bind(arc, S_MSG_RTRN, ANIM("cmn_msg_rtrn"));
	for (int b = 0; ok && b < BTN_COUNT; b++) {
		char to[16];
		snprintf(to, sizeof to, "btnL_%02d", b);
		ok = bind(arc, S_BTN_IN + b, ANIM("cntBtn_in"), "btnL_00", to)
			&& bind(arc, S_BTN_OUT + b, ANIM("cntBtn_out"), "btnL_00", to)
			&& bind(arc, S_BTN_PSH + b, ANIM("cntBtn_psh"), "btnL_00", to);
	}
	const char *dlgBtn[2] = {"BtnA", "BtnB"};
	for (int b = 0; ok && b < 2; b++)
		ok = bind(arc, S_MBTN_IN + b, ANIM("cmn_msg_btn_in"), 0, 0, dlgBtn[b])
			&& bind(arc, S_MBTN_OUT + b, ANIM("cmn_msg_btn_out"), 0, 0, dlgBtn[b])
			&& bind(arc, S_MBTN_PSH + b, ANIM("cmn_msg_btn_psh"), 0, 0, dlgBtn[b]);
	for (int p = 0; ok && p < 4; p++) {
		char only[8];
		snprintf(only, sizeof only, "_%02d", p);
		ok = bind(arc, S_BTRY_WHT + p, ANIM("btry_wht"), 0, 0, only)
			&& bind(arc, S_BTRY_GRY + p, ANIM("btry_gry"), 0, 0, only)
			&& bind(arc, S_BTRY_RED + p, ANIM("btry_red"), 0, 0, only);
	}
	ok = ok && bind(arc,S_OPT_OPEN,ANIM("cntrl_up")) && bind(arc,S_OPT_WINDOW,ANIM("cntrl_wndw_opn"))
        && bind(arc,S_OPT_CLOSE,ANIM("cntrl_dwn")) && bind(arc,S_OPT_HOVER,ANIM("optn_bar_in"))
        && bind(arc,S_OPT_OUT,ANIM("optn_bar_out")) && bind(arc,S_VIB_ON,ANIM("vb_btn_ylw_ylw"),0,0,"_10")
        && bind(arc,S_VIB_OFF,ANIM("vb_btn_ylw_ylw"),0,0,"_11") && bind(arc,S_CLOSE_HOVER,ANIM("close_bar_in")) && bind(arc,S_CLOSE_OUT,ANIM("close_bar_out"))
        && bind(arc,S_VIB_CLEAR,ANIM("vb_btn_wht_psh"));
    ok=ok && bind(arc,S_VOL_ON,ANIM("sound_ylw")) && bind(arc,S_VOL_OFF,ANIM("sound_gry"));
	for(int i=0;i<5;i++) {const char *part[]={"optnBtn_00","optnBtn_01","optnBtn_10","optnBtn_11","optnBtn_20"};
        ok=ok && bind(arc,S_SET_IN+i,ANIM("optn_btn_in"),0,0,part[i])
        && bind(arc,S_SET_OUT+i,ANIM("optn_btn_out"),0,0,part[i])
        && bind(arc,S_SET_PSH+i,ANIM("optn_btn_psh"),0,0,part[i]); }
    u32 soundSize=0;const u8 *sound=arc.GetFile("arc/sfx/hbm.pcm",&soundSize);KwceSoundLoad(sound,soundSize);
    g_home->LoadTextures(arc);
	g_home->LoadFonts(arc);
	for (int c = 0; c < 4; c++) {
		char name[32];
		snprintf(name, sizeof name, "arc/blyt/P%d_Def.brlyt", c + 1);
		g_cursor[c] = load_layout(arc, name);
		if (g_cursor[c]) { g_cursor[c]->LoadTextures(arc); g_cursor[c]->LoadFonts(arc); }
	}
	utf16("DVD 재생을 종료하고\nWii 메뉴로 돌아가시겠습니까?", g_msgWiiMenu, 64);
	utf16("재생을 정지했습니다.", g_msgStop, 64);
	if (!ok) { delete g_home; g_home = NULL; }
	return ok;
}

bool KwceHomeReady() { return g_home != NULL; }
bool KwceHomeActive() { return g_state != H_CLOSED; }

/* ---- animation playback ------------------------------------------------------------------ */
static void play(int slot)
{
	/* One animation per affected button. A late hover-out must not overwrite a press. */
    if(slot>=S_BTN_IN && slot<S_MSG_IN) {int b=(slot-S_BTN_IN)%4;g_slot[S_BTN_IN+b].playing=g_slot[S_BTN_OUT+b].playing=g_slot[S_BTN_PSH+b].playing=false;}
    if(slot>=S_MBTN_IN && slot<S_BTRY_WHT){int b=(slot-S_MBTN_IN)%2;g_slot[S_MBTN_IN+b].playing=g_slot[S_MBTN_OUT+b].playing=g_slot[S_MBTN_PSH+b].playing=false;}
    if(slot>=S_SET_IN && slot<S_COUNT){int b=(slot-S_SET_IN)%5;g_slot[S_SET_IN+b].playing=g_slot[S_SET_OUT+b].playing=g_slot[S_SET_PSH+b].playing=false;}
    if(slot>=S_BAR_IN && slot<=S_BAR_PSH)g_slot[S_BAR_IN].playing=g_slot[S_BAR_OUT].playing=g_slot[S_BAR_PSH].playing=false;
    if(slot==S_OPT_HOVER || slot==S_OPT_OUT)g_slot[S_OPT_HOVER].playing=g_slot[S_OPT_OUT].playing=false;
    if(slot==S_CLOSE_HOVER || slot==S_CLOSE_OUT)g_slot[S_CLOSE_HOVER].playing=g_slot[S_CLOSE_OUT].playing=false;
    g_slot[slot].frame = 0;
    g_slot[slot].playing = true;
	g_home->ApplyAnimation(slot, 0);
}

static void apply_end(int slot)
{
	g_slot[slot].frame = g_slot[slot].length;
	g_slot[slot].playing = false;
	g_home->ApplyAnimation(slot, g_slot[slot].length);
}

static bool busy(int slot) { return g_slot[slot].playing; }

static void advance(float frames)
{
	for (int s = 0; s < S_COUNT; s++) {
		Slot &a = g_slot[s];
		if (!a.playing) continue;
		a.frame += frames;
		if (a.frame >= a.length) { a.frame = a.length; a.playing = false; }
		g_home->ApplyAnimation(s, a.frame);
	}
}

/* ---- geometry ------------------------------------------------------------------------------ */
static float scale() { return screenheight / 456.0f; }

/* Pane rectangle in layout coordinates (y up), composed like Pane::Render. */
static bool find_rect(Pane *pane, const char *name, Mtx parent, float rect[4])
{
	const Pane::Header *h = pane->GetHeader();
	if (!h) return false;
	Mtx m1, m2, m3, m4, mv;
	guMtxIdentity(m1);
	guMtxScaleApply(m1, m1, h->scale.x * (wide() && pane->GetWidescren() ? 1.f/1.3684211f : 1.f), h->scale.y, 1.f);
	guMtxRotDeg(m2, 'x', h->rotate.x); guMtxRotDeg(m3, 'y', h->rotate.y); guMtxRotDeg(m4, 'z', h->rotate.z);
	guMtxConcat(m2, m3, m2); guMtxConcat(m2, m4, m2); guMtxConcat(m1, m2, m1);
	guMtxTransApply(m1, m1, h->translate.x, h->translate.y, h->translate.z);
	guMtxConcat(parent, m1, mv);
	if (!strncmp(h->name, name, 16)) {
		float x0 = -0.5f * pane->GetOriginX() * h->width, y0 = -0.5f * pane->GetOriginY() * h->height;
		guVector c[4] = {{x0, y0, 0}, {x0 + h->width, y0, 0}, {x0, y0 + h->height, 0}, {x0 + h->width, y0 + h->height, 0}};
		rect[0] = rect[1] = 1e9f; rect[2] = rect[3] = -1e9f;
		for (int i = 0; i < 4; i++) {
			guVector o;
			guVecMultiply(mv, &c[i], &o);
			if (o.x < rect[0]) rect[0] = o.x;
			if (o.y < rect[1]) rect[1] = o.y;
			if (o.x > rect[2]) rect[2] = o.x;
			if (o.y > rect[3]) rect[3] = o.y;
		}
		return true;
	}
	for (u32 i = 0; i < pane->panes.size(); i++)
		if (find_rect(pane->panes[i], name, mv, rect)) return true;
	return false;
}

static bool inside(const char *name, float lx, float ly)
{
	Pane *root = g_home->FindPane("RootPane");
	if (!root) return false;
	Mtx id;
	guMtxIdentity(id);
	guMtxScaleApply(id,id,wide()?1.3684211f:1.f,1.f,1.f);
	float r[4];
	return find_rect(root, name, id, r) && lx >= r[0] && lx <= r[2] && ly >= r[1] && ly <= r[3];
}

static void set_visible(const char *name, bool visible)
{
	Pane *p = g_home->FindPane(name);
	if (p) p->SetVisible(visible);
}

/* ---- behaviour ------------------------------------------------------------------------------ */
static int hit_test(float x, float y)
{
	float lx = (x - screenwidth * 0.5f) / scale(), ly = (screenheight * 0.5f - y) / scale();
	if (g_state == H_SETTINGS) {
        const char *opts[]={"B_optnBtn_00","B_optnBtn_01","B_optnBtn_10","B_optnBtn_11","B_optnBtn_20"};
        for (int i=0;i<5;i++) if(inside(opts[i],lx,ly)) return 40+i;
        if (inside("B_bar_10",lx,ly) || inside("cntrl_00",lx,ly)) return 30;
        if (inside("B_btn_00",lx,ly)) return HIT_BAR;
        return HIT_NONE;
    }
	if (g_state == H_DLG) {
		if (inside("B_BtnA", lx, ly)) return HIT_DLG_A;
		if (inside("B_BtnB", lx, ly)) return HIT_DLG_B;
		return HIT_NONE;
	}
	for (int b = 0; b < BTN_COUNT; b++) {
		char name[16];
		snprintf(name, sizeof name, "B_btnL_%02d", b);
		if (inside(name, lx, ly)) return b;
	}
	if (inside("B_bar_10", lx, ly) || inside("cntrl_00",lx,ly)) return 30;
	if (inside("B_btn_00", lx, ly)) return HIT_BAR;
	return HIT_NONE;
}

static void hover_in(int hit)
{
    KwceSoundPlay(4);
    if(hit>=40 && hit<=44)play(S_SET_IN+hit-40);
	if (hit == 30) play(g_state==H_SETTINGS?S_CLOSE_HOVER:S_OPT_HOVER);
	else if (hit == HIT_BAR) play(S_BAR_IN);
	else if (hit >= 0 && hit < BTN_COUNT) play(S_BTN_IN + hit);
	else if (hit == HIT_DLG_A || hit == HIT_DLG_B) play(S_MBTN_IN + hit - HIT_DLG_A);
}

static void hover_out(int hit)
{
    if(hit>=40 && hit<=44)play(S_SET_OUT+hit-40);
	if (hit == 30) play(g_state==H_SETTINGS?S_CLOSE_OUT:S_OPT_OUT);
	else if (hit == HIT_BAR) play(S_BAR_OUT);
	else if (hit >= 0 && hit < BTN_COUNT) play(S_BTN_OUT + hit);
	else if (hit == HIT_DLG_A || hit == HIT_DLG_B) play(S_MBTN_OUT + hit - HIT_DLG_A);
}

static void open_dialog(Dialog d)
{
	g_dialog = d;
	Textbox *text = (Textbox *)g_home->FindPane("T_Dialog");
	if (text) text->SetText(d == DLG_STOP ? g_msgStop : g_msgWiiMenu);
	set_visible("tx_msgBtn_00", d == DLG_WIIMENU);
	set_visible("tx_msgBtn_01", d == DLG_WIIMENU);
	set_visible("tx_msgBtn_02", d == DLG_STOP);
	set_visible("tx_msgBtn_03", d == DLG_STOP);
	/* dialog buttons start shrunk (0.9), as hmMenu_strt leaves them */
	apply_end(S_MBTN_OUT); apply_end(S_MBTN_OUT + 1);
	play(S_MSG_IN);
	g_state = H_DLG_OPENING;
}

static void close_menu(Pending pending)
{
	g_pending = pending;
    KwceSoundPlay(1);rumble_stop();
	play(S_FNSH);
	g_state = H_CLOSING;
}

static void start_exit()
{
	g_fade = 0;
	g_state = H_FADEOUT;
}

static void update_battery()
{
	for (int p = 0; p < 4; p++) {
		u32 type;
		int bars = -1;  /* -1: not connected */
		if (WPAD_Probe(p, &type) == WPAD_ERR_NONE) {
			u8 raw = WPAD_BatteryLevel(p);
			bars = raw > 0x82 ? 4 : raw > 0x6A ? 3 : raw > 0x4C ? 2 : raw > 0x30 ? 1 : 0;
		}
		if (bars == g_battery[p]) continue;
		g_battery[p] = bars;
		g_home->ApplyAnimation(bars < 0 ? S_BTRY_GRY + p : bars <= 1 ? S_BTRY_RED + p : S_BTRY_WHT + p,0);
		for (int i = 0; i < 4; i++) {
			char name[16];
			snprintf(name, sizeof name, "btryPwr_%02d_%d", p, i);
			set_visible(name, i < bars);
		}
	}
}

void KwceHomeOpen()
{
	if (!g_home || g_state != H_CLOSED) return;
    /* Capture the already drawn DVD frame once, like HBM's frozen backdrop.
       HOME can then present independently of the movie decoder's cadence. */
    u16 w=vmode->fbWidth,h=vmode->efbHeight;
    u32 bytes=GX_GetTexBufferSize(w,h,GX_TF_RGB565,GX_FALSE,0);
    if(!g_backdrop)g_backdrop=(u8 *)memalign(32,bytes);
    if(g_backdrop) {
        GX_SetTexCopySrc(0,0,w,h);GX_SetTexCopyDst(w,h,GX_TF_RGB565,GX_FALSE);
        DCInvalidateRange(g_backdrop,bytes);GX_CopyTex(g_backdrop,GX_FALSE);GX_PixModeSync();
        GX_InitTexObj(&g_backdropTex,g_backdrop,w,h,GX_TF_RGB565,GX_CLAMP,GX_CLAMP,GX_FALSE);
    }
	g_wasPaused = wiiIsPaused();
	g_savedSync = sync_interlace;
	sync_interlace = 0; // HOME is a UI; present every VI instead of the movie's field parity.
	if (!g_wasPaused) wiiPause();
	for (int s = 0; s < S_COUNT; s++) g_slot[s].playing = false;
	for (int b = 0; b < BTN_COUNT; b++) apply_end(S_BTN_OUT + b);
	apply_end(S_BAR_OUT);
	for (int p = 0; p < 4; p++) g_battery[p] = -2;
	update_battery();
	KwceSoundMenu(1);KwceSoundPlay(0);
	play(S_STRT);
	g_settingsWindow = false;
	g_hover = g_pressed = HIT_NONE;
	g_pending = P_NONE;
	g_state = H_OPENING;
	g_lastTick = gettime();
}

static void finish_close()
{
	g_state = H_CLOSED;
    KwceSoundMenu(0);rumble_stop();
	sync_interlace = g_savedSync;
	if (!g_wasPaused) wiiPause();
	switch (g_pending) {
		case P_TOPMENU: wiiDVDNav(MP_CMD_DVDNAV_TOPMENU); break;
		case P_MENU: wiiDVDNav(MP_CMD_DVDNAV_MENU); break;
		case P_RESTART: wiiDVDNav(MP_CMD_DVDNAV_RESTART); break;
		default: break;
	}
	g_pending = P_NONE;
}

/* Remote that pressed A this frame with its pointer on screen, else the first valid pointer. */
static int pointer_chan()
{
	int chan = -1;
	for (int i = 0; i < 4; i++) {
		WPADData *w = userInput[i].wpad;
		if (!w || !w->ir.valid) continue;
		if (w->btns_d & WPAD_BUTTON_A) return i;
		if (chan < 0) chan = i;
	}
	return chan;
}

static bool any_pressed(u32 wpadMask, u16 padMask)
{
	for (int i = 0; i < 4; i++) {
		if (userInput[i].wpad && (userInput[i].wpad->btns_d & wpadMask)) return true;
		if (userInput[i].pad.btns_d & padMask) return true;
	}
	return false;
}

/* Without a pointer (GameCube controller, remote off screen) the +Control Pad moves
   the selection: 2x2 button grid (타이틀 메뉴 DVD 메뉴 / 정지 Wii 메뉴로), bar above it. */
static int navigate(int cur)
{
	bool up = any_pressed(WPAD_BUTTON_UP | WPAD_CLASSIC_BUTTON_UP, PAD_BUTTON_UP);
	bool down = any_pressed(WPAD_BUTTON_DOWN | WPAD_CLASSIC_BUTTON_DOWN, PAD_BUTTON_DOWN);
	bool left = any_pressed(WPAD_BUTTON_LEFT | WPAD_CLASSIC_BUTTON_LEFT, PAD_BUTTON_LEFT);
	bool right = any_pressed(WPAD_BUTTON_RIGHT | WPAD_CLASSIC_BUTTON_RIGHT, PAD_BUTTON_RIGHT);
	if (!(up || down || left || right)) return cur;
	if(g_state==H_SETTINGS) {
        if(cur==HIT_NONE || cur<30)return 40;
        if(cur==30 || cur==HIT_BAR)return down?40:cur;
        int row=(cur-40)/2,col=(cur-40)%2;
        if(up)return row==0?30:40+(row-1)*2+col;
        if(down)return row>=1?44:42+col;
        return row==2?44:40+row*2+(left?0:1);
    }
    if (g_state == H_DLG) {
		if (left) return HIT_DLG_A;
		if (right) return HIT_DLG_B;
		return cur == HIT_NONE ? HIT_DLG_A : cur;
	}
	static const int grid[2][2] = {{BTN_TOPMENU, BTN_MENU}, {BTN_STOP, BTN_WIIMENU}};
	int row = -1, col = 0;
	for (int r = 0; r < 2; r++)
		for (int c = 0; c < 2; c++)
			if (grid[r][c] == cur) { row = r; col = c; }
	if (cur == HIT_NONE) return BTN_TOPMENU;
	if (cur == HIT_BAR || cur==30) return down ? BTN_TOPMENU : HIT_BAR;
	if (up) return row == 0 ? HIT_BAR : grid[0][col];
	if (down) return grid[1][col];
	return grid[row][left ? 0 : 1];
}

void KwceHomeInput()
{
	if (g_state == H_CLOSED) return;
	u64 now = gettime();
	float frames = diff_usec(g_lastTick, now) * 60.0f / 1000000.0f;  /* animations are 60 fps */
	g_lastTick = now;
	if (frames > 4) frames = 4;
	advance(frames);
	/* Native HBM backFlag=0 uses the video backdrop, never the scanline layer. */
	set_visible("back_02",false);
	for (int b=0;b<4;b++) { char name[16]; snprintf(name,sizeof name,"let_icn_%02d",b); set_visible(name,false); }
	update_battery();

	int chan = pointer_chan();
	bool pressedA = any_pressed(WPAD_BUTTON_A | WPAD_CLASSIC_BUTTON_A, PAD_BUTTON_A);
	bool interactive = g_state == H_MENU || g_state == H_DLG || g_state == H_SETTINGS;
	int hit = g_hover;
	if (interactive)
		hit = chan >= 0 ? hit_test(userInput[chan].wpad->ir.x, userInput[chan].wpad->ir.y) : navigate(g_hover);
	if (interactive && hit != g_hover) {
		if (g_hover != HIT_NONE) hover_out(g_hover);
		if (hit != HIT_NONE) { hover_in(hit); if (chan >= 0) rumble(chan); }
		g_hover = hit;
	}
	rumble_tick();

	bool closeKey = any_pressed(WPAD_BUTTON_HOME | WPAD_CLASSIC_BUTTON_HOME | WPAD_BUTTON_B, PAD_BUTTON_START | PAD_BUTTON_B);
	static int lastState = -1;
	if(interactive && pressedA && g_hover!=HIT_NONE)KwceSoundPlay(5);
	if (lastState != g_state || pressedA || closeKey) {
		trace_ui("input", g_state, g_hover, pressedA | (closeKey ? 2 : 0)); lastState = g_state;
	}

	switch (g_state) {
		case H_OPENING:
			if (!busy(S_STRT)) { g_state = H_MENU; for(int p=0;p<4;p++)g_battery[p]=-2; update_battery(); }
			break;
		case H_MENU:
			if (pressedA && g_hover == 30) { KwceSoundPlay(7); g_settingsWindow=false; play(S_OPT_OPEN); g_state=H_SETTINGS_OPENING; g_hover=HIT_NONE; }
			else if (pressedA && g_hover == HIT_BAR) { play(S_BAR_PSH); g_state = H_PRESS_BAR; }
			else if (pressedA && g_hover >= 0 && g_hover < BTN_COUNT) {
				g_pressed = g_hover; play(S_BTN_PSH + g_pressed); g_state = H_PRESS_BTN;
			}
			else if (closeKey) close_menu(P_NONE);
			break;
		case H_PRESS_BAR:
			if (!busy(S_BAR_PSH)) close_menu(P_NONE);
			break;
		case H_PRESS_BTN:
			if (busy(S_BTN_PSH + g_pressed)) break;
			hover_out(g_pressed); g_hover = HIT_NONE;
			if (g_pressed == BTN_TOPMENU) close_menu(P_TOPMENU);
			else if (g_pressed == BTN_MENU) close_menu(P_MENU);
			else open_dialog(g_pressed == BTN_STOP ? DLG_STOP : DLG_WIIMENU);
			break;
		case H_CLOSING:
			if (!busy(S_FNSH)) finish_close();
			break;
		case H_DLG_OPENING:
			if (!busy(S_MSG_IN)) g_state = H_DLG;
			break;
		case H_DLG:
			if (pressedA && (g_hover == HIT_DLG_A || g_hover == HIT_DLG_B)) {
				g_pressed = g_hover; play(S_MBTN_PSH + g_pressed - HIT_DLG_A); g_state = H_DLG_PRESS;
			}
			else if (g_dialog == DLG_WIIMENU && any_pressed(WPAD_BUTTON_B, PAD_BUTTON_B)) {
				if (g_hover != HIT_NONE) hover_out(g_hover);
				g_hover = HIT_NONE; play(S_MSG_RTRN); g_state = H_DLG_CLOSING;
			}
			break;
		case H_DLG_PRESS:
			if (busy(S_MBTN_PSH + g_pressed - HIT_DLG_A)) break;
			if (g_dialog == DLG_WIIMENU) {
				if (g_pressed == HIT_DLG_A) start_exit();
				else { play(S_MSG_RTRN); g_state = H_DLG_CLOSING; }
			} else {
				if (g_pressed == HIT_DLG_A) { play(S_MSG_OUT); close_menu(P_RESTART); }
				else start_exit();
			}
			g_hover = HIT_NONE;
			break;
		case H_DLG_CLOSING:
			if (!busy(S_MSG_RTRN)) g_state = H_MENU;
			break;
		case H_SETTINGS_OPENING:
            if (!busy(S_OPT_OPEN) && !g_settingsWindow) { play(S_OPT_WINDOW); g_settingsWindow=true; }
            if (g_settingsWindow && !busy(S_OPT_WINDOW)) { g_state=H_SETTINGS; g_home->ApplyAnimation(S_VIB_CLEAR,0); apply_end(g_vibration?S_VIB_ON:S_VIB_OFF); }
            break;
        case H_SETTINGS:
            if (closeKey || (pressedA && (g_hover==30 || g_hover==HIT_BAR))) {
                set_visible("T_msg_01",false); set_visible("N_opton_all",true);
                KwceSoundPlay(8);play(S_OPT_CLOSE); g_state=H_SETTINGS_CLOSING; g_hover=HIT_NONE;
            } else if (pressedA && (g_hover==40 || g_hover==41)) {
                play(S_SET_PSH+g_hover-40);
                KwceSoundPlay(g_hover==40?(WiiSettings.volume?9:11):(WiiSettings.volume<100?10:12));
                int vol=WiiSettings.volume+(g_hover==40?-10:10);
                if(vol<0)vol=0; if(vol>100)vol=100;
                WiiSettings.volume=vol; wiiSetVolume(vol);
            } else if (pressedA && (g_hover==42 || g_hover==43)) {
                g_vibration=g_hover==42;KwceSoundPlay(g_vibration?14:15);
                play(S_SET_PSH+g_hover-40);
                if(g_vibration){EnableRumble();rumble(chan);}else{DisableRumble();rumble_stop();}
                g_home->ApplyAnimation(S_VIB_CLEAR,0); apply_end(g_vibration?S_VIB_ON:S_VIB_OFF);
            } else if (pressedA && g_hover==44) {
                play(S_SET_PSH+4);KwceSoundPlay(13);
                utf16("재접속이 필요하면\n플레이어를 다시 실행해 주세요.",g_settingsNotice,128);
                Textbox *notice=(Textbox *)g_home->FindPane("T_msg_01");
                if(notice) { notice->SetText(g_settingsNotice); notice->GetHeader()->alpha=255; notice->SetVisible(true); }
                set_visible("N_opton_all",false);
            }
            for(int i=0;i<10;i++) { char name[16];snprintf(name,sizeof name,"vol_%02d",i);
                Material *m=g_home->FindMaterial(name);if(m)m->SetFrame(0,i<(WiiSettings.volume+9)/10?S_VOL_ON:S_VOL_OFF); }
            break;
        case H_SETTINGS_CLOSING:
            if(!busy(S_OPT_CLOSE))g_state=H_MENU;
            break;
		case H_FADEOUT:
			g_fade += (int)(frames * 255 / 30) + 1;
			if (g_fade >= 255) {
				g_fade = 255;
				VIDEO_SetBlack(TRUE);
				ExitRequested = true;
				sync_interlace = g_savedSync;
				/* The application exit flag alone does not leave MPlayerMenu's
				   controlledbygui == 0 wait. Follow WiiMC's normal quit path. */
				if (wiiIsPaused()) wiiPause();
				wiiGotoGui();
				g_state = H_CLOSED;
			}
			break;
		default:
			break;
	}
}

/* ---- drawing ---------------------------------------------------------------------------------- */
static void begin_layout_gx()
{
	GX_SetVtxAttrFmt(GX_VTXFMT0, GX_VA_POS, GX_POS_XYZ, GX_F32, 0);
	GX_SetVtxAttrFmt(GX_VTXFMT0, GX_VA_CLR0, GX_CLR_RGBA, GX_RGBA8, 0);
	for (int i = 0; i < 8; i++)
		GX_SetVtxAttrFmt(GX_VTXFMT0, GX_VA_TEX0 + i, GX_TEX_ST, GX_F32, 0);
	GX_SetZMode(GX_FALSE, GX_ALWAYS, GX_FALSE);
}

/* Undo everything the layout materials may set; MPlayer's draw_initYUV and WiiMC's
   ResetVideo_Menu only set part of the GX state themselves. */
static void end_layout_gx()
{
	GX_SetNumIndStages(0);
	for (int s = 0; s < 16; s++) {
		GX_SetTevDirect((u8)s);
		GX_SetTevSwapMode((u8)s, GX_TEV_SWAP0, GX_TEV_SWAP0);
		GX_SetTevKColorSel((u8)s, GX_TEV_KCSEL_1_4);
		GX_SetTevKAlphaSel((u8)s, GX_TEV_KASEL_1);
	}
	GX_SetTevSwapModeTable(GX_TEV_SWAP0, GX_CH_RED, GX_CH_GREEN, GX_CH_BLUE, GX_CH_ALPHA);
	GX_SetTevSwapModeTable(GX_TEV_SWAP1, GX_CH_RED, GX_CH_RED, GX_CH_RED, GX_CH_ALPHA);
	GX_SetTevSwapModeTable(GX_TEV_SWAP2, GX_CH_GREEN, GX_CH_GREEN, GX_CH_GREEN, GX_CH_ALPHA);
	GX_SetTevSwapModeTable(GX_TEV_SWAP3, GX_CH_BLUE, GX_CH_BLUE, GX_CH_BLUE, GX_CH_ALPHA);
	GX_SetChanCtrl(GX_COLOR0A0, GX_DISABLE, GX_SRC_REG, GX_SRC_VTX, GX_LIGHTNULL, GX_DF_NONE, GX_AF_NONE);
	GX_SetChanCtrl(GX_COLOR1A1, GX_DISABLE, GX_SRC_REG, GX_SRC_VTX, GX_LIGHTNULL, GX_DF_NONE, GX_AF_NONE);
	GX_SetFog(GX_FOG_NONE, 0, 1, 0.1f, 1, (GXColor){0, 0, 0, 0});
	GX_SetZTexture(GX_ZT_DISABLE, GX_TF_Z8, 0);
	for (int i = 0; i < 8; i++)
		GX_SetTexCoordGen2(GX_TEXCOORD0 + i, GX_TG_MTX2x4, GX_TG_TEX0 + i, GX_IDENTITY, GX_FALSE, GX_DTTIDENTITY);
	GX_SetAlphaCompare(GX_GREATER, 0, GX_AOP_AND, GX_ALWAYS, 0);
	GX_SetBlendMode(GX_BM_BLEND, GX_BL_SRCALPHA, GX_BL_INVSRCALPHA, GX_LO_CLEAR);
	GX_SetColorUpdate(GX_TRUE);
	GX_SetAlphaUpdate(GX_TRUE);
	ResetVideo_Menu();
}

static void render(Layout *layout, float s, u8 alpha)
{
	Mtx mv;
	guMtxIdentity(mv);
	guMtxScaleApply(mv, mv, s * (wide()?1.3684211f:1.f), s, 1.f);
	guMtxTransApply(mv, mv, 0.f, 0.f, -50.f);
	Vec2f screen = {(float)screenwidth, (float)screenheight};
	layout->Render(mv, screen, wide(), alpha);
}

void KwceCursorDraw(int chan, float x, float y, float angle)
{
	if (chan < 0 || chan > 3 || !g_cursor[chan]) return;
	float s = screenheight / 480.0f;
	Pane *trans = g_cursor[chan]->FindPane("N_Trans");
	Pane *rot = g_cursor[chan]->FindPane("N_Rot");
	Pane *srot = g_cursor[chan]->FindPane("N_SRot");
	if (!trans || !rot || !srot) return;
	trans->GetHeader()->translate.x = (x - screenwidth * 0.5f) / s;
	trans->GetHeader()->translate.y = (screenheight * 0.5f - y) / s;
	rot->GetHeader()->rotate.z = -angle;
	srot->GetHeader()->rotate.z = -angle;
	begin_layout_gx();
	render(g_cursor[chan], s, 0xFF);
	end_layout_gx();
}

void KwceHomeDraw()
{
	if (g_state == H_CLOSED) return;
	Menu_DrawRectangle(0,0,screenwidth,screenheight,(GXColor){0,0,0,85},1);
	static unsigned draws = 0;
	if (++draws % 120 == 0) trace_ui("draw", g_state, g_hover, 0);
	begin_layout_gx();
	render(g_home, scale(), 0xFF);
	end_layout_gx();
	for (int i = 3; i >= 0; i--) {
		WPADData *w = userInput[i].wpad;
		if (w && w->ir.valid) KwceCursorDraw(i, w->ir.x, w->ir.y, w->ir.angle);
	}
	if (g_state == H_FADEOUT && g_fade > 0)
		Menu_DrawRectangle(0, 0, screenwidth, screenheight, (GXColor){0, 0, 0, (u8)g_fade}, 1);
}

extern "C" void KwcePresentHome();
/* C entry point used only by MPlayer's pause loop. */
extern "C" int KwceHomeFrame()
{
    if (!KwceHomeActive()) return 0;
    static u64 rateStart=0; static int rateFrames=0;
    if(!rateStart)rateStart=gettime();
    if(++rateFrames==120) { trace_ui("home-cadence",rateFrames,(int)(diff_usec(rateStart,gettime())/1000),0);rateFrames=0;rateStart=gettime(); }
    static u64 lastEnd=0; static unsigned gap=0,input=0,draw=0,present=0,n=0;
    u64 t0=gettime(); if(lastEnd)gap+=diff_usec(lastEnd,t0);
    UpdatePads(); KwceHomeInput();
    u64 t1=gettime(); input+=diff_usec(t0,t1);
    if (!KwceHomeActive()) return 0;
    ResetVideo_Menu();
    if (g_backdrop) {
        GX_SetNumChans(1);GX_SetChanCtrl(GX_COLOR0A0,GX_DISABLE,GX_SRC_REG,GX_SRC_VTX,GX_LIGHTNULL,GX_DF_NONE,GX_AF_NONE);
        GX_SetNumTexGens(1);GX_SetTexCoordGen(GX_TEXCOORD0,GX_TG_MTX2x4,GX_TG_TEX0,GX_IDENTITY);
        GX_SetNumTevStages(1);GX_SetTevDirect(GX_TEVSTAGE0);GX_SetTevOrder(GX_TEVSTAGE0,GX_TEXCOORD0,GX_TEXMAP0,GX_COLOR0A0);GX_SetTevOp(GX_TEVSTAGE0,GX_MODULATE);
        GX_SetZMode(GX_FALSE,GX_ALWAYS,GX_FALSE);GX_SetBlendMode(GX_BM_NONE,GX_BL_ONE,GX_BL_ZERO,GX_LO_CLEAR);
        GX_SetAlphaCompare(GX_ALWAYS,0,GX_AOP_AND,GX_ALWAYS,0);GX_LoadTexObj(&g_backdropTex,GX_TEXMAP0);
        Mtx m;guMtxIdentity(m);guMtxTransApply(m,m,0,0,-50);GX_LoadPosMtxImm(m,GX_PNMTX0);
        GX_ClearVtxDesc();GX_SetVtxDesc(GX_VA_POS,GX_DIRECT);GX_SetVtxDesc(GX_VA_CLR0,GX_DIRECT);GX_SetVtxDesc(GX_VA_TEX0,GX_DIRECT);
        GX_SetVtxAttrFmt(GX_VTXFMT0,GX_VA_POS,GX_POS_XYZ,GX_F32,0);GX_SetVtxAttrFmt(GX_VTXFMT0,GX_VA_CLR0,GX_CLR_RGBA,GX_RGBA8,0);GX_SetVtxAttrFmt(GX_VTXFMT0,GX_VA_TEX0,GX_TEX_ST,GX_F32,0);
        const float xs[4]={0,(float)screenwidth,(float)screenwidth,0},ys[4]={0,0,(float)screenheight,(float)screenheight};
        const float us[4]={0,1,1,0},vs[4]={0,0,1,1};
        GX_Begin(GX_QUADS,GX_VTXFMT0,4);
        for(int i=0;i<4;i++){GX_Position3f32(xs[i],ys[i],0);GX_Color4u8(255,255,255,255);GX_TexCoord2f32(us[i],vs[i]);}
        GX_End();
    }
    KwceHomeDraw(); u64 t2=gettime(); draw+=diff_usec(t1,t2);
    KwcePresentHome();lastEnd=gettime();present+=diff_usec(t2,lastEnd);
    if(++n==120) { trace_ui("timing-a",gap/n,input/n,draw/n); trace_ui("timing-b",present/n,vmode->viTVMode,vmode->xfbMode); n=gap=input=draw=present=0; }
    return 1;
}
