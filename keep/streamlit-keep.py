import os
import time
import logging
import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StreamlitAppWaker:
    """
    针对Streamlit应用的自动唤醒脚本 (调试增强版 + Shadow DOM 支持)
    """
    
    APP_URL = os.environ.get("STREAMLIT_APP_URL", "https://idralguxkuj6pvd8sukcww.streamlit.app")
    INITIAL_WAIT_TIME = 15
    POST_CLICK_WAIT_TIME = 20
    TARGET_TEXT = "Yes, get this app back up"
    # 普通 XPath 定位
    BUTTON_SELECTOR = f"//button[contains(., '{TARGET_TEXT}')]"
    
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
        else:
            # 本地调试可以注释掉 headless
            # chrome_options.add_argument('--headless') 
            pass

        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--allow-running-insecure-content')
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logger.info("✅ Chrome驱动设置完成。")
        except Exception as e:
            logger.error(f"❌ 驱动初始化失败: {e}")
            raise

    def save_debug_artifacts(self, suffix="error"):
        """保存截图和HTML源码用于调试"""
        if not self.driver:
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_name = f"debug_{suffix}_{timestamp}.png"
        html_name = f"debug_{suffix}_{timestamp}.html"
        
        try:
            self.driver.save_screenshot(screenshot_name)
            logger.info(f"📸 [DEBUG] 已保存截图: {screenshot_name}")
        except Exception as e:
            logger.warning(f"⚠️ 无法保存截图: {e}")

        try:
            with open(html_name, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            logger.info(f"📄 [DEBUG] 已保存页面源码: {html_name}")
        except Exception as e:
            logger.warning(f"⚠️ 无法保存页面源码: {e}")

    def check_page_text_content(self):
        """检查页面纯文本中是否包含唤醒关键词"""
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            if self.TARGET_TEXT in body_text:
                logger.info(f"👀 [文本检查] 页面文本中发现了关键词: '{self.TARGET_TEXT}' -> 说明应用确实在休眠。")
                return True
            else:
                logger.info(f"👀 [文本检查] 页面文本中未发现关键词。")
                return False
        except Exception as e:
            logger.warning(f"⚠️ 无法获取页面文本: {e}")
            return False

    def click_shadow_dom_button(self):
        """
        使用 JavaScript 递归查找 Shadow DOM 中的按钮并点击
        这是解决 '找到 visible button' 问题的关键
        """
        logger.info("🕵️‍♂️ 启动 Shadow DOM 深度扫描...")
        
        js_script = """
        function findAndClickButton(root) {
            // 1. 查找当前 root 下的按钮
            let buttons = Array.from(root.querySelectorAll('button'));
            for (let btn of buttons) {
                if (btn.innerText.includes(arguments[0])) {
                    console.log("Found button in Shadow DOM!");
                    btn.click();
                    return true;
                }
            }
            
            // 2. 递归查找所有子元素的 shadowRoot
            let allElements = Array.from(root.querySelectorAll('*'));
            for (let el of allElements) {
                if (el.shadowRoot) {
                    if (findAndClickButton(el.shadowRoot)) return true;
                }
            }
            return false;
        }
        return findAndClickButton(document);
        """
        
        try:
            found = self.driver.execute_script(js_script, self.TARGET_TEXT)
            if found:
                logger.info("✅ 通过 JavaScript 在 Shadow DOM 中找到并点击了按钮！")
                return True
            else:
                logger.info("❌ Shadow DOM 深度扫描也未找到按钮。")
                return False
        except Exception as e:
            logger.error(f"❌ 执行 Shadow DOM 脚本时出错: {e}")
            return False

    def find_and_click_button(self, context_description="主页面"):
        logger.info(f"🔍 尝试在 {context_description} 查找唤醒按钮...")
        
        # 1. 尝试常规方法
        try:
            button = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, self.BUTTON_SELECTOR))
            )
            if button.is_displayed() and button.is_enabled():
                self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
                time.sleep(1) 
                button.click()
                logger.info(f"✅ 在 {context_description} 使用常规方法点击成功。")
                return True
        except TimeoutException:
            pass
        except Exception as e:
            logger.warning(f"⚠️ 常规点击尝试失败: {e}")

        # 2. 尝试 Shadow DOM 方法 (如果常规方法失败)
        if self.click_shadow_dom_button():
            logger.info(f"✅ 在 {context_description} 使用 Shadow DOM 方法点击成功。")
            return True

        logger.info(f"❌ 在 {context_description} 所有方法均尝试失败。")
        return False

    def is_app_woken_up(self):
        """
        判断是否唤醒：
        1. 检查是否还能找到按钮（常规+Shadow DOM）
        2. 检查页面文本是否还包含关键词
        """
        logger.info("🧐 检查唤醒状态...")
        self.driver.switch_to.default_content()
        
        # 如果文本里还有那句话，说明肯定没醒
        if self.check_page_text_content():
            logger.info("❌ 唤醒关键词仍在页面文本中，应用未唤醒。")
            return False
            
        # 再次确认是否有按钮存在
        try:
            # 简单检查常规 DOM
            WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located((By.XPATH, self.BUTTON_SELECTOR))
            )
            logger.info("❌ 唤醒按钮仍在 DOM 中。")
            return False
        except TimeoutException:
            pass
            
        logger.info("✅ 关键词消失且找不到按钮，判定唤醒成功。")
        return True

    def wakeup_app(self):
        if not self.APP_URL:
            raise Exception("⚠️ 环境变量 STREAMLIT_APP_URL 未配置。")
            
        logger.info(f"👉 访问: {self.APP_URL}")
        self.driver.get(self.APP_URL)
        logger.info(f"📄 Page Title: {self.driver.title}")
        
        logger.info(f"⏳ 等待加载 {self.INITIAL_WAIT_TIME} 秒...")
        time.sleep(self.INITIAL_WAIT_TIME)
        
        # 1. 先看一眼页面上有没有那句话，如果没有，可能根本不需要唤醒
        has_text = self.check_page_text_content()
        if not has_text:
            logger.info("⚠️ 页面初次加载后未发现唤醒关键词。可能应用已唤醒，或页面加载完全失败。")
            # 这种情况下，我们再截图确认一下，但如果不抛错，流程会继续
            self.save_debug_artifacts("no_text_found")
        
        # 2. 尝试点击 (主页面)
        click_success = self.find_and_click_button("主页面")
        
        # 3. 尝试点击 (iframe)
        if not click_success:
            logger.info("👉 尝试进入 iframe 查找...")
            try:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                logger.info(f"🔢 发现 {len(iframes)} 个 iframe")
                
                for i, iframe in enumerate(iframes):
                    try:
                        self.driver.switch_to.frame(iframe)
                        if self.find_and_click_button(f"iframe[{i+1}]"):
                            click_success = True
                            break
                    except Exception as e:
                         logger.warning(f"处理 iframe[{i}] 出错: {e}")
                    finally:
                        self.driver.switch_to.default_content()
            except Exception as e:
                logger.error(f"❌ iframe 处理全流程出错: {e}")
                
        if not click_success:
            # 如果之前检测到了文本，但现在没点到按钮，那是严重的定位失败
            if has_text:
                self.save_debug_artifacts("click_failed_but_text_exists")
                return False, "❌ 检测到休眠文本，但无法定位或点击按钮（Shadow DOM 扫描也失败）。"
            
            # 如果没检测到文本，也没点到按钮，可能应用本来就是醒的
            if self.is_app_woken_up():
                return True, "✅ 应用似乎已是唤醒状态（未发现休眠文本）。" 
            else:
                self.save_debug_artifacts("unknown_state")
                return False, "⚠️ 状态未知：未找到按钮，但也未通过唤醒检查。"
        
        logger.info(f"⏳ 点击成功，等待应用启动 {self.POST_CLICK_WAIT_TIME} 秒...")
        time.sleep(self.POST_CLICK_WAIT_TIME)
        
        if self.is_app_woken_up():
            return True, "✅ 唤醒成功！"
        else:
            self.save_debug_artifacts("still_sleeping")
            return False, "❌ 点击后应用似乎仍未唤醒。"

    def run(self):
        try:
            logger.info("🚀 开始执行...")
            success, result = self.wakeup_app() 
            return success, result
        except Exception as e:
            logger.error(f"❌ 严重错误: {e}")
            if self.driver:
                self.save_debug_artifacts("crash")
            return False, str(e)
        finally:
            if self.driver:
                logger.info("🧹 关闭驱动...")
                self.driver.quit()

def main():
    app_url = os.environ.get("STREAMLIT_APP_URL", "")
    if not app_url:
        logger.warning("⚠️ 未配置 STREAMLIT_APP_URL，请设置环境变量。")
    
    waker = StreamlitAppWaker()
    success, result = waker.run()
    logger.info(f"🏁 结果: {result}")
    
    if success:
        exit(0)
    else:
        exit(1)

if __name__ == "__main__":
    main()
