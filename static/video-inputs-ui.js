const videoProjectBrief=()=>state.project_brief&&typeof state.project_brief==='object'?state.project_brief:{summary:state.project_brief||''};
/* Actual generation inputs are previewed before approval; historical inputs stay immutable. */
function renderVideoInputs(choice){
 const host=document.querySelector('.video-layout');if(!host)return;
 const inputKey=state.project_id+':'+choice.key+':'+(choice.task?.id||'draft');
 const prior=document.querySelector('[data-video-inputs]');if(prior?.dataset.key===inputKey)return;prior?.remove();
 const box=document.createElement('section');box.className='panel';box.dataset.videoInputs='';box.dataset.key=inputKey;host.before(box);
 const shot=choice.shot,task=choice.task;
 const actual=task?.request?.content?.find(x=>x.type==='text')?.text||task?.request?.input?.prompt||task?.request?.prompt;
 const snapshots=task?.material_snapshot?.materials;
 const materials=shot?.asset_references||[];
 box.innerHTML=`<h2>片段生成方案</h2>${shot?`<p class="muted">先准备完整内容，再预览实际提示词、参考素材和费用，确认后生成。</p><label class="field" for="video-prompt-draft">视频 Prompt 草稿（动作、对白、声音与衔接）</label><textarea id="video-prompt-draft" rows="12"></textarea><label class="field" for="project-video-style">项目视频风格（所有后续片段共用）</label><textarea id="project-video-style" rows="5"></textarea><div class="form-grid"><div><label class="field" for="video-input-duration">时长／秒</label><input id="video-input-duration" type="number" min="4" max="30" step="1" value="${Number(shot.duration)}"></div><label class="asset-choice"><input id="video-input-audio" type="checkbox" ${(shot.material_video_audio??state.settings.audio??true)?'checked':''}>生成对白及声音</label></div><h3>参考素材</h3><div>${materials.map(r=>`<p>${esc(r.name)} · v${r.version}</p><div style="display:flex;gap:8px;flex-wrap:wrap">${r.views.map(v=>`<img src="${esc(v.url)}" alt="${esc(r.name+' '+v.label)}" style="width:100px;height:100px;object-fit:contain">`).join('')}</div>`).join('')||'<p>尚未绑定素材，请由制作助手准备本段素材引用。</p>'}</div><p>前置视频：本路径当前制作独立片段，尚未接入视频续写，不会自动引用上一段。</p><button type="button" data-preview-inputs>保存草稿并预览完整输入</button><div data-video-input-preview></div>`:'<p>请先选择一个片段。</p>'}${task?`<hr><h3>当前视频实际使用的输入</h3><p>${esc(task.name)} · ${task.request?.duration??'未记录'} 秒 · ${esc(task.request?.ratio||'未记录画幅')} · ${task.request?.generate_audio===true?'有声':task.request?.generate_audio===false?'无声':'音频设置未记录'}</p><p>素材：${snapshots?esc(snapshots.map(m=>m.name+' v'+m.version).join('、')):'旧任务未记录独立素材清单，请查看其请求记录'}</p><p>前置视频：${task.request?.content?.some(x=>x.type==='video_url')?'已传入参考视频':'本次未传入参考视频'}</p><details><summary>查看实际完整 Prompt</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(actual||'此任务未记录完整提示词')}</pre></details>`:''}`;
 if(!shot)return;
 box.querySelector('#video-prompt-draft').value=shot.material_video_prompt||shot.prompt||'';
 box.querySelector('#project-video-style').value=videoProjectBrief().video_style||'';
 box.querySelectorAll('textarea,input').forEach(el=>el.addEventListener('input',()=>{box.querySelector('[data-video-input-preview]').textContent='草稿已修改，请重新预览完整输入后生成。'}));
 const oldSubmit=document.querySelector('#video-submit');if(oldSubmit){oldSubmit.disabled=false;oldSubmit.textContent='先查看片段生成方案';oldSubmit.onclick=()=>box.scrollIntoView({behavior:'smooth',block:'start'})}
 document.querySelector('#video-next').textContent='素材参考直出视频：先在生成方案中预览完整输入，再确认费用和生成。';
 box.querySelector('[data-preview-inputs]').onclick=()=>act(async()=>{
  const pid=state.project_id,id=shot.id;
  const shots=state.shots.map(s=>s.id===id?{...s,material_video_prompt:box.querySelector('#video-prompt-draft').value,material_video_audio:box.querySelector('#video-input-audio').checked,duration:Number(box.querySelector('#video-input-duration').value)}:s);
  state=await api('save',{shots,project_brief:{...videoProjectBrief(),video_style:box.querySelector('#project-video-style').value}});
  const preview=await api('material-video/preview',{shot_id:id});if(state.project_id!==pid||!box.isConnected)return;
  const result=box.querySelector('[data-video-input-preview]');
  result.innerHTML=`<h3>即将发送的完整 Prompt</h3><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(preview.snapshot.request.content.find(x=>x.type==='text').text)}</pre><p>${preview.snapshot.materials.length} 张素材参考 · ${preview.snapshot.request.duration} 秒 · ${esc(preview.snapshot.request.ratio)} · ${preview.snapshot.request.generate_audio?'有声':'无声'} · 预估 ¥${Number(preview.estimated_cny).toFixed(2)}</p><p>前置视频：无；未使用关键帧。</p><button type="button" class="primary" data-confirm-video>确认这些输入并生成视频</button><p class="muted">有声模式不保证精确对白、音色或口型，产出后需审阅。</p>`;
  result.querySelector('[data-confirm-video]').onclick=()=>act(async()=>{
   const button=result.querySelector('[data-confirm-video]');button.disabled=true;
   try{await api('material-video/approve',{shot_id:id,fingerprint:preview.fingerprint,source:'用户在视频制作页审阅完整Prompt、素材与费用并确认生成'});state=await api('state');await api('material-video/submit',{shot_id:id,redo:!!task});state=await api('state');health=await api('health');renderVideoPreview()}finally{if(button.isConnected)button.disabled=false}
  });
 });
}
