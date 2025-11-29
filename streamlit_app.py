import streamlit as st
import os
import subprocess
import requests
import time
import threading
import json
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==========================================
# === 配置区域
# ==========================================
# 1. Komari 配置 (必填)
KOMARI_HOST = os.environ.get('KOMARI_HOST', 'https://km.bcbc.pp.ua')   # 必须带 http:// 或 https://
KOMARI_TOKEN = os.environ.get('KOMARI_TOKEN', 'vvAQAdXAjO8oA1Nl5u25g') # 密钥

# 2. 节点配置
UUID = os.environ.get('UUID', '8e3bd89a-4809-469e-99c5-ee9edeed7439')
ARGO_AUTH = os.environ.get('ARGO_AUTH', 'eyJhIjoiMzM5OTA1ZWFmYjM2OWM5N2M2YjZkYTI4NTgxMjlhMjQiLCJ0IjoiM2VlZTQyNzItZTQwZS00YmUzLThkYzQtMWU0MWFhZmUwNWMxIiwicyI6Ik1USTRaREl5WkRndFpqYzBaaTAwTkdJd0xXSTFaREl0WmpjME5EZ3pNRFV3TkdNMyJ9')       # Argo Token/Secret
ARGO_DOMAIN = os.environ.get('ARGO_DOMAIN', 'stre.61154321.dpdns.org')   # 固定域名
NAME = os.environ.get('NAME', 'StreamlitNode')

# 内部端口 (不要改)
ARGO_PORT = 8001
VPORT = 443
WORKDIR = "/tmp/komari_node"
LOG_FILE = f"{WORKDIR}/app.log"

# ==========================================
# === 核心逻辑
# ==========================================

def log(msg):
    """写入日志并打印"""
    timestamp = time.strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    print(formatted_msg)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(formatted_msg + "\n")
    except: pass

def init_env():
    """初始化目录和日志文件"""
    if not os.path.exists(WORKDIR):
        os.makedirs(WORKDIR)
    # 清空旧日志
    with open(LOG_FILE, "w") as f:
        f.write("--- Service Starting ---\n")

def download_file(filename, url):
    """下载文件"""
    dest = f"{WORKDIR}/{filename}"
    if os.path.exists(dest):
        log(f"File {filename} already exists, skipping download.")
        return True
        
    log(f"Downloading {filename} from {url}...")
    try:
        # 使用加速
        if "github.com" in url:
            url = f"https://ghfast.top/{url}"
        
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        os.chmod(dest, 0o775)
        log(f"Download {filename} success.")
        return True
    except Exception as e:
        log(f"Error downloading {filename}: {e}")
        return False

def prepare_binaries():
    """下载所需二进制文件 (强制 AMD64 适配 Streamlit)"""
    # 1. Xray (Web)
    download_file("web", "https://github.com/eooce/test/releases/download/123/web")
    
    # 2. Komari Agent (官方 AMD64)
    if KOMARI_HOST and KOMARI_TOKEN:
        download_file("komari-agent", "https://github.com/komari-monitor/komari-agent/releases/latest/download/komari-agent-linux-amd64")
    
    # 3. Argo (Bot) - 只有配置了 Argo 才下载
    # 默认下载 Cloudflared
    download_file("bot", "https://github.com/eooce/test/releases/download/amd64/bot")

def generate_config():
    """生成 Xray 配置文件"""
    log("Generating Xray config...")
    config = {
        "log": {"access": "/dev/null", "error": f"{WORKDIR}/xray_error.log", "loglevel": "warning"},
        "inbounds": [
            {
                "port": ARGO_PORT, # 监听 Argo 转发端口
                "protocol": "vless",
                "settings": {
                    "clients": [{"id": UUID, "flow": "xtls-rprx-vision"}],
                    "decryption": "none",
                    "fallbacks": [{"dest": 3001}, {"path": "/vless", "dest": 3002}]
                },
                "streamSettings": {"network": "tcp"}
            },
            {"port": 3001, "listen": "127.0.0.1", "protocol": "vless", "settings": {"clients": [{"id": UUID}], "decryption": "none"}, "streamSettings": {"network": "ws", "security": "none"}},
            {"port": 3002, "listen": "127.0.0.1", "protocol": "vless", "settings": {"clients": [{"id": UUID, "level": 0}], "decryption": "none"}, "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/vless"}}, "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]}}
        ],
        "outbounds": [{"protocol": "freedom"}]
    }
    with open(f"{WORKDIR}/config.json", "w") as f:
        json.dump(config, f, indent=2)

