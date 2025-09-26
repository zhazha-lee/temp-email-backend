# app/main.py

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx
import random
import string
from typing import Annotated

app = FastAPI( )

# 定义允许的来源
origins = [
    "http://localhost:3000",
    # "https://your-frontend-domain.com", # 以后您部署前端时 ，把域名加到这里
]

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# mail.tm API 的基础 URL
MAIL_TM_API_URL = "https://api.mail.tm"

# 创建一个可复用的异步 HTTP 客户端
client = httpx.AsyncClient(base_url=MAIL_TM_API_URL )

@app.get("/")
def read_root():
    return {"message": "欢迎使用基于 mail.tm 的临时邮件后端代理"}

@app.post("/api/session/new")
async def create_new_session():
    """
    创建一个新的临时邮箱会话。
    """
    try:
        # 1. 获取可用域名
        domains_res = await client.get("/domains")
        domains_res.raise_for_status()
        domains = domains_res.json()['hydra:member']
        if not domains:
            raise HTTPException(status_code=500, detail="mail.tm 未提供可用域名")
        
        selected_domain = random.choice(domains)['domain']
        
        # 2. 生成随机地址和密码
        address = f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}@{selected_domain}"
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

        # 3. 在 mail.tm 创建账户
        account_payload = {"address": address, "password": password}
        # 注意：创建账户的请求可能会因为地址已被占用而失败，但在我们的随机生成逻辑下概率极低
        await client.post("/accounts", json=account_payload)
        
        # 4. 获取认证 Token
        token_payload = {"address": address, "password": password}
        token_res = await client.post("/token", json=token_payload)
        token_res.raise_for_status()
        
        token = token_res.json()['token']
        
        # 返回给前端需要的所有信息
        return {"address": address, "token": token}

    except httpx.HTTPStatusError as e:
        print(f"mail.tm API 错误: {e.response.status_code} - {e.response.text}" )
        raise HTTPException(status_code=e.response.status_code, detail=f"创建会话失败: {e.response.text}")

@app.get("/api/emails")
async def get_emails(token: Annotated[str, Query(description="从 /api/session/new 获取的认证 Token")]):
    """
    根据前端提供的 Token，从 mail.tm 获取邮件列表。
    """
    if not token:
        raise HTTPException(status_code=400, detail="必须提供认证 Token")
    
    headers = {'Authorization': f'Bearer {token}'}
    try:
        # mail.tm 的 /messages 接口是分页的，这里我们只获取第一页
        response = await client.get("/messages?page=1", headers=headers)
        response.raise_for_status()
        # 'hydra:member' 字段包含了邮件列表数组
        return response.json()['hydra:member']
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(status_code=401, detail="Token 无效或已过期 ，请重新创建会话")
        raise HTTPException(status_code=e.response.status_code, detail=f"获取邮件列表失败: {e.response.text}")

# ====================================================================
# vvvvvvvvvvvvvvvvvvvv   这是我们新增的 API 端点   vvvvvvvvvvvvvvvvvvvv
# ====================================================================

@app.get("/api/email/{email_id}")
async def get_email_details(
    email_id: str, 
    token: Annotated[str, Query(description="从 /api/session/new 获取的认证 Token")]
):
    """
    根据邮件 ID 和 Token，获取单封邮件的完整内容。
    """
    if not token:
        raise HTTPException(status_code=400, detail="必须提供认证 Token")
    
    headers = {'Authorization': f'Bearer {token}'}
    try:
        # mail.tm 获取单封邮件的接口是 /messages/{id}
        response = await client.get(f"/messages/{email_id}", headers=headers)
        response.raise_for_status()
        
        # 直接返回 mail.tm 提供的完整邮件数据
        return response.json()
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(status_code=401, detail="Token 无效或已过期 ，请重新创建会话")
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="找不到指定的邮件")
        
        print(f"获取邮件详情时出错: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"获取邮件详情失败: {e.response.text}")

# ====================================================================
# ^^^^^^^^^^^^^^^^^^^^   新增 API 端点结束   ^^^^^^^^^^^^^^^^^^^^^^^^
# ====================================================================
