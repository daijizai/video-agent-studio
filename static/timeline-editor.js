/* Non-destructive, project-local timeline: original task videos stay unchanged. */
const TimelineEditor=(()=>{
 const exportsByProject=new Map(),liveViews=new Map(),liveVersions=new Map();
 const escapeText=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const fmt=n=>{n=Math.max(0,Number(n)||0);return `${Math.floor(n/60)}:${(n%60).toFixed(1).padStart(4,'0')}`};
 function mount(box,clips,project){
  const available=clips.filter(c=>c.task.review_status==='accepted'&&c.task.local_video).map(c=>({id:c.task.id,name:c.segment.name,url:c.task.local_video,duration:Number(c.task.media_info?.duration||c.task.request?.duration||0)})).filter(c=>c.duration>.1);
  if(!available.length)return;
  const key=`frame-timeline-v1-${project}`,ids=available.map(c=>c.id).sort().join('|');let saved=null;
  try{saved=JSON.parse(localStorage.getItem(key)||'null')}catch{}
  let tracks=saved?.ids===ids&&Array.isArray(saved.tracks)?saved.tracks.map(v=>{const c=available.find(x=>x.id===v.id);return c?{...c,start:Math.max(0,Number(v.start)||0),end:Math.min(c.duration,Number(v.end)||c.duration)}:null}).filter(Boolean):available.map(c=>({...c,start:0,end:c.duration}));
  if(tracks.length!==available.length||tracks.some(t=>t.end-t.start<.1))tracks=available.map(c=>({...c,start:0,end:c.duration}));
  let active=0,continuing=false;const total=()=>tracks.reduce((s,t)=>s+t.end-t.start,0);const elapsed=i=>tracks.slice(0,i).reduce((s,t)=>s+t.end-t.start,0);
  const version=()=>JSON.stringify(tracks.map(({id,start,end})=>({id,start,end})));
  const save=()=>{localStorage.setItem(key,JSON.stringify({ids,tracks:JSON.parse(version())}));renderExport()};
  let exportState=exportsByProject.get(project);
  if(!exportState){let prev=null;try{prev=JSON.parse(localStorage.getItem('frame-timeline-export-'+project)||'null')}catch{};if(prev&&typeof prev.url==='string'&&new RegExp('^/media/'+project+'/edit_[a-f0-9]{32}\\.mp4$').test(prev.url)&&typeof prev.signature==='string')exportState={status:'completed',...prev};else exportState={status:'idle'};exportsByProject.set(project,exportState)}
  box.innerHTML=`<div class="timeline-head"><div><h2>视频剪辑台</h2><p>拖动片段两端裁剪；原视频不会改变。画面无损导出：保留原分辨率和帧率；文件可能较大。</p></div><div class="timeline-export-actions"><button type="button" data-timeline-export>导出视频</button><div role="status" aria-live="polite" data-export-status></div><a data-timeline-download hidden download>下载剪辑后的视频</a></div></div><div class="timeline-player"><video controls playsinline preload="metadata" aria-label="剪辑预览" data-timeline-video></video></div><div class="timeline-controls"><button type="button" data-timeline-play>▶ 播放剪辑</button><span data-timeline-clock>0:00.0 / 0:00.0</span><input data-timeline-scrub type="range" min="0" step="0.04" value="0" aria-label="剪辑时间进度"></div><div class="timeline-header"><strong>视频轨道</strong><span data-timeline-total></span></div><div class="timeline-track" data-timeline-track aria-label="视频时间线"></div><p class="timeline-hint">选择片段后也可以用数字精确调整；拖动右侧手柄可剪掉尾部。</p><div data-timeline-detail></div><p role="status" data-timeline-status></p><div data-timeline-output></div>`;
  const video=box.querySelector('[data-timeline-video]'),scrub=box.querySelector('[data-timeline-scrub]'),track=box.querySelector('[data-timeline-track]'),status=box.querySelector('[data-timeline-status]');
  function renderExport(){
   const btn=box.querySelector('[data-timeline-export]'),message=box.querySelector('[data-export-status]'),link=box.querySelector('[data-timeline-download]');
   btn.disabled=exportState.status==='running';btn.textContent=exportState.status==='running'?'正在导出…':'导出视频';
   if(exportState.status==='completed'){
    const stale=exportState.signature!==version();message.textContent=stale?'上一次导出对应之前的剪辑范围。':`导出完成（${fmt(exportState.duration)}），已开始下载。`;
    link.hidden=false;link.href=exportState.url;link.textContent=stale?'下载上一次导出':'重新下载视频';
   }else{link.hidden=true;message.textContent=exportState.status==='running'?'正在拼接并生成文件，请稍候…':exportState.status==='failed'?exportState.error||'导出失败，请重试。':''}
  }
  liveViews.set(project,renderExport);liveVersions.set(project,version);
  function notifyExport(){liveViews.get(project)?.()}
  function clock(){const at=Math.max(0,Math.min(total(),elapsed(active)+(video.currentTime||tracks[active].start)-tracks[active].start));scrub.value=at;box.querySelector('[data-timeline-clock]').textContent=`${fmt(at)} / ${fmt(total())}`}
  function open(i,pos=0,play=false){active=i;const t=tracks[i];continuing=play;video.src=t.url;video.onloadedmetadata=()=>{video.currentTime=Math.min(t.end-.01,t.start+Math.max(0,pos));clock();if(continuing)video.play().catch(()=>{status.textContent='请点击播放继续预览。'})};draw()}
  function move(dir){const j=active+dir;if(j<0||j>=tracks.length)return;[tracks[active],tracks[j]]=[tracks[j],tracks[active]];active=j;save();draw();clock()}
  function draw(){
   scrub.max=total();box.querySelector('[data-timeline-total]').textContent=`${tracks.length} 段 · ${fmt(total())}`;
   track.innerHTML=tracks.map((t,i)=>`<div class="timeline-clip ${i===active?'is-active':''}" data-index="${i}" style="flex:${Math.max(.15,t.end-t.start)}"><button type="button" class="timeline-select" data-select="${i}" aria-label="选择 ${escapeText(t.name)}"><strong>${escapeText(t.name)}</strong><span>${fmt(t.start)}–${fmt(t.end)}</span></button><button type="button" class="timeline-handle left" data-edge="start" data-index="${i}" aria-label="拖动裁剪 ${escapeText(t.name)} 开头"></button><button type="button" class="timeline-handle right" data-edge="end" data-index="${i}" aria-label="拖动裁剪 ${escapeText(t.name)} 结尾"></button></div>`).join('');
   const t=tracks[active];box.querySelector('[data-timeline-detail]').innerHTML=`<div class="timeline-detail"><strong>${escapeText(t.name)}</strong><label>起点（秒）<input data-start type="number" min="0" max="${t.duration}" step="0.1" value="${t.start.toFixed(1)}"></label><label>终点（秒）<input data-end type="number" min="0" max="${t.duration}" step="0.1" value="${t.end.toFixed(1)}"></label><span>原片 ${fmt(t.duration)}</span><button type="button" data-before ${active===0?'disabled':''}>← 前移</button><button type="button" data-after ${active===tracks.length-1?'disabled':''}>后移 →</button><button type="button" data-reset>恢复整段</button></div>`;
   track.querySelectorAll('[data-select]').forEach(b=>b.onclick=()=>{video.pause();open(Number(b.dataset.select))});
   track.querySelectorAll('[data-edge]').forEach(h=>h.onpointerdown=e=>{e.preventDefault();e.stopPropagation();const i=Number(h.dataset.index),t=tracks[i],edge=h.dataset.edge,clip=h.parentElement,scale=(t.end-t.start)/Math.max(clip.getBoundingClientRect().width,1),x=e.clientX,original=t[edge];h.setPointerCapture(e.pointerId);h.onpointermove=ev=>{let v=original+(ev.clientX-x)*scale;v=Math.round(v*10)/10;t[edge]=edge==='start'?Math.max(0,Math.min(t.end-.1,v)):Math.min(t.duration,Math.max(t.start+.1,v));clip.querySelector('span').textContent=`${fmt(t.start)}–${fmt(t.end)}`};h.onpointerup=()=>{active=i;save();video.pause();open(i);status.textContent='裁剪范围已保存。'}});
   const detail=box.querySelector('[data-timeline-detail]');for(const edge of ['start','end'])detail.querySelector(`[data-${edge}]`).onchange=e=>{const n=Number(e.target.value);if(!Number.isFinite(n)||n<0||n>t.duration||(edge==='start'&&n>t.end-.1)||(edge==='end'&&n<t.start+.1)){status.textContent='裁剪范围无效，请检查起点和终点。';draw();return}t[edge]=n;save();video.pause();open(active);status.textContent='裁剪范围已保存。'};
   detail.querySelector('[data-before]').onclick=()=>move(-1);detail.querySelector('[data-after]').onclick=()=>move(1);detail.querySelector('[data-reset]').onclick=()=>{t.start=0;t.end=t.duration;save();video.pause();open(active)};
  }
  video.ontimeupdate=()=>{clock();const t=tracks[active];if(video.currentTime>=t.end-.015&&!video.paused){if(active+1<tracks.length)open(active+1,0,true);else{video.pause();continuing=false}}};
  video.onended=()=>{if(active+1<tracks.length)open(active+1,0,true);else continuing=false};
  box.querySelector('[data-timeline-play]').onclick=()=>{if(!video.paused){video.pause();continuing=false;return}if(video.currentTime>=tracks[active].end-.05)open(0,0,true);else video.play().catch(()=>{status.textContent='请点击播放器开始播放。'})};
  scrub.oninput=()=>{const x=Number(scrub.value);let i=0;while(i<tracks.length-1&&x>=elapsed(i)+tracks[i].end-tracks[i].start)i++;video.pause();open(i,x-elapsed(i),false)};
  box.querySelector('[data-timeline-export]').onclick=async()=>{
   if(exportState.status==='running')return;
   const requestTracks=tracks.map(({id,start,end})=>({task_id:id,start,end})),signature=version();
   exportState.status='running';exportState.signature=signature;notifyExport();
   try{
    const call=async(path,payload)=>{const r=await fetch('/api/timeline/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:project,...payload})});const d=await r.json();if(!r.ok)throw Error(d.error||'导出失败');return d};
    let j=await call('start',{clips:requestTracks});
    while(j.status==='running'){await new Promise(r=>setTimeout(r,1200));j=await call('status',{job_id:j.id})}
    if(j.status!=='completed')throw Error(j.error||'导出失败');
    Object.assign(exportState,{status:'completed',url:j.url,duration:j.duration,signature});
    localStorage.setItem('frame-timeline-export-'+project,JSON.stringify({url:j.url,duration:j.duration,signature}));
    notifyExport();
    if(signature===liveVersions.get(project)?.()){const link=document.createElement('a');link.href=j.url;link.download='';document.body.appendChild(link);link.click();link.remove()}
   }catch(e){exportState.status='failed';exportState.error=e.message;notifyExport()}
  };
  renderExport();open(0);
 }
 return {mount};
})();
