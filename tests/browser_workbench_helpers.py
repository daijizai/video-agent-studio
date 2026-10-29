"""Shared navigation for the compact workspace's existing browser fixtures."""
from urllib.parse import urlsplit


def workspace_home(page):
    url=urlsplit(page.url)
    page.goto(f'{url.scheme}://{url.netloc}/workspace.html')


def new_project(page, title):
    workspace_home(page)
    page.get_by_role('button',name='＋ 新建项目',exact=True).click()
    page.get_by_label('项目名称',exact=True).fill(title)
    page.get_by_role('button',name='创建并打开',exact=True).click()
    page.locator('.current-project').filter(has_text=title).wait_for()


def switch_project(page, project_id, route='shots'):
    workspace_home(page)
    page.locator(f'[data-open="{project_id}"]').click()
    page.locator('.current-project').wait_for()
    page.goto(page.url.split('#')[0]+'#'+route)


def open_material_details(page, card=None):
    (card if card is not None else page.locator('.material-card').first).locator('[data-detail]').click()


def open_shot_feedback(page, index=0):
    page.locator('.shot').nth(index).locator('[data-shot-panel="feedback"]').click()
