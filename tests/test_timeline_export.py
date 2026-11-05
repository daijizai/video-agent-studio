import hashlib,io,subprocess,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import timeline_export,media_files
class TimelineExportTest(unittest.TestCase):
 def test_trim_concat_and_preserve_sources(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);folder=root/'assets'/'2';folder.mkdir(parents=True)
   tasks=[]
   for n,color in [('a','red'),('b','blue')]:
    p=folder/(n+'.mp4');subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'testsrc2=s=64x64:r=24:d=2,eq=brightness={0.1 if color=="red" else -0.1}','-c:v','libx264','-pix_fmt','yuv420p','-y',str(p)],check=True)
    tasks.append({'id':n,'status':'completed','review_status':'accepted','local_video':f'/media/2/{n}.mp4','accepted_video_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
   state={'project_id':2,'tasks':tasks}
   with self.assertRaises(ValueError):timeline_export.start(state,root,[{'task_id':'b','start':0,'end':3}])
   original=[(folder/(n+'.mp4')).read_bytes() for n in ('a','b')]
   job=timeline_export.start(state,root,[{'task_id':'a','start':0.5,'end':1.5},{'task_id':'b','start':0,'end':1}])
   for _ in range(100):
    j=timeline_export.status(2,job['id'])
    if j['status']!='running':break
    time.sleep(.05)
   self.assertEqual(j['status'],'completed',j);out=folder/Path(j['url']).name
   self.assertAlmostEqual(media_files.probe_video(out)['duration'],2,delta=.25)
   def hashes(file,filter_expr=None):
    cmd=['ffmpeg','-v','error','-i',str(file)]
    if filter_expr:cmd+=['-vf',filter_expr]
    cmd+=['-f','framemd5','-']
    text=subprocess.run(cmd,check=True,capture_output=True,text=True).stdout
    return [line.rsplit(',',1)[-1].strip() for line in text.splitlines() if line and not line.startswith('#')]
   expected=hashes(folder/'a.mp4','trim=start=0.5:end=1.5,setpts=PTS-STARTPTS')+hashes(folder/'b.mp4','trim=start=0:end=1,setpts=PTS-STARTPTS')
   self.assertEqual(hashes(out),expected,'导出每一帧的解码像素必须与裁剪后的原帧一致')
   self.assertEqual(original,[(folder/(n+'.mp4')).read_bytes() for n in ('a','b')])
   state['tasks'][1]['review_status']='rejected_quality'
   with self.assertRaises(ValueError):timeline_export.start(state,root,[{'task_id':'b','start':0,'end':1}])
 def test_pending_clip_exports_with_selected_music(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);folder=root/'assets'/'2';folder.mkdir(parents=True)
   video=folder/'clip.mp4';music=folder/'sound.mp4'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=64x64:r=24:d=2','-c:v','libx264','-pix_fmt','yuv420p','-y',str(video)],check=True)
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=2','-c:a','aac','-y',str(music)],check=True)
   state={'project_id':2,'tasks':[{'id':'clip','status':'completed','review_status':'pending','local_video':'/media/2/clip.mp4'}],'project_brief':{'timeline_audio':{'url':'/media/2/sound.mp4'}}}
   job=timeline_export.start(state,root,[{'task_id':'clip','start':.5,'end':1.5}],True)
   for _ in range(100):
    result=timeline_export.status(2,job['id'])
    if result['status']!='running':break
    time.sleep(.05)
   self.assertEqual(result['status'],'completed',result)
   info=media_files.probe_video(folder/Path(result['url']).name)
   self.assertTrue(info['has_audio']);self.assertAlmostEqual(info['duration'],1,delta=.2)

 def test_stacked_export_uses_uploaded_picture_and_project_soundtrack(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);folder=root/'assets'/'2';folder.mkdir(parents=True)
   lower=folder/'clip.mp4';upper=root/'reference.mp4';music=folder/'sound.mp4'
   for path,video in [(lower,'color=green:s=160x90:r=24:d=1'),(upper,'color=red:s=160x120:r=30:d=2')]:
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',video,'-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True)
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=1','-c:a','aac',str(music)],check=True)
   with self.assertRaises(ValueError):timeline_export.import_upper(root,2,'bad.mp4',io.BytesIO(b'no'),2)
   self.assertFalse(list(folder.glob('upper_*')))
   with upper.open('rb') as stream:
    imported,_=timeline_export.import_upper(root,2,upper.name,stream,upper.stat().st_size)
   state={'project_id':2,'tasks':[{'id':'clip','status':'completed','local_video':'/media/2/clip.mp4'}],
          'project_brief':{'timeline_audio':{'url':'/media/2/sound.mp4'},'timeline_upper':imported}}
   clips=[{'task_id':'clip','start':0,'end':1}]
   with self.assertRaises(ValueError):timeline_export.start(state,root,clips,True,{'url':imported['url'].replace('/2/','/3/'),'start':0})
   with self.assertRaises(ValueError):timeline_export.start(state,root,clips,True,{'url':imported['url'],'start':1.5})
   job=timeline_export.start(state,root,clips,True,{'url':imported['url'],'start':.5})
   for _ in range(100):
    result=timeline_export.status(2,job['id'])
    if result['status']!='running':break
    time.sleep(.05)
   self.assertEqual(result['status'],'completed',result)
   out=folder/Path(result['url']).name
   info=media_files.probe_video(out)
   self.assertEqual((info['video']['width'],info['video']['height']), (1080,1440))
   self.assertTrue(info['has_audio'])
   self.assertAlmostEqual(info['duration'],1,delta=.05)
   frame=subprocess.check_output(['ffmpeg','-v','error','-i',str(out),'-vf','crop=2:1440:539:0,scale=2:1440','-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'])
   def pixel(row):return frame[row*6:row*6+3]
   for row in (0,83,692,731,1340,1439):
    self.assertLess(max(pixel(row)),10,'画面顶底和中间应为黑色留白')
   for row in (84,691):
    red,green,_=pixel(row)
    self.assertGreater(red,green+70,'上半屏应为608行参考视频')
   for row in (732,1339):
    red,green,_=pixel(row)
    self.assertGreater(green,red+40,'下半屏应为608行片段画面')

if __name__=='__main__':unittest.main()
