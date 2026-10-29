"""Optional Playwright verification; does not submit generation jobs."""
from playwright.sync_api import sync_playwright
import os
with sync_playwright() as p:
    browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(os.getenv('STUDIO_URL','http://127.0.0.1:8765'));page.get_by_role('heading',name='把故事，推进到下一帧。').wait_for()
    for name in ['剧本','素材资产库','分镜工作台','视频制作','工具与设置','制作总览']:
        page.locator('nav').get_by_role('link',name=name).click();page.locator('h1').wait_for()
    for width in [375,768,1440]:
        page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors,errors
    browser.close();print('Browser navigation and responsive checks passed')
