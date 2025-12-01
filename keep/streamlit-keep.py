import os
import time
import logging
import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StreamlitAppWaker:
    """
    Streamlit 自动唤醒脚本 - 针对 "Zzzz" 休眠界面优化
    """
    APP_URL = os.environ.get("STREAMLIT_APP_URL", "https://clxxbzd8esxpas3xpofbzw.streamlit.app")
    # 增加一点等待时间，确保休眠界面完全渲染
    INITIAL_WAIT_TIME = 18
    POST_CLICK_WAIT_TIME = 20
    
    # 1. 休眠关键词 (基于您的截图精确匹配)
    SLEEP_KEYWORDS = [
        "Zzzz",                          # 标题
        "This app has gone to sleep",    # 正文 (注意是 This 不是 Your)
        "Yes, get this app back up"      # 按钮文本
    ]
    
    # 2. 崩溃关键词 (需要人工介入)
    CRASH_KEYWORDS = [
        "Oh no",
        "Error running app",
        "Streamlit server is currently unavailable"
    ]
    
    # 按钮定位 (匹配截图中的蓝色按钮)
    # 匹配文本包含 "Yes, get this app back up" 的按钮
    BUTTON_SELECTOR = "//button[contains(., 'Yes, get this app back up')]"
    
    def __init__(self):
        self.driver = None
        self.setup_driver()
    
    def setup_driver(self):
        logger.info("⚙️ 正在设置Chrome驱动...")
        chrome_options = Options()
        
        if os.getenv('GITHUB_ACTIONS'):
            logger.info("⚙️ 检测到CI环境，启用headless模式。")
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')

        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--ignore-certificate-errors')
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logger.info("✅ Chrome驱动设置完成。")
        except Exception as e:
            logger.error(f"❌ 驱动初始化失败: {e}")
            raise

    def save_debug_artifacts(self, suffix="error"):
        """保存截图和源码，方便出问题时查看"""
        if not self.driver: return
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            self.driver.save_screenshot(f"debug_{suffix}_{timestamp}.png")
            with open(f"debug_{suffix}_{timestamp}.html", "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            logger.info(f"📸 [DEBUG] 已保存截图: debug_{suffix}_{timestamp}.png")
        except Exception:
            pass

    def check_text_in_context(self, context_name):
        """检查当前页面(或iframe)的文本内容"""
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            text = body.text
            
            # 如果 body.text 为空，尝试 JS 获取
            if not text.strip():
                text = self.driver.execute_script("return document.body.innerText || document.body.textContent;")
            
            # 1. 先检查是不是崩了
            for keyword in self.CRASH_KEYWORDS:
                if keyword in text:
                    logger.error(f"🚨 [{context_name}] 发现崩溃关键词: '{keyword}'")
                    return 2, keyword  # 状态2: 崩溃
            
            # 2. 再检查是不是睡了
            for keyword in self.SLEEP_KEYWORDS:
                if keyword in text:
                    logger.info(f"💤 [{context_name}] 发现休眠关键词: '{keyword}'")
                    return 1, keyword  # 状态1: 休眠
                    
            return 0, None # 状态0: 正常运行
        except Exception as e:
            logger.warning(f"⚠️ [{context_name}] 文本获取失败: {e}")
            return 0, None

    def scan_page_status(self):
        """扫描主页面和所有iframe"""
        # 1. 检查主页面
        self.driver.switch_to.default_content()
        status, keyword = self.check_text_in_context("Main")
        if status != 0: return status, keyword, None

        # 2. 检查 iframe (Streamlit 有时把内容放在 iframe 里)
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for i, iframe in enumerate(iframes):
                self.driver.switch_to.default_content()
                self.driver.switch_to.frame(iframe)
                status, keyword = self.check_text_in_context(f"Iframe-{i}")
                if status != 0: 
                    self.driver.switch_to.default_content()
                    return status, keyword, i
                self.driver.switch_to.default_content()
        except Exception:
            pass
            
        return 0, None, None

    def find_and_click_wakeup(self, iframe_index=None):
        """尝试点击唤醒按钮"""
        # 如果目标在 iframe 里，先切进去
        if iframe_index is not None:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            if len(iframes) > iframe_index:
                self.driver.switch_to.frame(iframes[iframe_index])
        
        # 1. 常规点击
        try:
            logger.info(f"👆 尝试点击按钮: {self.BUTTON_SELECTOR}")
            btn = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.XPATH, self.BUTTON_SELECTOR)))
            self.driver.execute_script("arguments[0].scrollIntoView(true);", btn)
            time.sleep(1)
            btn.click()
            return True
        except Exception as e:
            logger.warning(f"常规点击失败: {e}")
            pass
            
        # 2. Shadow DOM 点击 (终极方案)
        # 很多时候按钮被 Shadow Root 包裹，普通 Selenium 找不到
        js = """
        function scan(root) {
            if(root.querySelectorAll) {
                // 查找所有按钮
                root.querySelectorAll('button').forEach(b => {
                    // 如果按钮文字包含关键词，就点它
                    if(b.innerText.includes('Yes, get this app') || b.innerText.includes('Wake up')) {
                        console.log('Found button in Shadow DOM, clicking...');
                        b.click();
                    }
                });
                // 递归查找 Shadow Root
                root.querySelectorAll('*').forEach(e => { if(e.shadowRoot) scan(e.shadowRoot); });
            }
        }
        scan(document);
        """
        try:
            logger.info("🕵️‍♂️ 尝试 Shadow DOM 穿透点击...")
            self.driver.execute_script(js)
            time.sleep(2)
            return True
        except:
            return False

    def run_check(self):
        if not self.APP_URL: raise Exception("⚠️ 未配置 STREAMLIT_APP_URL")
        
        logger.info(f"👉 访问: {self.APP_URL}")
        self.driver.get(self.APP_URL)
        logger.info(f"⏳ 等待页面加载 {self.INITIAL_WAIT_TIME} 秒...")
        time.sleep(self.INITIAL_WAIT_TIME)
        
        # --- 第一次扫描 ---
        status, keyword, iframe_idx = self.scan_page_status()
        
        if status == 2:
            # 崩溃
            self.save_debug_artifacts("crash")
            return False, f"❌ 应用已崩溃 (发现 '{keyword}')！请手动登录重启。"
            
        elif status == 1:
            # 休眠 -> 执行唤醒
            logger.info(f"💤 检测到休眠状态 (发现 '{keyword}')，正在尝试唤醒...")
            
            # 尝试点击
            self.find_and_click_wakeup(iframe_idx)
            
            logger.info(f"⏳ 点击完成，等待应用启动 {self.POST_CLICK_WAIT_TIME} 秒...")
            time.sleep(self.POST_CLICK_WAIT_TIME)
            
            # --- 复查 ---
            # 唤醒后，页面应该刷新，我们再看一次状态
            self.driver.switch_to.default_content() # 切回主页面复查
            status, keyword, _ = self.scan_page_status()
            
            if status == 0:
                return True, "✅ 唤醒操作已执行，且休眠提示已消失，应用正在启动中！"
            elif status == 1:
                self.save_debug_artifacts("wakeup_failed")
                return False, "❌ 尝试了点击按钮，但页面依然显示休眠状态，唤醒可能失败。"
            elif status == 2:
                self.save_debug_artifacts("crash_after_wake")
                return False, "❌ 唤醒过程中应用崩溃。"
                
        else:
            # 正常
            # 这里我们不报错，因为如果应用本身就是醒着的，脚本任务也算完成了
            return True, "✅ 应用处于运行状态 (未检测到 Zzzz 休眠信号)。"

    def run(self):
        try:
            success, result = self.run_check() 
            return success, result
        except Exception as e:
            logger.error(f"❌ 脚本运行出错: {e}")
            if self.driver: self.save_debug_artifacts("script_error")
            return False, str(e)
        finally:
            if self.driver: 
                logger.info("🧹 关闭浏览器...")
                self.driver.quit()

def main():
    waker = StreamlitAppWaker()
    success, result = waker.run()
    logger.info(f"🏁 最终结果: {result}")
    
    # 只要不是脚本出错或应用崩溃，都算 Pass (exit 0)
    # 如果唤醒失败或应用崩溃，报 Fail (exit 1) 以便发送通知
    exit(0 if success else 1)

if __name__ == "__main__":
    main()
