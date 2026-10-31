async function renderProviders(page) {
 if(!['overview','tasks','characters','diagnostics'].includes(page))return;
 if((location.hash.slice(1)||'overview')!==page)return;
 const panel=document.createElement('section');panel.className='panel provider-panel';
 const cfg=state.settings;
 const save=async(patch,message)=>{state=await api('settings',patch);toast(message+'；未发起生成');render()};
 const resolutions=(provider,model)=>provider==='minimax'?(model==='MiniMax-H3'?['768P','2K']:['480P','768P']):['720p','1080p','480p'];
 if(page==='overview')return;
 if(page==='tasks'){
  panel.className='video-settings-bar';
  panel.innerHTML=`<span class="muted" id="video-settings-summary"></span><button id="video-settings-open" aria-haspopup="dialog">制作设置</button>`;
  $('#view').prepend(panel);
  const names={seedance25:'Seedance 2.5',seedance:'Seedance 2.0 Mini',minimax:cfg.minimax_model||'MiniMax-H3','wan3-prime':'Wan3.0 Prime',wan3:'Wan3.0',wan:'Wan 2.6'};
  $('#video-settings-summary').textContent=[names[cfg.provider]||cfg.provider||'Seedance 2.5',cfg.resolution,cfg.ratio,cfg.provider==='minimax'?'模型处理音频':cfg.audio?'默认有声':'默认无声（片段可调整）'].filter(Boolean).join(' · ');
  $('#video-settings-open').onclick=()=>{
   const dialog=document.createElement('dialog');dialog.className='video-settings-dialog';dialog.setAttribute('aria-labelledby','video-settings-title');
   dialog.innerHTML=`<div class="video-settings-head"><div><h2 id="video-settings-title">制作设置</h2><p class="muted">用于本项目后续视频生成</p></div><button type="button" data-close aria-label="关闭制作设置">×</button></div><div class="video-settings-body"><label class="field" for="provider-choice">视频生成模型</label><select id="provider-choice"><option value="minimax">MiniMax H3 · 可选</option><option value="wan3-prime">千问AI Wan3.0-Video-Prime · 可选</option><option value="wan3">Wan3.0-Video 标准版 · 可选</option><option value="wan">阿里 Wan 2.6 R2V Flash · 对照</option><option value="seedance25" selected>字节 Seedance 2.5 · 默认</option><option value="seedance">Seedance 2.0 Mini · 对照</option></select><div id="minimax-model-options"><label class="field" for="minimax-model">MiniMax 视频模型</label><select id="minimax-model"><option>MiniMax-H3</option><option>MiniMax-H3-Highspeed</option><option>MiniMax-H3-Lite</option><option>MiniMax-H3-Max</option></select></div><div class="form-grid"><div><label class="field" for="provider-resolution">分辨率</label><select id="provider-resolution"></select></div><div><label class="field" for="provider-ratio">画幅</label><select id="provider-ratio"><option value="16:9">16:9 横屏</option><option value="9:16">9:16 竖屏</option><option value="3:4">3:4 竖屏</option><option value="1:1">1:1 方形</option></select></div></div><label class="field" for="provider-audio">音频</label><select id="provider-audio"></select><p class="muted" id="model-spec-note" role="status"></p><p id="video-settings-error" role="alert"></p></div><div class="video-settings-footer"><button data-cancel>取消</button><button id="provider-save" class="primary">保存设置</button></div>`;
   panel.append(dialog);
   const q=selector=>dialog.querySelector(selector);
   q('#provider-choice').value=cfg.provider||'seedance25';q('#minimax-model').value=cfg.minimax_model||'MiniMax-H3';q('#provider-ratio').value=cfg.ratio||'16:9';
   let audioDraft=String(cfg.audio||false);
   const update=(initial=false)=>{
    const provider=q('#provider-choice').value,mini=provider==='minimax',values=resolutions(provider,q('#minimax-model').value),resolution=initial?cfg.resolution:q('#provider-resolution').value;
    q('#minimax-model-options').hidden=!mini;
    q('#provider-resolution').innerHTML=values.map(v=>`<option value="${v}">${v}</option>`).join('');q('#provider-resolution').value=values.includes(resolution)?resolution:values[0];
    const ratio=q('#provider-ratio'),supported34=['seedance25','minimax'].includes(provider);ratio.querySelector('[value="3:4"]').disabled=!supported34;if(!supported34&&ratio.value==='3:4')ratio.value='16:9';
    const audio=q('#provider-audio');if(!audio.disabled&&audio.value)audioDraft=audio.value;audio.innerHTML=mini?'<option value="provider_default">由模型处理（无独立开关）</option>':'<option value="false">无声</option><option value="true">原生有声</option>';audio.disabled=mini;if(!mini)audio.value=audioDraft;
    q('#model-spec-note').textContent='支持分辨率：'+values.join(' / ')+(resolution&&!values.includes(resolution)?'。已切换为兼容规格，请确认后保存。':'。修改设置不会重新生成已有视频。');
   };
   update(true);q('#provider-choice').onchange=()=>update();q('#minimax-model').onchange=()=>update();
   const close=()=>dialog.close();q('[data-close]').onclick=close;q('[data-cancel]').onclick=close;dialog.onclose=()=>dialog.remove();dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)close()}});
   q('#provider-save').onclick=async()=>{
    const button=q('#provider-save');button.disabled=true;
    try{const provider=q('#provider-choice').value;state=await api('settings',{provider,minimax_model:q('#minimax-model').value,resolution:q('#provider-resolution').value,ratio:q('#provider-ratio').value,audio:provider==='minimax'?cfg.audio||false:q('#provider-audio').value==='true'});close();toast('制作设置已保存；未发起生成');render()}
    catch(error){q('#video-settings-error').textContent=error.message;button.disabled=false}
   };
   dialog.showModal();
  };
 }else if(page==='characters'){
  const actions=document.querySelector('.asset-heading-actions');if(!actions)return;
  const button=document.createElement('button');button.id='image-model-open';button.type='button';button.textContent='图片默认模型';button.setAttribute('aria-haspopup','dialog');actions.prepend(button);
  button.onclick=()=>{
   const dialog=document.createElement('dialog');dialog.className='video-settings-dialog';dialog.setAttribute('aria-labelledby','image-model-title');
   dialog.innerHTML=`<div class="video-settings-head"><div><h2 id="image-model-title">图片生成默认模型</h2><p class="muted">用于本项目后续图片生成</p></div><button data-close aria-label="关闭图片模型设置">×</button></div><div class="video-settings-body"><label class="field" for="image-default-model">默认模型</label><select id="image-default-model"><option value="doubao-seedream-5-0-flash-260915">Seedream 5.0 Flash · 默认</option><option value="qwen-image-3.0-pro">Qwen Image3.0 Pro · 可选</option><option value="qwen-image-3.0">Qwen Image3.0 标准版 · 可选</option></select><p class="muted">已有素材保持原版本，保存设置不会发起生成。</p><p id="image-model-error" role="alert"></p></div><div class="video-settings-footer"><button data-cancel>取消</button><button id="image-model-save" class="primary">保存设置</button></div>`;
   $('#view').append(dialog);const q=selector=>dialog.querySelector(selector);q('#image-default-model').value=state.settings.image_model||'doubao-seedream-5-0-flash-260915';
   const close=()=>dialog.close();q('[data-close]').onclick=close;q('[data-cancel]').onclick=close;dialog.onclose=()=>dialog.remove();
   q('#image-model-save').onclick=async()=>{const submit=q('#image-model-save');submit.disabled=true;try{state=await api('settings',{image_model:q('#image-default-model').value});close();toast('图片默认模型已保存；未发起生成');render()}catch(error){q('#image-model-error').textContent=error.message;submit.disabled=false}};
   dialog.showModal();
  };
 }else{
    panel.innerHTML=`<div class="panel-head"><h2>镜头请求预检</h2><span class="badge">零网络调用</span></div><p>先保存参考图和分镜，再预览官方请求与费用估算。当前供应商：${esc(state.settings.provider||'seedance25')}。仅支持图片参考，视频输入尚未开放。</p><label class="field" for="preview-shot">镜头</label><select id="preview-shot">${state.shots.map(s=>`<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('')}</select><div class="shot-actions"><button id="provider-preview">预览请求与估价</button><button id="provider-submit" ${health.video_generation?'':'disabled'}>提交供应商${health.video_generation?'':' · 视频未授权'}</button><a class="button" href="#tasks">选择视频模型</a></div><pre id="provider-result" aria-live="polite"></pre>`;
    $('#view').prepend(panel);
    $('#provider-preview').onclick=()=>act(async()=>{const result=await api('provider/preview',{shot_id:$('#preview-shot').value});$('#provider-result').textContent='估算 ¥'+result.estimated_cny+' / '+result.note+'\n未请求模型；不含重试、存储和后期成本。\n'+JSON.stringify(result.payload,null,2)});
    $('#provider-submit').onclick=()=>act(async()=>{state=await api('provider/submit',{shot_id:$('#preview-shot').value});toast('已提交供应商，任务编号已持久化');render()});
 }
}
