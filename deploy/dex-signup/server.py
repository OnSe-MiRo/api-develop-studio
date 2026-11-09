"""Loopback Dex admin RPC; expose only the signup path through the HTTPS gateway."""
import os
import re
import uuid

import bcrypt
import grpc
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from create_pb2 import Password, CreatePasswordReq
from create_pb2_grpc import DexStub

app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
dex = DexStub(grpc.insecure_channel('127.0.0.1:5557'))
public_origin = os.environ['STUDIO_PUBLIC_URL']


@app.post('/auth/signup')
async def signup(request: Request):
    def reply(status, message):
        return JSONResponse({'message': message}, status_code=status, headers={'Cache-Control': 'no-store'})

    if request.headers.get('origin') != public_origin or request.headers.get('content-type', '').split(';')[0] != 'application/json':
        return reply(403, 'Studio 회원가입 화면에서 다시 시도하세요.')
    try:
        body = await request.json()
    except ValueError:
        return reply(400, '입력값을 확인하세요.')
    if not isinstance(body, dict) or set(body) != {'email', 'password'} or not all(isinstance(v, str) for v in body.values()):
        return reply(400, '이메일과 비밀번호를 입력하세요.')
    email = body['email'].strip().lower()
    password = body['password']
    if len(email) > 254 or not re.fullmatch(r'[a-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+', email):
        return reply(400, '이메일 주소를 확인하세요.')
    if len(password) < 8 or len(password.encode('utf-8', errors='replace')) > 72 or any(0xD800 <= ord(c) <= 0xDFFF for c in password):
        return reply(400, '비밀번호는 8자 이상이며 UTF-8 기준 72바이트 이하여야 합니다.')
    def create():
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
        account = Password(email=email, hash=hashed, username=email, user_id='signup-' + uuid.uuid4().hex)
        return dex.CreatePassword(CreatePasswordReq(password=account), timeout=5)
    try:
        result = await run_in_threadpool(create)
        duplicate = result.already_exists
    except grpc.RpcError as exc:
        if exc.code() != grpc.StatusCode.ALREADY_EXISTS:
            return reply(503, '가입 요청을 처리할 수 없습니다. 잠시 후 다시 시도하세요.')
        duplicate = True
    if duplicate:
        return reply(409, '이미 가입된 이메일입니다. 다른 이메일을 입력하거나 SSO 로그인으로 이동하세요.')
    return reply(200, 'SSO 로그인에서 이메일과 비밀번호를 입력하세요.')
