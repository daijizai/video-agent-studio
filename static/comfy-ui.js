/* Independent UI module. Host passes transport/state; no auto-submit or auto-poll. */
(() => {
  'use strict';
  const statusText = {submitting:'等待执行',uploading:'准备素材',queued:'排队中',running:'修复中',unknown:'提交待核对，已锁定重试',archive_pending:'结果待下载，可重试下载',completed:'候选待审阅',adopted:'已采用，分镜须重新审批',failed:'执行失败',rejected:'执行器拒绝'};
  window.ComfyRepairUI = {
    mount(container, {state, api, refresh, ready = false, paused = true, approved = true, backend = 'seedream', executionAllowed = false, resumableTaskIds = []}) {
      // api(action,payload) must enforce same-origin, project/revision and authorization server-side.
      // Deliberately does not bind itself to any unintegrated production route.
      container.replaceChildren();
      const safeImage = url => typeof url === 'string' && url.startsWith('/media/'+state.project_id+'/') && /^[A-Za-z0-9_-]+\.png$/.test(url.slice(('/media/'+state.project_id+'/').length));
      const blocked = (state.image_tasks || []).some(t => ['reserved','submitting','uploading','queued','running','unknown','archive_pending'].includes(t.status));
      let submitted = false;
      const el = (tag, text, parent = container) => {const n = document.createElement(tag); if (text != null) n.textContent = text; parent.append(n); return n;};
      el('h3', '局部画面修复');
      el('p', backend==='local'?'框选要修改的区域，保留其余画面。结果先作为候选。':'框选要修改的区域，描述想要的变化。会尽量保留其余画面，但不保证框外内容或像素不变；结果先作为整图候选，由你决定是否采用。');
      el('p', paused ? '项目已暂停新生成。' : !approved ? '请先确认当前画面，再制作修复候选。' : !ready ? '局部修复暂不可用。' : !executionAllowed?'当前图片预算或编辑执行许可不足。':'可以制作候选；实际编辑效果尚未验证，请对比检查。');
      const label = el('label', '原图所在镜头'); const select = el('select', null, label);
      for (const shot of state.shots || []) if (shot.storyboard_local) {const o = el('option', shot.name, select); o.value = shot.id;}
      el('p', '在图上拖动框选。键盘可按回车选择中央区域，用方向键移动，Shift＋方向键调整大小，Esc清除。');
      const canvas = el('canvas'); canvas.tabIndex = 0; canvas.setAttribute('aria-label', '框选要修改的区域'); canvas.style.maxWidth = '100%'; canvas.style.height = 'auto'; canvas.style.touchAction = 'none';
      let selection = null, start = null, image = null;
      const paint = () => {if (!image) return; const ctx = canvas.getContext('2d'); ctx.clearRect(0,0,canvas.width,canvas.height); ctx.drawImage(image,0,0); if (selection) {ctx.fillStyle='rgba(40,120,210,.3)'; ctx.fillRect(...selection); ctx.strokeStyle='#fff'; ctx.lineWidth=Math.max(2,canvas.width/300); ctx.strokeRect(...selection);}};
      const load = () => {selection = null; image = null; const shot = state.shots.find(s => s.id === select.value); if (!shot || !safeImage(shot.storyboard_local)) return; const next = new Image(); next.onload = () => {if (select.value !== shot.id) return; image = next; canvas.width = next.naturalWidth; canvas.height = next.naturalHeight; paint();}; next.src = shot.storyboard_local;};
      const point = e => {const box = canvas.getBoundingClientRect(); return [Math.max(0,Math.min(canvas.width,Math.round((e.clientX-box.left)*canvas.width/box.width))),Math.max(0,Math.min(canvas.height,Math.round((e.clientY-box.top)*canvas.height/box.height)))];};
      canvas.addEventListener('pointerdown', e => {if (!image) return; start = point(e); canvas.setPointerCapture(e.pointerId);});
      canvas.addEventListener('pointermove', e => {if (!start) return; const end=point(e); selection=[Math.min(start[0],end[0]),Math.min(start[1],end[1]),Math.abs(end[0]-start[0]),Math.abs(end[1]-start[1])]; paint();});
      canvas.addEventListener('pointerup', e => {if (!start) return; const end=point(e); selection=[Math.min(start[0],end[0]),Math.min(start[1],end[1]),Math.abs(end[0]-start[0]),Math.abs(end[1]-start[1])]; start=null; paint();});
      canvas.addEventListener('pointercancel', () => {start=null; selection=null; paint();});
      canvas.addEventListener('keydown', e => {if (!image) return; if (e.key==='Escape') {selection=null; paint(); return;} if (e.key==='Enter') {e.preventDefault(); selection=[Math.floor(canvas.width/4),Math.floor(canvas.height/4),Math.floor(canvas.width/2),Math.floor(canvas.height/2)]; paint(); return;} if (!selection || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) return; e.preventDefault(); const axis=['ArrowLeft','ArrowRight'].includes(e.key)?0:1, delta=['ArrowLeft','ArrowUp'].includes(e.key)?-8:8, limit=axis===0?canvas.width:canvas.height; if(e.shiftKey) selection[axis+2]=Math.max(1,Math.min(limit-selection[axis],selection[axis+2]+delta)); else selection[axis]=Math.max(0,Math.min(limit-selection[axis+2],selection[axis]+delta)); paint();});
      select.addEventListener('change', load); load();
      const descLabel = el('label', '要修改的内容'); const desc = el('textarea', null, descLabel); desc.maxLength = 1500;
      let strength; if(backend==='local'){const strengthLabel = el('label', '修改强度'); strength = el('input', null, strengthLabel); strength.type = 'range'; strength.min = '.2'; strength.max = '1'; strength.step = '.05'; strength.value = '.7';}
      const message = el('p', backend==='local'?'本机执行不新增外部模型调用费；仍须具有对应图片执行授权。':'Seedream 图片编辑 · 单次预占 ¥0.12，实际费用以账单为准。原图会发送至火山方舟处理。'); message.setAttribute('role', 'status');
      const run = el('button', '生成局部修复候选'); run.type = 'button'; run.disabled = paused || !approved || !ready || !executionAllowed || !select.options.length || blocked || submitted;
      const action = async (button, operation) => {button.disabled = true; try {await operation(); await refresh();} catch (error) {message.textContent = '本次操作未完成，请核对原任务。结果不明时请勿重复生成。'; if(submitted) await refresh();} finally {button.disabled = run === button ? paused || !approved || !ready || !executionAllowed || !select.options.length || blocked || submitted : false;}};
      run.addEventListener('click', () => action(run, async () => {
        const shot = state.shots.find(s => s.id === select.value);
        if (!image || !selection || selection[2]<1 || selection[3]<1 || !desc.value.trim()) throw new Error('请框选修改区域，并描述想要的变化。');
        const common = {project_id:state.project_id, revision:state.revision, shot_id:shot.id};
        let task;
        if(backend==='local'){
          const maskCanvas=document.createElement('canvas'); maskCanvas.width=canvas.width; maskCanvas.height=canvas.height; const ctx=maskCanvas.getContext('2d'); ctx.fillStyle='#000'; ctx.fillRect(0,0,canvas.width,canvas.height); ctx.fillStyle='#fff'; ctx.fillRect(...selection);
          const blob = await new Promise(resolve => maskCanvas.toBlob(resolve, 'image/png')); if(!blob) throw new Error('无法准备区域'); const bytes = new Uint8Array(await blob.arrayBuffer());
          let binary = ''; for (let i=0; i<bytes.length; i+=8192) binary += String.fromCharCode(...bytes.subarray(i,i+8192));
          const upload = await api('mask', {...common, png_base64:btoa(binary)});
          task = await api('begin', {...common, backend:'local',source_url:shot.storyboard_local, mask_url:upload.local_url, values:{description:desc.value.trim(), strength:Number(strength.value)}, request_id:crypto.randomUUID().replaceAll('-','')});
        }else{
          task=await api('begin',{...common,source_url:shot.storyboard_local,region:{x:selection[0],y:selection[1],width:selection[2],height:selection[3]},description:desc.value.trim(),request_id:crypto.randomUUID().replaceAll('-','')});
        }
        submitted = true;
        await api('execute', {project_id:state.project_id, task_id:task.id});
      }));
      for (const task of (state.image_tasks || []).filter(t => ['comfy-masked-repair','seedream-edit'].includes(t.provider) && state.shots.some(s=>s.id===t.shot_id))) {
        const article = el('article'); el('h4', task.name, article); el('p', statusText[task.status] || '状态待核对', article);
        if (task.error || task.poll_error || task.download_error) el('p', '任务需要核对，请查询原任务或联系工作台维护者。', article);
        if (task.candidate_local) {
          const shot = state.shots.find(s => s.id === task.shot_id);
          const show = (url, alt) => {if (!safeImage(url)) return; const figure = el('figure', null, article); const img = el('img', null, figure); img.src = url; img.alt = alt; img.style.maxWidth = '100%'; el('figcaption', alt, figure);};
          show(task.archived_source, '原图'); show(task.candidate_local, '局部修复候选，待人工检查');
          if (task.status === 'completed' && shot) {
            const adopt = el('button', '采用候选并重新审阅分镜', article); adopt.type = 'button';
            adopt.addEventListener('click', () => action(adopt, () => api('adopt', {project_id:state.project_id, revision:state.revision, task_id:task.id, candidate_sha256:task.candidate_sha256, source:'用户在局部修复面板点击采用当前候选'})));
          }
        }
        if (task.status === 'submitting') {const execute = el('button', '执行已准备的修复', article); execute.type='button'; execute.disabled=paused || !approved || !ready || !resumableTaskIds.includes(task.id) || task.provider!=='seedream-edit'; execute.addEventListener('click',()=>action(execute,()=>api('execute',{project_id:state.project_id,task_id:task.id})));}
        if ((task.provider==='seedream-edit' && task.status==='completed' && task.download_error) || (task.provider_task_id && ['queued','running','unknown','archive_pending'].includes(task.status))) {
          const poll = el('button', task.status === 'archive_pending' || task.download_error ? '重试下载原结果' : '查询原任务', article); poll.type = 'button';
          poll.addEventListener('click', () => action(poll, () => api('poll', {project_id:state.project_id, task_id:task.id})));
        }
      }
    }
  };
})();

