async function renderWorkspace() {
  $('#workspace-context').innerHTML=`<a href="/workspace.html" class="workspace-home-link" aria-label="返回工作空间首页">工作空间</a><strong class="current-project" title="${esc(state.title)}">${esc(state.title)}</strong>`;
}
