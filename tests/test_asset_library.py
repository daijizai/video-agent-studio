import base64
import copy
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

import asset_library as lib


def png(width=384, height=384, color=(80,100,120)):
    def chunk(kind, body):return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
    raw=(b'\0'+bytes(color)*width)*height
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')


class AssetFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.database=self.root/'studio.db'
        self.initial={'title':'测试故事','script':'记者拿着钥匙走进值班室。','continuity':'钥匙无钥匙圈。','project_brief':'',
            'characters':[{'id':'c1','name':'记者','notes':'短发，灰夹克','role':'主角','version':3,'color':'#729c9b'}],
            'shots':[{'id':'s1','name':'发现钥匙','prompt':'video','image_prompt':'static','approved':True,'duration':5,'estimate':0}],
            'image_tasks':[],'tasks':[],'settings':{'image_model':'qwen-image-3.0-pro'},'budget':0}
        with sqlite3.connect(self.database) as con:
            con.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)')
            con.execute('CREATE TABLE revisions(id INTEGER PRIMARY KEY,created TEXT DEFAULT CURRENT_TIMESTAMP,body TEXT,project_id INTEGER)')
            con.execute('CREATE TABLE workspace(id INTEGER PRIMARY KEY,current_project INTEGER)')
            con.execute('INSERT INTO workspace VALUES(1,1)')
            for pid in [1,2]:con.execute('INSERT INTO state VALUES(?,?)',(pid,json.dumps(self.initial,ensure_ascii=False)))
        self.service=lib.AssetLibrary(self.root,self.database)

    def tearDown(self):self.tmp.cleanup()

    def state(self,pid=1):
        with self.service._connect() as con:return self.service._load(con,pid,require_selected=False)

    def action(self,action,**payload):
        return self.service.mutate(1,self.service.catalog(1)['revision'],action,payload)

    def create(self,kind='object',name='钥匙'):
        return self.action('create',kind=kind,name=name,summary='黄铜，无钥匙圈')['assets'][-1]

    def upload(self,asset,tag='main',data=None):
        self.action('upload',asset_id=asset['id'],view_tag=tag,filename='image.png',base64=base64.b64encode(data or png()).decode())
        return next(a for a in self.service.catalog(1)['assets'] if a['id']==asset['id'])


