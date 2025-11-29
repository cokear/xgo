import streamlit as st
import os
import subprocess
import requests
import time
import threading
import json
import base64
import re
import shutil
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==========================================
# === 强制配置 (硬编码路径以排除干扰)
# ==========================================
WORKDIR = "/tmp/komari-run"
LOG_FILE = f"{WORKDIR}/boot.log"
LIST_FILE = f"{WORKDIR}/list.txt"
SUB_FILE = f"{WORKDIR}/sub.txt"

# 环境变量获取
KOMARI_HOST = os.environ.get('KOMARI_HOST', 'https://km.bcbc.pp.ua').strip()
KOMARI_TOKEN = os.environ.get('KOMARI_TOKEN', '3vvAQAdXAjO8oA1Nl5u25g').strip()
UUID = os.environ.get('UUID', 'c9a63b58-6e2e-4c19-8940-53f7f74aae4b')
ARGO_AUTH = os.environ.get('ARGO_AUTH', 'eyJhIjoiMzM5OTA1ZWFmYjM2OWM5N2M2YjZkYTI4NTgxMjlhMjQiLCJ0IjoiM2VlZTQyNzItZTQwZS00YmUzLThkYzQtMWU0MWFhZmUwNWMxIiwicyI6Ik1USTRaREl5WkRndFpqYzBaaTAwTkdJd0xXSTFaREl0WmpjME5EZ3pNRFV3TkdNMyJ9')
ARGO_DOMAIN = os.environ.get('ARGO_DOMAIN', 'stre.61154321.dpdns.org')
NAME = os.environ.get('NAME', 'StreamlitNode')
CFIP = os.environ.get('CFIP', 'www.visa.com.tw')
CFPORT = int(os.environ.get('CFPORT', '443'))
ARGO_PORT = 8001

# ==========================================
# === 核心逻辑
# ==========================================

def log(msg):
    """写日志"""
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] {msg}")
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{t}] {msg}\n")
    except: pass

def init_env():
    """初始化环境"""
    if not os.path.exists(WORKDIR):
        os.makedirs(WORKDIR, exist_ok=True)
    # 不删除旧日志，避免刷新丢失信息
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f: f.write("--- Init ---\n")

def download_file(filename, url):
    """下载文件"""
    dest = f"{WORKDIR}/{filename}"
    if os.path.exists(dest): return
    log(f"Downloading {filename}...")
    try:
        if "github.com" in url: url = f"https://ghfast.top/{url}"
        r = requests.get(url, stream=True, timeout=30)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192): f.write(chunk)
        os.chmod(dest, 0o775)
        log(f"Installed {filename}")
    except Exception as e:
        log(f"Download Error {filename}: {e}")

def prepare_binaries():
    download_file("web", "https://github.com/eooce/test/releases/download/123/web")
    download_file("bot", "https://github.com/eooce/test/releases/download/amd64/bot")
    if KOMARI_HOST:
        download_file("komari-agent", "https://github.com/komari-monitor/komari-agent/releases/latest/download/komari-agent-linux-amd64")

def generate_nodes(domain):
    """生成节点文件"""
    node_name = f"{NAME}-Streamlit"
    
    # VLESS
    vless = f"vless://{UUID}@{CFIP}:{CFPORT}?encryption=none&security=tls&sni={domain}&fp=chrome&type=ws&host={domain}&path=%2Fvless-argo%3Fed%3D2048#{node_name}"
    
    # VMESS
    vmess_json = {
        "v": "2", "ps": node_name, "add": CFIP, "port": str(CFPORT), "id": UUID, "aid": "0",
        "scy": "none", "net": "ws", "type": "none", "host": domain,
        "path": "/vmess-argo?ed=2048", "tls": "tls", "sni": domain, "alpn": "", "fp": "chrome"
    }
    vmess = f"vmess://{base64.b64encode(json.dumps(vmess_json).encode()).decode()}"
    
    # Trojan
    trojan = f"trojan://{UUID}@{CFIP}:{CFPORT}?security=tls&sni={domain}&fp=chrome&type=ws&host={domain}&path=%2Ftrojan-argo%3Fed%3D2048#{node_name}"

    content = f"{vless}\n\n{vmess}\n\n{trojan}"
    
    # 写入文件
    try:
        with open(LIST_FILE, "w") as f: f.write(content)
        with open(SUB_FILE, "w") as f: f.write(base64.b64encode(content.encode()).decode())
        log(f"✅ Nodes generated for: {domain}")
        return True
    except Exception as e:
        log(f"❌ Node Gen Error: {e}")
        return False

