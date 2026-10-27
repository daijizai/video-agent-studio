"""Local fixture-only accessible image preview integration; no model calls."""
import os,sys,tempfile,threading,shutil,zlib,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from playwright.sync_api import sync_playwright

def png(w,h,color):
 def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
 raw=b''.join(b'\0'+bytes(color)*w for _ in range(h))
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);shutil.copytree(server.ROOT/'static',root/'static');server.ROOT=root;server.DATA=root/'data';server.DATA.mkdir();os.environ['STUDIO_SECRET_FILE']=str(root/'private'/'credentials.json');server.init();assets=root/'assets'/'1';assets.mkdir(parents=True)
 for name,color in [('old',(160,30,30)),('current',(30,70,160)),('second',(30,130,80))]:(assets/(name+'.png')).write_bytes(png(1200,1800,color))
 s=server.read();s['title']='本地图片预览测试夹具';first,second=s['shots'][:2]
 first.update(storyboard_local='/media/1/current.png',storyboard_task_id='current-task');second.update(storyboard_local='/media/1/second.png',storyboard_task_id='second-task')
 s['image_tasks']=[{'id':'old-task','shot_id':first['id'],'status':'completed','provider_task_id':'old-test','content_revision':1,'estimate':0,'local_artifact':'/media/1/old.png'},{'id':'current-task','shot_id':first['id'],'status':'completed','provider_task_id':'current-test','content_revision':2,'estimate':0,'local_artifact':'/media/1/current.png'},{'id':'second-task','shot_id':second['id'],'status':'completed','provider_task_id':'second-test','content_revision':3,'estimate':0,'local_artifact':'/media/1/second.png'}];server.save(s)
 http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   b=p.chromium.launch();page=b.new_page(viewport={'width':1440,'height':1000});errors=[];calls=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:calls.append(r.url) if '/submit' in r.url else None)
   page.clock.install()
   page.goto('http://127.0.0.1:'+str(http.server_port)+'/#shots');opener=page.locator('[data-shot-lightbox]').first;opener.wait_for();page.locator('.shot-details').first.locator('summary').first.click();page.locator('#ip0').fill('Unsaved details retained')
   opener.click();dialog=page.get_by_role('dialog');dialog.wait_for();page.wait_for_function('document.querySelector(".image-lightbox img").naturalWidth===1200');assert '当前图' in page.locator('#lightbox-identity').inner_text();assert page.locator('.image-lightbox img').get_attribute('src')=='/media/1/current.png'
   page.locator('#lightbox-original').click();assert page.locator('.image-lightbox img').evaluate('(i)=>Math.round(i.getBoundingClientRect().width)')==1200
   page.locator('#lightbox-fit').click();page.locator('#lightbox-in').click();assert page.locator('#lightbox-scale').inner_text()=='125%'
   page.locator('.lightbox-viewer').hover();page.mouse.wheel(0,-100);assert int(page.locator('#lightbox-scale').inner_text().rstrip('%'))>125
   page.locator('#lightbox-previous').click();assert '历史图' in page.locator('#lightbox-identity').inner_text();assert page.locator('.image-lightbox img').get_attribute('src')=='/media/1/old.png'
   page.locator('#lightbox-next').click();assert '当前图' in page.locator('#lightbox-identity').inner_text();page.keyboard.press('Escape');assert page.get_by_role('dialog').count()==0
   assert page.locator('#ip0').input_value()=='Unsaved details retained';assert page.locator('.shot-details').first.evaluate('(e)=>e.open');assert page.evaluate('document.activeElement.dataset.shotLightbox')==first['id']
   opener.click();page.locator('#lightbox-choice').select_option('2');assert page.locator('.image-lightbox img').get_attribute('src')=='/media/1/second.png';page.locator('#lightbox-close').click();assert page.get_by_role('dialog').count()==0
   opener.click();page.mouse.click(1,1);assert page.get_by_role('dialog').count()==0
   page.set_viewport_size({'width':375,'height':812});opener.click();page.wait_for_function('document.querySelector(".image-lightbox img").naturalWidth===1200');assert page.locator('.image-lightbox').evaluate('(e)=>e.getBoundingClientRect().width<=innerWidth');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   page.locator('.lightbox-viewer').evaluate('''(el)=>{const t=(id,x)=>new Touch({identifier:id,target:el,clientX:x,clientY:100});el.dispatchEvent(new TouchEvent('touchstart',{touches:[t(1,50),t(2,100)],bubbles:true,cancelable:true}));el.dispatchEvent(new TouchEvent('touchmove',{touches:[t(1,25),t(2,125)],bubbles:true,cancelable:true}));el.dispatchEvent(new TouchEvent('touchend',{touches:[],bubbles:true}));}''');assert int(page.locator('#lightbox-scale').inner_text().rstrip('%'))>=190
   for _ in range(15):page.keyboard.press('Tab');assert page.evaluate('document.querySelector(".image-lightbox").contains(document.activeElement)')
   page.keyboard.press('Escape');opener.click()
   (assets/'newer.png').write_bytes(png(1200,1800,(100,80,40)));fresh=server.read();fresh['shots'][0]['storyboard_local']='/media/1/newer.png';fresh['shots'][0]['storyboard_task_id']='newer-task';fresh['image_tasks'].append({'id':'newer-task','shot_id':first['id'],'status':'completed','provider_task_id':'newer-test','content_revision':4,'estimate':0,'local_artifact':'/media/1/newer.png'});server.save(fresh)
   page.clock.fast_forward(9000);page.wait_for_function('document.querySelector("#lightbox-identity").textContent.includes("历史图")');assert page.locator('.image-lightbox img').get_attribute('src')=='/media/1/current.png';page.keyboard.press('Escape')
   page.get_by_role('button',name='＋ 新建项目',exact=True).click();page.get_by_label('项目名称',exact=True).fill('隔离项目B');page.get_by_role('button',name='创建项目',exact=True).click();page.wait_for_function('document.querySelectorAll(".shot").length===0');assert page.get_by_role('dialog').count()==0;assert page.locator('[data-shot-lightbox]').count()==0
   assert not calls,calls;assert not errors,errors;b.close();print('PASS: current/history identity, original/fit/button/wheel zoom, Esc/button/backdrop close, focus trap/restore, retained edits/details, mobile layout and project isolation; no generation')
 finally:http.shutdown();http.server_close()
