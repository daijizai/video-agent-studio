async function renderWorkspace() {
  const workspace=await api('projects');
  $('.crumb').innerHTML=`<label for="project-select">工作空间 / </label><select id="project-select" aria-label="选择项目">${workspace.projects.map(p=>`<option value="${p.id}" ${p.id===state.project_id?'selected':''}>${esc(p.title)}${p.demo?' · 示例':''}</option>`).join('')}</select><button id="new-project">＋ 新建项目</button>`;
  $('.header-actions .badge').textContent=state.demo?'示例项目 · 策划内容':'独立项目 · 本机保存';
  $('#project-select').onchange=()=>act(async()=>{state=await api('projects/switch',{project_id:Number($('#project-select').value)});health=await api('health');toast('项目已切换，所有制作数据独立保存');render()});
  $('#new-project').onclick=()=>{
    const dialog=document.createElement('dialog');
    dialog.innerHTML=`<form id="new-project-form"><h2>创建项目</h2><p>剧本、角色、分镜、任务与预算独立保存。</p><label class="field" for="project-name">项目名称</label><input id="project-name" maxlength="80" required autocomplete="off"><div class="shot-actions"><button class="primary" type="submit">创建项目</button><button type="button" id="cancel-project">取消</button></div><p id="project-error" role="alert"></p></form>`;
    document.body.append(dialog);dialog.showModal();
    $('#cancel-project').onclick=()=>dialog.close();
    dialog.onclose=()=>dialog.remove();
    $('#new-project-form').onsubmit=async e=>{e.preventDefault();try{state=await api('projects/new',{title:$('#project-name').value});health=await api('health');dialog.close();toast('独立项目已创建');location.hash='overview';render()}catch(error){$('#project-error').textContent=error.message}};
  };
}
