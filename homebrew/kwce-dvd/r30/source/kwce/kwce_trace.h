/* Non-identifying local playback stages; never media bytes, titles or keys. */
#ifndef KWCE_TRACE_H
#define KWCE_TRACE_H
#ifdef __cplusplus
extern "C" {
#endif
void KwceDvdTrace(const char *event, int a, int b);
#ifdef __cplusplus
}
#endif
#endif
