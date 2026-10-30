/* Segment drafts and immutable task inputs; playback never submits generation. */
const SegmentStudio=(()=>{
 let project=null,selected=null,signature='',initializing=false,catalog=null,creative=null,playing=false;
 let overviewId=null,overviewTime=0,overviewWasPlaying=false;
 const drafts=new Map(),candidates=new Map();
 const statuses={queued:'排队中',running:'生成中',submitting:'正在提交',completed:'已完成',failed:'生成失败',rejected:'供应商拒绝',cancelled:'已取消',unknown:'结果待核对'};
 const costInfo=t=>{
  const tokens=t?.usage?.completion_tokens,req=t?.request||{},res=t?.provider_metadata?.resolution||req.resolution;
  if(t?.status!=='completed'||req.model!=='doubao-seedance-2-5-260628'||!Number.isInteger(tokens)||!['480p','720p','1080p'].includes(res))return null;
  const hasVideo=(req.content||[]).some(x=>x.type==='video_url');const rate=res==='1080p'?(hasVideo?46:77):(hasVideo?42:70);
  return {tokens,rate,amount:tokens*rate/1000000,hasVideo};
 };
 const taskFacts=t=>{
  if(!t)return '';
  const details=t.provider_metadata||{},start=Number(details.created_at||t.submitted_epoch||0),status=statuses[t.status]||t.status||'待核对';
  const running=['queued','running','submitting'].includes(t.status),usage=t.usage?.completion_tokens;
  const time=running&&start>0?`<span data-task-elapsed="${start}"></span>`:'';
  const cost=costInfo(t),actual=t.actual_cost_cny,reported=t.reported_original_cny;
  const invoice=actual!=null?'已核实实付：¥'+Number(actual).toFixed(4):reported!=null?'账单原价：¥'+Number(reported).toFixed(4)+'（用户提供）':'';
  return `<section class="task-facts" aria-label="生成进度与费用"><h3>生成进度与费用</h3><p role="status">状态：${esc(t.review_status==='rejected_quality'?'审核未通过：'+(t.review_reason||''):status)}${time}。${running?'供应商没有返回百分比。':''}</p>${invoice?`<p>${esc(invoice)}</p>`:''}<p>模型返回用量：${Number.isInteger(usage)?usage.toLocaleString()+' tokens':'任务完成后返回，当前未知'}</p>${cost?`<p>按官方公示单价推算原价：¥${cost.amount.toFixed(4)}（${cost.hasVideo?'含视频输入':'无视频输入'}，¥${cost.rate}/百万 tokens；价格核对于 2026-10-30）。不含账号折扣、资源包抵扣，不等于账单实付。<a href="https://docs.volcengine.com/docs/ark/model-pricing?lang=zh" target="_blank" rel="noopener noreferrer">官方单价</a></p>`:''}${t.provider_error?`<p>供应商错误：${esc(t.provider_error.code||'')} ${esc(t.provider_error.message||'')}</p>`:''}${t.poll_error?`<p>状态查询未完成：${esc(t.poll_error)}</p>`:''}</section>`;
 };
 function updateElapsed(){document.querySelectorAll('[data-task-elapsed]').forEach(el=>{const sec=Math.max(0,Math.floor(Date.now()/1000-Number(el.dataset.taskElapsed)));el.textContent=' · 已等待 '+Math.floor(sec/60)+'分'+String(sec%60).padStart(2,'0')+'秒'})}
 let elapsedTimer=null;
 const voiceDescription=snapshot=>{const refs=snapshot?.voice_references?.length?snapshot.voice_references:(snapshot?.voice_reference?[snapshot.voice_reference]:[]);return refs.length?refs.map(v=>v.expected_speakers.join('、')+' · '+v.mapping_status).join('；'):'无，未单独传入声音参考'};
 const qualityReference=snapshot=>{const r=snapshot?.quality_reference;if(!r)return '未设置';return r.status==='sent'?'已传入独立基准视频（'+r.duration+'秒）':r.status==='shared_with_parent'?'上一段同时作为画质基准':'未传入基准视频'};
 const promptOf=t=>t?.request?.content?.find(x=>x.type==='text')?.text||t?.request?.input?.prompt||t?.request?.prompt||'';
 const tasksOf=s=>(state.tasks||[]).filter(t=>t.segment_id===s.id||(s.legacy_task_ids||[]).includes(t.id));
 const segments=()=>[...(state.video_segments||[])].sort((a,b)=>a.order-b.order);
 const source=t=>safeVideoSource(t?{local_url:t.local_video,url:t.video_url}:null);
 const selectedTask=s=>{const tasks=tasksOf(s);return tasks.find(t=>t.id===candidates.get(s.id))||tasks.find(t=>t.id===s.selected_task_id)||tasks.at(-1)};
 const playable=s=>{const t=selectedTask(s);return t?.status==='completed'&&t.review_status!=='rejected_quality'&&source(t)?t:null};
 const brief=()=>state.project_brief&&typeof state.project_brief==='object'?state.project_brief:{summary:state.project_brief||''};
 const html=()=>`<section id="segment-studio" aria-label="分段视频制作"><p>正在读取视频片段…</p></section>`;

 function captureOverview(host){
  const video=host.querySelector('[data-overview-video]');
  if(video){overviewId=video.dataset.segmentId;overviewTime=Number.isFinite(video.currentTime)?video.currentTime:0;overviewWasPlaying=!video.paused&&!video.ended}
 }
 function renderOverview(host,formal){
  const clips=formal.filter(s=>s.include_in_playlist!==false).map(s=>{
   const chosen=selectedTask(s),tasks=tasksOf(s);const t=chosen?.status==='completed'&&chosen.review_status!=='rejected_quality'&&source(chosen)?chosen:tasks.filter(x=>x.status==='completed'&&x.review_status!=='rejected_quality'&&source(x)).at(-1);
   return t?{segment:s,task:t}:null
  }).filter(Boolean);
  const box=document.createElement('section');box.className='panel video-overview';box.setAttribute('aria-label','视频总览');
  if(!clips.length){box.innerHTML='<h2>视频总览</h2><p>暂无可播放的正式片段，生成完成后会自动加入。</p>';host.querySelector('.segment-layout').before(box);return}
  if(!clips.some(c=>c.segment.id===overviewId)){overviewId=clips[0].segment.id;overviewTime=0;overviewWasPlaying=false}
  const initial=clips.find(c=>c.segment.id===overviewId),duration=clips.reduce((n,c)=>n+Number(c.task.media_info?.duration||c.task.request?.duration||0),0);
  box.innerHTML=`<div class="panel-head"><h2>视频总览</h2><span class="muted">${clips.length} 段 · 约 ${duration.toFixed(1)} 秒</span></div><div class="video-stage overview-stage"><video data-overview-video controls playsinline preload="metadata" aria-label="项目视频总览"></video></div><p data-overview-current aria-live="polite"></p><div class="overview-clips" role="group" aria-label="选择总览片段">${clips.map((c,i)=>`<button type="button" data-overview-pick="${esc(c.segment.id)}" aria-pressed="${c.segment.id===overviewId}">${i+1}. ${esc(c.segment.name)}</button>`).join('')}</div><p class="muted">按片段顺序自动连续播放；这是播放总览，尚未合成为单个成片。</p>`;
  host.querySelector('.segment-layout').before(box);const video=box.querySelector('[data-overview-video]');
  attachVideoSpeed(video,'overview');
  function selectClip(id,autoplay,seek=0){
   const idx=clips.findIndex(c=>c.segment.id===id);if(idx<0)return;const clip=clips[idx];overviewId=id;video.dataset.segmentId=id;video.src=source(clip.task);
   box.querySelector('[data-overview-current]').textContent='正在查看 '+(idx+1)+' / '+clips.length+' · '+clip.segment.name;
   box.querySelectorAll('[data-overview-pick]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.overviewPick===id)));
   video.onloadedmetadata=()=>{if(seek>0&&seek<video.duration)video.currentTime=seek};if(autoplay)video.play().catch(()=>{overviewWasPlaying=false;toast('请点击播放器继续播放')});
  }
  video.onplay=()=>host.querySelector('#video-stage video')?.pause();
  video.onended=()=>{const idx=clips.findIndex(c=>c.segment.id===overviewId);if(idx+1<clips.length){overviewTime=0;overviewWasPlaying=true;selectClip(clips[idx+1].segment.id,true)}else{overviewWasPlaying=false;toast('总览播放完成')}};
  video.onerror=()=>{overviewWasPlaying=false;toast('总览视频加载失败，已停止播放')};
  box.querySelectorAll('[data-overview-pick]').forEach(b=>b.onclick=()=>{overviewTime=0;overviewWasPlaying=false;selectClip(b.dataset.overviewPick,false)});
  selectClip(initial.segment.id,overviewWasPlaying,overviewTime);
 }
 function current(){return segments().find(s=>s.id===selected)}
 function capture(){const root=document.querySelector('#segment-editor');if(!root)return;drafts.set(root.dataset.segmentId,{name:root.querySelector('[data-segment-name]').value,material_video_prompt:root.querySelector('[data-segment-prompt]').value,duration:Number(root.querySelector('[data-segment-duration]').value),material_video_audio:root.querySelector('[data-segment-audio]').checked,material_video_parent_task_id:root.querySelector('[data-segment-parent]').value,reference_asset_ids:[...root.querySelectorAll('[data-segment-asset]:checked')].map(x=>x.value),shot_language_ids:[...root.querySelectorAll('[data-selected-shot]')].map(x=>x.value),video_style:root.querySelector('[data-segment-style]').value,include_in_playlist:root.querySelector('[data-segment-playlist]').checked})}
 async function refresh(){const pid=state.project_id;const fresh=await api('state');if(state.project_id!==pid)return;state=fresh;health=await api('health');signature='';mount()}
 function mount(){
  if(location.hash!=='#tasks'||!document.querySelector('#segment-studio'))return;
  if(project!==state.project_id){project=state.project_id;selected=null;catalog=null;signature='';drafts.clear();candidates.clear();playing=false;overviewId=null;overviewTime=0;overviewWasPlaying=false}
  if(!Array.isArray(state.video_segments)){
   if(initializing)return;initializing=true;act(async()=>{try{await api('material-video/init-segments',{});await refresh()}finally{initializing=false}});return;
  }
  if(!catalog){if(initializing)return;initializing=true;act(async()=>{try{const pid=project;const [r,cr]=await Promise.all([fetch('/api/assets'),fetch('/api/workspace/creative-resources')]);const c=await r.json();if(!r.ok)throw Error(c.error);creative=cr.ok?await cr.json():{items:[]};if(project!==pid)return;catalog=c;signature='';mount()}finally{initializing=false}});return}
  const list=segments();if(!list.some(s=>s.id===selected))selected=list.find(s=>!s.legacy_task_ids?.length)?.id||list[0]?.id;
  const key=JSON.stringify({project,selected,segments:state.video_segments,tasks:(state.tasks||[]).map(t=>[t.id,t.status,t.local_video,t.video_url]),candidate:candidates.get(selected)});
  const host=document.querySelector('#segment-studio');if(signature===key&&host.querySelector('[data-new-segment]'))return;capture();captureOverview(host);signature=key;
  const seg=current(),task=seg?selectedTask(seg):null,versions=seg?tasksOf(seg):[],draft=seg?(drafts.get(seg.id)||{...seg,video_style:brief().video_style||'',reference_asset_ids:(seg.asset_references||[]).map(r=>r.asset_id),shot_language_ids:(seg.shot_language||[]).map(r=>r.id)}):null;
  const history=list.filter(s=>s.id.startsWith('legacy-segment-')&&s.name.startsWith('历史测试 · '));
  const formal=list.filter(s=>!history.includes(s));
  const segmentButton=s=>`<button type="button" data-pick-segment="${esc(s.id)}" aria-pressed="${s.id===selected}"><strong>${esc(s.name)}</strong><span>${s.duration} 秒 · ${tasksOf(s).length?'有 '+tasksOf(s).length+' 个候选':'Prompt草稿'}${s.include_in_playlist===false?' · 不参与连播':''}</span></button>`;
  host.innerHTML=`<div class="panel-head"><h1>视频片段</h1><div class="shot-actions"><button type="button" data-new-segment>＋ 新片段</button><button type="button" data-play-all>${playing?'停止连播':'连续播放片段'}</button></div></div><div class="segment-layout"><nav class="panel segment-list" aria-label="视频片段列表">${formal.map(segmentButton).join('')||'<p>先创建一个视频片段。</p>'}${history.length?`<details class="segment-history" ${history.some(s=>s.id===selected)?'open':''}><summary>历史测试（${history.length}）</summary>${history.map(segmentButton).join('')}</details>`:''}</nav><div class="segment-main">${seg?`<section class="panel" id="segment-editor"><h2>下次生成的 Prompt 草稿</h2><p class="muted">修改草稿不会影响已有视频；生成前会再次展示完整请求供确认。</p><label class="field" for="segment-name">片段名称</label><input id="segment-name" data-segment-name value="${esc(draft.name)}"><label class="field" for="segment-prompt">完整 Prompt 草稿</label><textarea id="segment-prompt" data-segment-prompt rows="15"></textarea><div class="form-grid"><div><label class="field" for="segment-duration">计划时长／秒（按剧情自然拆分）</label><input id="segment-duration" data-segment-duration type="number" min="4" max="30" value="${draft.duration}"></div><div><label class="asset-choice"><input data-segment-audio type="checkbox" ${draft.material_video_audio?'checked':''}>生成对白及声音</label><label class="asset-choice"><input data-segment-playlist type="checkbox" ${draft.include_in_playlist!==false?'checked':''}>参与顺序连播</label></div></div><details><summary>素材、项目视频风格与前置片段</summary><fieldset><legend>本段参考素材</legend>${catalog.assets.filter(a=>a.adopted_version).map(a=>{const v=a.versions.find(v=>v.version===a.adopted_version);const view=v.views.find(x=>x.tag===(a.kind==='character'?'body_front':'main'));return `<label class="asset-choice"><input type="checkbox" data-segment-asset value="${esc(a.id)}" ${(draft.reference_asset_ids||[]).includes(a.id)?'checked':''}>${esc(v.name)} · v${v.version}${view?`<img src="${esc(view.url)}" alt="${esc(v.name)}参考图" width="64" height="64" style="object-fit:contain">`:''}</label>`}).join('')}</fieldset><label class="field" for="segment-style">项目视频风格</label><textarea id="segment-style" data-segment-style rows="6"></textarea><label class="field" for="segment-parent">计划依赖的前置视频</label><select id="segment-parent" data-segment-parent><option value="">无，独立生成本段</option>${(state.tasks||[]).filter(t=>t.status==='completed'&&!versions.some(v=>v.id===t.id)).map(t=>`<option value="${esc(t.id)}" ${draft.material_video_parent_task_id===t.id?'selected':''}>${esc(t.name)} · ${esc(t.id.slice(0,8))}</option>`).join('')}</select><p class="muted">前置片段可记录为计划依赖；续写需选择已验收的Seedance片段；预览会显示实际传入的原视频、素材与费用。</p></details><div class="shot-actions"><button data-save-segment>保存草稿</button><button data-preview-segment class="primary">保存并预览完整生成输入</button></div><p data-segment-notice role="status"></p><div data-segment-preview></div></section><section class="panel"><h2>本段视频候选与对应输入</h2>${versions.length?`<label class="field" for="segment-candidate">候选版本</label><select id="segment-candidate">${versions.map((t,i)=>`<option value="${esc(t.id)}" ${t.id===task?.id?'selected':''}>候选 ${i+1} · ${esc(t.status)} · ${esc(t.id.slice(0,8))}</option>`).join('')}</select>`:''}<div id="video-stage" class="video-stage">${source(task)?`<video controls playsinline preload="metadata" aria-label="${esc(seg.name)}候选视频" src="${esc(source(task))}"></video>`:'<p>本段尚无可播放视频。先查看并确认上方完整输入。</p>'}</div>${task?`${taskFacts(task)}<details class="candidate-prompt"><summary>查看这个视频实际使用的 Prompt</summary><p class="muted">这份是生成时保存的记录，可用于核对；下方草稿可继续编辑。</p><pre class="segment-request">${esc(promptOf(task)||'历史任务未记录完整Prompt')}</pre></details><p>实际参考素材：${esc(task.material_snapshot?.materials?.map(m=>m.name+' v'+m.version).join('、')||'历史任务未记录素材清单')}</p><p>实际前置视频：${esc(task.material_snapshot?.parent_video?.task_id||'无，未传入视频参考')}</p><p>实际声音参考：${esc(voiceDescription(task.material_snapshot))}</p><p>实际镜头语言：${esc((task.material_snapshot?.shot_language||[]).map(x=>x.name).join(' · ')||'未记录或未选择')}</p><p class="muted">以上是该次任务的历史输入快照；修改上方草稿不会改写这段视频的Prompt。</p><div class="shot-actions"><button data-query-segment ${task.provider_task_id?'':'disabled'}>查询这个原任务</button><button data-pick-playback ${task.status==='completed'&&task.review_status!=='rejected_quality'?'':'disabled'}>设为本段连播候选</button></div>`:''}</section>`:''}</div></div>`;
  updateElapsed();if(!elapsedTimer)elapsedTimer=setInterval(updateElapsed,1000);
  renderOverview(host,formal);
  const assembled=safeVideoSource(state.final_video);
  if(assembled){
   const finalBox=document.createElement('section');finalBox.className='panel video-overview';finalBox.setAttribute('aria-label','完整视频');
   finalBox.innerHTML=`<div class="panel-head"><h2>完整视频</h2><a href="${esc(assembled)}" download>下载完整视频</a></div><div class="video-stage overview-stage"><video controls playsinline preload="metadata" aria-label="完整视频播放" src="${esc(assembled)}"></video></div><p class="muted">由已选择的片段拼接，成片待审阅。</p>`;
   host.querySelector('.video-overview').before(finalBox);
   const finalPlayer=finalBox.querySelector('video');finalPlayer.onplay=()=>host.querySelectorAll('video').forEach(v=>{if(v!==finalPlayer)v.pause()});
   attachVideoSpeed(finalPlayer,'final');
   const exportBox=document.createElement('div');exportBox.className='video-download-options';
   exportBox.innerHTML=`<label>下载倍速 <select aria-label="下载视频倍速">${Array.from({length:10},(_,i)=>`<option value="${((11+i)/10).toFixed(1)}">${((11+i)/10).toFixed(1)}×</option>`).join('')}</select></label><button type="button" data-speed-download>倍速下载</button><span role="status" aria-live="polite" data-speed-status></span>`;
   finalBox.append(exportBox);
   const exportButton=exportBox.querySelector('[data-speed-download]'),exportSelect=exportBox.querySelector('select'),exportStatus=exportBox.querySelector('[data-speed-status]');
   async function speedRequest(action,body){const response=await fetch('/api/video-speed/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw Error(data.error||'导出失败');return data}
   exportButton.onclick=async()=>{
    const pid=state.project_id,sourceSha=state.final_video?.sha256,rate=Number(exportSelect.value);exportButton.disabled=true;exportSelect.disabled=true;exportStatus.textContent='正在准备倍速视频…';
    try{
     let job=await speedRequest('start',{project_id:pid,rate,source_sha256:sourceSha,source_url:state.final_video?.local_url});
     while(job.status==='running'){
      if(!exportBox.isConnected||state.project_id!==pid)return;
      exportStatus.textContent='正在处理 '+job.progress+'%';await new Promise(resolve=>setTimeout(resolve,900));
      job=await speedRequest('status',{project_id:pid,job_id:job.id});
     }
     if(job.status!=='completed')throw Error(job.error||'导出失败');
     if(!exportBox.isConnected||state.project_id!==pid)return;
     const result=safeVideoSource({local_url:job.url});if(!result)throw Error('导出地址无效');
     exportStatus.textContent='已完成，';const link=document.createElement('a');link.href=result;link.download='video_'+rate.toFixed(1)+'x.mp4';link.textContent='点击下载';exportStatus.append(link);link.click();
    }catch(error){if(exportBox.isConnected)exportStatus.textContent=error.message||'导出失败'}finally{if(exportBox.isConnected){exportButton.disabled=false;exportSelect.disabled=false}}
   };
   host.querySelectorAll('video:not([aria-label="完整视频播放"])').forEach(v=>v.addEventListener('play',()=>finalPlayer.pause()));
  }
  attachVideoSpeed(host.querySelector('#video-stage video'),'segment');
  const editorPanel=host.querySelector('#segment-editor'),videoPanel=editorPanel?.nextElementSibling;
  if(videoPanel)editorPanel.before(videoPanel);
  host.querySelector('[data-new-segment]').onclick=()=>act(async()=>{capture();playing=false;const r=await api('material-video/create-segment',{});selected=r.segment.id;await refresh()});
  host.querySelectorAll('[data-pick-segment]').forEach(b=>b.onclick=()=>{capture();playing=false;selected=b.dataset.pickSegment;signature='';mount()});
  host.querySelector('[data-play-all]').onclick=()=>{if(playing){playing=false;host.querySelector('#video-stage video')?.pause();signature='';mount();return}const first=list.find(s=>s.include_in_playlist!==false&&playable(s));if(!first){toast('尚无可连播片段；历史测试默认不参与。');return}capture();playing=true;selected=first.id;signature='';mount();host.querySelector('#video-stage video')?.play().catch(()=>{playing=false;toast('请点击播放器开始播放')})};
  if(!seg)return;
  host.querySelector('#segment-editor').dataset.segmentId=seg.id;
  host.querySelector('[data-segment-prompt]').value=draft.material_video_prompt||'';host.querySelector('[data-segment-style]').value=draft.video_style||'';
  if(task){
   const quality=state.project_brief?.video_quality,base=(state.tasks||[]).find(t=>t.id===quality?.baseline_task_id),review=task.quality_review;
   const box=document.createElement('section');box.className='panel';box.setAttribute('aria-label','画质对照');
   const stale=review&&review.status!=='unavailable'&&(review.baseline_task_id!==quality?.baseline_task_id||review.baseline_sha256!==quality?.baseline_sha256);
   const summary=stale?'画质基准已变更，请重新检查。':review?.status==='unavailable'?review.note:review?review.possible_softness?'抽样提示可能比基准更柔和，请查看实际画面。':'抽样未发现明显变软，仍请查看实际画面。':'尚未检查；可与画质基准对照。';
   const baseSrc=source(base),candidateSrc=source(task);
   box.innerHTML=`<h2>画质对照</h2><p>${esc(summary)}</p><p class="muted">抽样结果会受景别、运动和画面内容影响，不能替代人工审阅。</p>${task.material_snapshot?`<p>生成时画质基准：${esc(qualityReference(task.material_snapshot))}</p>`:''}${quality&&baseSrc&&candidateSrc?`<details><summary>查看基准与当前视频</summary><div class="quality-compare"><div><p>画质基准</p><div class="video-stage"><video controls playsinline preload="metadata" aria-label="画质基准视频" src="${esc(baseSrc)}"></video></div></div><div><p>当前视频</p><div class="video-stage"><video controls playsinline preload="metadata" aria-label="画质对照当前视频" src="${esc(candidateSrc)}"></video></div></div></div></details>`:''}<div class="shot-actions">${quality&&task.status==='completed'?'<button type="button" data-check-quality>检查画质</button>':''}${task.review_status==='accepted'&&task.id!==quality?.baseline_task_id?'<button type="button" data-set-quality>设为画质基准</button>':''}</div>`;
   videoPanel.after(box);
   box.querySelectorAll('video').forEach((v,i)=>attachVideoSpeed(v,'quality-'+i));
   const check=box.querySelector('[data-check-quality]');if(check)check.onclick=()=>act(async()=>{check.disabled=true;try{await api('material-video/check-quality',{segment_id:seg.id,task_id:task.id});await refresh()}finally{check.disabled=false}});
   const set=box.querySelector('[data-set-quality]');if(set)set.onclick=()=>act(async()=>{await api('material-video/set-quality-baseline',{task_id:task.id});await refresh()});
  }
  const editor=host.querySelector('#segment-editor');editor.querySelectorAll('input,textarea,select').forEach(el=>el.addEventListener('input',()=>{capture();host.querySelector('[data-segment-preview]').textContent='草稿已修改，请重新预览。'}));
  const shotBox=document.createElement('div');shotBox.className='shot-language-choice';
  const shotItems=creative?.items||[],oldShots=seg.shot_language||[];
  function showShotChoices(ids){
   const chosen=ids.map(id=>oldShots.find(x=>x.id===id)||shotItems.find(x=>x.id===id)).filter(Boolean);
   shotBox.innerHTML=`<div><strong>镜头语言</strong><p>${chosen.length?chosen.map(x=>esc(x.name)).join(' · '):'未选择，可由制作助手按剧情安排。'}</p></div><button type="button" data-choose-shot aria-haspopup="dialog">选择镜头语言</button><div data-shot-values>${chosen.map(x=>`<input type="hidden" data-selected-shot value="${esc(x.id)}">`).join('')}</div>`;
   shotBox.querySelector('[data-choose-shot]').onclick=()=>{
    const node=document.createElement('dialog');node.className='shot-language-dialog';node.setAttribute('aria-labelledby','shot-language-title');
    const groups=[['size','景别'],['composition','构图'],['movement','运镜']];
    node.innerHTML=`<div class="panel-head"><h2 id="shot-language-title">选择镜头语言</h2><button type="button" data-close aria-label="关闭">×</button></div><p class="muted">每类可选一项；不同镜头可在视频描述中具体安排。</p>${groups.map(([kind,label])=>{const current=chosen.find(x=>x.kind===kind);const items=shotItems.filter(x=>x.kind===kind);const missing=current&&!items.some(x=>x.id===current.id);return `<label class="field" for="shot-choice-${kind}">${label}</label><select id="shot-choice-${kind}" data-shot-kind="${kind}"><option value="">由制作助手安排</option>${missing?`<option value="${esc(current.id)}" selected>${esc(current.name)}（已有版本）</option>`:''}${items.map(x=>`<option value="${esc(x.id)}" ${current?.id===x.id?'selected':''}>${esc(x.name)} · ${esc(x.description)}</option>`).join('')}</select>`}).join('')}<p class="muted"><a href="/creative-resources.html" target="_blank" rel="noopener">浏览全部创作资源 ↗</a></p><div class="shot-actions"><button type="button" data-cancel>取消</button><button type="button" class="primary" data-confirm>使用这些选项</button></div>`;
    document.body.append(node);node.addEventListener('close',()=>node.remove(),{once:true});node.querySelector('[data-close]').onclick=()=>node.close();node.querySelector('[data-cancel]').onclick=()=>node.close();
    node.querySelector('[data-confirm]').onclick=()=>{const next=[...node.querySelectorAll('[data-shot-kind]')].map(x=>x.value).filter(Boolean);node.close();showShotChoices(next);capture();host.querySelector('[data-segment-preview]').textContent='镜头语言已修改，请保存并重新预览。'};
    node.showModal();
   };
  }
  showShotChoices(draft.shot_language_ids||[]);editor.querySelector('[data-segment-prompt]').before(shotBox);
  async function saveDraft(){capture();await api('material-video/save-segment',{segment_id:seg.id,draft:drafts.get(seg.id)});const pid=project;const fresh=await api('state');if(pid!==project)throw Error('项目已切换');state=fresh;host.querySelector('[data-segment-notice]').textContent='草稿已保存；没有提交生成。'}
  const parentField=editor.querySelector('[data-segment-parent]');
  const tailBox=document.createElement('div');tailBox.className='field';
  const tail=seg.material_video_tail,tailMode=seg.material_video_reference_mode==='tail';
  tailBox.innerHTML=`<p>前段参考：${tailMode?'本地片尾（暂不可提交）':'完整原视频'}${tail?' · 已裁出 '+esc(tail.duration_seconds)+' 秒':''}</p><label for="segment-tail-length">截取前段最后几秒</label> <select id="segment-tail-length" aria-label="截取前段最后几秒"><option value="3">3 秒</option><option value="5" selected>5 秒</option><option value="8">8 秒</option></select> <button type="button" data-prepare-tail>截取片尾</button> ${tailMode?'<button type="button" data-use-full>改用完整原视频</button>':''}<p class="muted">片尾目前仅保存在本机，尚不能提交模型。人物画面可能受平台素材规则限制。</p>`;
  parentField.after(tailBox);
  tailBox.querySelector('[data-prepare-tail]').onclick=()=>act(async()=>{const button=tailBox.querySelector('[data-prepare-tail]');button.disabled=true;try{await saveDraft();const seconds=Number(tailBox.querySelector('#segment-tail-length').value);await api('material-video/prepare-tail',{segment_id:seg.id,seconds});drafts.delete(seg.id);await refresh()}finally{button.disabled=false}});
  const fullButton=tailBox.querySelector('[data-use-full]');if(fullButton)fullButton.onclick=()=>act(async()=>{await api('material-video/save-segment',{segment_id:seg.id,draft:{material_video_reference_mode:'original'}});drafts.delete(seg.id);await refresh()});
  host.querySelector('[data-save-segment]').onclick=()=>act(saveDraft);
  host.querySelector('[data-preview-segment]').onclick=()=>act(async()=>{await saveDraft();const preview=await api('material-video/preview',{segment_id:seg.id});if(selected!==seg.id||project!==state.project_id)return;const result=host.querySelector('[data-segment-preview]');result.innerHTML=`<h3>将发送给模型的完整 Prompt</h3><pre class="segment-request">${esc(preview.snapshot.request.content.find(x=>x.type==='text').text)}</pre><p>素材：${esc(preview.snapshot.materials.map(m=>m.name+' v'+m.version).join('、'))}</p><p>声音参考：${esc(voiceDescription(preview.snapshot))}</p><p>镜头语言：${esc((preview.snapshot.shot_language||[]).map(x=>x.name).join(' · ')||'未选择')}</p><p>${preview.snapshot.request.duration} 秒 · ${esc(preview.snapshot.request.resolution||'分辨率未记录')} · ${esc(preview.snapshot.request.ratio)} · ${preview.snapshot.request.generate_audio?'有声':'无声'} · 生成后按返回 Token 推算原价 · 无首帧 · 前置视频：${esc(preview.snapshot.parent_video?.task_id||'无')}</p><p>画质基准：${esc(qualityReference(preview.snapshot))}</p>${(preview.snapshot.quality_warnings||[]).map(w=>`<p role="status">${esc(w)}</p>`).join('')}<button data-submit-segment class="primary">确认本次完整输入并生成</button>`;result.querySelector('[data-submit-segment]').onclick=()=>act(async()=>{const button=result.querySelector('[data-submit-segment]');button.disabled=true;try{await api('material-video/approve',{segment_id:seg.id,fingerprint:preview.fingerprint,source:'用户在片段页确认完整输入与费用'});state=await api('state');const r=await api('material-video/submit',{segment_id:seg.id,redo:!!versions.length});candidates.set(seg.id,r.task_id);drafts.delete(seg.id);await refresh()}finally{if(button.isConnected)button.disabled=false}})});
  const select=host.querySelector('#segment-candidate');if(select)select.onchange=()=>{capture();playing=false;candidates.set(seg.id,select.value);signature='';mount()};
  const query=host.querySelector('[data-query-segment]');if(query)query.onclick=()=>act(async()=>{state=await api('provider/poll',{task_id:task.id});signature='';mount()});
  const pick=host.querySelector('[data-pick-playback]');if(pick)pick.onclick=()=>act(async()=>{await api('material-video/save-segment',{segment_id:seg.id,draft:{selected_task_id:task.id}});await refresh()});
  const video=host.querySelector('#video-stage video');if(video){video.onplay=()=>host.querySelector('[data-overview-video]')?.pause();video.onerror=()=>{playing=false;toast('视频加载失败，连播已停止')};video.onended=()=>{if(!playing)return;const next=list.slice(list.findIndex(s=>s.id===selected)+1).find(s=>s.include_in_playlist!==false&&playable(s));if(!next){playing=false;toast('连续播放结束');return}capture();selected=next.id;signature='';mount();host.querySelector('#video-stage video')?.play().catch(()=>{playing=false;toast('请点击播放器继续')})};if(playing)video.play().catch(()=>{})}
 }
 return {html,mount};
})();
videoPageHTML=()=>SegmentStudio.html();
renderVideoPreview=()=>SegmentStudio.mount();
