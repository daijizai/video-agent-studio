import contextlib, io, json, os, stat, tempfile, unittest, sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import secret_store, providers
class SecretIsolationTests(unittest.TestCase):
    def test_external_permissions_and_redaction(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(Path(tmp)/'private'/'credentials.json')}):
            token='fake-private-credential-for-unit-test'
            output=io.StringIO()
            with contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):secret_store.write_key('WAN3_API_KEY',token)
            path=secret_store.secret_path()
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode),0o700)
            self.assertNotIn(token,output.getvalue());self.assertEqual(secret_store.get_key('WAN3_API_KEY'),token)
            self.assertNotIn(token,json.dumps(providers.config_status()))
            self.assertEqual(secret_store.redact({'message':token,'nested':[token]}),{'message':'[REDACTED]','nested':['[REDACTED]']})
    def test_repository_path_rejected(self):
        with patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(secret_store.ROOT/'.env')}):
            with self.assertRaises(ValueError):secret_store.write_key('WAN3_API_KEY','fake-test-credential')
    def test_transport_error_does_not_echo_secret(self):
        token='fake-private-credential-for-unit-test'
        with patch('urllib.request.OpenerDirector.open',side_effect=RuntimeError(token)):
            try:providers.transport('GET','https://example.com',{'Authorization':'Bearer '+token})
            except RuntimeError as error:self.assertNotIn(token,str(error))
