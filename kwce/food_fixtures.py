"""Synthetic local feed for the Food (Demae) channel internal screens.

Fictional data only, shaped from the pinned WiiLink food-server response
structures (workspace/channels/food/references/food-server-*/responses.py).
Covers the BROWSE chain so the lead can walk category -> shop list -> shop
menu -> item detail. It deliberately serves NOTHING for the cart/basket/order
actions (webApi_Authkey, webApi_basket_*, webApi_order_done, webApi_inquiry_*,
webApi_validate_condition): AGENTS.md forbids order/upload flows even locally,
so the FoodServer returns 404 for those and the channel shows a service error
at the point of ordering. All values are ASCII/romaji: the channel's server
path is Shift-JIS, which cannot carry Hangul.
"""
import json, struct, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CATS = [  # (key, CategoryCode, name, [(shopCode, name, catchphrase, waitTime)])
    ('Pizza', 1, 'Pizza', [(101, 'Napoli Pizza House', 'Wood-fired classics', 25),
                           (102, 'Seoul Pizza Lab', 'Local-style pies', 30)]),
    ('Sushi', 3, 'Sushi', [(301, 'Hangang Sushi', 'Fresh daily nigiri', 20)]),
    ('FastFood', 7, 'Fast Food', [(701, 'Bun Sik Express', 'Tteokbokki and more', 15)]),
]
MENUS = {101: [(11, 'Pizzas', 'Signature pizzas')],
         102: [(21, 'Pies', 'House recipes')],
         301: [(31, 'Nigiri Sets', 'Chef selection')],
         701: [(71, 'Street Food', 'Snacks and sets')]}
ITEMS = {11: [(1101, 'Margherita', 'Tomato, basil, mozzarella', '12.00'),
              (1102, 'Bulgogi Pizza', 'Marinated beef, onion', '15.50')],
         21: [(2101, 'Classic Cheese', 'Three cheese blend', '11.00')],
         31: [(3101, 'Omakase 8pc', 'Eight-piece nigiri set', '18.00')],
         71: [(7101, 'Tteokbokki', 'Spicy rice cakes', '6.50'),
              (7102, 'Kimbap', 'Seaweed rice roll', '4.50')]}
EULA = ('Food Channel local test build. Synthetic data only. No real orders '
        'are placed. Payment on delivery; no card or Wii Points.')


def cdata(v):
    return '<![CDATA[%s]]>' % v


def el(tag, inner):
    return '<%s>%s</%s>' % (tag, inner, tag)


def status_prefix():
    return el('apiStatus', el('code', cdata('0'))) + el('version', cdata('1'))


def wrap_response(inner):
    return '<response>' + status_prefix() + inner + '</response>'


def document_template():
    body = (el('container0', el('contents', cdata(EULA)))
            + el('container1', el('contents', cdata('')))
            + el('container2', el('contents', cdata(''))))
    return wrap_response(body)


def area_list_segment():
    # areaCode=0: offer one selectable area segment.
    inner = (el('areaList', el('place', el('segment', cdata('WiiLink'))
             + el('list', el('areaPlace', el('areaName', cdata('WiiLink'))
                             + el('areaCode', cdata('2')))))) + el('areaCount', cdata('1')))
    return '<response>' + status_prefix() + inner + '</response>'


def area_list_assign():
    # areaCode=2: assign a deterministic fictional area code.
    inner = (el('areaList', el('place', el('container0', cdata('aaaa'))
             + el('segment', cdata('WiiLink'))
             + el('list', el('areaPlace', el('areaName', cdata('Reunion Tower'))
                             + el('areaCode', cdata('00000000001'))
                             + el('isNextArea', cdata('0')) + el('display', cdata('1'))
                             + el('kanji1', cdata('300')) + el('kanji2', cdata('Reunion Tower'))
                             + el('kanji3', cdata('two')) + el('kanji4', cdata('three'))))))
             + el('areaCount', cdata('1')))
    return '<response>' + status_prefix() + inner + '</response>'


