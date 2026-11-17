/*
Copyright (c) 2010 - Wii Banner Player Project
Copyright (c) 2012 - Dimok

This software is provided 'as-is', without any express or implied
warranty. In no event will the authors be held liable for any damages
arising from the use of this software.

Permission is granted to anyone to use this software for any purpose,
including commercial applications, and to alter it and redistribute it
freely, subject to the following restrictions:

1. The origin of this software must not be misrepresented; you must not
claim that you wrote the original software. If you use this software
in a product, an acknowledgment in the product documentation would be
appreciated but is not required.

2. Altered source versions must be plainly marked as such, and must not be
misrepresented as being the original software.

3. This notice may not be removed or altered from any source
distribution.
*/
#include "Window.h"
#include "Layout.h"

void Window::Load(Pane::Header *file)
{
	if(!file)
		return;

	const u8 *section_start = (const u8 *)file;

	Pane::Load(file);
	header = (Window::Header *) (file+1);

	// read content
	QuadPane::Load((QuadPane::Header *)(section_start + header->content_offset));

	// read frames
	const u32 *frame_offsets = (const u32 *) (section_start + header->frame_table_offset);
	for(u32 i = 0; i < header->frame_count; i++)
		frames.push_back((Frame *) (section_start + frame_offsets[i]));
}

/* KWCE: single-frame windows follow NW4R lyt_window.cpp. HOME uses
 * a corner texture mirrored around all four edges; the content is inset. */
void Window::Draw(const BannerResources& resources, u8 alpha, const float ws_scale, Mtx &view) const
{
    if (frames.size() != 1 || frames[0]->material_index >= resources.materials.size()) {
        QuadPane::Draw(resources, alpha, ws_scale, view); return;
    }
    const Material *frame = resources.materials[frames[0]->material_index];
    const Texture *tex = frame->FirstTexture(resources);
    if (!tex || !tex->Width() || !tex->Height()) return;
    const u8 *start = (const u8 *)Pane::GetHeader();
    const QuadPane::Header *content = (const QuadPane::Header *)(start + header->content_offset);
    const float *uv = (const float *)(content + 1);
    float w = GetWidth(), h = GetHeight(), tw = tex->Width(), th = tex->Height();
    float x = -0.5f * GetOriginX() * w, y = -0.5f * GetOriginY() * h;
    if (w <= 0 || h <= 0) return;
    GX_LoadPosMtxImm(view, GX_PNMTX0);
    auto quad = [&](const Material *mat, float qx, float qy, float qw, float qh,
                    float u0, float v0, float u1, float v1, const GXColor *colors) {
        if (qw <= 0 || qh <= 0) return;
        mat->Apply(resources, alpha, true);
        GX_ClearVtxDesc();
        GX_SetVtxDesc(GX_VA_POS, GX_DIRECT); GX_SetVtxDesc(GX_VA_CLR0, GX_DIRECT);
        GX_SetVtxDesc(GX_VA_TEX0, GX_DIRECT);
        const float px[4] = {qx,qx+qw,qx+qw,qx}, py[4] = {qy,qy,qy+qh,qy+qh};
        const float us[4] = {u0,u1,u1,u0}, vs[4] = {v0,v0,v1,v1};
        const int order[4] = {0,1,3,2};
        GX_Begin(GX_QUADS, GX_VTXFMT0, 4);
        for (int i=0; i<4; i++) {
            GXColor c = colors ? colors[order[i]] : (GXColor){255,255,255,255};
            GX_Position3f32(px[i],py[i],0); GX_Color4u8(c.r,c.g,c.b,MultiplyAlpha(c.a,alpha)); GX_TexCoord2f32(us[i],vs[i]);
        }
        GX_End();
    };
    if (content->material_index < resources.materials.size())
        quad(resources.materials[content->material_index],x+tw-header->infl.l,y+th-header->infl.t,
             w-2*tw+header->infl.l+header->infl.r,h-2*th+header->infl.t+header->infl.b,
             content->tex_coord_count ? uv[0] : 0,content->tex_coord_count ? uv[1] : 0,
             content->tex_coord_count ? uv[6] : 1,content->tex_coord_count ? uv[7] : 1,content->vertex_colors);
    quad(frame,x,y,w-tw,th,0,0,(w-tw)/tw,1,NULL);
    quad(frame,x+w-tw,y,tw,h-th,1,0,0,(h-th)/th,NULL);
    quad(frame,x+tw,y+h-th,w-tw,th,(w-tw)/tw,1,0,0,NULL);
    quad(frame,x,y+th,tw,h-th,0,(h-th)/th,1,0,NULL);
}
