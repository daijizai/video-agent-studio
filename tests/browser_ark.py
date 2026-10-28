"""Isolated Ark UI integration: mock sync image only, no real model calls."""
import os,sys,tempfile,threading,shutil,struct,zlib,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server,ark_provider,secret_store,generation_scope
from playwright.sync_api import sync_playwright

def png():
 def chunk(tag,data):return struct.pack('!I',len(data))+tag+data+struct.pack('!I',zlib.crc32(tag+data)&0xffffffff)
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00'))+chunk(b'IEND',b'')

with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);shutil.copytree(server.ROOT/'static',root/'static');server.ROOT=root;server.DATA=root/'data';server.DATA.mkdir();os.environ['STUDIO_SECRET_FILE']=str(root/'private'/'credentials.json');server.init()
 secret_store.write_key('ARK_API_KEY','fake-browser-ark-only')
 generation_scope.authorize_budgets(1,server.DATA/'studio.db',1,20,'fixture explicitly authorizes mock models',1,models=[ark_provider.IMAGE_MODEL,ark_provider.VIDEO_MODEL])
 scope=generation_scope.read();scope['1']['paused']=True;generation_scope.path().write_text(json.dumps(scope))
 def cache(pid,tid,url):
  p=root/'assets'/str(pid)/(tid+'.png');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(png());return '/media/'+str(pid)+'/'+tid+'.png'
 result={'status':'completed','image_urls':['https://example.byteimg.com/fixture.png'],'usage':{'generated_images':1},'actual_cost_cny':None}
 http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
 try:
  with patch('providers.transport',side_effect=AssertionError('real model calls forbidden')),patch.object(ark_provider.SeedreamProvider,'submit',return_value=result) as submit,patch.object(server,'cache_image',side_effect=cache),sync_playwright() as p:
   browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto('http://127.0.0.1:'+str(http.server_port)+'/#tools');page.locator('#provider-choice').wait_for()
   page.locator('#provider-choice').select_option('seedance25');page.locator('#image-default-model').select_option(ark_provider.IMAGE_MODEL)
   page.get_by_role('button',name='保存供应商配置',exact=True).click();page.wait_for_function("document.querySelector('#provider-choice')?.value==='seedance25'")
   page.reload();page.locator('#provider-choice').wait_for();assert page.locator('#provider-choice').input_value()=='seedance25';assert page.locator('#image-default-model').input_value()==ark_provider.IMAGE_MODEL
   assert generation_scope.is_paused(1,server.DATA/'studio.db')
   page.get_by_role('link',name='04 分镜工作台',exact=True).click();page.locator('[data-image-preview]').first.click();page.wait_for_function("document.querySelector('[data-image-result]')?.textContent.includes('doubao-seedream-5-0-flash-260915')")
   assert page.locator('[data-image-generate]').first.is_disabled();submit.assert_not_called()
   # Resume only this artificial fixture, never the real project.
   scope=generation_scope.read();scope['1']['paused']=False;generation_scope.path().write_text(json.dumps(scope));page.reload();page.locator('[data-image-generate]').first.wait_for();page.locator('[data-image-generate]').first.click()
   page.wait_for_function("document.querySelector('[data-image-art] img')!==null")
   assert submit.call_count==1;assert '图片已保存' in page.locator('[data-image-poll]').first.inner_text();assert page.locator('[data-image-poll]').first.is_disabled()
   assert not server.read()['shots'][0]['approved'];assert server.read()['image_tasks'][-1]['provider']=='seedream'
   page.get_by_role('link',name='05 视频制作与预览',exact=True).click();page.locator('#video-stage .video-empty').wait_for();assert page.locator('video').count()==0
   page.get_by_role('button',name='＋ 新建项目',exact=True).click();page.get_by_label('项目名称',exact=True).fill('Ark isolated project');page.get_by_role('button',name='创建项目',exact=True).click()
   page.wait_for_function("document.querySelector('#project-select option:checked')?.textContent.includes('Ark isolated project')")
   assert server.read()['image_tasks']==[];assert submit.call_count==1
   for w in [375,768,1440]:page.set_viewport_size({'width':w,'height':900});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
   assert not errors,errors;browser.close();print('PASS: Ark model selection, pause retained, offline preview, sync result image, no false approval, project isolation, responsive UI; no real inference')
 finally:http.shutdown();http.server_close()
