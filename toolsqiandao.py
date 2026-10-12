import os
import re
import time
import hmac
import hashlib
import base64
import json
import datetime
from urllib.parse import quote_plus, unquote
import requests

# ===== 环境变量 =====
def getenv(name, default=""):
    v = os.environ.get(name)
    return default if v is None or str(v).strip() == "" else str(v).strip()
# 日志脱敏
def get_safe_log(text):
    """
    尝试解析 JSON 并隐藏敏感字段，如果不是 JSON 则截断输出
    """
    try:
        data = json.loads(text)
        # 1. 隐藏 Cookie
        if "cookie" in data:
            data["cookie"] = "****** (已隐藏)"
        
        # 2. 隐藏 formhash (只保留前2位)
        if "formhash" in data:
            fh = str(data["formhash"])
            data["formhash"] = fh[:2] + "***" if len(fh) > 2 else "***"

        # 返回处理后的 JSON 字符串
        return json.dumps(data, ensure_ascii=False)
    except:
        # 如果解析失败，说明不是标准JSON，只截取前 50 个字符
        return text[:50] + "..."



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

# ===== README 稳定运行统计 =====
# 签到确认成功后，把 README 里「已稳定运行：yyyy-mm-dd ~ yyyy-mm-dd（N 天）。」一行
# 按 START_DATE ~ 当天 的日历天数重算并写回，交由 workflow 提交。
START_DATE          = getenv("T00LS_START_DATE", "2026-01-15")
README_PATH         = getenv("T00LS_README_PATH", "README.md")
README_STATS_MARKER = "已稳定运行："      # 含全角冒号，只匹配正文顶部那一行

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

# ===== README 稳定运行统计更新 =====
def _parse_date(s):
    try:
        return datetime.date.fromisoformat(str(s).strip())
    except Exception:
        return None


def update_readme_stats(today=None, path=None):
    """
    按 START_DATE ~ 当天 的日历天数重算 README 中「已稳定运行」那一行，
    返回 True 表示文件确有改动。
    任何异常都只打日志、不抛出——不能因为改 README 把一次成功的签到判成失败。
    """
    try:
        path = path or README_PATH
        start = _parse_date(START_DATE)
        if not start:
            print(f"README 统计：T00LS_START_DATE 非法（{START_DATE!r}），跳过。")
            return False

        end = today or datetime.date.today()
        days = (end - start).days
        new_line = f"已稳定运行：{start.isoformat()} ~ {end.isoformat()}（{days} 天）。"

        # newline="" 关闭换行转换，原样保留文件里的 LF / CRLF
        with open(path, "r", encoding="utf-8", newline="") as f:
            lines = f.read().splitlines(keepends=True)

        for i, ln in enumerate(lines):
            if not ln.lstrip().startswith(README_STATS_MARKER):
                continue
            eol = ln[len(ln.rstrip("\r\n")):]        # 沿用原文件行尾
            if new_line + eol == ln:
                print(f"README 统计无变化：{new_line}")
                return False
            lines[i] = new_line + eol
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write("".join(lines))
            print(f"README 统计已更新：{new_line}")
            return True

        print(f"README 统计：未找到含「{README_STATS_MARKER}」的行，跳过。")
        return False
    except FileNotFoundError:
        print(f"README 统计：找不到 {path}，跳过。")
        return False
    except Exception as e:
        print(f"README 统计更新失败（已忽略）：{e}")
        return False


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
        print("登录响应：", get_safe_log(login_resp.text))
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

        if not (status == "success" or already_signed):
            raise Exception(f"签到未成功：status={status}, message={message}")

        # 今日签到已确认（新签成功 / 此前已签），刷新 README 的稳定运行天数
        update_readme_stats()

        if status == "success":
            send_dingtalk("T00ls 签到成功", f"**接口返回**：\n\n```\n{jr or raw}\n```")
        else:
            send_dingtalk("T00ls 今日已签到", f"**接口返回**：\n\n```\n{jr or raw}\n```\n\n> 提示：接口提示已签过。")

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