def generate_xray_config():
    config = {
        "log": {"access": "/dev/null", "error": "/dev/null", "loglevel": "none"},
        "inbounds": [
            {
                "port": ARGO_PORT, 
                "protocol": "vless",
                "settings": {
                    "clients": [{"id": UUID, "flow": "xtls-rprx-vision"}],
                    "decryption": "none",
                    "fallbacks": [
                        {"dest": 3001}, 
                        {"path": "/vless-argo", "dest": 3002}, 
                        {"path": "/vmess-argo", "dest": 3003}, 
                        {"path": "/trojan-argo", "dest": 3004}
                    ]
                },
                "streamSettings": {"network": "tcp"}
            },
            {"port": 3001, "listen": "127.0.0.1", "protocol": "vless", "settings": {"clients": [{"id": UUID}], "decryption": "none"}, "streamSettings": {"network": "ws", "security": "none"}},
            {"port": 3002, "listen": "127.0.0.1", "protocol": "vless", "settings": {"clients": [{"id": UUID, "level": 0}], "decryption": "none"}, "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/vless-argo"}}, "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]}},
            {"port": 3003, "listen": "127.0.0.1", "protocol": "vmess", "settings": {"clients": [{"id": UUID, "alterId": 0}]}, "streamSettings": {"network": "ws", "wsSettings": {"path": "/vmess-argo"}}, "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]}},
            {"port": 3004, "listen": "127.0.0.1", "protocol": "trojan", "settings": {"clients": [{"password": UUID}]}, "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/trojan-argo"}}, "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]}}
        ],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}, {"protocol": "blackhole", "tag": "block"}]
    }
    with open(f"{WORKDIR}/config.json", "w") as f:
        json.dump(config, f, indent=2)

def start_process(cmd):
    # 使用 >> 追加日志，防止覆盖
    full_cmd = f"stdbuf -oL {cmd} >> {LOG_FILE} 2>&1 &"
    subprocess.Popen(full_cmd, shell=True, cwd=WORKDIR)

def run_services():
    # 1. Start Xray
    start_process(f"./web -c config.json")
    
    # 2. Start Komari (修复后的参数)
    if KOMARI_HOST and KOMARI_TOKEN:
        start_process(f"./komari-agent -e {KOMARI_HOST} -t {KOMARI_TOKEN} --disable-web-ssh --disable-auto-update")
    
    # 3. Start Argo
    if os.path.exists(f"{WORKDIR}/bot"):
        if ARGO_AUTH:
            if "TunnelSecret" in ARGO_AUTH:
                with open(f"{WORKDIR}/tunnel.json", "w") as f: f.write(ARGO_AUTH)
                tid = ARGO_AUTH.split('"')[11]
                yml = f"tunnel: {tid}\ncredentials-file: {WORKDIR}/tunnel.json\nprotocol: http2\ningress:\n  - hostname: {ARGO_DOMAIN}\n    service: http://localhost:{ARGO_PORT}\n    originRequest:\n      noTLSVerify: true\n  - service: http_status:404"
                with open(f"{WORKDIR}/tunnel.yml", "w") as f: f.write(yml)
                start_process(f"./bot tunnel --config tunnel.yml run")
                generate_nodes(ARGO_DOMAIN) # 固定域名直接生成
            else:
                start_process(f"./bot tunnel --no-autoupdate run --token {ARGO_AUTH}")
                if ARGO_DOMAIN: generate_nodes(ARGO_DOMAIN)
        else:
            # 临时隧道
            start_process(f"./bot tunnel --no-autoupdate --url http://localhost:{ARGO_PORT}")

# ==========================================
# === UI 逻辑
# ==========================================
def main():
    st.set_page_config(page_title="Komari Dashboard", layout="wide")
    st.title("⚡ Komari & Xray Dashboard")

    # 1. 首次运行初始化
    if "init_ok" not in st.session_state:
        init_env()
        # 先生成一个假的节点，证明 UI 是好的
        generate_nodes("WAITING_FOR_TUNNEL.com") 
        prepare_binaries()
        generate_config()
        run_services()
        st.session_state["init_ok"] = True
        st.toast("Services Started")

    # 2. 尝试从日志获取 Argo 域名
    argo_url = "Scanning logs..."
    if ARGO_DOMAIN:
        argo_url = ARGO_DOMAIN
    elif os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f:
                content = f.read()
                match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', content)
                if match:
                    domain = match.group(0).replace("https://", "")
                    argo_url = domain
                    # 发现新域名，更新节点文件
                    generate_nodes(domain)
        except: pass

    # 3. 显示区域
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📡 Status")
        st.info(f"**Argo Domain:** {argo_url}")
        st.info(f"**Komari:** {'✅ Configured' if KOMARI_HOST else '❌ Not Configured'}")
        
        # 显示工作目录文件列表 (调试神器)
        st.subheader("📂 File System Check")
        try:
            files = os.listdir(WORKDIR)
            st.code(f"Files in {WORKDIR}:\n" + "\n".join(files))
        except Exception as e:
            st.error(f"Cannot read dir: {e}")

    with col2:
        st.subheader("🚀 Node Links (list.txt)")
        if os.path.exists(LIST_FILE):
            with open(LIST_FILE, "r") as f:
                st.code(f.read(), language="text")
        else:
            st.error(f"list.txt not found at {LIST_FILE}")
            
        st.subheader("📜 Subscription (Base64)")
        if os.path.exists(SUB_FILE):
            with open(SUB_FILE, "r") as f:
                st.text_area("Sub Content", f.read(), height=100)

    # 4. 完整日志
    with st.expander("查看完整后台日志 (Full Logs)", expanded=True):
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                lines = f.readlines()
                st.code("".join(lines[-30:]))
        else:
            st.write("No logs yet.")

    # 自动刷新
    time.sleep(3)
    st.rerun()

if __name__ == "__main__":
    main()
