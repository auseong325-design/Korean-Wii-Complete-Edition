/* KWCE DVD player: RFNA (wbf1) reader.  See kwce_font.h.
 *
 * Format notes (nw4r ArchiveFont): blocks GLGR, FINF, TGLP, CWDH*, CMAP*.
 * TGLP sheets are I4 8x8-tiled, each stored as [u32 size][CX Huffman 8-bit stream].
 */
#include "kwce_font.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define BE16(p) ((uint16_t)(((p)[0]<<8)|(p)[1]))
#define BE32(p) ((uint32_t)(((p)[0]<<24)|((p)[1]<<16)|((p)[2]<<8)|(p)[3]))

typedef struct { const uint8_t *block; } CMapRef;

static uint8_t *g_data;
static uint32_t g_size;
static const uint8_t *g_font; static uint32_t g_fontLen;
static int g_height, g_ascent, g_cellW, g_cellH, g_baseline, g_sheetW, g_sheetH, g_cols, g_rows, g_sheets;
static const uint8_t *g_sheetStream[64];
static uint32_t g_sheetLen[64];
static const uint8_t *g_cwdh[16]; static int g_cwdhCount;
static CMapRef g_cmap[64]; static int g_cmapCount;
static uint8_t g_defaultWidth[3];

#define SHEET_CACHE 4
static int g_cacheSheet[SHEET_CACHE] = {-1,-1,-1,-1};
static uint8_t *g_cachePixels[SHEET_CACHE];
static unsigned g_cacheAge[SHEET_CACHE], g_clock;

/* CX Huffman, 8-bit symbols (type 0x28). Returns 0 on success. */
static int cx_huffman8(const uint8_t *src, uint32_t len, uint8_t *dst, uint32_t dstLen)
{
	if (len < 5 || src[0] != 0x28) return -1;
	uint32_t size = src[1] | (src[2]<<8) | (src[3]<<16);
	if (size > dstLen) return -1;
	const uint8_t *tree = src + 4;
	uint32_t table = (tree[0] + 1) * 2, pos = 4 + table, out = 0;
	uint32_t node = 1;  /* offset into tree */
	while (out < size) {
		if (pos + 4 > len) return -1;
		uint32_t word = src[pos] | (src[pos+1]<<8) | (src[pos+2]<<16) | ((uint32_t)src[pos+3]<<24); pos += 4;
		for (int bit = 31; bit >= 0 && out < size; bit--) {
			uint8_t value = tree[node]; int right = (word >> bit) & 1;
			uint32_t child = (node & ~1u) + (value & 0x3f) * 2 + 2 + right;
			if (child >= table) return -1;
			if (value & (right ? 0x40 : 0x80)) { dst[out++] = tree[child]; node = 1; }
			else node = child;
		}
	}
	return 0;
}

static const uint8_t *find_u8_file(const uint8_t *d, uint32_t size, const char *name, uint32_t *outLen)
{
	if (size < 0x20 || BE32(d) != 0x55AA382D) return NULL;
	uint32_t root = BE32(d+4); if (root + 12 > size) return NULL;
	uint32_t count = BE32(d + root + 8), strs = root + count * 12;
	for (uint32_t i = 1; i < count; i++) {
		const uint8_t *e = d + root + i * 12;
		if (e[0] != 0) continue;
		uint32_t nameOff = (e[1]<<16)|(e[2]<<8)|e[3];
		if (strs + nameOff >= size) return NULL;
		if (!strcmp((const char *)d + strs + nameOff, name)) {
			uint32_t off = BE32(e+4), len = BE32(e+8);
			if (off + len > size) return NULL;
			*outLen = len; return d + off;
		}
	}
	return NULL;
}

