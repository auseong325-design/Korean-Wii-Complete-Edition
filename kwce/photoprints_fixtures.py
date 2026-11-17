"""Synthetic READ-ONLY local-feed responses for the Photo Prints Channel.

Shaped from the pinned public WiiLink24/cam-server response format
(statusCode/latestClientVersion envelope + key=value / key_N=value body). Only
the catalog operations the UI needs to open its product/notice screens are
served; every order/upload/payment operation is refused by the server, so this
module intentionally produces NO getOrderID / image-upload / order responses.
All data is fictional ASCII (kept ASCII so it never depends on channel-font
Hangul coverage). Nothing here accepts input.
"""
import hashlib

STATUS_OK=1000
# The two read-only operations served. Everything else -> 404 at the server.
READ_ONLY_OPERATIONS=('getItemInformation','getExemptionInformation')

ITEMS=[
    ("Photo Print","A simple print for anywhere.","Print responsibly.",1,10,10,100,"$","Preview only - ordering disabled"),
    ("Notebook","A simple notebook to treasure.","Print responsibly.",2,10,10,300,"$","Preview only - ordering disabled"),
    ("Photo Album","A fun album everyone will love.","Print responsibly.",2,10,10,500,"$","Preview only - ordering disabled"),
    ("Mii Card","As if you were on a business card.","Print responsibly.",3,1,1,200,"$","Preview only - ordering disabled"),
    ("Calendar","A calendar anyone can enjoy.","Print responsibly.",1,12,12,400,"$","Preview only - ordering disabled"),
    ("Business Card","The perfect business card.","Print responsibly.",3,1,1,250,"$","Preview only - ordering disabled"),
    ("Sample Item","Catalog preview entry.","Print responsibly.",1,10,10,100,"$","Preview only - ordering disabled"),
]


def _format(pairs):
    out=[]
    for key,value in pairs:
        if isinstance(value,list):
            for i,v in enumerate(value):out.append(f"{key}_{i+1}={v}")
        else:out.append(f"{key}={value}")
    return ("\n".join(out)+"\n").encode("ascii")


def get_item_information():
    code=[f"{i+1:05}" for i in range(len(ITEMS))]
    cols={"itemCode":code,"itemPriceCode":code,
        "itemName":[x[0] for x in ITEMS],"itemComment1":[x[1] for x in ITEMS],"itemComment2":[x[2] for x in ITEMS],
        "size":[x[3] for x in ITEMS],"imageCount":[x[4] for x in ITEMS],"pageCount":[x[5] for x in ITEMS],
        "price":[x[6] for x in ITEMS],"imageCountDisp":[x[4] for x in ITEMS],"pageCountDisp":[x[5] for x in ITEMS],
        "priceUnit":[x[7] for x in ITEMS],"delivery":[x[8] for x in ITEMS]}
    pairs=[("statusCode",STATUS_OK),("latestClientVersion","0x02"),("message",""),
        ("errorItems",[0]*len(ITEMS))]+list(cols.items())
    return _format(pairs)


def get_exemption_information():
    pairs=[("statusCode",STATUS_OK),("latestClientVersion","0x02"),("errorItems",[0,0,0,0]),("message",""),
        ("exemptionID","PREVIEW"),("exemptionTEXT","Local preview feed - catalog view only, ordering disabled.")]
    return _format(pairs)


def responses():
    return {"getItemInformation":get_item_information(),"getExemptionInformation":get_exemption_information()}


def manifest():
    data=responses()
    return dict(revision=1,local_only=True,synthetic=True,read_only=True,
        accepts_uploads=False,accepts_orders=False,
        operations=[dict(operation=op,file=f"op_{op}.bin",sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
                    for op,body in sorted(data.items())],
        refused_operations=["getOrderID","isAvailableOrderID","getServiceInformation","updateOrderInformation",
            "fixOrderInformation","noticeOrderFinish","getImageID","getAssets"],
        note="Review stops at product selection; starting an order (getOrderID) and all image uploads are refused.")
