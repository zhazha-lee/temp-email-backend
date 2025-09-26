# app/main.py

from fastapi import FastAPI, HTTPException, Query
import httpx
import random
import string
from typing import Annotated

app = FastAPI( )

# mail.tm API 的基础 URL
MAIL_TM_API_URL = "https://api.mail.tm"

# 创建一个可复用的异步 HTTP 客户端 ，以提高性能
client = httpx.AsyncClient(base_url=MAIL_TM_API_URL )

@app.get("/")
def read_root():
    return {"message": "欢迎使用基于 mail.tm 的临时邮件后端代理"}

@app.post("/api/session/new")
async def create_new_session():
    """
    创建一个新的临时邮箱会话。
    这个函数会完成三件事：
    1. 从 mail.tm 获取一个可用的域名。
    2. 生成一个随机的邮箱地址和密码。
    3. 使用地址和密码在 mail.tm 创建账户并获取用于后续请求的认证 Token。
    """
    try:
        # 1. 获取可用域名
        domains_res = await client.get("/domains")
        domains_res.raise_for_status()  # 如果 API 返回错误状态码，则抛出异常
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
        # 如果调用 mail.tm API 时出错 ，将错误信息返回给前端，方便调试
        print(f"mail.tm API 错误: {e.response.status_code} - {e.response.text}")
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

