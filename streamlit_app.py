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
# === 配置区域
# ==========================================
# 核心路径 (固定)
WORKDIR = "/tmp/komari-run"
LOG_FILE = f"{WORKDIR}/boot.log"
LIST_FILE = f"{WORKDIR}/list.txt"
SUB_FILE = f"{WORKDIR}/sub.txt"

# 环境变量
KOMARI_HOST = os.environ.get('KOMARI_HOST', 'https://km.bcbc.pp.ua').strip()
KOMARI_TOKEN = os.environ.get('KOMARI_TOKEN', '3vvAQAdXAjO8oA1Nl5u25g').strip()
UUID = os.environ.get('UUID', '20e6e496-cf19-45c8-b883-14f5e11cd9f1')
ARGO_AUTH = os.environ.get('ARGO_AUTH', '')
ARGO_DOMAIN = os.environ.get('ARGO_DOMAIN', '')
NAME = os.environ.get('NAME', 'StreamlitNode')
CFIP = os.environ.get('CFIP', 'www.visa.com.tw')
CFPORT = int(os.environ.get('CFPORT', '443'))
ARGO_PORT = 8001

# ==========================================
# === 核心逻辑
# ==========================================

def log(msg):
    """日志仅输出到后台控制台和文件(用于抓取域名)，不再显示在UI"""
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] {msg}")
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{t}] {msg}\n")
    except: pass

def init_env():
    if not os.path.exists(WORKDIR):
        os.makedirs(WORKDIR, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f: f.write("--- Init ---\n")

def download_file(filename, url):
    dest = f"{WORKDIR}/{filename}"
    if os.path.exists(dest): return
    log(f"Downloading {filename}...")
    try:
        if "github.com" in url: url = f"https://ghfast.top/{url}"
        r = requests.get(url, stream=True, timeout=30)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192): f.write(chunk)
        os.chmod(dest, 0o775)
    except Exception as e:
        log(f"Download Error {filename}: {e}")

def prepare_binaries():
    download_file("web", "https://github.com/eooce/test/releases/download/123/web")
    download_file("bot", "https://github.com/eooce/test/releases/download/amd64/bot")
    if KOMARI_HOST:
        download_file("komari-agent", "https://github.com/komari-monitor/komari-agent/releases/latest/download/komari-agent-linux-amd64")

def generate_nodes(domain):
    """生成节点文件并打印到控制台"""
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
        
        # --- 关键：在官方日志区域输出节点信息 ---
        print("\n" + "="*40)
        print("⚡ NODE LINKS GENERATED (Copy from here) ⚡")
        print("="*40)
        print(content)
        print("="*40 + "\n")
        
        return True
    except Exception as e:
        log(f"Node Gen Error: {e}")
        return False

def generate_config():
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
    # 使用 >> 追加日志
    full_cmd = f"stdbuf -oL {cmd} >> {LOG_FILE} 2>&1 &"
    subprocess.Popen(full_cmd, shell=True, cwd=WORKDIR)

def run_services():
    # 1. Start Xray
    start_process(f"./web -c config.json")
    
    # 2. Start Komari
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
                generate_nodes(ARGO_DOMAIN) 
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
        prepare_binaries()
        generate_config()
        run_services()
        st.session_state["init_ok"] = True
        st.toast("Services Started")

    # 2. 尝试从日志获取 Argo 域名
    argo_url = "Scanning..."
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
                    # 发现新域名，避免重复生成
                    current_node = ""
                    if os.path.exists(LIST_FILE):
                        with open(LIST_FILE, "r") as lf: current_node = lf.read()
                    
                    if domain not in current_node:
                        generate_nodes(domain)
        except: pass

    # 3. 显示区域 (简洁版)
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📡 Status")
        st.success(f"**Argo Domain:** {argo_url}")
        st.info(f"**Komari:** {'✅ Online' if KOMARI_HOST else '❌ Not Configured'}")
        
        # 显示 Base64 订阅内容供复制
        if os.path.exists(SUB_FILE):
            st.text_input("Subscription URL (Auto-copy)", f"https://{argo_url}/sub" if "trycloudflare" in argo_url else "Check Logs")
            with open(SUB_FILE, "r") as f:
                st.text_area("Base64 Subscription", f.read(), height=100)

    with col2:
        st.subheader("🚀 Node Links")
        if os.path.exists(LIST_FILE):
            with open(LIST_FILE, "r") as f:
                st.code(f.read(), language="text")
        else:
            st.warning("Waiting for Argo Tunnel...")

    # 自动刷新
    time.sleep(5)
    st.rerun()

if __name__ == "__main__":
    main()
