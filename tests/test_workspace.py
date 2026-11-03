import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

_initial = tempfile.TemporaryDirectory(prefix='patent-import-test-')
os.environ['DATA_DIR'] = _initial.name
os.environ['APP_ENV'] = 'development'
os.environ['APP_ORIGIN'] = 'http://127.0.0.1:8096'
os.environ.pop('BOOTSTRAP_ADMIN_EMAIL', None)
os.environ.pop('BOOTSTRAP_ADMIN_PASSWORD', None)
import app


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='patent-workspace-test-')
        self.original_data = app.DATA
        app.DATA = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'APP_ENV':'development','APP_ORIGIN':'http://127.0.0.1:8096'}, clear=False)
        self.env.start()
        os.environ.pop('OPENAI_API_KEY', None)
        os.environ.pop('OPENAI_MODEL', None)
        app.initialize()
        with contextlib.closing(app.db()) as c,c:
            app.create_user(c,'admin@example.test','Test administrator','TestOnlyPassword2026!','admin')
            app.create_user(c,'member@example.test','Test member','MemberOnlyPassword2026!')
        self.cookie = ''

    def tearDown(self):
        self.env.stop()
        app.DATA = self.original_data
        self.temp.cleanup()

    def request(self,path,method='GET',body=None,origin='http://127.0.0.1:8096',cookie=None):
        content=json.dumps(body).encode() if body is not None else b''
        env={'PATH_INFO':path,'REQUEST_METHOD':method,'CONTENT_LENGTH':str(len(content)),'CONTENT_TYPE':'application/json','wsgi.input':io.BytesIO(content),'HTTP_ORIGIN':origin,'HTTP_HOST':'127.0.0.1:8096','HTTP_COOKIE':self.cookie if cookie is None else cookie,'REMOTE_ADDR':'127.0.0.1'}
        received={}
        def start(status,headers):
            received.update(status=int(status.split()[0]),headers=dict(headers))
        raw=b''.join(app.application(env,start))
        received['body']=json.loads(raw) if received['headers'].get('Content-Type','').startswith('application/json') else raw.decode(errors='replace')
        return received

    def login(self,email='admin@example.test',password='TestOnlyPassword2026!'):
        response=self.request('/api/login','POST',dict(email=email,password=password))
        self.assertEqual(response['status'],200,response)
        self.cookie=response['headers']['Set-Cookie'].split(';')[0]
        return response

    def matter(self):
        response=self.request('/api/matters','POST',dict(title='Synthetic intake mechanism',company='Synthetic test company',objective='Protect reusable technical differentiation',horizon='Next 12 months'))
        self.assertEqual(response['status'],201,response)
        return response['body']['id']

    def test_anonymous_access_and_static_boundaries(self):
        self.assertEqual(self.request('/api/matters')['status'],401)
        self.assertEqual(self.request('/api/team')['status'],401)
        self.assertEqual(self.request('/../app.py')['status'],404)
        self.assertEqual(self.request('/skills/portfolio-strategy/SKILL.md')['status'],404)
        self.assertEqual(self.request('/')['status'],200)
        self.assertIn("script-src 'self'",self.request('/')['headers']['Content-Security-Policy'])

    def test_signin_origin_cookie_and_revocation(self):
        self.assertEqual(self.request('/api/login','POST',dict(email='admin@example.test',password='bad'),origin='https://wrong.example')['status'],403)
        with patch.dict(os.environ,APP_ENV='production'):
            response=self.login()
        self.assertIn('; Secure',response['headers']['Set-Cookie'])
        self.assertIn('HttpOnly',response['headers']['Set-Cookie'])
        self.assertEqual(self.request('/api/session')['body']['user']['role'],'admin')
        self.request('/api/logout','POST',{})
        self.assertEqual(self.request('/api/matters')['status'],401)

    def test_login_throttling_persists_failed_attempts(self):
        for _ in range(8):
            self.assertEqual(self.request('/api/login','POST',dict(email='admin@example.test',password='wrong'))['status'],401)
        self.assertEqual(self.request('/api/login','POST',dict(email='admin@example.test',password='TestOnlyPassword2026!'))['status'],429)

    def test_shared_matters_and_admin_boundary(self):
        self.login(); ident=self.matter()
        self.login('member@example.test','MemberOnlyPassword2026!')
        self.assertEqual(self.request('/api/matters/'+ident)['status'],200)
        self.assertEqual(self.request('/api/team')['status'],403)
        self.assertEqual(self.request('/api/team','POST',{})['status'],403)

    def test_account_disabling_invalidates_active_sessions(self):
        self.login('member@example.test','MemberOnlyPassword2026!'); member_cookie=self.cookie
        self.login(); member=next(r for r in self.request('/api/team')['body'] if r['role']=='member')
        self.assertEqual(self.request('/api/team/'+member['id'],'PATCH',dict(active=False))['status'],200)
        self.assertEqual(self.request('/api/matters',cookie=member_cookie)['status'],401)

    def test_sources_and_revision_conflicts(self):
        self.login(); ident=self.matter()
        source=self.request(f'/api/matters/{ident}/sources','POST',dict(name='mechanism.md',text='Synthetic evidence: request event points to document version.'))
        self.assertEqual(source['status'],201,source)
        self.assertEqual(len(source['body']['sha256']),64)
        self.assertEqual(self.request(f'/api/matters/{ident}/sources','POST',dict(name='not-parsed.pdf',text='content'))['status'],400)
        fields=dict(title='Changed',company='Synthetic test company',objective='Review',horizon='12 months',revision=1)
        self.assertEqual(self.request('/api/matters/'+ident,'PATCH',fields)['status'],200)
        self.assertEqual(self.request('/api/matters/'+ident,'PATCH',fields)['status'],409)

    def test_missing_ai_config_and_calculator_validation(self):
        self.login(); ident=self.matter()
        response=self.request(f'/api/matters/{ident}/runs','POST',dict(skill='portfolio-strategy',kind='draft',question='Build a draft',request_id='missing-config'))
        self.assertEqual(response['status'],503)
        invalid=self.request(f'/api/matters/{ident}/runs','POST',dict(skill='portfolio-strategy',kind='calculation',question='Calculate',calculator_input='{}',request_id='bad-json-schema'))
        self.assertEqual(invalid['status'],422,invalid)
        detail=self.request('/api/matters/'+ident)['body']
        self.assertEqual(detail['runs'][0]['status'],'failed')

    def test_original_calculators_match_supplied_repository_examples(self):
        for skill in ('portfolio-strategy','filing-review'):
            with self.subTest(skill=skill):
                path=Path(__file__).parent/'samples'
                actual=app.calculate(skill,(path/f'{skill}-input.json').read_text())
                expected=json.loads((path/f'{skill}-expected-output.json').read_text())
                self.assertEqual(actual,expected)

    def test_run_snapshot_and_duplicate_submission(self):
        self.login(); ident=self.matter()
        source=self.request(f'/api/matters/{ident}/sources','POST',dict(name='evidence.md',text='Synthetic action provenance mechanism.'))
        raw=(Path(__file__).parent/'samples/portfolio-strategy-input.json').read_text()
        body=dict(skill='portfolio-strategy',kind='calculation',question='Compute supplied example',calculator_input=raw,request_id='same-click')
        first=self.request(f'/api/matters/{ident}/runs','POST',body)
        self.assertEqual(first['status'],201,first)
        second=self.request(f'/api/matters/{ident}/runs','POST',body)
        self.assertEqual(first['body']['id'],second['body']['id'])
        exported=self.request(f'/api/matters/{ident}/export')['body']
        self.assertEqual(len(exported['runs']),1)
        snapshot=json.loads(exported['runs'][0]['snapshot'])
        self.assertEqual(snapshot['sources'][0]['id'],source['body']['id'])
        self.assertEqual(snapshot['calculator_input'],raw)
        self.assertTrue(snapshot['skill_manifest']['files'])

    def test_openai_wire_payload_and_response_state(self):
        self.login(); ident=self.matter()
        self.request(f'/api/matters/{ident}/sources','POST',dict(name='architecture.md',text='Synthetic request links to a versioned evidence item.'))
        response=io.BytesIO(json.dumps(dict(status='completed',id='synthetic-response',model='test-model',usage={'total_tokens':42},output=[dict(type='message',content=[dict(type='output_text',text='# Synthetic draft\nNeeds inventor clarification.')])])).encode())
        with patch.dict(os.environ,OPENAI_API_KEY='synthetic-test-key',OPENAI_MODEL='test-model'),patch('urllib.request.urlopen',return_value=response) as network:
            result=self.request(f'/api/matters/{ident}/runs','POST',dict(skill='invention-intake',kind='draft',question='Prepare an intake draft',request_id='ai-test'))
        self.assertEqual(result['status'],201,result)
        request=network.call_args.args[0]; payload=json.loads(request.data)
        self.assertEqual(request.full_url,'https://api.openai.com/v1/responses')
        self.assertFalse(payload['store'])
        self.assertIn('Technical',payload['instructions'])
        self.assertIn('Skill resource: references/evidence.md',payload['instructions'])
        self.assertIn('Synthetic request links',payload['input'][0]['content'])
        self.assertEqual(json.loads(result['body']['result'])['response_id'],'synthetic-response')
        incomplete=io.BytesIO(b'{"status":"incomplete","output":[]}')
        with patch.dict(os.environ,OPENAI_API_KEY='synthetic-test-key',OPENAI_MODEL='test-model'),patch('urllib.request.urlopen',return_value=incomplete):
            result=self.request(f'/api/matters/{ident}/runs','POST',dict(skill='invention-intake',kind='draft',question='Continue',request_id='incomplete-test'))
        self.assertEqual(result['status'],502,result)
        self.assertIn('did not return a completed draft',result['body']['error'])


if __name__=='__main__':
    unittest.main()
