/* KWCE DVD player, default build: libdvdcss without CSS decryption.
 *
 * Replaces css.c. Device access (device.c / DI_ReadDVD) is unchanged; no disc
 * or title key is requested, derived or recovered, and scrambled sectors are
 * never unscrambled. The first scrambled sector sets kwce_css_scrambled so the
 * player can stop and tell the user. Build with --css to use upstream css.c.
 */
#include "config.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <limits.h>
#include "dvdcss/dvdcss.h"
#include "common.h"
#include "css.h"
#include "libdvdcss.h"
#include "../../kwce/kwce_trace.h"

volatile int kwce_css_scrambled = 0;

void _dvdcss_test( dvdcss_t dvdcss )
{
    /* Route every sector through _dvdcss_unscramble, which only detects scrambling. */
    dvdcss->b_scrambled = 1;
}

int _dvdcss_title( dvdcss_t dvdcss, int i_block )
{
    (void)i_block;
    memset( dvdcss->css.p_title_key, 0, KEY_SIZE );
    return 0;
}

int _dvdcss_disckey( dvdcss_t dvdcss )
{
    memset( dvdcss->css.p_disc_key, 0, KEY_SIZE );
    return -1;
}

int _dvdcss_titlekey( dvdcss_t dvdcss, int i_pos, dvd_key_t p_title_key )
{
    (void)dvdcss; (void)i_pos;
    memset( p_title_key, 0, KEY_SIZE );
    return -1;
}

int _dvdcss_unscramble( uint8_t *p_key, uint8_t *p_sec )
{
    (void)p_key;
    /* DVD pack followed by an MPEG-2 video/audio PES. NAV/system packets
     * have a different header: their byte 0x14 is not a scramble flag. */
    unsigned off=14+(p_sec[13]&7);
    if( p_sec[0]==0 && p_sec[1]==0 && p_sec[2]==1 && p_sec[3]==0xba &&
        p_sec[off]==0 && p_sec[off+1]==0 && p_sec[off+2]==1 &&
        (p_sec[off+3]==0xbd || (p_sec[off+3]>=0xc0 && p_sec[off+3]<=0xef)) &&
        (p_sec[off+6]&0x30) ) {
        if(!kwce_css_scrambled)KwceDvdTrace("scrambled-pes",1,0);
        kwce_css_scrambled=1;
    }
    return 0;
}
