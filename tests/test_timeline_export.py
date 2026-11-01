import hashlib,subprocess,sys,tempfile,time,unittest
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
if __name__=='__main__':unittest.main()
