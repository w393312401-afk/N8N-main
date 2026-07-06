import urllib.request, json

n8n_url = 'http://localhost:5678/api/v1/workflows/13CnpyRAeEwAyv5D'
n8n_key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiMjk1NjgwNi00YThiLTQyNmQtYTUwYS0zOGY4YzY4OTY5OWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMTNkZjQ2ZTktMWY0ZS00NWJmLThjZjYtMDIwNTcyMGFkOTg5IiwiaWF0IjoxNzc2MzAyNDU0fQ.loBTnubP_me5AQXLejivQLY-1pe0miFIuGQyd8yfhNs'

req = urllib.request.Request(n8n_url, headers={'X-N8N-API-KEY': n8n_key})
wf = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))

for node in wf['nodes']:
    # 1. Update cfg-panel
    if node['name'] == '配置面板':
        params = node['parameters']['values']['string']
        exists = any(p['name'] == 'videoApiKey' for p in params)
        if not exists:
            params.append({
                'name': 'videoApiKey',
                'value': 'sk-Zo4Y4dqod8Zb9V0UcGsxKfc7SwvQQyW4slCYFtXMJFnP0q6o'
            })
            print('Added videoApiKey to 配置面板.')

    # 2. Update build-video-req
    elif node['name'] == '构建视频请求':
        code = node['parameters']['jsCode']
        if 'authHeader:' not in code:
            new_code = code.replace(
                'requestUrl: cfg.videoApiUrl,',
                'requestUrl: cfg.videoApiUrl,\n  authHeader: cfg.videoApiKey ? `Bearer ${cfg.videoApiKey}` : "",'
            )
            node['parameters']['jsCode'] = new_code
            print('Updated 构建视频请求 code.')

    # 3. Update call-video
    elif node['name'] == '调用视频接口':
        if 'headerParameters' not in node['parameters']:
            node['parameters']['headerParameters'] = {'parameters': []}
        headers = node['parameters']['headerParameters']['parameters']
        exists = any(h['name'] == 'Authorization' for h in headers)
        if not exists:
            headers.append({
                'name': 'Authorization',
                'value': '={{ $json.authHeader }}'
            })
            print('Updated 调用视频接口 headers.')

allowed_settings = ['executionOrder', 'timezone', 'saveDataErrorExecution', 'saveDataSuccessExecution', 'saveManualExecutions', 'callerPolicy', 'errorWorkflow']
new_settings = {k: v for k, v in wf.get('settings', {}).items() if k in allowed_settings}

update_payload = {
    'name': wf['name'],
    'nodes': wf['nodes'],
    'connections': wf['connections'],
    'settings': new_settings
}

update_req = urllib.request.Request(
    n8n_url,
    headers={'X-N8N-API-KEY': n8n_key, 'Content-Type': 'application/json'},
    method='PUT',
    data=json.dumps(update_payload).encode('utf-8')
)
try:
    urllib.request.urlopen(update_req)
    print('Workflow successfully updated')
except Exception as e:
    print('Error:', e)
    if hasattr(e, 'read'): print(e.read().decode('utf-8'))
