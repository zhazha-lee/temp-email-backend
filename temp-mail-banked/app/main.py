from fastapi import FastAPI, HTTPException, Query
# 1. 导入 CORSMiddleware
from fastapi.middleware.cors import CORSMiddleware
import httpx
import random
import string
from typing import Annotated

app = FastAPI( )

# 2. 定义允许的来源
# 在开发环境中，我们需要允许来自 localhost:3000 的请求
# 在生产环境中，您可能需要添加您前端部署后的域名
origins = [
    "http://localhost:3000",  # Next.js 开发服务器的默认地址
    # "https://your-frontend-domain.com", # 以后您部署前端时 ，把域名加到这里
]

# 3. 添加 CORS 中间件到您的 FastAPI 应用
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 允许访问的源列表
    allow_credentials=True, # 是否支持 cookie
    allow_methods=["*"],    # 允许所有 HTTP 方法 (GET, POST, etc.)
    allow_headers=["*"],    # 允许所有 HTTP 请求头
)


# --- 以下的所有代码保持不变 ---

MAIL_TM_API_URL = "https://api.mail.tm"
client = httpx.AsyncClient(base_url=MAIL_TM_API_URL )

@app.get("/")
def read_root():
    return {"message": "欢迎使用基于 mail.tm 的临时邮件后端代理"}

@app.post("/api/session/new")
async def create_new_session():
    # ... (此函数内容不变)
    try:
        domains_res = await client.get("/domains")
        domains_res.raise_for_status()
        domains = domains_res.json()['hydra:member']
        if not domains:
            raise HTTPException(status_code=500, detail="mail.tm 未提供可用域名")
        
        selected_domain = random.choice(domains)['domain']
        address = f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}@{selected_domain}"
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

        account_payload = {"address": address, "password": password}
        await client.post("/accounts", json=account_payload)
        
        token_payload = {"address": address, "password": password}
        token_res = await client.post("/token", json=token_payload)
        token_res.raise_for_status()
        
        token = token_res.json()['token']
        return {"address": address, "token": token}
    except httpx.HTTPStatusError as e:
        print(f"mail.tm API 错误: {e.response.status_code} - {e.response.text}" )
        raise HTTPException(status_code=e.response.status_code, detail=f"创建会话失败: {e.response.text}")

@app.get("/api/emails")
async def get_emails(token: Annotated[str, Query(description="从 /api/session/new 获取的认证 Token")]):
    # ... (此函数内容不变)
    if not token:
        raise HTTPException(status_code=400, detail="必须提供认证 Token")
    
    headers = {'Authorization': f'Bearer {token}'}
    try:
        response = await client.get("/messages?page=1", headers=headers)
        response.raise_for_status()
        return response.json()['hydra:member']
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(status_code=401, detail="Token 无效或已过期 ，请重新创建会话")
        raise HTTPException(status_code=e.response.status_code, detail=f"获取邮件列表失败: {e.response.text}")
