/* Non-destructive, project-local timeline: original task videos stay unchanged. */
const TimelineEditor=(()=>{
 const exportsByProject=new Map(),liveViews=new Map(),liveVersions=new Map();
 const escapeText=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const fmt=n=>{n=Math.max(0,Number(n)||0);return `${Math.floor(n/60)}:${(n%60).toFixed(1).padStart(4,'0')}`};
 function mount(box,clips,project,audioConfig,upperConfig,onImport){
  const available=clips.filter(c=>c.task.review_status!=='rejected_quality'&&c.task.local_video).map(c=>({id:c.task.id,name:c.segment.name+(c.task.review_status==='accepted'?'':'（待审阅）'),url:c.task.local_video,duration:Number(c.task.media_info?.duration||c.task.request?.duration||0)})).filter(c=>c.duration>.1);
  if(!available.length)return;
  const key=`frame-timeline-v1-${project}`,ids=available.map(c=>c.id).sort().join('|');let saved=null;
  try{saved=JSON.parse(localStorage.getItem(key)||'null')}catch{}
  let tracks=Array.isArray(saved?.tracks)?[...saved.tracks.map(v=>{const c=available.find(x=>x.id===v.id);return c?{...c,start:Math.max(0,Number(v.start)||0),end:Math.min(c.duration,Number(v.end)||c.duration)}:null}).filter(Boolean),...available.filter(c=>!saved.tracks.some(v=>v.id===c.id)).map(c=>({...c,start:0,end:c.duration}))]:available.map(c=>({...c,start:0,end:c.duration}));
  if(tracks.length!==available.length||tracks.some(t=>t.end-t.start<.1))tracks=available.map(c=>({...c,start:0,end:c.duration}));
  let active=0,continuing=false;const total=()=>tracks.reduce((s,t)=>s+t.end-t.start,0);const elapsed=i=>tracks.slice(0,i).reduce((s,t)=>s+t.end-t.start,0);
  const version=()=>JSON.stringify(tracks.map(({id,start,end})=>({id,start,end})));
  const validUpper=c=>c&&Number.isFinite(c.duration)&&c.duration>0&&new RegExp('^/media/'+project+'/upper_[a-f0-9]{32}\\.mp4$').test(c.url);
  let upper=validUpper(upperConfig)?upperConfig:null;
  let upperStart=saved?.upper?.url===upper?.url?Math.max(0,Number(saved?.upper?.start)||0):0;
  let upperEnabled=!!upper&&(saved?.upper?.url!==upper.url||saved.upper.enabled!==false);
  const upperSelection=()=>upper&&upperEnabled?{url:upper.url,start:upperStart}:null;
  const includeMusic=()=>!!audio&&!audio.muted;
  const exportVersion=()=>JSON.stringify({tracks:JSON.parse(version()),music:includeMusic(),upper:upperSelection()});
  const save=()=>{localStorage.setItem(key,JSON.stringify({ids,tracks:JSON.parse(version()),upper:upper?{url:upper.url,start:upperStart,enabled:upperEnabled}:null}));renderExport()};
  let exportState=exportsByProject.get(project);
  if(!exportState){let prev=null;try{prev=JSON.parse(localStorage.getItem('frame-timeline-export-'+project)||'null')}catch{};if(prev&&typeof prev.url==='string'&&new RegExp('^/media/'+project+'/edit_[a-f0-9]{32}\\.mp4$').test(prev.url)&&typeof prev.signature==='string')exportState={status:'completed',...prev};else exportState={status:'idle'};exportsByProject.set(project,exportState)}
  box.innerHTML=`<div class="timeline-head"><div><h2>视频剪辑台</h2><p>拖动片段两端裁剪。单轨导出保留原分辨率、帧率和像素。</p></div><div class="timeline-export-actions"><button type="button" data-timeline-export>导出视频</button><div role="status" aria-live="polite" data-export-status></div><a data-timeline-download hidden download>下载剪辑后的视频</a></div></div><div class="timeline-player"><video controls playsinline preload="metadata" aria-label="剪辑预览" data-timeline-video></video></div><div class="timeline-controls"><button type="button" data-timeline-play>▶ 播放剪辑</button><span data-timeline-clock>0:00.0 / 0:00.0</span><input data-timeline-scrub type="range" min="0" step="0.04" value="0" aria-label="剪辑时间进度"></div><div class="timeline-header"><strong>视频轨道</strong><span data-timeline-total></span></div><div class="timeline-track" data-timeline-track aria-label="视频时间线"></div><p class="timeline-hint">选择片段后也可以用数字精确调整；拖动右侧手柄可剪掉尾部。</p><div data-timeline-audio-area></div><div data-timeline-detail></div><p role="status" data-timeline-status></p><div data-timeline-output></div>`;
  const video=box.querySelector('[data-timeline-video]'),scrub=box.querySelector('[data-timeline-scrub]'),track=box.querySelector('[data-timeline-track]'),status=box.querySelector('[data-timeline-status]');
  const audioArea=box.querySelector('[data-timeline-audio-area]');let audio=null;
  const upperArea=document.createElement('section');
  upperArea.className='timeline-upper';
  upperArea.setAttribute('aria-label','上半屏视频');
  audioArea.before(upperArea);
  function renderUpper(){
   upperArea.innerHTML=`<div class="timeline-header"><strong>上半屏视频</strong></div>
    <label class="timeline-upper-file">${upper?'替换上半屏 MP4':'导入上半屏 MP4'} <input type="file" accept="video/mp4,.mp4" data-upper-file></label>
    ${upper?`<div class="timeline-detail"><strong>${escapeText(upper.name)} · ${fmt(upper.duration)}</strong>
    <label>源视频起点（秒）<input data-upper-start type="number" min="0" max="${upper.duration}" step="0.01" value="${upperStart}"></label>
    <label class="timeline-upper-toggle"><input type="checkbox" data-upper-enabled ${upperEnabled?'checked':''}> 上下拼接</label></div>`:''}
    <p class="timeline-hint">上下画面等宽等高，中间用黑条分隔，导出为 3:4。剪辑轨道放在下半屏，上半屏只取画面。导出后可在此播放成片。</p>
    <p role="status" data-upper-status></p>`;
   const fileInput=upperArea.querySelector('[data-upper-file]'),message=upperArea.querySelector('[data-upper-status]');
   fileInput.onchange=async()=>{
    const file=fileInput.files[0];if(!file)return;
    if(!file.size||file.size>128*1024*1024){message.textContent='请选择不超过128MB的MP4。';fileInput.value='';return}
    fileInput.disabled=true;message.textContent='正在导入上半屏视频…';
    try{
     const query=new URLSearchParams({project_id:project,name:file.name});
     const response=await fetch('/api/timeline/import-upper?'+query,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
     const data=await response.json();
     if(!response.ok||!validUpper(data.upper))throw Error(data.error||'导入失败');
     upper=data.upper;upperStart=0;upperEnabled=true;save();renderUpper();
     onImport?.().catch(()=>{});
    }catch(error){message.textContent=error.message;fileInput.disabled=false;fileInput.value=''}
   };
   if(upper){
    upperArea.querySelector('[data-upper-enabled]').onchange=e=>{upperEnabled=e.target.checked;save()};
    upperArea.querySelector('[data-upper-start]').onchange=e=>{
     const start=e.target.valueAsNumber;
     if(!Number.isFinite(start)||start<0||start>=upper.duration){message.textContent='请输入有效的源视频起点。';e.target.value=upperStart;return}
     upperStart=start;message.textContent='';save();
    };
   }
  }
  if(audioConfig && new RegExp('^/media/'+project+'/original_soundtrack(?:_[A-Za-z0-9_-]+)?\\.mp4$').test(audioConfig.url) && Array.isArray(audioConfig.peaks)){
   audioArea.innerHTML=`<div class="timeline-header"><strong>音轨 · ${escapeText(audioConfig.name)}</strong><label><input type="checkbox" data-audio-enable checked> 播放原声</label></div><audio controls data-timeline-audio preload="metadata" aria-label="单独试听项目原音轨" style="width:100%"></audio><div class="timeline-audio-track" aria-label="原声波形"><div data-waveform class="timeline-waveform"></div><span class="timeline-audio-playhead" data-audio-playhead></span></div><p class="timeline-hint">可单独试听；波形与剪辑时间对齐。原声可能包含音乐和其他声音，勾选时将随剪辑一起导出。</p>`;
   audio=audioArea.querySelector('[data-timeline-audio]');audio.src=audioConfig.url;
   if(audioConfig.full_url===`/media/${project}/original_soundtrack_full.mp4`){
    const full=document.createElement('details');full.innerHTML='<summary>试听完整原片音轨</summary><audio controls preload="metadata" aria-label="完整原片音轨" style="width:100%"></audio>';full.querySelector('audio').src=audioConfig.full_url;audioArea.append(full);
   }
   const wave=audioArea.querySelector('[data-waveform]');wave.innerHTML=audioConfig.peaks.map(v=>`<span style="height:${Math.max(4,Math.min(100,Number(v)*100))}%"></span>`).join('');
   audioArea.querySelector('[data-audio-enable]').onchange=e=>{audio.muted=!e.target.checked;renderExport()};
  }
  function syncAudio(at,play){if(!audio)return;const a=Math.max(0,at);if(Number.isFinite(audio.duration)&&a>=audio.duration){audio.pause();return}if(Math.abs(audio.currentTime-a)>.16)audio.currentTime=a;if(play&&audio.paused)audio.play().catch(()=>{status.textContent='原声播放受浏览器限制，请重新点击播放剪辑。'});if(!play&&!audio.paused)audio.pause()}
  function renderExport(){
   const btn=box.querySelector('[data-timeline-export]'),message=box.querySelector('[data-export-status]'),link=box.querySelector('[data-timeline-download]');
   btn.disabled=exportState.status==='running';btn.textContent=exportState.status==='running'?'正在导出…':upperSelection()?'导出上下拼接':'导出视频';
   if(exportState.status==='completed'){
    const stale=exportState.signature!==exportVersion();message.textContent=stale?'上一次导出对应之前的剪辑设置。':`导出完成（${fmt(exportState.duration)}）。`;
    link.hidden=false;link.href=exportState.url;link.textContent=stale?'下载上一次导出':'重新下载视频';
    const output=box.querySelector('[data-timeline-output]');
    if(exportState.stacked&&output.dataset.url!==exportState.url){
     output.innerHTML='<div class="timeline-header"><strong>上下拼接成片</strong></div><div class="timeline-player"><video controls playsinline preload="metadata" aria-label="上下拼接成片预览"></video></div>';
     output.querySelector('video').src=exportState.url;output.dataset.url=exportState.url;
    }else if(!exportState.stacked){output.replaceChildren();delete output.dataset.url}
   }else{link.hidden=true;message.textContent=exportState.status==='running'?'正在拼接并生成文件，请稍候…':exportState.status==='failed'?exportState.error||'导出失败，请重试。':''}
  }
  liveViews.set(project,renderExport);liveVersions.set(project,exportVersion);
  function notifyExport(){liveViews.get(project)?.()}
  function clock(){const at=Math.max(0,Math.min(total(),elapsed(active)+(video.currentTime||tracks[active].start)-tracks[active].start));scrub.value=at;const head=box.querySelector('[data-audio-playhead]');if(head)head.style.left=`${100*at/Math.max(total(),.01)}%`;if(audio&&!video.paused)syncAudio(at,true);box.querySelector('[data-timeline-clock]').textContent=`${fmt(at)} / ${fmt(total())}`}
  function open(i,pos=0,play=false){active=i;const t=tracks[i];continuing=play;video.src=t.url;video.onloadedmetadata=()=>{video.currentTime=Math.min(t.end-.01,t.start+Math.max(0,pos));clock();if(continuing)video.play().catch(()=>{status.textContent='请点击播放继续预览。'})};draw()}
  function move(dir){const j=active+dir;if(j<0||j>=tracks.length)return;[tracks[active],tracks[j]]=[tracks[j],tracks[active]];active=j;save();draw();clock()}
  function draw(){
   scrub.max=total();const wave=box.querySelector('[data-waveform]');if(wave)wave.style.width=`${100*Number(audioConfig.duration||0)/Math.max(total(),.01)}%`;box.querySelector('[data-timeline-total]').textContent=`${tracks.length} 段 · ${fmt(total())}`;
   track.innerHTML=tracks.map((t,i)=>`<div class="timeline-clip ${i===active?'is-active':''}" data-index="${i}" style="flex:${Math.max(.15,t.end-t.start)}"><button type="button" class="timeline-select" data-select="${i}" aria-label="选择 ${escapeText(t.name)}"><strong>${escapeText(t.name)}</strong><span>${fmt(t.start)}–${fmt(t.end)}</span></button><button type="button" class="timeline-handle left" data-edge="start" data-index="${i}" aria-label="拖动裁剪 ${escapeText(t.name)} 开头"></button><button type="button" class="timeline-handle right" data-edge="end" data-index="${i}" aria-label="拖动裁剪 ${escapeText(t.name)} 结尾"></button></div>`).join('');
   const t=tracks[active];box.querySelector('[data-timeline-detail]').innerHTML=`<div class="timeline-detail"><strong>${escapeText(t.name)}</strong><label>起点（秒）<input data-start type="number" min="0" max="${t.duration}" step="0.1" value="${t.start.toFixed(1)}"></label><label>终点（秒）<input data-end type="number" min="0" max="${t.duration}" step="0.1" value="${t.end.toFixed(1)}"></label><span>原片 ${fmt(t.duration)}</span><button type="button" data-before ${active===0?'disabled':''}>← 前移</button><button type="button" data-after ${active===tracks.length-1?'disabled':''}>后移 →</button><button type="button" data-reset>恢复整段</button></div>`;
   track.querySelectorAll('[data-select]').forEach(b=>b.onclick=()=>{continuing=false;video.pause();syncAudio(elapsed(Number(b.dataset.select)),false);open(Number(b.dataset.select))});
   track.querySelectorAll('[data-edge]').forEach(h=>h.onpointerdown=e=>{e.preventDefault();e.stopPropagation();const i=Number(h.dataset.index),t=tracks[i],edge=h.dataset.edge,clip=h.parentElement,scale=(t.end-t.start)/Math.max(clip.getBoundingClientRect().width,1),x=e.clientX,original=t[edge];h.setPointerCapture(e.pointerId);h.onpointermove=ev=>{let v=original+(ev.clientX-x)*scale;v=Math.round(v*10)/10;t[edge]=edge==='start'?Math.max(0,Math.min(t.end-.1,v)):Math.min(t.duration,Math.max(t.start+.1,v));clip.querySelector('span').textContent=`${fmt(t.start)}–${fmt(t.end)}`};h.onpointerup=()=>{active=i;save();video.pause();open(i);status.textContent='裁剪范围已保存。'}});
   const detail=box.querySelector('[data-timeline-detail]');for(const edge of ['start','end'])detail.querySelector(`[data-${edge}]`).onchange=e=>{const n=Number(e.target.value);if(!Number.isFinite(n)||n<0||n>t.duration||(edge==='start'&&n>t.end-.1)||(edge==='end'&&n<t.start+.1)){status.textContent='裁剪范围无效，请检查起点和终点。';draw();return}t[edge]=n;save();video.pause();open(active);status.textContent='裁剪范围已保存。'};
   detail.querySelector('[data-before]').onclick=()=>move(-1);detail.querySelector('[data-after]').onclick=()=>move(1);detail.querySelector('[data-reset]').onclick=()=>{t.start=0;t.end=t.duration;save();video.pause();open(active)};
  }
  video.onplay=()=>syncAudio(elapsed(active)+video.currentTime-tracks[active].start,true);
  video.onpause=()=>{if(audio)audio.pause()};
  video.ontimeupdate=()=>{clock();const t=tracks[active];if(video.currentTime>=t.end-.015&&!video.paused){if(active+1<tracks.length)open(active+1,0,true);else{continuing=false;video.pause();syncAudio(total(),false)}}};
  video.onended=()=>{if(active+1<tracks.length)open(active+1,0,true);else continuing=false};
  box.querySelector('[data-timeline-play]').onclick=()=>{if(!video.paused){continuing=false;video.pause();syncAudio(elapsed(active)+video.currentTime-tracks[active].start,false);return}if(video.currentTime>=tracks[active].end-.05)open(0,0,true);else video.play().catch(()=>{status.textContent='请点击播放器开始播放。'})};
  scrub.oninput=()=>{const x=Number(scrub.value);let i=0;while(i<tracks.length-1&&x>=elapsed(i)+tracks[i].end-tracks[i].start)i++;continuing=false;video.pause();syncAudio(x,false);open(i,x-elapsed(i),false)};
  box.querySelector('[data-timeline-export]').onclick=async()=>{
   if(exportState.status==='running')return;
   const requestTracks=tracks.map(({id,start,end})=>({task_id:id,start,end})),signature=exportVersion(),upperRequest=upperSelection();
   exportState.status='running';exportState.signature=signature;notifyExport();
   try{
    const call=async(path,payload)=>{const r=await fetch('/api/timeline/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:project,...payload})});const d=await r.json();if(!r.ok)throw Error(d.error||'导出失败');return d};
    let j=await call('start',{clips:requestTracks,include_music:includeMusic(),upper:upperRequest});
    while(j.status==='running'){await new Promise(r=>setTimeout(r,1200));j=await call('status',{job_id:j.id})}
    if(j.status!=='completed')throw Error(j.error||'导出失败');
    const result={url:j.url,duration:j.duration,signature,stacked:!!upperRequest};
    Object.assign(exportState,{status:'completed',...result});
    localStorage.setItem('frame-timeline-export-'+project,JSON.stringify(result));
    notifyExport();
    if(!upperRequest&&signature===liveVersions.get(project)?.()){const link=document.createElement('a');link.href=j.url;link.download='';document.body.appendChild(link);link.click();link.remove()}
   }catch(e){exportState.status='failed';exportState.error=e.message;notifyExport()}
  };
  renderUpper();renderExport();open(0);
 }
 return {mount};
})();