def shop_block(code, name, catch, wait):
    return el('Shop', el('shopCode', cdata(str(code))) + el('homeCode', cdata(str(code)))
              + el('name', cdata(name)) + el('catchphrase', cdata(catch))
              + el('minPrice', cdata('1')) + el('yoyaku', cdata('1')) + el('activate', cdata('on'))
              + el('waitTime', cdata(str(wait))) + el('paymentList', el('athing', cdata('Fox Card')))
              + el('shopStatus', el('status', el('isOpen', cdata('1')))))


def category_list():
    roots = [status_prefix()]
    for key, cc, name, shops in CATS:
        shoplist = ''.join(shop_block(*s) for s in shops)
        cat = el('LargeCategoryName', cdata('Meal')) + el('CategoryList', el('TestingCategory',
              el('CategoryCode', cdata('%02d' % cc)) + el('ShopList', shoplist)))
        roots.append('<%s>%s</%s>' % (key, cat, key))
    # multiple_root_nodes: concatenated root elements
    return ''.join(['<response>'] + roots + ['</response>'])


def shop_one():
    code = 101
    rec = ''
    for mc, mname, minfo in MENUS[code]:
        it = ITEMS[mc][0]
        rec += el('container0', el('menuCode', cdata(str(mc))) + el('itemCode', cdata(str(it[0])))
                  + el('name', cdata(it[1])) + el('price', cdata(it[3])) + el('info', cdata(it[2]))
                  + el('size', cdata('Regular')) + el('image', cdata(str(it[0]))) + el('isSoldout', cdata('0')))
    inner = el('response', el('categoryCode', cdata('01')) + el('address', cdata('1 Demae Street'))
               + el('attention', cdata('')) + el('amenity', cdata('Open daily'))
               + el('menuListCode', cdata('1')) + el('activate', cdata('on')) + el('waitTime', cdata('10'))
               + el('timeorder', cdata('y')) + el('tel', cdata('000-0000-0000'))
               + el('yoyakuMinDate', cdata('1')) + el('yoyakuMaxDate', cdata('30'))
               + el('paymentList', el('athing', cdata('Fox Card'))) + el('interval', cdata('30'))
               + el('shopStatus', el('hours', el('all', el('message', cdata('Welcome!')))
                   + el('today', el('values', el('hours', el('start', cdata('00:00:00'))
                       + el('end', cdata('24:59:59')) + el('holiday', cdata('n')))))
                   + el('delivery', el('values', el('hours', el('start', cdata('00:00:00'))
                       + el('end', cdata('24:59:59')) + el('holiday', cdata('n'))))))
                   + el('selList', '') + el('holiday', cdata('')) + el('status', el('isOpen', cdata('1')))))
    inner += el('recommendItemList', rec)
    return ''.join(['<response>', status_prefix(), inner, '</response>'])


def menu_list():
    code = 101; data = ''
    for mc, mname, minfo in MENUS[code]:
        data += el('menu', el('menuCode', cdata(str(mc))) + el('linkTitle', cdata(mname))
                    + el('enabledLink', cdata('1')) + el('name', cdata(mname)) + el('info', cdata(minfo))
                    + el('setNum', cdata('0')) + el('lunchMenuList', el('isLunchTimeMenu', cdata('1'))
                        + el('hour', el('start', cdata('1')) + el('end', cdata('1'))) + el('isOpen', cdata('1')))
                    + el('message', cdata('')))
    inner = el('response', el('menu', data))
    return ''.join(['<response>', status_prefix(), inner, '</response>'])


def item_bits(it):
    return (el('menuCode', cdata('11')) + el('itemCode', cdata(str(it[0]))) + el('name', cdata(it[1]))
            + el('price', cdata(it[3])) + el('info', cdata(it[2])) + el('size', cdata('Regular'))
            + el('image', cdata(str(it[0]))) + el('isSoldout', cdata('0')))


