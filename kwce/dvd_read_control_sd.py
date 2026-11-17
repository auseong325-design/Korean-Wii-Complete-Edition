"""Native61: retain validated icon reads, acknowledge once, use the stock layout."""
from . import dvd_prefetch_sd as base

TARGETS=base.TARGETS
README='KWCE-DVD-READ-CONTROL-ko.txt'
PATHS=TARGETS|{README}


def upgrade_definition(raw):
    return base.upgrade_definition(raw,before=60,after=61)


def sd_files(package):
    meta,files=base._sd_files(package,kind='dvd-thumbnail-read-control-v1',paths=PATHS,
                            before=60,after=61,
                            manifest_name='KWCE-DVD-READ-CONTROL-manifest.json')
    if (meta.get('thumbnail_read_control') is not True
            or meta.get('custom_icon_layout') is not False
            or meta.get('success_sound')!='WIPL_SE_DECIDE'
            or meta.get('other_functional_changes') is not False):
        raise ValueError('Read control scope mismatch')
    return meta,files


def verify_card(package,card):
    base.verify_card(package,card,verifier=sd_files)
