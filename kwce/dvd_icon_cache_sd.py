"""Native60 candidate: publish validated icon bytes before exposing them to GX."""
from . import dvd_prefetch_sd as base

TARGETS=base.TARGETS
README='KWCE-DVD-ICON-CACHE-ko.txt'
PATHS=TARGETS|{README}


def upgrade_definition(raw):
    return base.upgrade_definition(raw,before=59,after=60)


def sd_files(package):
    meta,files=base._sd_files(package,kind='dvd-icon-cache-store-v1',paths=PATHS,
                             before=59,after=60,manifest_name='KWCE-DVD-ICON-CACHE-manifest.json')
    if (meta.get('icon_cache_store') is not True or meta.get('thumbnail_hook') is not True
            or meta.get('other_functional_changes') is not False):
        raise ValueError('Icon cache candidate scope mismatch')
    return meta,files


def verify_card(package,card):
    base.verify_card(package,card,verifier=sd_files)
