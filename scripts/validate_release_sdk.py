"""Validate release SDKs against a disposable SQLite workspace and loopback HTTP server.

Run from the repository root. Requires the pinned JAR/Java dependencies.
Does not use existing Studio databases, ownership records, or Redis.
"""
import sys,os,json,tempfile,time,io,zipfile,hashlib,compileall,urllib.request,threading,socket
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,help='Optional new JSON report path; refuses overwrite')
args=parser.parse_args()
if args.output and args.output.exists():parser.error('output already exists')
root=Path(tempfile.mkdtemp(prefix='doc1-real-')).resolve()
os.environ['STUDIO_DB_PATH']=str(root/'studio.db');os.environ['EXAMPLE_PROJECT']='false'
os.environ.pop('STUDIO_DATABASE_URL',None);os.environ.pop('STUDIO_DATABASE_URL_FILE',None)
os.environ['STUDIO_REDIS_URL']=''
os.environ['STUDIO_AUTH_MODE']='local'
os.environ['API_TEST_HOST']='127.0.0.1'
from api_test.services import studio
for attr,name in [('PROJECT_ROOT','projects'),('CASE_ROOT','case'),('PIPELINE_ROOT','pipelines')]:
 path=root/name;path.mkdir();setattr(studio,attr,path)
studio._COLLABORATION_STORE=None
store=studio.collaboration_store()
document={'openapi':'3.0.3','info':{'title':'Release Original','version':'1.0.0'},'servers':[{'url':'https://example.test'}],'paths':{'/items':{'get':{'operationId':'listItems','summary':'List items','responses':{'200':{'description':'ok','content':{'application/json':{'schema':{'type':'object','properties':{'id':{'type':'integer'}}},'example':{'id':7}}}}}}}}}
saved=store.save('projects','doc-release.json',{'name':'Original','base_url':'https://example.test','variables':{'plain':{'notForSdk':'PRIVATE_SENTINEL'}},'docs_file':{'document':document}})
from api_test.release_store import ReleaseStore
releases=ReleaseStore(store.database_path,context=store.context)
draft=releases.create('doc-release.json',{'version':'1.0.0','projectRevision':saved.revision})
release=releases.transition('doc-release.json',draft['id'],{'revision':1,'state':'published','reason':'Synthetic validation'})
store.save('projects','doc-release.json',{'name':'Changed','base_url':'https://changed.test','docs_file':{'document':{**document,'info':{'title':'Changed Latest','version':'9.0.0'}}}},expected_revision=saved.revision)
from api_test.main import create_app
import uvicorn

def start():
 app=create_app(studio)
 sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen()
 address=f'http://127.0.0.1:{sock.getsockname()[1]}'
 server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False))
 thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
 deadline=time.monotonic()+5
 while not server.started and time.monotonic()<deadline:time.sleep(.01)
 assert server.started
 return server,thread,address

def call(address,path,body=None,binary=False):
 request=urllib.request.Request(address+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=10) as response:
  value=response.read();return (value,dict(response.headers)) if binary else json.loads(value)

server,thread,address=start();base='/api/projects/doc-release.json/portal/'+release['id']
results=[];zip_hashes={}
try:
 portal=call(address,base);assert portal['document']['info']['title']=='Release Original'
 for language,extension in [('python','.py'),('javascript','.js'),('typescript','.ts'),('java','.java'),('kotlin','.kt'),('go','.go'),('csharp','.cs')]:
  started=time.monotonic();job=call(address,base+'/sdk',{'language':language});assert job['status']=='queued'
  deadline=time.monotonic()+40
  while time.monotonic()<deadline:
   result=call(address,'/api/runs/'+job['runId'])
   if result['status'] in ('passed','failed','error','cancelled','timeout'):break
   time.sleep(.1)
  assert result['status']=='passed',result
  payload,headers=call(address,base+'/sdk/'+language,binary=True)
  metadata=result['result']['artifact'];digest=hashlib.sha256(payload).hexdigest()
  assert metadata['sha256']==digest and metadata['sizeBytes']==len(payload)
  assert metadata['sourceDigest']==release['sourceDigest']
  assert b'PRIVATE_SENTINEL' not in payload
  with zipfile.ZipFile(io.BytesIO(payload)) as z:
   assert z.testzip() is None
   names=z.namelist();assert any(name.endswith(extension) for name in names)
   manifest=json.loads(z.read(next(name for name in names if name.endswith('/studio-release.json'))))
   assert manifest['releaseId']==release['id'] and manifest['projectRevision']==1 and manifest['sourceDigest']==release['sourceDigest']
   import yaml
   assert yaml.safe_load(z.read(next(name.split('/')[0] for name in names)+'/'+manifest['sourcePath']))==document
   for name in names:
    if not name.endswith('/'):assert b'PRIVATE_SENTINEL' not in z.read(name)
   if language=='python':
    extracted=root/'python-sdk';z.extractall(extracted);assert compileall.compile_dir(extracted,quiet=1)
  zip_hashes[language]=digest
  results.append({'language':language,'bytes':len(payload),'sha256':digest,'seconds':round(time.monotonic()-started,3),'sourceRevision':1,'zipCRC':'passed'})
  print(json.dumps(results[-1]),flush=True)
finally:
 server.should_exit=True;thread.join(10);assert not thread.is_alive()
server,thread,address=start()
try:
 for language,digest in zip_hashes.items():
  payload,_=call(address,base+'/sdk/'+language,binary=True);assert hashlib.sha256(payload).hexdigest()==digest
 report={'root':str(root),'releaseId':release['id'],'sourceDigest':release['sourceDigest'],'frozenSourceRevision':1,'liveProjectRevision':2,'artifacts':results,'applicationRestartDownloadParity':True,'pythonSyntax':'passed','realHTTP':True}
 report_path=args.output or root/'validation.json'
 report_path.write_text(json.dumps(report,indent=2)+'\n')
 print('REPORT: '+str(report_path),flush=True)
 print('RESTART PARITY PASSED',flush=True)
finally:
 server.should_exit=True;thread.join(10);assert not thread.is_alive()
