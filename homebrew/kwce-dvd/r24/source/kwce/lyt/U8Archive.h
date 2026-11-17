/* KWCE DVD player: minimal read-only U8 archive for the layout engine.
 *
 * Replaces USB Loader GX's utils/U8Archive (no ASH/LZ77 here: the player's UI
 * archive is built uncompressed, see kwce/dvd_home_ui.py). The archive buffer
 * is owned by the caller and must stay alive while layouts reference it.
 */
#ifndef KWCE_LYT_U8ARCHIVE_H
#define KWCE_LYT_U8ARCHIVE_H

#include <gctypes.h>
#include <string>

class U8Archive
{
public:
	U8Archive(const u8 *data, u32 size) : data(data), size(size), nodes(0), names(0), count(0)
	{
		if (!data || size < 0x20 || *(const u32 *)data != 0x55AA382D)
			return;
		u32 root = ((const u32 *)data)[1];
		if (root + 12 > size)
			return;
		nodes = data + root;
		count = ((const u32 *)nodes)[2];
		if (root + count * 12 > size)
		{
			count = 0;
			return;
		}
		names = (const char *)(nodes + count * 12);
	}

	bool IsValid() const { return count > 0; }

	/* path like "/arc/timg/name.tpl" or "arc/timg/name.tpl"; NULL if missing. */
	const u8 *GetFile(const std::string &path, u32 *length = 0) const
	{
		if (!count)
			return 0;
		std::string p = path;
		while (!p.empty() && p[0] == '/')
			p.erase(0, 1);
		/* walk directories: each directory node's [2] is the index after its last child */
		u32 dir = 0, i = 1, end = count;
		size_t start = 0;
		while (start <= p.size())
		{
			size_t slash = p.find('/', start);
			std::string part = p.substr(start, slash == std::string::npos ? std::string::npos : slash - start);
			bool last = slash == std::string::npos;
			bool found = false;
			for (; i < end; )
			{
				const u32 *n = (const u32 *)(nodes + i * 12);
				bool isDir = (n[0] >> 24) == 1;
				const char *name = names + (n[0] & 0xFFFFFF);
				if (part == name || (part.empty() && name[0] == '.' && name[1] == 0))
				{
					if (last)
					{
						if (isDir || n[1] + n[2] > size)
							return 0;
						if (length)
							*length = n[2];
						return data + n[1];
					}
					if (!isDir)
						return 0;
					dir = i;
					end = n[2];
					i = i + 1;
					found = true;
					break;
				}
				i = isDir ? n[2] : i + 1;
			}
			if (!found)
			{
				/* Nintendo archives put everything under a "." directory */
				if (dir == 0 && i == end && start == 0 && part != ".")
				{
					p = "./" + p;
					i = 1;
					end = count;
					continue;
				}
				return 0;
			}
			start = slash + 1;
		}
		return 0;
	}

private:
	const u8 *data;
	u32 size;
	const u8 *nodes;
	const char *names;
	u32 count;
};

#endif
