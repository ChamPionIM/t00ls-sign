import os
import re
import time
import hmac
import hashlib
import base64
import json
from urllib.parse import quote_plus, unquote
import requests

# ===== 环境变量 =====
def getenv(name, default=""):
    v = os.environ.get(name)
    return default if v is None or str(v).strip() == "" else str(v).strip()

# T00ls 账户
USERNAME   = getenv("T00LS_USERNAME")
PASSWORD   = getenv("T00LS_PASSWORD")
QUESTIONID = getenv("T00LS_QUESTIONID", "0")
ANSWER     = getenv("T00LS_ANSWER", "")

# 钉钉机器人（只保留这两个）
DD_ACCESS_TOKEN = getenv("DD_ACCESS_TOKEN", "")
DD_SECRET       = getenv("DD_SECRET", "")  # 开启加签才填；未开启可留空

# 其它可选
BASE_URL = getenv("T00LS_BASE_URL", "https://www.t00ls.com").rstrip("/")
TIMEOUT  = int(getenv("T00LS_TIMEOUT", "15"))
RETRIES  = int(getenv("T00LS_RETRIES", "2"))

# 代理（如需）
HTTP_PROXY  = getenv("HTTP_PROXY", getenv("http_proxy", ""))
HTTPS_PROXY = getenv("HTTPS_PROXY", getenv("https_proxy", ""))
PROXIES = {}
if HTTP_PROXY:  PROXIES["http"]  = HTTP_PROXY
if HTTPS_PROXY: PROXIES["https"] = HTTPS_PROXY

# ===== 钉钉通知 =====
def send_dingtalk(title: str, content: str):
    if not DD_ACCESS_TOKEN:
        print("未配置 DD_ACCESS_TOKEN，跳过钉钉通知。")
        return
    try:
        webhook = f"https://oapi.dingtalk.com/robot/send?access_token={DD_ACCESS_TOKEN}"
        if DD_SECRET:
            ts = str(round(time.time() * 1000))
            sign_raw = hmac.new(
                DD_SECRET.encode("utf-8"),
                f"{ts}\n{DD_SECRET}".encode("utf-8"),
                digestmod=hashlib.sha256
            ).digest()
            sign = quote_plus(base64.b64encode(sign_raw).decode("utf-8"))
            webhook = f"{webhook}&timestamp={ts}&sign={sign}"

        headers = {"Content-Type": "application/json;charset=utf-8"}
        payload = {"msgtype": "markdown", "markdown": {"title": title, "text": f"### {title}\n\n{content}"}}
        r = requests.post(webhook, headers=headers, data=json.dumps(payload), timeout=10, proxies=PROXIES or None)
        jr = {}
        try:
            jr = r.json()
        except Exception:
            pass
        if r.status_code != 200 or (isinstance(jr, dict) and jr.get("errcode") not in (0, None)):
            print(f"钉钉通知失败：HTTP {r.status_code}, resp={jr}")
        else:
            print("钉钉通知成功。")
    except Exception as e:
        print(f"钉钉通知异常：{e}")

# ===== 带重试请求 =====
def do_request(method, url, session=None, **kwargs):
    last_exc = None
    for i in range(max(RETRIES, 1)):
        try:
            if session:
                return session.request(method, url, timeout=TIMEOUT, proxies=PROXIES or None, **kwargs)
            else:
                return requests.request(method, url, timeout=TIMEOUT, proxies=PROXIES or None, **kwargs)
        except Exception as e:
            last_exc = e
            print(f"[重试 {i+1}/{RETRIES}] {method} {url} 失败：{e}")
            time.sleep(1 + i)
    if last_exc:
        raise last_exc

# ===== 主逻辑 =====
def main():
    if not USERNAME or not PASSWORD:
        msg = "缺少必要环境变量：T00LS_USERNAME / T00LS_PASSWORD"
        print(msg)
        send_dingtalk("T00ls 签到失败", f"**错误信息**：\n\n```\n{msg}\n```")
        return

    try:
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"})

        # 1) 登录
        login_url = f"{BASE_URL}/login.json"
        login_data = {
            "action": "login",
            "username": USERNAME,
            "password": PASSWORD,
            "questionid": QUESTIONID,
            "answer": ANSWER
        }
        login_resp = do_request("POST", login_url, session=s, data=login_data)
        print("登录响应：", login_resp.text[:500])
        if login_resp.status_code != 200:
            raise Exception(f"登录请求失败，状态码: {login_resp.status_code}")

        lj = {}
        try:
            lj = login_resp.json()
        except Exception:
            pass
        login_formhash = lj.get("formhash")

        # 把 JSON 中返回的 cookie 写回 Session（不少站不会下发 Set-Cookie 头）
        for ck, cv in (lj.get("cookie") or {}).items():
            s.cookies.set(ck, unquote(cv), domain=".t00ls.com")

        # 2) 获取 uid / formhash
        profile_url = f"{BASE_URL}/members-profile.json"
        profile_resp = do_request("GET", profile_url, session=s)
        if profile_resp.status_code != 200:
            raise Exception(f"获取用户信息失败，状态码: {profile_resp.status_code}")

        uid_match = re.search(r'"uid":"(\d+)"', profile_resp.text)
        formhash_match = re.search(r'"formhash":"(.+?)"', profile_resp.text)
        uid = uid_match.group(1) if uid_match else None
        formhash = formhash_match.group(1) if formhash_match else login_formhash
        if not formhash:
            raise Exception("未提取到 formhash（登录/资料页均未返回）")

        # 3) 签到
        sign_url = f"{BASE_URL}/ajax-sign.json"
        referer = f"{BASE_URL}/members-profile-{uid}.html" if uid else f"{BASE_URL}/members-profile.html"
        sign_headers = {"Referer": referer}
        sign_data = {"signsubmit": "apply", "formhash": formhash}
        sign_resp = do_request("POST", sign_url, session=s, headers=sign_headers, data=sign_data)
        if sign_resp.status_code != 200:
            raise Exception(f"签到请求失败，状态码: {sign_resp.status_code}")

        raw = sign_resp.text
        print("签到结果：", raw[:500])

        # —— 结果分类：成功 / 已签过 / 失败 —— #
        status = "unknown"
        message = raw
        jr = None
        try:
            jr = sign_resp.json()
            status = (jr.get("status") or "").lower()
            message = (jr.get("message") or "") or raw
        except Exception:
            pass

        already_signed = ("alreadysign" in message.lower()) or ("已签" in message)

        if status == "success":
            send_dingtalk("T00ls 签到成功", f"**接口返回**：\n\n```\n{jr or raw}\n```")
        elif already_signed:
            send_dingtalk("T00ls 今日已签到", f"**接口返回**：\n\n```\n{jr or raw}\n```\n\n> 提示：接口提示已签过。")
        else:
            raise Exception(f"签到未成功：status={status}, message={message}")

    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print("异常：", err)
        send_dingtalk("T00ls 签到失败", f"**错误信息**：\n\n```\n{err}\n```")

if __name__ == "__main__":
    main()

# ===== 环境变量示例（注释，复制时忽略） =====
# T00LS_USERNAME="你的用户名"
# T00LS_PASSWORD="你的密码"
# T00LS_QUESTIONID="0"
# T00LS_ANSWER=""
# DD_ACCESS_TOKEN="xxxx"
# DD_SECRET="SECxxxx"     # 未开启加签可留空
# 可选：
# HTTP_PROXY="http://127.0.0.1:7890"
# HTTPS_PROXY="http://127.0.0.1:7890"