def item_list():
    items = ITEMS[11]; full = ''
    for i, it in enumerate(items):
        size = item_bits(it) + el('sizeList', el('itemCode', cdata(str(it[0]))) + el('name', cdata(it[1]))
                + el('price', cdata(it[3])) + el('info', cdata(it[2])) + el('size', cdata('Regular'))
                + el('image', cdata(str(it[0]))) + el('isSoldout', cdata('0')))
        full += el('container%d' % i, el('name', cdata(it[1])) + el('item', size))
    inner = el('Count', cdata(str(len(items)))) + el('List', full)
    return ''.join(['<response>', status_prefix(), inner, '</response>'])


def item_one():
    it = ITEMS[11][0]
    inner = el('price', cdata(it[3])) + el('optionList', el('testing', el('info', cdata(it[2]))
             + el('code', cdata('1')) + el('type', cdata('1')) + el('name', cdata(it[1]))
             + el('list', el('item_one', item_bits(it)))))
    return ''.join(['<response>', status_prefix(), inner, '</response>'])


ACTIONS = {
    'webApi_document_template': lambda: {'': document_template()},
    'webApi_area_list': lambda: {'0': area_list_segment(), '2': area_list_assign(), '': area_list_assign()},
    'webApi_category_list': lambda: {'': category_list()},
    'webApi_shop_list': lambda: {'': category_list()},
    'webApi_area_shopinfo': lambda: {'': wrap_response('')},
    'webApi_shop_one': lambda: {'': shop_one()},
    'webApi_menu_list': lambda: {'': menu_list()},
    'webApi_item_list': lambda: {'': item_list()},
    'webApi_item_one': lambda: {'': item_one()},
}
# Deliberately NOT served (order/cart/auth) -> FoodServer returns 404.
BLOCKED = ['webApi_Authkey', 'webApi_basket_list', 'webApi_basket_add', 'webApi_basket_reset',
           'webApi_basket_delete', 'webApi_basket_modify', 'webApi_validate_condition',
           'webApi_order_done', 'webApi_inquiry_done']


# ---------------------------------------------------------------------------
# Revision 2: serialized like the pinned WiiLink food-server
# (references/food-server-*/helpers.py + responses.py). Lead Dolphin review of
# v1: the channel rejected the very first answer (document template, error
# 338395). v1 put apiStatus/version FIRST and wrapped multi-root answers in a
# single <response>. WiiLink appends apiStatus and version AFTER the data
# (@response) or as separate trailing root nodes (@multiple_root_nodes) and
# pretty-prints with lxml. The channel walks child nodes by index and skips the
# last data node, hence WiiLink's trailing "Placeholder" category and "menu2".
# ---------------------------------------------------------------------------
class Repeated(list):
    """WiiLink RepeatedElement list: every item becomes a sibling with the same tag."""


def _x(tag, value, level=0):
    """lxml pretty_print shape of WiiLink dict_to_etree (2-space indent, CDATA scalars)."""
    ind = '  ' * level
    if isinstance(value, Repeated):
        return ''.join(_x(tag, item, level) for item in value) if value else f'{ind}<{tag}/>\n'
    if value is None or (isinstance(value, dict) and not value):
        return f'{ind}<{tag}/>\n'
    if isinstance(value, dict):
        return f'{ind}<{tag}>\n' + ''.join(_x(k, v, level + 1) for k, v in value.items()) + f'{ind}</{tag}>\n'
    if isinstance(value, bool):
        value = '1' if value else '0'
    return f'{ind}<{tag}>{cdata(value)}</{tag}>\n'


STATUS = [('apiStatus', {'code': 0}), ('version', 1)]


def response_doc(data):
    """@response(): data children first, then apiStatus and version, inside <response>."""
    return _x('response', dict(list(data.items()) + STATUS))


def multi_root_doc(data):
    """@multiple_root_nodes(): every key is its own root node; status roots come last."""
    return ''.join(_x(k, v) for k, v in list(data.items()) + STATUS)


