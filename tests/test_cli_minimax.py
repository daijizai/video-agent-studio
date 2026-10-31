"""CLI to real loopback backend using temporary state and mocked provider execution."""
import contextlib,copy,io,json,os,subprocess,sys,tempfile,threading,unittest,warnings
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cli,generation_scope,providers,secret_store,server

class MiniMaxCLI(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.env=patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(self.root/'private'/'credentials.json')});self.env.start();self.addCleanup(self.env.stop)
  self.old_data=server.DATA;server.DATA=self.root/'data';server.DATA.mkdir();server.init();self.addCleanup(setattr,server,'DATA',self.old_data)
  self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=self.http.serve_forever,daemon=True).start();self.addCleanup(self.stop)
  self.url='http://127.0.0.1:'+str(self.http.server_port)
  self.transport=patch.object(providers,'transport',side_effect=AssertionError('no real provider transport'));self.transport.start();self.addCleanup(self.transport.stop)
  self.run_cli('projects','create','MiniMax CLI test')
 def stop(self):self.http.shutdown();self.http.server_close()
 def run_cli(self,*args,ok=True):
  result=subprocess.run([sys.executable,str(Path(cli.__file__)),'--url',self.url,*args],capture_output=True,text=True,timeout=15)
  self.assertEqual(result.returncode,0 if ok else 1,result.stderr)
  return json.loads(result.stdout if ok else result.stderr)['data' if ok else 'error']
 def configure(self,model='MiniMax-H3'):
  return self.run_cli('provider','configure','--provider','minimax','--model',model,'--resolution','768P')
 def segment(self):
  segment=self.run_cli('segments','create')['segment'];draft=self.root/'draft.json'
  draft.write_text(json.dumps({'name':'opening','duration':6,'material_video_prompt':'A robot slowly opens a door.','material_video_audio':False,'reference_asset_ids':[]}))
  self.run_cli('segments','update',segment['id'],'--file',str(draft));return segment['id']
 def approve(self,sid):
  p=self.run_cli('segments','preview',sid);self.run_cli('segments','approve',sid,'--fingerprint',p['fingerprint'],'--source','test human reviewed this exact preview');return p
 def budget(self,video='10'):
  self.run_cli('budgets','authorize','--image','0','--video',video,'--model','MiniMax-H3','--source','test human finite model budget')
 def test_model_configuration_variants_and_pause_unchanged(self):
  self.budget();scopes=generation_scope.read();scopes[str(server.read()['project_id'])]['paused']=True;generation_scope.path().write_text(json.dumps(scopes));before=generation_scope.path().read_bytes()
  for model in ('MiniMax-H3','MiniMax-H3-Highspeed','MiniMax-H3-Lite','MiniMax-H3-Max'):
   state=self.configure(model);self.assertEqual(state['settings']['minimax_model'],model);self.assertEqual(state['settings']['resolution'],'768P')
  self.assertEqual(before,generation_scope.path().read_bytes());self.assertTrue(generation_scope.is_paused(server.read()['project_id'],server.DATA/'studio.db'))
 def test_invalid_options_do_not_write_settings(self):
  original=copy.deepcopy(server.read()['settings'])
  for args in [('--model','invented'),('--model','MiniMax-H3-Lite','--resolution','2K'),('--resolution','720p'),('--audio',),('--no-audio',)]:
   self.run_cli('provider','configure','--provider','minimax',*args,ok=False)
  self.assertEqual(server.read()['settings'],original)
  state=self.run_cli('provider','configure','--provider','minimax');self.assertEqual(state['settings']['minimax_model'],'MiniMax-H3');self.assertEqual(state['settings']['resolution'],'768P')
 def test_secret_uses_hidden_prompt_and_private_backend_storage(self):
  output=io.StringIO();error=io.StringIO();value='offline-cli-minimax-key'
  with patch.object(sys,'argv',['cli.py','--url',self.url,'secret','--provider','minimax']),patch.object(sys.stdin,'isatty',return_value=True),patch.object(cli.getpass,'getpass',return_value=value),contextlib.redirect_stdout(output),contextlib.redirect_stderr(error):
   self.assertEqual(cli.main(),0)
  self.assertNotIn(value,output.getvalue()+error.getvalue());self.assertEqual(secret_store.get_key('MINIMAX_API_KEY'),value)
  self.assertEqual(secret_store.secret_path().stat().st_mode&0o777,0o600)
  self.assertEqual(secret_store.secret_path().parent.stat().st_mode&0o777,0o700)
  exported=self.run_cli('export');self.assertNotIn(value,json.dumps(exported));self.assertNotIn(value,json.dumps(self.run_cli('provider','status')))
 def test_secret_rejects_pipe_and_echo_fallback(self):
  self.assertIn('交互终端',self.run_cli('secret','--provider','minimax',ok=False));self.assertFalse(secret_store.secret_path().exists())
  def fallback(*args):warnings.warn('Cannot control echo on the terminal.',cli.getpass.GetPassWarning)
  output=io.StringIO();error=io.StringIO()
  with patch.object(sys,'argv',['cli.py','--url',self.url,'secret','--provider','minimax']),patch.object(sys.stdin,'isatty',return_value=True),patch.object(cli.getpass,'getpass',side_effect=fallback),contextlib.redirect_stdout(output),contextlib.redirect_stderr(error):self.assertEqual(cli.main(),1)
  self.assertFalse(secret_store.secret_path().exists())
 def test_segment_creation_preview_human_confirmation_submit_and_poll(self):
  self.configure();sid=self.segment();secret_store.write_key('MINIMAX_API_KEY','offline-cli-minimax-key');self.budget()
  self.assertEqual(self.run_cli('segments','get',sid)['name'],'opening');self.assertEqual(len(self.run_cli('segments','list')),1)
  with patch.object(providers.Provider,'submit',return_value='minimax-remote-id') as submit:
   self.run_cli('segments','submit',sid,ok=False);submit.assert_not_called()
   preview=self.approve(sid);self.assertFalse(preview['network_called']);self.assertEqual(preview['snapshot']['request']['model'],'MiniMax-H3');submit.assert_not_called()
   result=self.run_cli('segments','submit',sid);self.assertEqual(result['status'],'queued');self.assertEqual(submit.call_count,1)
   self.run_cli('segments','submit',sid,'--redo',ok=False);self.assertEqual(submit.call_count,1)
  tid=result['task_id'];self.assertEqual(len(self.run_cli('segments','tasks',sid)),1)
  with patch.object(providers.Provider,'status',return_value={'status':'running','video_url':None,'usage':{},'actual_cost_cny':None}) as status:
   self.run_cli('segments','status',tid);status.assert_called_once_with('minimax-remote-id')
   self.run_cli('tasks','status',tid);self.assertEqual(status.call_count,2)
  self.assertEqual(server.read()['tasks'][0]['provider'],'minimax')
  self.run_cli('projects','create','other');self.run_cli('segments','status',tid,ok=False);self.run_cli('segments','preview',sid,ok=False)
 def test_changed_model_invalidates_confirmation(self):
  self.configure();sid=self.segment();self.approve(sid);self.configure('MiniMax-H3-Lite')
  with patch.object(providers.Provider,'submit') as submit:
   self.run_cli('segments','submit',sid,ok=False);submit.assert_not_called()
  self.assertEqual(server.read()['tasks'],[])
 def test_pause_budget_and_unknown_guards_survive_cli(self):
  self.configure();sid=self.segment();self.approve(sid);secret_store.write_key('MINIMAX_API_KEY','offline-cli-minimax-key')
  with patch.object(providers.Provider,'submit') as submit:
   self.run_cli('segments','submit',sid,ok=False);submit.assert_not_called()
   self.budget('1');self.run_cli('segments','submit',sid,ok=False);submit.assert_not_called()
   self.budget('10');scopes=generation_scope.read();scopes[str(server.read()['project_id'])]['paused']=True;generation_scope.path().write_text(json.dumps(scopes))
   self.run_cli('segments','submit',sid,ok=False);submit.assert_not_called();self.assertEqual(server.read()['tasks'],[])
   scopes[str(server.read()['project_id'])]['paused']=False;generation_scope.path().write_text(json.dumps(scopes));submit.side_effect=TimeoutError('mock timeout')
   self.run_cli('segments','submit',sid,ok=False);self.assertEqual(submit.call_count,1)
   self.run_cli('segments','submit',sid,'--redo',ok=False);self.assertEqual(submit.call_count,1)
  task=server.read()['tasks'][0];self.assertEqual(task['status'],'unknown');self.assertEqual(task['estimate'],3)
 def test_read_only_list_and_explicit_initialization(self):
  before=server.read()['revision'];self.assertEqual(self.run_cli('segments','list'),[]);self.assertEqual(server.read()['revision'],before)
  self.assertEqual(self.run_cli('segments','init')['segments'],[]);self.assertEqual(self.run_cli('segments','list'),[])

if __name__=='__main__':unittest.main()
