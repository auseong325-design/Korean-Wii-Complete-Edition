/* Bounded GC card comment decoder. This is project code, not Nintendo code.
 * Uses 43K's existing PrFILE2 CP932 converter and its existing tables.
 * No save text or console data is embedded. r3/r4/r5 match the wrapper.
 */
typedef unsigned char u8;
typedef unsigned short u16;
__attribute__((section(".entry")))
void gc_comment(u16 *dst, const u8 *src, int capacity) {
    unsigned read = 0, written = 0;
    if (capacity <= 0) return;
    unsigned limit = capacity < 32 ? (unsigned)capacity : 32;
    while (read < 32 && written + 1 < limit && src[read]) {
        unsigned c = src[read], step = 1;
        if ((c >= 0x81 && c <= 0x9f) || (c >= 0xe0 && c <= 0xfc)) step = 2;
        if (read + step > 32 || (step == 2 && !src[read+1])) break;
        ((int (*)(const u8 *, u16 *))0x815bd2c0)(src + read, dst + written);
        read += step;
        written++;
    }
    dst[written] = 0;
}
