"""Korean TV Guide manual with local navigation and no external links/images."""
import html,json
from .channels import ROOT,ChannelArchive

def korean_manual(content):
    config=json.loads((ROOT/'configs/tvguide-manual-v1-ko.json').read_text(encoding='utf-8'));pages=config['pages']
    if len(pages)!=18:raise ValueError('TV manual page coverage')
    outer=ChannelArchive(content);archive=ChannelArchive(outer.get('JPN.arc'));changed=[]
    def page(title,body):
        return ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"><html lang="ko"><head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8"><title>'+html.escape(title)+'</title><style type="text/css">body{font-size:16px;line-height:1.55;background:#fff;color:#222;margin:14px}h1{font-size:22px;color:#087eac}h2{font-size:18px;background:#e4f4fa;padding:5px}a{color:#087eac}p{margin:10px 0}.nav{padding:10px;background:#e4f4fa}</style></head><body>'+body+'</body></html>').encode('utf-8')
    def put(name,payload):
        nonlocal archive
        archive=ChannelArchive(archive.replace(name,payload));changed.append(name)
    links=''.join('<li><a target="mainFrame" href="page_%02d/page_%02d.html">%d. %s</a></li>'%(i,i,i,html.escape(p['title']))for i,p in enumerate(pages,1))
    put('html/index_mainFrame.html',page('TV 가이드 설명서','<h1>TV 가이드 채널 설명서</h1><p>한국어 로컬 시험본 · 실제 서비스 지원은 별도 확인이 필요합니다.</p><ol>'+links+'</ol>'))
    put('html/index_topFrame.html',page('TV 가이드','<h1>Wii · TV 가이드 채널</h1>'))
    for name in ['html/index_contentsFrame.html','html/index_bottomFrame.html']:
        put(name,page('목차','<a target="mainFrame" href="index_mainFrame.html">설명서 목차</a>'))
    for i,p in enumerate(pages,1):
        body='<h1>%d. %s</h1>'%(i,html.escape(p['title']))
        for heading,text in p['sections']:body+='<h2>'+html.escape(heading)+'</h2><p>'+html.escape(text)+'</p>'
        body+='<p class="nav"><a href="../index_mainFrame.html">목차</a>'
        if i>1:body+=' | <a href="../page_%02d/page_%02d.html">이전</a>'%(i-1,i-1)
        if i<18:body+=' | <a href="../page_%02d/page_%02d.html">다음</a>'%(i+1,i+1)
        body+='</p>';put('html/page_%02d/page_%02d.html'%(i,i),page(p['title'],body))
    # Keep the original frameset entry and every asset, but only local Korean
    # HTML is linked by the rewritten pages. No untranslated screenshot captions.
    for name in changed:
        raw=archive.get(name)
        if any(bad in raw for bad in [b'<script',b'<img',b'https://',b'http://wiilink',b'http://www.nintendo']):raise ValueError('TV manual external/unused content')
    return outer.replace('JPN.arc',archive.compact()),dict(pages=18,html_files=len(changed),local_navigation_only=True,example_screenshots_replaced_with_text=True)
