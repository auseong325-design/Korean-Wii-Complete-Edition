/* Bounded first-read comparison. No retries, error query, or media output.
 * Called with the device watcher suspended after libdi mount completes.
 * Uses the same static aligned buffer and 0/16/256 single-sector order as
 * the successful HBC probe. Success is not a DVD-Video validity assertion.
 */
static unsigned char kwceProbeBuffer[2048] __attribute__((aligned(32)));
static bool KwceProbeFirstReads(void)
{
    const unsigned sectors[3] = {0,16,256};
    for (unsigned i=0;i<3;i++) {
        KwceDvdTrace("first-read-begin",i,DI_GetStatus());
        int result=DI_ReadDVD(kwceProbeBuffer,1,sectors[i]);
        KwceDvdTrace("first-read-end",i,result);
        KwceDvdTrace("first-read-mode",i,DI_GetStatus());
        if(result!=0) return false;
    }
    return true;
}