bool KwceFontLoad(uint8_t *data, uint32_t size)
{
	const uint8_t *font = data; uint32_t fontLen = size;
	if (size >= 4 && BE32(data) == 0x55AA382D)
		font = find_u8_file(data, size, "wbf1.brfna", &fontLen);
	if (!font || fontLen < 0x30 || memcmp(font, "RFNA", 4)) { free(data); return false; }
	uint32_t pos = BE16(font + 0x0c); int blocks = BE16(font + 0x0e);
	g_cwdhCount = g_cmapCount = 0; g_sheets = 0;
	for (int b = 0; b < blocks && pos + 8 <= fontLen; b++) {
		const uint8_t *blk = font + pos; uint32_t blen = BE32(blk + 4);
		if (blen < 8 || pos + blen > fontLen) break;
		if (!memcmp(blk, "FINF", 4)) {
			memcpy(g_defaultWidth, blk + 0x0c, 3);
			g_height = blk[0x1c]; g_ascent = blk[0x1e];
		} else if (!memcmp(blk, "TGLP", 4)) {
			g_cellW = blk[0x08]; g_cellH = blk[0x09]; g_baseline = (int8_t)blk[0x0a];
			uint16_t fmt = BE16(blk + 0x12);
			g_sheets = BE16(blk + 0x10); g_cols = BE16(blk + 0x14); g_rows = BE16(blk + 0x16);
			g_sheetW = BE16(blk + 0x18); g_sheetH = BE16(blk + 0x1a);
			uint32_t img = BE32(blk + 0x1c);
			if ((fmt & 0x7fff) != 0 || !(fmt & 0x8000) || g_sheets > 64) { g_sheets = 0; break; }
			for (int s = 0; s < g_sheets; s++) {
				if (img + 4 > fontLen) { g_sheets = 0; break; }
				g_sheetLen[s] = BE32(font + img); g_sheetStream[s] = font + img + 4; img += 4 + g_sheetLen[s];
			}
		} else if (!memcmp(blk, "CWDH", 4) && g_cwdhCount < 16) g_cwdh[g_cwdhCount++] = blk;
		else if (!memcmp(blk, "CMAP", 4) && g_cmapCount < 64) g_cmap[g_cmapCount++].block = blk;
		pos += blen;
	}
	if (!g_sheets || !g_height || !g_cmapCount) { free(data); return false; }
	g_data = data; g_size = size; g_font = font; g_fontLen = fontLen;
	return true;
}

const uint8_t *KwceFontFile(uint32_t *len)
{
	if (len) *len = g_fontLen;
	return g_data ? g_font : NULL;
}

bool KwceFontReady(void) { return g_data != NULL; }

static int glyph_index(uint32_t code)
{
	for (int i = 0; i < g_cmapCount; i++) {
		const uint8_t *b = g_cmap[i].block;
		uint16_t first = BE16(b + 8), last = BE16(b + 10), method = BE16(b + 12);
		if (code < first || code > last) continue;
		if (method == 0) return BE16(b + 20) + (code - first);
		if (method == 1) { uint16_t g = BE16(b + 20 + 2 * (code - first)); if (g != 0xffff) return g; continue; }
		if (method == 2) {
			int n = BE16(b + 20), lo = 0, hi = n - 1;
			while (lo <= hi) {
				int mid = (lo + hi) / 2; uint16_t c = BE16(b + 22 + 4 * mid);
				if (c == code) return BE16(b + 24 + 4 * mid);
				if (c < code) lo = mid + 1; else hi = mid - 1;
			}
		}
	}
	return -1;
}

static const uint8_t *glyph_widths(int index)
{
	for (int i = 0; i < g_cwdhCount; i++) {
		const uint8_t *b = g_cwdh[i];
		uint16_t first = BE16(b + 8), last = BE16(b + 10);
		if (index >= first && index <= last) return b + 16 + 3 * (index - first);
	}
	return g_defaultWidth;
}

