#!/usr/bin/env python3
"""One-time CI provisioning; never overwrite an existing Worker."""
import json
import os
import urllib.request
import uuid

base = 'https://api.cloudflare.com/client/v4/accounts/86191ab109215f74781aef56cee40263'
headers = {'Authorization': 'Bearer '+os.environ['CLOUDFLARE_API_TOKEN']}


def request(path, method='GET', payload=None, content_type='application/json'):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode() if payload is not None else None
    call = urllib.request.Request(base+path, data=data, method=method,
                                  headers=dict(headers, **{'Content-Type': content_type}))
    with urllib.request.urlopen(call, timeout=60) as response:
        result = json.load(response)
    if not result['success']:
        raise RuntimeError('Cloudflare provisioning failed')
    return result['result']


scripts = request('/workers/scripts')
if not any(script['id'] == 'fansionia-packages' for script in scripts):
    boundary = uuid.uuid4().hex
    metadata = json.dumps({'main_module': 'index.mjs', 'compatibility_date': '2026-10-24'})
    source = 'export default { fetch() { return new Response("Repository initialization in progress\\n", {status:404,headers:{"Cache-Control":"no-store"}}); } };'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n{metadata}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="index.mjs"; filename="index.mjs"\r\nContent-Type: application/javascript+module\r\n\r\n{source}\r\n'
            f'--{boundary}--\r\n').encode()
    request('/workers/scripts/fansionia-packages', 'PUT', body, 'multipart/form-data; boundary='+boundary)
    request('/workers/scripts/fansionia-packages/subdomain', 'POST', {'enabled': True, 'previews_enabled': False})
    print('Created the repository Worker; routing becomes available only after verified publication.')
else:
    print('Repository Worker already exists; its code and routes were preserved.')