def start_process(name, cmd):
    """启动后台进程并将输出重定向到主日志"""
    log(f"Starting {name}...")
    # 使用 stdbuf -oL 强制行缓冲，让日志实时显示
    full_cmd = f"stdbuf -oL {cmd} >> {LOG_FILE} 2>&1 &"
    subprocess.Popen(full_cmd, shell=True, cwd=WORKDIR)

def run_services():
    """启动所有服务"""
    
    # 1. 启动 Xray
    start_process("Xray", f"./web -c config.json")
    
    # 2. 启动 Komari Agent
    if KOMARI_HOST and KOMARI_TOKEN:
        # 修正参数：-e Endpoint -t Token
        start_process("Komari Agent", f"./komari-agent -e {KOMARI_HOST} -t {KOMARI_TOKEN} --disable-command-execute --disable-auto-update")
    else:
        log("Komari config missing, skipping agent.")

    # 3. 启动 Argo Tunnel
    if os.path.exists(f"{WORKDIR}/bot"):
        if ARGO_AUTH and "TunnelSecret" in ARGO_AUTH:
            # 固定隧道 json 模式
            with open(f"{WORKDIR}/tunnel.json", "w") as f: f.write(ARGO_AUTH)
            tunnel_id = ARGO_AUTH.split('"')[11]
            yml = f"tunnel: {tunnel_id}\ncredentials-file: {WORKDIR}/tunnel.json\nprotocol: http2\ningress:\n  - hostname: {ARGO_DOMAIN}\n    service: http://localhost:{ARGO_PORT}\n    originRequest:\n      noTLSVerify: true\n  - service: http_status:404"
            with open(f"{WORKDIR}/tunnel.yml", "w") as f: f.write(yml)
            start_process("Argo (Fixed)", f"./bot tunnel --config tunnel.yml run")
        elif ARGO_AUTH:
            # Token 模式
            start_process("Argo (Token)", f"./bot tunnel --no-autoupdate run --token {ARGO_AUTH}")
        else:
            # 临时隧道模式
            start_process("Argo (Quick)", f"./bot tunnel --no-autoupdate --url http://localhost:{ARGO_PORT}")

# ==========================================
# === Streamlit UI 主入口
# ==========================================
def main():
    st.set_page_config(page_title="Komari Node Monitor", layout="wide")
    st.title("🚀 Komari Node & Agent Monitor")
    
    # 初始化环境
    if "init_done" not in st.session_state:
        init_env()
        prepare_binaries()
        generate_config()
        run_services()
        st.session_state["init_done"] = True
        st.toast("Services started!", icon="✅")

    # 实时日志显示区域
    st.subheader("📝 Real-time Logs")
    log_placeholder = st.empty()
    
    # 自动刷新日志
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
            # 显示最后 50 行
            log_content = "".join(lines[-50:])
            log_placeholder.code(log_content, language="text")
    else:
        log_placeholder.info("Waiting for logs...")

    # 提取 Argo 域名
    argo_url = "Waiting..."
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            content = f.read()
            # 查找临时隧道地址
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', content)
            if match:
                argo_url = match.group(0)
            elif ARGO_DOMAIN:
                argo_url = f"https://{ARGO_DOMAIN}"
    
    st.subheader("🔗 Connection Info")
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**Argo URL:** {argo_url}")
    with col2:
        st.info(f"**Komari Host:** {KOMARI_HOST if KOMARI_HOST else 'Not Configured'}")

    # 手动刷新按钮
    if st.button("Refresh Logs"):
        st.rerun()

    # 自动刷新 (利用 Streamlit 的机制保持活跃)
    time.sleep(2)
    st.rerun()

if __name__ == "__main__":
    main()