V2_AREA = '00000000001'  # deterministic stand-in for WiiLink's random 11-digit area code
V2_PRICES = {1101: '1200', 1102: '1550', 2101: '1100', 3101: '1800', 7101: '650', 7102: '450'}
WIILINK_CATEGORIES = [('Pizza', 1), ('Bento', 2), ('Sushi', 3), ('Fish', 4), ('Seafood', 5), ('American', 6),
                      ('Fast', 7), ('Indian', 8), ('Party', 9), ('Drinks', 10), ('Other', 11), ('Placeholder', 11)]
OPEN_HOURS = {'start': '00:00:00', 'end': '24:59:59', 'holiday': 'n'}


def _v2_shop(code, name, catch, wait):
    return {'shopCode': code, 'homeCode': code, 'name': name, 'catchphrase': catch, 'minPrice': 1,
            'yoyaku': 1, 'activate': 'on', 'waitTime': wait, 'paymentList': {'athing': 'Cash'},
            'shopStatus': {'status': {'isOpen': 1}}}


def _v2_item(menu_code, it, sizes=False):
    code, name, info, _old_price = it
    item = {'menuCode': menu_code, 'itemCode': code, 'name': name, 'price': V2_PRICES[code], 'info': info,
            'size': 'Regular', 'image': code, 'isSoldout': 0}
    if sizes:
        item['sizeList'] = {'itemCode': code, 'name': name, 'price': V2_PRICES[code], 'info': info,
                            'size': 'Regular', 'image': code, 'isSoldout': 0}
    return item


def _v2_menu(code, name, info):
    return {'menuCode': code, 'linkTitle': name, 'enabledLink': 1, 'name': name, 'info': info, 'setNum': 0,
            'lunchMenuList': {'isLunchTimeMenu': 1, 'hour': {'start': 1, 'end': 1}, 'isOpen': 1},
            'message': 'Local test menu'}


def v2_document_template():
    return response_doc({'container0': {'contents': EULA},
                         'container1': {'contents': 'Local test build. No order is ever sent.'},
                         'container2': {'contents': 'Synthetic data only.'}})


def v2_area_list_segment():  # areaCode=0: first search
    return response_doc({'areaList': {'place': {'segment': 'WiiLink', 'list': {
        'areaPlace': {'areaName': 'WiiLink', 'areaCode': 2}}}}, 'areaCount': 1})


def v2_area_list_assign():  # areaCode=2: assign the fictional area code
    return response_doc({'areaList': {'place': {'container0': 'aaaa', 'segment': 'WiiLink', 'list': {
        'areaPlace': {'areaName': 'KWCE Test Area', 'areaCode': V2_AREA, 'isNextArea': 0, 'display': 1,
                      'kanji1': '300', 'kanji2': 'KWCE Test Area', 'kanji3': 'Block 2', 'kanji4': 'Lot 3'}}}},
        'areaCount': 1})


def v2_area_list_zip():  # zipCode search: segments + a separate <selectedArea> root node
    return v2_area_list_segment() + _x('selectedArea', {'areaCode': 1})


def v2_category_list():
    by_code = {cc: shops for _key, cc, _name, shops in CATS}
    cats = {key: {'LargeCategoryName': 'Meal', 'CategoryList': {'TestingCategory': {
        'CategoryCode': '%02d' % cc, 'ShopList': {'Shop': Repeated(_v2_shop(*s) for s in by_code.get(cc, []))}}}}
        for key, cc in WIILINK_CATEGORIES}
    return multi_root_doc({'response': cats})


