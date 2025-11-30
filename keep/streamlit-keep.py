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
    针对Streamlit应用的自动唤醒脚本 (调试增强版 + Shadow DOM 支持 + iframe 文本深度检查)
    """
    
    APP_URL = os.environ.get("STREAMLIT_APP_URL", "")
    INITIAL_WAIT_TIME = 15
    POST_CLICK_WAIT_TIME = 20
    # 定义多个可能的关键词，命中任意一个即认为处于休眠状态
    TARGET_KEYWORDS = [
        "Yes, get this app back up",
        "Your app has gone to sleep",
        "Wake up"
    ]
    
    # 按钮定位：匹配关键词
    BUTTON_SELECTOR = f"//button[contains(., 'Yes, get this app back up') or contains(., 'Wake up')]"
    
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

    def check_text_in_current_context(self, context_name="Main Context"):
        """获取当前上下文（主页面或iframe）的可见文本并检查关键词"""
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            # 获取可见文本
            text_content = body.text
            # 如果 body.text 为空（有时候 ShadowDOM 会导致这种情况），尝试获取 innerHTML 的简化版
            if not text_content.strip():
                text_content = self.driver.execute_script("return document.body.innerText || document.body.textContent;")
            
            # 打印前 100 个字符用于调试，让我们知道 Selenium 到底看到了什么
            preview_text = text_content.strip().replace('\n', ' ')[:100]
            logger.info(f"👀 [{context_name}] 页面可见文本前100字: '{preview_text}...'")

            for keyword in self.TARGET_KEYWORDS:
                if keyword in text_content:
                    logger.info(f"🎯 [{context_name}] 发现休眠关键词: '{keyword}'")
                    return True
            return False
        except Exception as e:
            logger.warning(f"⚠️ [{context_name}] 获取文本失败: {e}")
            return False

    def check_page_text_content_recursive(self):
        """递归检查主页面和所有 iframe 中的文本"""
        logger.info("🔎 开始全局文本检查 (Main + Iframes)...")
        
        # 1. 检查主页面
        self.driver.switch_to.default_content()
        if self.check_text_in_current_context("Main Page"):
            return True

        # 2. 检查 iframe
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                logger.info(f"🔢 发现 {len(iframes)} 个 iframe，正在逐个检查文本...")
            
            for i, iframe in enumerate(iframes):
                try:
                    self.driver.switch_to.default_content() # 先切回主，再切入 iframe
                    self.driver.switch_to.frame(iframe)
                    if self.check_text_in_current_context(f"Iframe-{i+1}"):
                        self.driver.switch_to.default_content()
                        return True
                except Exception as e:
                    logger.warning(f"⚠️ 检查 iframe[{i}] 文本时出错: {e}")
        except Exception as e:
            logger.error(f"❌ 遍历 iframe 出错: {e}")
        finally:
            self.driver.switch_to.default_content()
            
        logger.info("💨 全局检查结束，未发现任何休眠关键词。")
        return False

    def click_shadow_dom_button(self):
        """
        使用 JavaScript 递归查找 Shadow DOM 中的按钮并点击
        """
        logger.info("🕵️‍♂️ 启动 Shadow DOM 深度扫描...")
        
        js_script = """
        function findAndClickButton(root, keywords) {
            // 1. 查找当前 root 下的按钮
            let buttons = Array.from(root.querySelectorAll('button'));
            for (let btn of buttons) {
                // 检查按钮文本是否包含任意关键词
                for (let keyword of keywords) {
                    if (btn.innerText.includes(keyword)) {
                        console.log("Found button in Shadow DOM: " + btn.innerText);
                        btn.click();
                        return true;
                    }
                }
            }
            
            // 2. 递归查找所有子元素的 shadowRoot
            let allElements = Array.from(root.querySelectorAll('*'));
            for (let el of allElements) {
                if (el.shadowRoot) {
                    if (findAndClickButton(el.shadowRoot, keywords)) return true;
                }
            }
            return false;
        }
        return findAndClickButton(document, arguments[0]);
        """
        
        try:
            # 传入 TARGET_KEYWORDS 列表
            found = self.driver.execute_script(js_script, self.TARGET_KEYWORDS)
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
        
        # 1. 尝试常规方法 (WebDriverWait)
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

        # 2. 尝试 Shadow DOM 方法
        if self.click_shadow_dom_button():
            logger.info(f"✅ 在 {context_description} 使用 Shadow DOM 方法点击成功。")
            return True

        logger.info(f"❌ 在 {context_description} 所有方法均尝试失败。")
        return False

    def is_app_woken_up(self):
        """
        判断是否唤醒：
        1. 检查是否还能找到按钮（常规+Shadow DOM）
        2. 全局递归检查页面文本
        """
        logger.info("🧐 检查唤醒状态...")
        self.driver.switch_to.default_content()
        
        # 如果文本里还有那句话，说明肯定没醒
        if self.check_page_text_content_recursive():
            logger.info("❌ 唤醒关键词仍在页面(或iframe)文本中，应用未唤醒。")
            return False
            
        logger.info("✅ 关键词消失，判定唤醒成功。")
        return True

    def wakeup_app(self):
        if not self.APP_URL:
            raise Exception("⚠️ 环境变量 STREAMLIT_APP_URL 未配置。")
            
        logger.info(f"👉 访问: {self.APP_URL}")
        self.driver.get(self.APP_URL)
        logger.info(f"📄 Page Title: {self.driver.title}")
        
        logger.info(f"⏳ 等待加载 {self.INITIAL_WAIT_TIME} 秒...")
        time.sleep(self.INITIAL_WAIT_TIME)
        
        # 1. 文本预检 (包含 iframe)
        has_text = self.check_page_text_content_recursive()
        
        if not has_text:
            logger.info("⚠️ [诊断] 页面加载后未发现休眠关键词。")
            self.save_debug_artifacts("no_text_found")
            # 明确提示用户脚本能力的边界
            return True, "✅ 应用处于运行状态（未休眠）。\n⚠️ 注意：脚本运行在‘访客模式’，无法看到或点击‘重启应用’按钮。如果应用卡死，请手动登录重启。"
        
        # 2. 尝试点击 (主页面)
        click_success = self.find_and_click_button("主页面")
        
        # 3. 尝试点击 (iframe)
        if not click_success:
            logger.info("👉 尝试进入 iframe 查找...")
            try:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                for i, iframe in enumerate(iframes):
                    try:
                        self.driver.switch_to.default_content()
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
            if has_text:
                self.save_debug_artifacts("click_failed_but_text_exists")
                return False, "❌ 检测到休眠文本，但无法定位或点击按钮（Shadow DOM 扫描也失败）。"
            
            # 再次检查状态
            if self.is_app_woken_up():
                 return True, "✅ 应用处于运行状态（未休眠）。\n⚠️ 注意：脚本运行在‘访客模式’，无法看到或点击‘重启应用’按钮。如果应用卡死，请手动登录重启。"
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