static const uint8_t *sheet_pixels(int sheet)
{
	for (int i = 0; i < SHEET_CACHE; i++)
		if (g_cacheSheet[i] == sheet) { g_cacheAge[i] = ++g_clock; return g_cachePixels[i]; }
	int victim = 0;
	for (int i = 1; i < SHEET_CACHE; i++) if (g_cacheAge[i] < g_cacheAge[victim]) victim = i;
	uint32_t raw = (uint32_t)g_sheetW * g_sheetH / 2;
	uint8_t *tiled = (uint8_t *)malloc(raw);
	if (!g_cachePixels[victim]) g_cachePixels[victim] = (uint8_t *)malloc((size_t)g_sheetW * g_sheetH);
	if (!tiled || !g_cachePixels[victim] || cx_huffman8(g_sheetStream[sheet], g_sheetLen[sheet], tiled, raw)) { free(tiled); return NULL; }
	uint8_t *px = g_cachePixels[victim]; const uint8_t *t = tiled;
	for (int by = 0; by < g_sheetH; by += 8)
		for (int bx = 0; bx < g_sheetW; bx += 8)
			for (int y = 0; y < 8; y++)
				for (int x = 0; x < 8; x += 2, t++) {
					px[(by + y) * g_sheetW + bx + x] = (*t >> 4) * 17;
					px[(by + y) * g_sheetW + bx + x + 1] = (*t & 15) * 17;
				}
	free(tiled);
	g_cacheSheet[victim] = sheet; g_cacheAge[victim] = ++g_clock;
	return px;
}

void KwceFontMetrics(int pixelSize, int *ascent, int *descent)
{
	float s = (float)pixelSize / (g_height ? g_height : 1);
	*ascent = (int)lroundf(g_ascent * s);
	*descent = (int)lroundf((g_height - g_ascent) * s);
}

bool KwceFontGlyph(uint32_t code, int pixelSize, KwceGlyph *out)
{
	memset(out, 0, sizeof(*out));
	if (!g_data || pixelSize <= 0) return false;
	int index = glyph_index(code);
	if (index < 0) return false;
	int perSheet = g_cols * g_rows, sheet = index / perSheet, item = index % perSheet;
	if (sheet >= g_sheets) return false;
	const uint8_t *w = glyph_widths(index);
	int left = (int8_t)w[0], gw = w[1], adv = (int8_t)w[2];
	float s = (float)pixelSize / g_height;
	out->advance = (int)lroundf(adv * s);
	out->left = (int)lroundf(left * s);
	out->top = (int)lroundf(g_baseline * s);
	if (gw == 0) {  /* space: an empty 1x1 bitmap keeps FreeTypeGX's texture path valid */
		out->buffer = (uint8_t *)calloc(1, 1); out->width = out->rows = 1; out->top = 0;
		return out->buffer != NULL;
	}
	const uint8_t *px = sheet_pixels(sheet);
	if (!px) return false;
	int cx = (item % g_cols) * (g_cellW + 1), cy = (item / g_cols) * (g_cellH + 1);
	int ow = (int)lroundf(gw * s), oh = (int)lroundf(g_cellH * s);
	if (ow < 1) ow = 1; if (oh < 1) oh = 1;
	out->buffer = (uint8_t *)malloc(ow * oh);
	if (!out->buffer) return false;
	out->width = ow; out->rows = oh;
	for (int y = 0; y < oh; y++)
		for (int x = 0; x < ow; x++) {
			/* bilinear sample of the source cell, like GX texture filtering */
			float sx = (x + 0.5f) / s - 0.5f, sy = (y + 0.5f) / s - 0.5f;
			int x0 = (int)floorf(sx), y0 = (int)floorf(sy); float fx = sx - x0, fy = sy - y0;
			float acc = 0;
			for (int j = 0; j < 2; j++)
				for (int i = 0; i < 2; i++) {
					int xx = x0 + i, yy = y0 + j;
					float wgt = (i ? fx : 1 - fx) * (j ? fy : 1 - fy);
					if (xx >= 0 && xx < gw && yy >= 0 && yy < g_cellH) acc += wgt * px[(cy + yy) * g_sheetW + cx + xx];
				}
			out->buffer[y * ow + x] = (uint8_t)(acc > 255 ? 255 : acc);
		}
	return true;
}

void KwceFontFreeGlyph(KwceGlyph *glyph) { free(glyph->buffer); glyph->buffer = NULL; }