def v2_shop_one():
    code = 101
    rec = {'container%d' % i: _v2_item(mc, ITEMS[mc][0], sizes=True) for i, (mc, _n, _i) in enumerate(MENUS[code])}
    shop = {'categoryCode': '01', 'address': '1 Demae Street', 'attention': '', 'amenity': 'Open daily',
            'menuListCode': 1, 'activate': 'on', 'waitTime': 10, 'timeorder': 'y', 'tel': '000-0000-0000',
            'yoyakuMinDate': 1, 'yoyakuMaxDate': 30, 'paymentList': {'athing': 'Cash'}, 'interval': 30,
            'shopStatus': {'hours': {'all': {'message': 'Welcome!'}, 'today': {'values': {'hours': OPEN_HOURS}},
                                     'delivery': {'values': {'hours': OPEN_HOURS}}},
                           'selList': {}, 'holiday': 'Closed on test holidays', 'status': {'isOpen': 1}}}
    return multi_root_doc({'response': shop, 'recommendItemList': rec})


def v2_menu_list():
    menus = Repeated(_v2_menu(*m) for m in MENUS[101])
    return multi_root_doc({'response': {'menu': menus, 'menu2': _v2_menu(2, 'More dishes', 'Placeholder entry')}})


def v2_item_list():
    mc = 11
    entries = {'container%d' % i: {'name': it[1], 'item': _v2_item(mc, it, sizes=True)} for i, it in enumerate(ITEMS[mc])}
    return multi_root_doc({'Count': len(ITEMS[mc]), 'List': entries})


def v2_item_one():
    mc = 11; it = ITEMS[mc][0]
    return multi_root_doc({'price': V2_PRICES[it[0]], 'optionList': {'testing': {
        'info': it[2], 'code': 1, 'type': 1, 'name': it[1], 'list': {'item_one': _v2_item(mc, it)}}}})


ACTIONS_V2 = {
    'webApi_document_template': lambda: {'': v2_document_template()},
    'webApi_area_list': lambda: {'0': v2_area_list_segment(), '2': v2_area_list_assign(), '': v2_area_list_zip()},
    'webApi_category_list': lambda: {'': v2_category_list()},
    'webApi_shop_list': lambda: {'': v2_category_list()},
    'webApi_area_shopinfo': lambda: {'': response_doc({})},
    'webApi_shop_one': lambda: {'': v2_shop_one()},
    'webApi_menu_list': lambda: {'': v2_menu_list()},
    'webApi_item_list': lambda: {'': v2_item_list()},
    'webApi_item_one': lambda: {'': v2_item_one()},
}
MULTI_ROOT_V2 = {'webApi_category_list', 'webApi_shop_list', 'webApi_shop_one', 'webApi_menu_list',
                 'webApi_item_list', 'webApi_item_one'}

# Revision 3: lead Dolphin review of v2 got through the intro, terms, address
# check and region setup, then category_list failed (error 336295). v2 left
# eight categories as an empty <Shop/> node, a shape the live WiiLink service
# (shops in every category) never sends. v3 gives every category one fictional
# shop; Placeholder repeats Other, as in WiiLink.
V3_EXTRA_SHOPS = {2: [(201, 'Dosirak Box', 'Lunch boxes', 20)], 4: [(401, 'Busan Grill', 'Grilled fish', 25)],
                  5: [(501, 'Jeju Seafood', 'Seafood platters', 30)], 6: [(601, 'Diner 66', 'Burgers and fries', 20)],
                  8: [(801, 'Curry Corner', 'Curry and rice', 20)], 9: [(901, 'Party Platter', 'Trays for groups', 40)],
                  10: [(1001, 'Tea Stop', 'Tea and juice', 10)], 11: [(1111, 'Night Snack', 'Late-night bites', 25)]}


def v3_category_list():
    by_code = {cc: shops for _key, cc, _name, shops in CATS}
    by_code.update(V3_EXTRA_SHOPS)
    cats = {key: {'LargeCategoryName': 'Meal', 'CategoryList': {'TestingCategory': {
        'CategoryCode': '%02d' % cc, 'ShopList': {'Shop': Repeated(_v2_shop(*s) for s in by_code[cc])}}}}
        for key, cc in WIILINK_CATEGORIES}
    return multi_root_doc({'response': cats})


ACTIONS_V3 = dict(ACTIONS_V2, webApi_category_list=lambda: {'': v3_category_list()},
                  webApi_shop_list=lambda: {'': v3_category_list()})

