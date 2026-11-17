#ifndef KWCE_DIAGNOSTICS_H
#define KWCE_DIAGNOSTICS_H
/* Read-only Wii/HC scheduler inspection, writes only its own SD report. */
int kwce_diagnostic_capture(const char *phase, int (*version_fn)(u64));
#endif
