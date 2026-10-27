import json,os,subprocess,sys,tempfile,threading,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
class CLIIntegration(unittest.TestCase):
    def test_cli_uses_backend_and_preserves_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous=server.DATA;server.DATA=Path(tmp)/'db';server.DATA.mkdir();server.init()
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            def cli(*args,ok=True):
                run=subprocess.run([sys.executable,str(server.ROOT/'cli.py'),'--url','http://127.0.0.1:'+str(http.server_port),*args],capture_output=True,text=True)
                self.assertEqual(run.returncode,0 if ok else 1,run.stderr)
                return json.loads(run.stdout if ok else run.stderr)
            try:
                self.assertTrue(cli('projects','list')['ok']);created=cli('projects','create','CLI film')['data'];pid=created['project_id']
                script=Path(tmp)/'script.txt';script.write_text('CLI script isolated from demo')
                cli('script','set','--file',str(script));self.assertEqual(cli('script','get')['data']['script'],script.read_text())
                char=Path(tmp)/'character.json';char.write_text(json.dumps({'name':'A','notes':'fixed outfit'}));cli('characters','add','--file',str(char));self.assertEqual(len(cli('characters','list')['data']),1)
                shot=Path(tmp)/'shot.json';shot.write_text(json.dumps({'name':'A walks','prompt':'A in fog','duration':5,'estimate':3}))
                cli('shots','add','--file',str(shot));sid=cli('shots','list')['data'][0]['id'];cli('budget','10')
                self.assertEqual(cli('tasks','preview',sid)['data']['payload']['model'],'wan3.0-video')
                cli('shots','approve',sid);self.assertTrue(cli('shots','list')['data'][0]['approved'])
                cli('tasks','submit',sid,ok=False);self.assertEqual(server.read()['tasks'],[])
                shot.write_text(json.dumps({'prompt':'changed scene'}));cli('shots','update',sid,'--file',str(shot));self.assertFalse(cli('shots','list')['data'][0]['approved'])
                review=Path(tmp)/'review.txt';review.write_text('identity check pending');cli('shots','review',sid,'--file',str(review))
                self.assertEqual(cli('shots','list')['data'][0]['review'],review.read_text())
                cli('projects','select','1');self.assertNotEqual(cli('script','get')['data']['script'],script.read_text())
                cli('projects','select',str(pid));self.assertEqual(cli('export')['data']['title'],'CLI film')
                cli('tasks','status','missing',ok=False);cli('secret','--provider','wan3',ok=False)
            finally:http.shutdown();http.server_close();server.DATA=previous
