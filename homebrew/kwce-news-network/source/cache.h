#ifndef KWCE_NEWS_CACHE_H
#define KWCE_NEWS_CACHE_H
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
typedef struct {
    int valid_vff;
    unsigned entries, parsed, fresh, expired, future, country_49, country_136;
    unsigned language_english, unsupported_or_invalid, crc_ok, crc_bad, structural_bad, language_empty, expired_utc9, topic_bad, source_bad, location_bad, image_bad;
} news_cache_summary;
void news_cache_set_snapshot(FILE *out);
int news_cache_inspect(const unsigned char *data, size_t bytes, uint32_t now_unix,
                       news_cache_summary *out);
#endif
