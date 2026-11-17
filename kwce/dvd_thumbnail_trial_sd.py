"""One-call-site control: restore stock ChannelSelect update, retain other native58 hooks."""
from . import dvd_prefetch_sd as base

TARGETS=base.TARGETS
README='KWCE-DVD-STOCK-THUMBNAIL-TRIAL-ko.txt'
PATHS=TARGETS|{README}


def upgrade_definition(raw):
    return base.upgrade_definition(raw,before=58,after=59)


def sd_files(package):
    meta,files=base._sd_files(package,kind='dvd-stock-thumbnail-trial-v1',paths=PATHS,
                             before=58,after=59,manifest_name='KWCE-DVD-STOCK-THUMBNAIL-TRIAL-manifest.json')
    if meta.get('thumbnail_hook') is not False or meta.get('other_hook_changes') is not False:
        raise ValueError('Stock-thumbnail control scope mismatch')
    return meta,files


def verify_card(package,card):
    base.verify_card(package,card,verifier=sd_files)