class AssetTests(AssetFixture):
    def test_legacy_read_is_no_migration_and_only_two_types(self):
        catalog=self.service.catalog(1);self.assertEqual(len(catalog['assets']),1)
        role=catalog['assets'][0];self.assertEqual(role['kind'],'character');self.assertEqual(role['latest_version'],3)
        self.assertEqual(role['versions'][0]['summary'],'短发，灰夹克');self.assertEqual(role['versions'][0]['views'],[])
        self.assertEqual(self.state()['characters'],self.initial['characters']);self.assertNotIn('material_assets',self.state())
        self.assertEqual(catalog['revision'],0)
        with self.assertRaises(ValueError):self.create('scene')

    def test_import_version_adopt_history_and_original_are_immutable(self):
        asset=self.create();first=copy.deepcopy(asset['versions'][0])
        asset=self.upload(asset);version=asset['versions'][-1];view=version['views'][0]
        self.assertEqual(asset['adopted_version'],None);self.assertEqual(asset['versions'][0],first)
        self.assertEqual(self.service.media(1,view['url'])[0],png())
        self.action('adopt',asset_id=asset['id'],version=2)
        asset=self.upload(asset,data=png(color=(1,2,3)))
        self.assertEqual(asset['adopted_version'],2);self.assertEqual(asset['versions'][1]['views'][0],view)
        self.action('unadopt',asset_id=asset['id'],version=2)
        reloaded=lib.AssetLibrary(self.root,self.database).catalog(1)['assets'][-1]
        self.assertIsNone(reloaded['adopted_version']);self.assertEqual(len(reloaded['versions']),3)

    def test_reference_is_pinned_and_candidate_or_adoption_does_not_replace_it(self):
        asset=self.upload(self.create());view=asset['versions'][-1]['views'][0]
        self.action('adopt',asset_id=asset['id'],version=2)
        self.action('bind',shot_id='s1',asset_id=asset['id'],version=2,view_ids=[view['id']])
        shot=self.state()['shots'][0];self.assertFalse(shot['approved']);record=lib.record_binding(shot)
        pinned=copy.deepcopy(shot['asset_references'])
        asset=self.upload(asset,data=png(color=(10,20,30)))
        self.action('adopt',asset_id=asset['id'],version=3)
        self.assertEqual(self.state()['shots'][0]['asset_references'],pinned)
        self.assertTrue(lib.valid_binding(record,self.state()['shots'][0]))
        self.action('unbind',shot_id='s1',asset_id=asset['id'])
        self.assertFalse(lib.valid_binding(record,self.state()['shots'][0]))

    def test_unadopted_candidate_does_not_change_characters_or_shot_approval(self):
        role=self.service.catalog(1)['assets'][0]
        self.action('edit',asset_id=role['id'],name='新名字',summary='新衣服',variant='雨衣')
        self.upload(role,'portrait')
        self.assertEqual(self.state()['characters'],self.initial['characters']);self.assertTrue(self.state()['shots'][0]['approved'])
        self.action('adopt',asset_id=role['id'],version=5)
        self.assertEqual(self.state()['characters'][0]['name'],'新名字')
        self.assertEqual(self.state()['characters'][0]['version'],4)

    def test_safe_project_existing_import_does_not_scan_or_accept_paths(self):
        folder=self.root/'assets'/'1';folder.mkdir(parents=True);(folder/'existing.png').write_bytes(png())
        with self.service._connect() as con:
            state=self.initial.copy();state['shots']=copy.deepcopy(state['shots']);state['shots'][0]['storyboard_local']='/media/1/existing.png'
            con.execute('UPDATE state SET body=? WHERE id=1',(json.dumps(state),))
        source=self.service.catalog(1)['sources'][0];asset=self.create()
        self.action('import-existing',asset_id=asset['id'],view_tag='main',source_id=source['source_id'])
        with self.assertRaises(ValueError):self.action('import-existing',asset_id=asset['id'],view_tag='main',source_id='../../private')
        url=self.service.catalog(1)['assets'][-1]['versions'][-1]['views'][0]['url']
        with self.assertRaises(ValueError):self.service.media(2,url)
        with self.assertRaises(ValueError):self.service.media(1,'/asset-media/1/../../secret.png')
        with self.service._connect() as con:con.execute('UPDATE workspace SET current_project=2')
        with self.assertRaises(ValueError):self.service.media(1,url)

    def test_symlinks_tampering_stale_revision_and_invalid_data_are_rejected(self):
        asset=self.upload(self.create());view=asset['versions'][-1]['views'][0];file=self.service._file(1,view['url'])
        file.write_bytes(png(color=(1,1,1)))
        with self.assertRaises(ValueError):self.action('adopt',asset_id=asset['id'],version=2)
        file.unlink();outside=self.root/'outside.png';outside.write_bytes(png());file.symlink_to(outside)
        with self.assertRaises(ValueError):self.service.media(1,view['url'])
        with self.assertRaises(ValueError):self.service.mutate(1,0,'create',{'kind':'object','name':'过期'})
        for data in [b'<svg/>',png()[:-4],b'x'*(lib.MAX_BYTES+1)]:
            with self.assertRaises(ValueError):lib.inspect_image(data)
        with self.assertRaises(ValueError):lib.inspect_image(png(),'../../image.png')
        with self.assertRaises(ValueError):lib.inspect_image(png(),'image.jpg')
        with self.assertRaises(ValueError):lib.inspect_image(png(9000,1))

    def test_internal_refs_require_new_binding(self):
        self.assertTrue(lib.valid_binding({},{}));self.assertFalse(lib.valid_binding({}, {'asset_references':[{'asset_id':'x'}]}))

    def test_new_master_or_appearance_never_splices_old_alternate_views(self):
        asset=self.upload(self.create());asset=self.upload(asset,tag='side')
        self.assertEqual(len(asset['versions'][-1]['views']),2)
        self.action('adopt',asset_id=asset['id'],version=3)
        asset=self.upload(asset,data=png(color=(1,2,3)))
        self.assertEqual(len(asset['versions'][-1]['views']),1)
        self.assertEqual(len(asset['versions'][2]['views']),2)
        self.assertEqual(asset['adopted_version'],3)
        self.action('edit',asset_id=asset['id'],summary='改为银色新款')
        asset=self.service.catalog(1)['assets'][-1]
        self.assertEqual(asset['versions'][-1]['views'],[])
        self.assertEqual(asset['adopted_version'],3)

    def test_story_inventory_is_deterministic_and_objects_remain_independent(self):
        proposed=self.service.propose(1);self.assertFalse(proposed['network_called'])
        self.assertEqual([s['name'] for s in proposed['items']],['钥匙'])
        self.action('organize',names=['钥匙'])
        self.assertEqual(self.service.propose(1)['items'],[])
        role=self.service.catalog(1)['assets'][0];obj=self.service.catalog(1)['assets'][-1]
        self.action('edit',asset_id=obj['id'],related_asset_ids=[role['id']])
        current=self.service.catalog(1)['assets'][-1]
        self.assertEqual(current['kind'],'object');self.assertNotIn('holder',current['versions'][-1])

    @unittest.skipUnless(shutil.which('ffmpeg'),'existing FFmpeg needed for raster decoder fixtures')
    def test_jpeg_and_webp_pixels_are_decoded_not_only_header_checked(self):
        for encoder,format,filename in [('mjpeg','image2pipe','image.jpg'),('libwebp','webp','image.webp')]:
            result=subprocess.run([shutil.which('ffmpeg'),'-v','error','-f','image2pipe','-c:v','png','-i','pipe:0',
                '-frames:v','1','-c:v',encoder,'-f',format,'pipe:1'],input=png(),capture_output=True,timeout=10)
            if result.returncode:self.skipTest('fixture encoder unavailable')
            info=lib.inspect_image(result.stdout,filename);self.assertEqual((info['width'],info['height']),(384,384))
            with self.assertRaises(ValueError):lib.inspect_image(result.stdout[:-10],filename)


if __name__=='__main__':unittest.main()