// Public review integration; no private workspace-home files are touched.
function mountComfyRepair(page) {
  if(page!=='shots')return;
  document.querySelectorAll('[data-comfy-shot]').forEach(panel=>{
    panel.addEventListener('toggle',async()=>{
      if(!panel.open || panel.dataset.mounted)return;
      panel.dataset.mounted='loading';
      const pid=state.project_id,shot=state.shots.find(s=>s.id===panel.dataset.comfyShot),body=panel.querySelector('.comfy-repair-body');
      if(!shot?.storyboard_local){body.textContent='局部修复暂不可用，请先准备当前镜头画面。';return;}
      let readiness={ready:false};try{readiness=await api('repair/preflight');}catch{}
      if(state.project_id!==pid || !panel.isConnected)return;
      const refresh=async()=>{const updated=await api('state');if(updated.project_id!==pid || state.project_id!==pid)return;state=updated;health=await api('health');render();const next=[...document.querySelectorAll('[data-comfy-shot]')].find(p=>p.dataset.comfyShot===shot.id);if(next)next.open=true;};
      const request=async(action,payload)=>{if(state.project_id!==pid)throw new Error('项目已切换');const task=state.image_tasks.find(t=>t.id===payload.task_id);return api((task?.provider==='comfy-masked-repair' || action==='mask'?'comfy/':'repair/')+action,payload);};
      ComfyRepairUI.mount(body,{state:{...state,shots:[shot]},api:request,refresh,ready:readiness.ready,paused:!!health.generation_paused,approved:currentApproved(shot),backend:'seedream',executionAllowed:!!readiness.execution_allowed,resumableTaskIds:readiness.resumable_task_ids||[]});
      panel.dataset.mounted='true';
      panel.dataset.resultStamp=repairResultStamp(shot.id);
    });
  });
}

function repairResultStamp(shotId){return JSON.stringify((state.image_tasks||[]).filter(t=>t.shot_id===shotId && ['comfy-masked-repair','seedream-edit'].includes(t.provider)).map(t=>[t.id,t.candidate_sha256,t.review_status,!!t.download_error,['unknown','failed','archive_pending','completed','adopted'].includes(t.status)?t.status:'inflight']));}
function refreshComfyRepairPanels(){document.querySelectorAll('[data-comfy-shot][open]').forEach(panel=>{if(panel.dataset.mounted!=='true')return;if(panel.dataset.resultStamp!==repairResultStamp(panel.dataset.comfyShot)){delete panel.dataset.mounted;panel.dispatchEvent(new Event('toggle'));}});}
