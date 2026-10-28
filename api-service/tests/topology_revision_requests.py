"""旧契约测试显式读取当前保存版本；不拦截或自动改写HTTP请求。"""
def saved_revision(http, url, scope):
    detail = http.get(url, params=scope)
    assert detail.status_code == 200, detail.text
    return detail.json()['revision']