# Revision 4: v3 reached the category screen, then shop_list failed (error
# 339293). The pinned Python server answers shop_list with the whole multi-root
# category list; WiiLink's live Go backend (Demae-Dominos main.go:
# NormalResponse("webApi_shop_list", categoryList), main_menu.go) answers with
# ONE category inside <response>, no Placeholder, then version and apiStatus.
# The fixture server picks files by areaCode only, so every category opens the
# Pizza shops (CategoryCode 01), as the Dominos backend always does.


def v4_shop_list():
    pizza = CATS[0]
    data = {pizza[0]: {'LargeCategoryName': 'Meal', 'CategoryList': {'TestingCategory': {
        'CategoryCode': '%02d' % pizza[1], 'ShopList': {'Shop': Repeated(_v2_shop(*s) for s in pizza[3])}}}}}
    return _x('response', dict(list(data.items()) + [('version', 1), ('apiStatus', {'code': 0})]))


ACTIONS_V4 = dict(ACTIONS_V3, webApi_shop_list=lambda: {'': v4_shop_list()})
MULTI_ROOT_V4 = MULTI_ROOT_V2 - {'webApi_shop_list'}

# Revision 5: v4 still failed on opening a category (339293 again). The pinned
# Python server answers webApi_area_shopinfo with an empty dict ("blank for
# now"); the live Go backend (main_menu.go shopInfo, MultipleRootNodes) lists the
# shops as <container><CategoryCode/><ShopList/></container> nodes plus one
# trailing placeholder container. v5 fills area_shopinfo that way.


def v5_area_shopinfo():
    by_code = {cc: shops for _key, cc, _name, shops in CATS}
    by_code.update(V3_EXTRA_SHOPS)
    codes = sorted(by_code)
    containers = Repeated({'CategoryCode': '%02d' % cc, 'ShopList': {'Shop': Repeated(_v2_shop(*s) for s in by_code[cc])}}
                          for cc in codes + codes[-1:])  # last one repeated as the skipped placeholder
    return multi_root_doc({'response': {'container': containers}})


ACTIONS_V5 = dict(ACTIONS_V4, webApi_area_shopinfo=lambda: {'': v5_area_shopinfo()})
MULTI_ROOT_V5 = MULTI_ROOT_V4 | {'webApi_area_shopinfo'}

# Revision 6: v5 still failed with the same 339293 on opening a category, so the
# list shape is not the cause. v6 copies the live Go backend's values too:
# homeCode 1 for every shop (v2-v5 used the shop code), minPrice as a 2-decimal
# string, and the Dominos-style lists (Pizza + Placeholder in category_list,
# container 01 + placeholder 02 in area_shopinfo, Pizza only in shop_list).


def _v6_shop(code, name, catch, wait):
    shop = _v2_shop(code, name, catch, wait)
    shop.update(homeCode=1, minPrice='10.00')
    return shop


def _v6_category(code):
    return {'LargeCategoryName': 'Meal', 'CategoryList': {'TestingCategory': {
        'CategoryCode': '%02d' % code, 'ShopList': {'Shop': Repeated(_v6_shop(*s) for s in CATS[0][3])}}}}


def v6_category_list():
    return multi_root_doc({'response': {'Pizza': _v6_category(1), 'Placeholder': _v6_category(2)}})


def v6_area_shopinfo():
    shops = lambda: {'Shop': Repeated(_v6_shop(*s) for s in CATS[0][3])}
    return multi_root_doc({'response': {'container': Repeated(
        [{'CategoryCode': '01', 'ShopList': shops()}, {'CategoryCode': '02', 'ShopList': shops()}])}})


def v6_shop_list():
    return _x('response', {'Pizza': _v6_category(1), 'version': 1, 'apiStatus': {'code': 0}})


ACTIONS_V6 = dict(ACTIONS_V5, webApi_category_list=lambda: {'': v6_category_list()},
                  webApi_area_shopinfo=lambda: {'': v6_area_shopinfo()},
                  webApi_shop_list=lambda: {'': v6_shop_list()})

