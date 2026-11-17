/* KWCE: never starve presentation while audio/decoder and input keep running.
 * VI mode low bits: 0 interlaced, 1 double-strike, 2 progressive (libogc).
 * No I/O here: this policy is used from the vertical-retrace interrupt. */
#ifndef KWCE_PRESENT_H
#define KWCE_PRESENT_H
static inline int KwceShouldPresent(unsigned mode, int sync, int nextField,
                                   int home, unsigned missed)
{
    if (home || mode!=0 || missed>=2) return 1;
    if (sync==1) return !nextField;
    if (sync==2) return !!nextField;
    return 1;
}

/* Behavior regression matrix executed once at startup in both emulator modes.
 * A constant progressive field must still present every frame. An unavailable
 * interlaced field can defer at most two retraces; HOME always presents. */
static inline int KwcePresentSelfTest(void)
{
    int failed=0;
    for(unsigned mode=1;mode<=2;++mode)
        for(int field=0;field<2;++field)
            for(int sync=0;sync<=2;++sync)
                failed+=!KwceShouldPresent(mode,sync,field,0,0);
    failed+=!KwceShouldPresent(0,1,0,0,0);
    failed+=!KwceShouldPresent(0,2,1,0,0);
    failed+=KwceShouldPresent(0,1,1,0,0);
    failed+=KwceShouldPresent(0,2,0,0,0);
    failed+=!KwceShouldPresent(0,1,1,0,2);
    failed+=!KwceShouldPresent(0,2,0,0,2);
    failed+=!KwceShouldPresent(0,1,1,1,0);
    failed+=!KwceShouldPresent(0,2,0,1,0);
    return failed;
}
#endif
