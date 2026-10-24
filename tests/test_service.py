"""Exercise owner permissions, persistence, conflict handling and API validation."""
import importlib.util
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

spec = importlib.util.spec_from_file_location('personal_review_server', Path(__file__).resolve().parents[1] / 'scripts' / 'serve.py')
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class ReviewServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = service.ThreadingHTTPServer(('127.0.0.1', 0), service.Handler)
        self.server.db_path = Path(self.tmp.name) / 'reviews.sqlite3'
        self.server.place_ids = {'test-place'}
        self.server.secure_cookie = False
        self.server.failures = {}
        service.connect(self.server.db_path).close()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ''

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.tmp.cleanup()

    def call(self, path, method='GET', body=None, headers=None):
        connection = HTTPConnection(*self.server.server_address)
        combined = {'Content-Type':'application/json','X-Personal-Review':'1'}
        if self.cookie:
            combined['Cookie'] = self.cookie
        combined.update(headers or {})
        connection.request(method, path, json.dumps(body) if body is not None else None, combined)
        response = connection.getresponse()
        cookie = response.getheader('Set-Cookie')
        if cookie:
            self.cookie = cookie.split(';')[0]
        status, raw = response.status, response.read()
        connection.close()
        return status, json.loads(raw)

    def login(self):
        status, payload = self.call('/api/session','POST',{'setup':True,'password':'test-owner-password'})
        self.assertEqual(status,200)
        self.assertTrue(payload['owner'])

    def test_public_read_owner_only_write_and_logout(self):
        self.assertEqual(self.call('/api/reviews')[0],200)
        self.assertEqual(self.call('/api/reviews/test-place','PUT',{'rating':4})[0],401)
        self.assertEqual(self.call('/api/export')[0],401)
        self.login()
        status, payload = self.call('/api/reviews/test-place','PUT',{'rating':4,'comment':'还会再来。','revision':0,'visitDate':'2026-10-20','revisit':True})
        self.assertEqual(status,200)
        self.assertEqual(payload['review']['revision'],1)
        with service.connect(self.server.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM reviews').fetchone()[0],1)
        self.assertEqual(self.call('/api/reviews/test-place','PUT',{'rating':3,'revision':0})[0],409)
        self.assertEqual(self.call('/api/reviews/test-place','PUT',{'rating':3,'revision':1}, {'Origin':'https://unrelated.example'})[0],403)
        self.assertEqual(self.call('/api/reviews/test-place','PUT',{'rating':0,'comment':'只想写一句。','revision':1})[0],200)
        self.assertEqual(self.call('/api/logout','POST',{})[0],200)
        self.assertEqual(self.call('/api/reviews')[1]['reviews']['test-place']['comment'],'只想写一句。')
        self.assertEqual(self.call('/api/reviews/test-place','DELETE',{'revision':2})[0],401)
        self.assertEqual(self.call('/api/session','POST',{'password':'test-owner-password'})[0],200)
        self.assertEqual(self.call('/api/reviews/test-place','DELETE',{'revision':2})[0],200)
        self.assertEqual(self.call('/api/reviews')[1]['reviews'],{})

    def test_validation_and_unknown_place(self):
        self.login()
        for payload in ({'rating':6},{'rating':True},{'rating':0,'comment':''},{'rating':3,'visitDate':'invalid'},{'rating':3,'comment':'x'*5001}):
            self.assertEqual(self.call('/api/reviews/test-place','PUT',payload)[0],400)
        self.assertEqual(self.call('/api/reviews/not-a-place','PUT',{'rating':3})[0],404)
        self.assertEqual(self.call('/api/reviews/test-place','PUT',{'rating':5}, {'X-Personal-Review':''})[0],403)

    def test_remote_hostname_cannot_claim_initial_password(self):
        status, payload = self.call('/api/session', headers={'Host':'public.example'})
        self.assertEqual(status,200)
        self.assertFalse(payload['canSetup'])
        self.assertEqual(self.call('/api/session','POST',{'setup':True,'password':'test-owner-password'}, {'Host':'public.example'})[0],403)


if __name__ == '__main__':
    unittest.main()