# Revision 7 (wave 2, lead review of build-v4): the terms box (Title/00-2T_regulat1, 516 units, wbf1) wrapped the
# synthetic English mid-word ("No r / eal"). Korean cannot be served on this path: WiiLink's server and this feed
# are Shift-JIS without an XML declaration (references/food-server-*/helpers.py), Shift-JIS has no Hangul and the
# DOL carries no character-reference handling. v7 therefore breaks the same English at word boundaries (widths
# measured with kwce.food_textfit); everything else equals v6.
EULA_V7 = ('Food Channel local test build. Synthetic data only. No\n'
           'real orders are placed. Payment on delivery; no card\n'
           'or Wii Points.')


def v7_document_template():
    return response_doc({'container0': {'contents': EULA_V7},
                         'container1': {'contents': 'Local test build. No order is ever sent.'},
                         'container2': {'contents': 'Synthetic data only.'}})


ACTIONS_V7 = dict(ACTIONS_V6, webApi_document_template=lambda: {'': v7_document_template()})


def placeholder_jpg():
    """A tiny valid baseline JPEG (16x16 gray)."""
    # Minimal JPEG assembled once; content is a flat gray block.
    import io
    try:
        import sys
        sys.path.insert(0, str(ROOT / 'tools/channel-python'))
        from PIL import Image
        buf = io.BytesIO(); Image.new('RGB', (16, 16), (210, 210, 210)).save(buf, 'JPEG', quality=70)
        return buf.getvalue()
    except Exception:
        return None


def write_feed(feed: Path, revision: int = 1):
    actions = {1: ACTIONS, 2: ACTIONS_V2, 3: ACTIONS_V3, 4: ACTIONS_V4, 5: ACTIONS_V5, 6: ACTIONS_V6, 7: ACTIONS_V7}[revision]
    feed.mkdir(parents=True, exist_ok=True)
    nwapi = feed / 'nwapi'; nwapi.mkdir(exist_ok=True)
    files = []
    for action, fn in actions.items():
        for key, xml in fn().items():
            name = f'nwapi/{action}{("_" + key) if key else ""}.xml'
            data = xml.encode('shift-jis')
            (feed / name).write_bytes(data); files.append(name)
    img = feed / 'img'; img.mkdir(exist_ok=True)
    jpg = placeholder_jpg()
    if jpg:
        (img / 'placeholder.jpg').write_bytes(jpg); files.append('img/placeholder.jpg')
    manifest = dict(revision=revision, channel='food', local_only=True, synthetic=True,
                    served_actions=sorted(actions), blocked_actions=sorted(BLOCKED),
                    note='Browse chain only; order/cart/auth actions return 404 (ordering not served).',
                    data='fictional, ASCII/romaji (server path is Shift-JIS, no Hangul)', files=sorted(files))
    if revision >= 2:
        import hashlib
        manifest['serialization'] = ('pinned WiiLink food-server shape: apiStatus/version after the data '
                                     '(@response) or as trailing root nodes (@multiple_root_nodes), lxml pretty-print')
        manifest['sha256'] = {name: hashlib.sha256((feed / name).read_bytes()).hexdigest() for name in sorted(files)}
    (feed / 'fixture-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Write a numbered synthetic Food feed (create-once).')
    ap.add_argument('out', nargs='?', type=Path)
    ap.add_argument('--revision', type=int, choices=(1, 2, 3, 4, 5, 6, 7), default=1)
    args = ap.parse_args()
    out = args.out or ROOT / f'workspace/channels/food/local-feed-v{args.revision}'
    if args.out is None and out.exists():
        raise SystemExit('Existing numbered feed preserved: ' + str(out))
    m = write_feed(out, args.revision)
    print('feed revision', m['revision'], 'files', len(m['files']), 'served', len(m['served_actions']),
          'blocked', len(m['blocked_actions']))
