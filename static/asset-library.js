/* Public asset workflow: story -> master -> adopted views -> pinned shot reference. */
const MaterialLibrary = (() => {
  const e=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const version=(asset,n=asset.latest_version)=>asset.versions.find(v=>v.version===n);
  const adoptedSource=asset=>{const latest=version(asset),adopted=asset.adopted_version?version(asset,asset.adopted_version):null;return adopted&&asset.adopted_design_matches_latest!==false&&latest.summary===adopted.summary&&(latest.variant||'')===(adopted.variant||'')?adopted:null};
  const typeName=kind=>kind==='character'?'角色':'物品';
  const taskName={reserved:'计划已确认 · 等待执行',submitting:'提交中 · 请勿重复',queued:'排队中',running:'生成中',unknown:'提交结果待核对',completed:'生成已完成',failed:'生成失败',rejected:'请求未受理',cancelled:'未提交计划已取消'};
  let active=null,shotCatalog=null;
  function dialog(title,body){
    const opener=document.activeElement;
    const node=document.createElement('dialog');node.className='asset-dialog';
    node.innerHTML=`<header><h2>${e(title)}</h2><button type="button" data-close aria-label="关闭${e(title)}">关闭</button></header><div data-body>${body}</div><p class="dialog-error" role="alert"></p>`;
    node.setAttribute('aria-label',title);node.querySelector('.dialog-error').tabIndex=-1;
    document.body.append(node);node.querySelector('[data-close]').onclick=()=>node.close();
    node.addEventListener('keydown',event=>{
      if(event.key!=='Tab')return;
      const controls=[...node.querySelectorAll('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href],summary,[tabindex="0"]')].filter(el=>el.getClientRects().length);
      const first=controls[0],last=controls.at(-1);
      if(!first){event.preventDefault();return}
      if(!controls.includes(document.activeElement)){event.preventDefault();(event.shiftKey?last:first).focus();return}
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
    });
    node.addEventListener('close',()=>{node.remove();if(opener?.isConnected)opener.focus()},{once:true});node.showModal();
    return node;
  }
  async function safe(node,fn){
    const error=node.querySelector('.dialog-error');if(error)error.textContent='';
    const buttons=[...node.querySelectorAll('button')].filter(b=>!b.disabled&&!b.hasAttribute('data-close'));
    buttons.forEach(b=>b.disabled=true);node.setAttribute('aria-busy','true');
    const progress=document.createElement('p');progress.className='muted';progress.setAttribute('role','status');progress.textContent='正在处理，请稍候…';node.append(progress);
    try{return await fn()}catch(ex){if(error){error.textContent=ex.message;error.focus()}else throw ex}finally{progress.remove();node.removeAttribute('aria-busy');buttons.forEach(b=>{if(b.isConnected)b.disabled=false})}
  }
  async function getCatalog(){const response=await fetch('/api/assets');const data=await response.json();if(!response.ok)throw Error(data.error||'素材库读取失败');return data}
  async function request(catalog,action,payload={}){
    const response=await fetch('/api/assets/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:catalog.project_id,revision:catalog.revision,...payload})});
    const data=await response.json();if(!response.ok)throw Error(data.error||'素材操作未完成');return data;
  }
  function openImage(view,title){
    const node=dialog(title,`<p>${e(view.label)} · ${view.width} × ${view.height}</p><div class="shot-actions"><button data-fit>适应窗口</button><button data-original>原尺寸</button></div><div class="asset-large-stage"><img src="${e(view.url)}" alt="${e(title+' '+view.label)}"></div>`);
    node.classList.add('asset-lightbox');const img=node.querySelector('img');
    node.querySelector('[data-original]').onclick=()=>{img.style.maxWidth='none';img.style.maxHeight='none';img.style.width=view.width+'px'};
    node.querySelector('[data-fit]').onclick=()=>{img.style.maxWidth='100%';img.style.maxHeight='65dvh';img.style.width=''};
  }
  function viewsHTML(v){return (v.views||[]).map(view=>`<div class="asset-view"><button type="button" data-open-image="${e(view.id)}" aria-label="放大${e(view.label)}"><img src="${e(view.url)}" alt="${e(view.label)}" loading="lazy"></button><small>${e(view.label)} · ${view.width} × ${view.height}</small></div>`).join('')}
  function bindImages(node,v,title){node.querySelectorAll('[data-open-image]').forEach(b=>b.onclick=()=>openImage(v.views.find(x=>x.id===b.dataset.openImage),title))}
  function editor(catalog,asset,onDone){
    const current=asset?version(asset):{name:'',summary:'',role:'',variant:'',related_asset_ids:[]};
    const roles=catalog.assets.filter(a=>a.kind==='character');
    const node=dialog(asset?'编辑'+typeName(asset.kind)+'设定':'新增角色或物品',`<form data-editor>${asset?'':`<label class="field" for="material-kind">素材类型</label><select id="material-kind"><option value="character">角色</option><option value="object">物品</option></select>`}<label class="field" for="material-name">名称</label><input id="material-name" maxlength="80" required value="${e(current.name)}"><label class="field" for="material-summary">简要设定</label><textarea id="material-summary" rows="5" placeholder="写下外貌、性格或物品的形状与材质，不需要写提示词。">${e(current.summary)}</textarea><label class="field" for="material-variant">外观版本说明（可选）</label><input id="material-variant" maxlength="160" placeholder="例如：夜班制服 / 旧款黄铜" value="${e(current.variant)}"><details><summary>故事关系（可选）</summary><label class="field" for="material-role">故事中的作用</label><input id="material-role" maxlength="160" value="${e(current.role)}">${roles.length?`<p class="muted">与哪些角色有关？物品始终独立保存。</p>${roles.map(a=>`<label class="asset-choice"><input type="checkbox" data-related value="${e(a.id)}" ${(current.related_asset_ids||[]).includes(a.id)?'checked':''}>${e(version(a).name)}</label>`).join('')}`:''}</details><div class="shot-actions"><button class="primary" type="submit">${asset?'保存为新版本':'创建素材'}</button></div><p class="muted">保存设定不会发起生成，也不会自动采用候选图片。外观设定改动会重新开始候选视图，旧图保留在历史版本。</p></form>`);
    node.querySelector('form').onsubmit=event=>{event.preventDefault();safe(node,async()=>{
      const payload={name:node.querySelector('#material-name').value,summary:node.querySelector('#material-summary').value,variant:node.querySelector('#material-variant').value,role:node.querySelector('#material-role').value,related_asset_ids:[...node.querySelectorAll('[data-related]:checked')].map(x=>x.value)};
      if(asset)payload.asset_id=asset.id;else payload.kind=node.querySelector('#material-kind').value;
      const result=await request(catalog,asset?'edit':'create',payload);node.close();await onDone(result);
    })};
  }
  function designHTML(design){
    if(!design)return '<p class="muted">系统正在补齐设计草案。</p>';
    const rows=design.summary||[],pick=labels=>rows.filter(r=>labels.includes(r.label)).map(r=>r.value).join('；');
    const identity=pick(['身份','年龄','服役年限','外观身份','主体类型','脸部轮廓','头部轮廓','辨识特征','头部外壳','传感器与辨识特征','体态与结构','辨识结构']),hair=pick(['发型与发色','头部覆盖','毛皮/外壳']),clothes=pick(['外层服装','内搭','下装','鞋','上身外壳','关节护套','下肢结构','机足','机体结构','关节','手部与机足','表面材料','固定识别特征','肢体/操作部件']),object=pick(['形状','材质','结构','颜色','磨损标记']);
    return `<section class="asset-design"><h3>设计草案 v${e(design.design_version||'1')}</h3>${design.conflicts?.length?`<p class="dialog-error">需核对故事事实：${e(design.conflicts.join('；'))}</p>`:''}<p class="muted">${design.ready?'由制作助手按独立Skill交接，尚不表示图片或一致性已批准。':'制作助手尚未交接完整视觉设计；无需用户填写脸型、服装锚点或技术参数。'}</p>${identity?`<p><strong>主体：</strong>${e(identity)}</p>`:''}${hair?`<p><strong>发型：</strong>${e(hair)}</p>`:''}${clothes?`<p><strong>服装/结构：</strong>${e(clothes)}</p>`:''}${object?`<p><strong>外观：</strong>${e(object)}</p>`:''}<section class="design-sources">${rows.map(r=>`<p><strong>${e(r.label)}</strong> · ${e(r.source)}<br>${e(r.value)}</p>`).join('')}</section></section>`;
  }
  function productionLabel(asset){const status=asset.production_status||{};
    if(!asset.adopted_version)return '设计与母版待审阅';
    if(!status.reviewed_tags?.length)return '历史采用 · 当前制作规范待复核';
    if(asset.kind==='object')return '物品主图/所选视图已人工审阅';
    if(!status.identity_reviewed)return '身份母版待建立';
    if(!status.body_reviewed)return '身份母版已审阅 · 全身正面待建立';
    return status.multiview_reviewed?'头部与全身六视图已人工审阅':'基础母版已审阅 · 头部与全身视图待补齐';
  }
  function choosePlan(catalog,asset,onDone){
    const master=asset.master_plan?.identity_tag||(asset.kind==='character'?'portrait':'main'),structure=asset.master_plan?.structure_tag||'body_front',adopted=adoptedSource(asset);
    const status=asset.production_status||{},reviewed=status.reviewed_tags||[];
    const source=adopted?.views.find(v=>v.tag===master&&reviewed.includes(master));
    const bodyReady=!!(source&&reviewed.includes(structure));
    const allowed=tag=>tag===master||!!(source&&(asset.kind==='object'||!['body_side','body_back','three_quarter'].includes(tag)||bodyReady));
    const defaultTag=!source?master:asset.kind==='character'&&!bodyReady?structure:null;
    const labels=catalog.view_labels[asset.kind];
    const node=dialog('选择需要的独立视图',`<p>${e(version(asset).name)} · 当前设定 v${asset.latest_version}</p><p class="muted">${asset.kind==='character'?'人物准备头部和全身的正、侧、背六个独立视图。先采用首张母版，再补齐其余视图；头像母版可作为头部正面。':'先采用物品主图，再按需要补充侧面、背面或细节。'}</p>${source?`<p class="asset-pause">扩展视图基于已采用 v${adopted.version}。全身优先沿用已采用的全身正面，头部优先沿用头像或头部正面。</p>`:''}<fieldset><legend>本次生成</legend>${Object.entries(labels).filter(([tag])=>(asset.available_view_tags||[]).includes(tag)).map(([tag,label])=>`<label class="asset-choice"><input type="checkbox" data-view-tag value="${tag}" ${tag===defaultTag?'checked':''} ${!allowed(tag)?'disabled':''}>${e(label)}${tag===master?' · 母版':''}</label>`).join('')}</fieldset><button class="primary" data-preview>预览本次生成计划</button>`);
    const previewButton=node.querySelector('[data-preview]');
    const updateSelection=()=>{previewButton.disabled=!node.querySelector('[data-view-tag]:checked')};
    if(defaultTag&&!(asset.available_view_tags||[]).includes(defaultTag)){const note=document.createElement('p');note.className='muted';note.textContent='下一步视图描述尚待制作助手交接，已采用母版会保留。';node.querySelector('[data-body]').prepend(note)}
    updateSelection();
    node.querySelectorAll('[data-view-tag]').forEach(control=>control.onchange=()=>{
      if(!control.checked){updateSelection();return};
      const single=control.value===master||(asset.kind==='character'&&control.value==='body_front');
      node.querySelectorAll('[data-view-tag]').forEach(other=>{if(other!==control&&(single||other.value===master||(asset.kind==='character'&&other.value==='body_front')))other.checked=false});updateSelection();
    });
    node.querySelector('[data-preview]').onclick=()=>safe(node,async()=>{
      const tags=[...node.querySelectorAll('[data-view-tag]:checked')].map(el=>el.value);
      const items=tags.map(tag=>{const reference=tag.startsWith('body_')?(adopted?.views.find(v=>v.tag==='body_front')||source):tag.startsWith('head_')?(adopted?.views.find(v=>v.tag==='head_front')||source):source;return {asset_id:asset.id,version:asset.latest_version,view_tag:tag,...(tag!==master&&reference?{reference_version:adopted.version,reference_view_id:reference.id}:{})}});
      const model=document.querySelector('#material-model')?.value||catalog.default_model;
      const preview=await request(catalog,'generation/preview',{items,model});node.close();confirmPlan(catalog,items,model,preview,onDone);
    });
  }
  function confirmPlan(catalog,items,model,preview,onDone){
    const enabled=catalog.generation_enabled&&(catalog.allowed_models||[]).includes(model);
    const designs=[...new Map((preview.designs||[]).map(d=>[d.asset_id,d])).values()];
    const node=dialog('确认生成计划',`${designs.map(designHTML).join('')}<p>${e(catalog.models?.[model]||model)} · 每项一张独立原图</p><ol class="asset-plan-list">${preview.items.map(item=>`<li>${e(item.name)} · ¥${Number(item.estimate).toFixed(2)}</li>`).join('')}</ol><div class="asset-cost">预计 ¥${Number(preview.estimated_cny).toFixed(2)}</div><p class="muted">${e(preview.note)}</p>${enabled?'':'<p class="asset-pause">'+(catalog.generation_paused?'当前项目暂停生成。计划可以预览，不会恢复授权或产生调用。':!(catalog.allowed_models||[]).includes(model)?'此模型尚未纳入当前项目授权范围，不会发起调用。':'当前没有可执行的图片预算授权，请先在设置中处理。')+'</p>'}<div class="shot-actions"><button class="primary" data-confirm ${enabled?'':'disabled'}>${enabled?'确认生成 '+items.length+' 张':'生成暂不可用'}</button></div><p class="muted">结果先保存为候选。只有人工采用后，才供新镜头选用。</p>`);
    const requestId=crypto.randomUUID().replaceAll('-','');
    node.querySelector('[data-confirm]').onclick=()=>safe(node,async()=>{
      const result=await request({...catalog,revision:preview.revision},'generation/submit',{items,model,fingerprint:preview.fingerprint,request_id:requestId});node.close();await onDone(result);
    });
  }
  async function upload(catalog,asset,onDone){
    const node=dialog('补充已有图片',`<p class="muted">可从电脑选择，或从本项目已保存的图片中选择。每次只导入一张独立视图，原图按项目隔离保存。</p><label class="field" for="material-upload-tag">这张图片的视图</label><select id="material-upload-tag">${Object.entries(catalog.view_labels[asset.kind]).map(([tag,label])=>`<option value="${tag}">${e(label)}</option>`).join('')}</select><label class="field" for="material-upload-file">选择本机图片（PNG / JPEG / WebP，最多12MB）</label><input id="material-upload-file" type="file" accept="image/png,image/jpeg,image/webp"><button data-import-file style="margin-top:12px">导入选定图片</button>${catalog.sources.length?`<hr><label class="field" for="material-existing">已有项目图片</label><select id="material-existing">${catalog.sources.map(s=>`<option value="${e(s.source_id)}">${e(s.name)}</option>`).join('')}</select><button data-import-existing style="margin-top:12px">导入这张项目图片</button>`:''}<p class="muted">导入成为新候选版本，不覆盖历史或已采用的素材。</p>`);
    node.querySelector('[data-import-file]').onclick=()=>safe(node,async()=>{
      const file=node.querySelector('#material-upload-file').files[0];if(!file)throw Error('请先选择一张图片');
      if(file.size>catalog.limits.max_bytes)throw Error('图片超过12MB，请选择较小原图');
      if(typeof createImageBitmap==='function'){const image=await createImageBitmap(file);try{if(image.width>8192||image.height>8192||image.width*image.height>16000000)throw Error('图片尺寸超过支持范围')}finally{image.close()}}
      const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
      const result=await request(catalog,'upload',{asset_id:asset.id,view_tag:node.querySelector('#material-upload-tag').value,filename:file.name,base64:btoa(binary)});node.close();await onDone(result);
    });
    const existing=node.querySelector('[data-import-existing]');if(existing)existing.onclick=()=>safe(node,async()=>{
      const result=await request(catalog,'import-existing',{asset_id:asset.id,view_tag:node.querySelector('#material-upload-tag').value,source_id:node.querySelector('#material-existing').value});node.close();await onDone(result);
    });
  }
  function history(catalog,asset,onDone){
    const node=dialog(version(asset).name+' · 版本与视图',`<label class="field" for="material-history-version">查看版本</label><select id="material-history-version">${[...asset.versions].reverse().map(v=>`<option value="${v.version}">v${v.version}${asset.adopted_version===v.version?' · 已采用':' · 候选/历史'}</option>`).join('')}</select><div data-version-body></div>`);
    function draw(){
      const v=version(asset,Number(node.querySelector('select').value)),body=node.querySelector('[data-version-body]');
      const review=v.production_status||{},isAdopted=asset.adopted_version===v.version,needsReview=isAdopted&&!(review.reviewed_tags||[]).length;
      body.innerHTML=`${designHTML(v.design_summary)}<p style="white-space:pre-wrap">${e(v.summary)}</p>${v.variant?`<p>外观：${e(v.variant)}</p>`:''}<div class="asset-view-grid">${viewsHTML(v)}</div>${v.views.length?'':'<p class="empty">此版本尚无图片。可先生成母版，之后补需要的视图。</p>'}<div class="shot-actions"><button class="primary" data-adopt>${needsReview?'按当前规范重新审阅 v'+v.version:isAdopted?'取消采用 v'+v.version:'人工采用 v'+v.version}</button>${isAdopted&&needsReview?`<button data-unadopt>取消历史采用 v${v.version}</button>`:''}<button data-plan ${asset.design_summary?.ready?'':'disabled'}>生成需要的视图</button></div><p class="muted">采用版本用于后续选择；镜头已引用的旧版本不会自动替换。</p>`;
      bindImages(body,v,v.name);
      if(!v.design_summary?.ready&&(!isAdopted||needsReview))body.querySelector('[data-adopt]').disabled=true;
      if(v.views.length&&v.design_summary?.ready&&(!isAdopted||needsReview)){
        const adoptButton=body.querySelector('[data-adopt]');adoptButton.disabled=true;
        const status=document.createElement('p');status.className='muted';status.setAttribute('role','status');status.textContent='正在载入原图，显示完整后可采用。';body.append(status);
        const images=[...body.querySelectorAll('img')];images.forEach(img=>img.loading='eager');
        Promise.all(images.map(img=>img.decode())).then(()=>{if(adoptButton.isConnected){adoptButton.disabled=false;status.textContent='请逐张检查身份、外观和视图，再决定采用。'}}).catch(()=>{if(status.isConnected)status.textContent='原图未能完整显示，请关闭后重试；暂不能采用。'});
      }
      const cancel=body.querySelector('[data-unadopt]');if(cancel)cancel.onclick=()=>safe(node,async()=>{const result=await request(catalog,'unadopt',{asset_id:asset.id,version:v.version});node.close();await onDone(result)});
      body.querySelector('[data-plan]').onclick=()=>{node.close();choosePlan(catalog,asset,onDone)};
      body.querySelector('[data-adopt]').onclick=()=>safe(node,async()=>{
        const result=await request(catalog,isAdopted&&!needsReview?'unadopt':'adopt',{asset_id:asset.id,version:v.version});node.close();await onDone(result);
      });
    }
    node.querySelector('select').onchange=draw;draw();
  }
  async function mount(container,options){
    if(active)active.closed=true;
    const context={closed:false,filter:'all',query:'',layout:(()=>{try{return localStorage.getItem('frame-material-layout')==='list'?'list':'grid'}catch{return 'grid'}})(),catalog:null};active=context;
    container.innerHTML=`<div class="asset-library"><div class="title-row"><div class="page-heading"><span class="muted">素材</span><span data-asset-count class="muted"></span></div><div class="asset-heading-actions"><button data-organize>从故事整理素材</button><button class="primary" data-create>＋ 新增素材</button></div></div><div class="asset-toolbar"><div class="asset-filters" role="group" aria-label="素材类型筛选"><button data-filter="all" aria-pressed="true">全部</button><button data-filter="character" aria-pressed="false">角色</button><button data-filter="object" aria-pressed="false">物品</button></div><input class="asset-search" type="search" aria-label="搜索素材" placeholder="搜索名称或设定"><div class="asset-layout-switch" role="group" aria-label="素材显示方式"><button data-layout="grid">网格</button><button data-layout="list">列表</button></div><div class="asset-model"><label for="material-model" class="muted">本次图片模型</label><select id="material-model"></select></div></div><div data-asset-notice role="status"></div><div data-asset-list class="asset-grid"><p>正在读取本项目素材…</p></div><section class="panel" data-asset-tasks style="margin-top:24px"></section></div>`;
    container.querySelector('.asset-toolbar').insertAdjacentHTML('beforebegin','<div class="asset-heading-actions" style="margin-bottom:16px"><button type="button" data-project-style aria-haspopup="dialog">项目视觉风格</button></div>');
    const alive=()=>!context.closed&&container.isConnected&&location.hash==='#characters'&&context.catalog?.project_id===options.projectId;
    const done=async()=>{if(!alive())return;await load();if(options.onMutation)await options.onMutation()};
    function draw(){
      const catalog=context.catalog,notice=container.querySelector('[data-asset-notice]');
      notice.innerHTML=catalog.generation_paused?'':catalog.generation_enabled?'<p class="muted">先预览本次素材、视图和总费用，再确认生成。结果完成后仍需人工采用。</p>':`<p class="asset-pause">${catalog.generation_paused?'本项目的新生成已暂停。':'本项目尚无可执行的图片预算授权。'}可整理设定、预览费用和审阅已有素材；不会自动生成。</p>`;
      const list=catalog.assets.filter(a=>(context.filter==='all'||a.kind===context.filter)&&(!context.query||[version(a).name,version(a).summary].join(' ').toLocaleLowerCase().includes(context.query)));
      container.querySelector('[data-asset-count]').textContent=list.length+' / '+catalog.assets.length;
      container.querySelector('[data-asset-list]').classList.toggle('asset-list',context.layout==='list');
      container.querySelectorAll('[data-layout]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.layout===context.layout)));
      container.querySelector('[data-asset-list]').innerHTML=list.length?list.map(a=>{
        const latest=version(a),cover=latest.views.find(v=>v.tag===(a.kind==='character'?'portrait':'main'))||latest.views[0];
        return `<article class="material-card" data-material="${e(a.id)}"><div class="material-cover ${cover?'has-image':'is-empty'}">${cover?`<button type="button" data-cover aria-label="放大${e(latest.name)}的${e(cover.label)}"><img src="${e(cover.url)}" alt="${e(latest.name+' '+cover.label)}" loading="lazy"></button>`:`<div class="material-empty"><p>尚无图片<br>${a.design_summary?.ready?'先生成一张'+e(catalog.view_labels[a.kind][a.master_plan?.identity_tag]||'外观')+'母版。':'待制作助手交接视觉设计，无需准备机器提示词。'}</p></div>`}</div><div class="material-content"><div class="panel-head"><h2>${e(latest.name)}</h2><span class="badge">${typeName(a.kind)}</span></div><div class="material-version">当前 v${a.latest_version} · ${a.adopted_version?'已采用 v'+a.adopted_version:'尚未采用'} · ${latest.views.length} 张独立视图</div><p class="material-summary">${e(latest.summary||'还没有简要设定。')}</p><p class="material-production">${e(productionLabel(a))}</p><div class="material-actions"><button class="primary" data-generate ${a.design_summary?.ready?'':'disabled'}>${adoptedSource(a)?.views.length?'生成需要的视图':'生成外观母版'}</button><button data-detail aria-haspopup="dialog">查看详情</button></div></div></article>`;
      }).join(''):'<section class="panel empty"><strong>这里还没有'+(context.filter==='all'?'素材':context.filter==='character'?'角色':'物品')+'</strong><p>从故事整理已有角色和物品，或新增一项简要设定，再生成母版。</p></section>';
      container.querySelectorAll('[data-material]').forEach(card=>{
        const a=catalog.assets.find(x=>x.id===card.dataset.material),latest=version(a),cover=latest.views.find(v=>v.tag===(a.kind==='character'?'portrait':'main'))||latest.views[0];
        if(cover)card.querySelector('[data-cover]').onclick=()=>openImage(cover,latest.name);
        card.querySelector('[data-generate]').onclick=()=>choosePlan(catalog,a,done);
        card.querySelector('[data-detail]').onclick=()=>{
          const node=dialog(latest.name+' · 素材详情',`<p class="material-version">当前 v${a.latest_version} · ${a.adopted_version?'已采用 v'+a.adopted_version:'尚未采用'} · ${latest.views.length} 张独立视图</p><p style="white-space:pre-wrap">${e(latest.summary||'还没有简要设定。')}</p>${designHTML(a.design_summary)}<div class="material-actions"><button data-history>视图与历史</button><button data-edit>编辑设定</button><button data-upload>导入已有图片</button></div>`);
          node.classList.add('asset-detail-dialog');
          node.querySelector('[data-history]').onclick=()=>{node.close();history(catalog,a,done)};
          node.querySelector('[data-edit]').onclick=()=>{node.close();editor(catalog,a,done)};
          node.querySelector('[data-upload]').onclick=()=>{node.close();upload(catalog,a,done)};
        };
      });
      const tasks=catalog.tasks||[],box=container.querySelector('[data-asset-tasks]');box.hidden=!tasks.length;
      box.innerHTML='<h2>素材生成记录</h2>'+tasks.map(t=>`<article class="asset-task"><strong>${e(t.name)}</strong> <span class="status">${e(taskName[t.status]||'待核对')}</span><p>预计 ¥${Number(t.estimate||0).toFixed(2)}${t.archived_version?' · 候选 v'+t.archived_version+' 已保存'+(t.currently_adopted?' · 已纳入当前采用版本':' · 待审阅或保留为候选'):''}</p>${t.error||t.result_issue||t.download_error?`<p>${e(t.error||t.result_issue||t.download_error)}</p>`:''}${['queued','running','unknown'].includes(t.status)||t.download_error?`<button data-task-poll="${e(t.id)}">${t.download_error?'仅重试保存原图':'查询原任务'}</button>`:''}</article>`).join('')+(catalog.batches||[]).filter(b=>tasks.some(t=>t.batch_id===b.id&&t.status==='reserved')).map(b=>`<div class="shot-actions"><button data-continue="${e(b.id)}" ${catalog.generation_enabled?'':'disabled'}>继续已确认计划</button><button data-cancel-batch="${e(b.id)}">取消尚未提交的计划项</button></div>`).join('');
      box.querySelectorAll('[data-task-poll]').forEach(b=>b.onclick=()=>run(()=>request(catalog,'generation/poll',{task_id:b.dataset.taskPoll})));
      box.querySelectorAll('[data-continue]').forEach(b=>b.onclick=()=>run(()=>request(catalog,'generation/advance',{batch_id:b.dataset.continue})));
      box.querySelectorAll('[data-cancel-batch]').forEach(b=>b.onclick=()=>run(()=>request(catalog,'generation/cancel',{batch_id:b.dataset.cancelBatch})));
    }
    async function run(fn){try{await fn();await done()}catch(error){container.querySelector('[data-asset-notice]').textContent=error.message}}
    function renderProjectStyle(catalog){
      const style=catalog.project_style||{},ref=style.reference,seen=new Set(),choices=[];
      for(const asset of catalog.assets)for(const ver of asset.versions)for(const view of ver.views||[]){if(!seen.has(view.id)){seen.add(view.id);choices.push({id:view.id,label:ver.name+' · '+view.label+' · v'+ver.version})}}
      const node=dialog('项目视觉风格','<div data-style-content></div>');
      const box=node.querySelector('[data-style-content]');
      box.innerHTML=`<p class="muted">同一项目后续图片共用风格；参考图仅用于色彩、光线和质感，不自动复制人物。风格变更保留历史。</p><label class="field" for="project-style-description">视觉风格描述</label><textarea id="project-style-description" rows="3" placeholder="例如：冷白工业空间，写实电影光影，低饱和色彩。">${e(style.description||'')}</textarea>${ref?`<p>当前参考图</p><img src="${e(ref.url)}" alt="当前项目风格参考图" style="max-width:180px;max-height:150px;object-fit:contain">`:''}<label class="field" for="project-style-source">风格参考图</label><select id="project-style-source"><option value="keep">${ref?'保留当前参考图':'暂不使用参考图'}</option>${ref?'<option value="clear">移除参考图</option>':''}${choices.map(v=>`<option value="${e(v.id)}">${e(v.label)}</option>`).join('')}</select><label class="field" for="project-style-file">或从电脑选择参考图（PNG / JPEG / WebP，最多10MB）</label><input type="file" id="project-style-file" accept="image/png,image/jpeg,image/webp"><button type="button" data-save-style style="margin-top:12px">保存项目风格</button><p class="muted">保存不生成图片，也不会替换已生成结果。修改简要描述后，详细风格需由制作助手重新整理；需确保参考图片可用于本项目。</p>`;
      const details=document.createElement('button');details.type='button';details.textContent='查看具体风格提示词';details.setAttribute('aria-haspopup','dialog');
      const prompt=style.prompt||style.description||'';
      details.onclick=()=>{
        const draft=box.querySelector('#project-style-description').value!==(style.description||'');
        const view=dialog('具体风格提示词',`<p class="muted">这是已保存的项目风格部分；生成时还会组合素材或镜头描述及参考图。</p>${draft?'<p class="muted">描述已修改但尚未保存；下方仍显示上次保存的内容。</p>':''}<p data-style-prompt style="white-space:pre-wrap;overflow-wrap:anywhere"></p>`);
        view.querySelector('[data-style-prompt]').textContent=style.prompt?prompt:style.description?'详细风格尚未整理，当前仅有简要描述：\n'+style.description:'尚未设置风格提示词。';
      };
      box.querySelector('#project-style-description').after(details);
      box.querySelector('[data-save-style]').onclick=()=>safe(node,async()=>{
        const payload={description:box.querySelector('#project-style-description').value,reference_action:'keep'},file=box.querySelector('#project-style-file').files[0],choice=box.querySelector('#project-style-source').value;
        if(file){if(file.size>10*1024*1024)throw Error('参考图超过10MB');const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));Object.assign(payload,{reference_action:'upload',filename:file.name,base64:btoa(binary)})}
        else if(choice==='clear')payload.reference_action='clear';else if(choice!=='keep')Object.assign(payload,{reference_action:'select',view_id:choice});
        await request(context.catalog,'style',payload);node.close();await done();
      });
    }
    async function load(){const data=await getCatalog();if(context.closed||!container.isConnected||data.project_id!==options.projectId)return;context.catalog=data;const select=container.querySelector('#material-model');if(!select.options.length){select.innerHTML=Object.entries(data.models||{}).map(([id,label])=>`<option value="${e(id)}">${e(label)}</option>`).join('');select.value=data.default_model}draw()}
    container.querySelector('[data-project-style]').onclick=()=>{if(context.catalog)renderProjectStyle(context.catalog)};
    container.querySelectorAll('[data-filter]').forEach(button=>button.onclick=()=>{context.filter=button.dataset.filter;container.querySelectorAll('[data-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));if(context.catalog)draw()});
    container.querySelector('.asset-search').oninput=event=>{context.query=event.target.value.trim().toLocaleLowerCase();if(context.catalog)draw()};
    container.querySelectorAll('[data-layout]').forEach(button=>button.onclick=()=>{context.layout=button.dataset.layout;try{localStorage.setItem('frame-material-layout',context.layout)}catch{}if(context.catalog)draw()});
    container.querySelector('[data-create]').onclick=()=>{if(context.catalog)editor(context.catalog,null,done)};
    container.querySelector('[data-organize]').onclick=()=>run(async()=>{
      const response=await fetch('/api/assets/propose'),proposal=await response.json();if(!response.ok)throw Error(proposal.error||'素材清单读取失败');
      const node=dialog('从故事整理素材',`<p>${e(proposal.note)}</p>${proposal.items.length?`<fieldset><legend>可加入的物品</legend>${proposal.items.map((item,i)=>`<label class="asset-choice"><input type="checkbox" data-proposed="${i}" checked>${e(item.name)}</label><p class="muted">${e(item.summary)}</p>`).join('')}</fieldset><button class="primary" data-create-proposed>加入素材清单</button>`:'<p>已有角色已保留。暂未发现新的物品候选；你也可以直接新增素材。</p>'}`);
      const button=node.querySelector('[data-create-proposed]');if(button)button.onclick=()=>safe(node,async()=>{await request(context.catalog,'organize',{names:[...node.querySelectorAll('[data-proposed]:checked')].map(b=>proposal.items[Number(b.dataset.proposed)].name)});node.close();await done()});
    });
    try{await load()}catch(error){if(container.isConnected)container.querySelector('[data-asset-notice]').textContent=error.message}
    let attempts=0;
    async function tick(){
      if(!alive()||attempts>=90)return;
      try{
        const catalog=context.catalog,live=(catalog.tasks||[]).find(t=>['queued','running'].includes(t.status));
        if(live){attempts++;await request(catalog,'generation/poll',{task_id:live.id});await load()}
        else if(catalog.generation_enabled){const batch=(catalog.batches||[]).find(b=>catalog.tasks.some(t=>t.batch_id===b.id&&t.status==='reserved')&&!catalog.tasks.some(t=>t.batch_id===b.id&&(['unknown','failed','rejected','submitting'].includes(t.status)||t.result_issue||t.download_error)));if(batch){attempts++;await request(catalog,'generation/advance',{batch_id:batch.id});await load()}}
      }catch(error){if(alive())container.querySelector('[data-asset-notice]').textContent=error.message}
      if(alive())setTimeout(tick,document.hidden?30000:8000);
    }
    if(alive())setTimeout(tick,8000);
  }
  async function mountShotReferences(state,options={}){
    if(location.hash!=='#shots')return;const pid=state.project_id;
    const catalog=await getCatalog();if(location.hash!=='#shots'||catalog.project_id!==pid)return;shotCatalog=catalog;
    state.shots.forEach((shot,i)=>{
      const card=document.querySelectorAll('.shot-body')[i];if(!card||card.querySelector('[data-material-refs]'))return;
      const box=document.createElement('details');box.className='asset-ref-summary';box.dataset.materialRefs=shot.id;
      const refs=shot.asset_references||[];
      box.innerHTML=`<summary>参考素材 · ${refs.length} 项</summary>${refs.map(r=>`<div class="asset-ref-row"><span>${e(r.name)} · v${r.version} · ${r.views.length} 张视图</span><button data-remove-ref="${e(r.asset_id)}">移除本镜引用</button></div>`).join('')}<button data-select-ref style="margin-top:10px">选择已采用素材</button><p class="muted">镜头固定使用明确版本，采用新版不会自动替换。修改引用后需要重新审阅。</p>`;
      card.append(box);
      const done=async()=>{if(options.onMutation)await options.onMutation()};
      box.querySelectorAll('[data-remove-ref]').forEach(b=>b.onclick=()=>act(async()=>{const latest=await getCatalog();await request(latest,'unbind',{shot_id:shot.id,asset_id:b.dataset.removeRef});await done()}));
      box.querySelector('[data-select-ref]').onclick=async()=>{
        try{
          const latest=await getCatalog(),choices=latest.assets.filter(a=>a.adopted_version&&(a.production_status?.ref_eligible_tags||[]).length);
          const node=dialog('为镜头选择素材',choices.length?`<p>${e(shot.name)} · 只选择本镜需要的独立视图，总计最多3张。</p><label class="field" for="material-ref-asset">已采用素材</label><select id="material-ref-asset">${choices.map(a=>`<option value="${e(a.id)}">${typeName(a.kind)} · ${e(version(a,a.adopted_version).name)} · v${a.adopted_version}</option>`).join('')}</select><div data-ref-views></div><button class="primary" data-use-ref>用于本镜 · 重新审阅</button>`:'<p>先到素材资产库生成并人工采用母版或视图，再来选择。</p><a class="button" href="#characters" data-library-link>打开素材资产库</a>');
          const link=node.querySelector('[data-library-link]');if(link)link.onclick=()=>node.close();
          if(!choices.length)return;
          function drawViews(){const asset=choices.find(a=>a.id===node.querySelector('select').value),v=version(asset,asset.adopted_version);node.querySelector('[data-ref-views]').innerHTML=v.views.filter(view=>(asset.production_status?.ref_eligible_tags||[]).includes(view.tag)).map((view,j)=>`<label class="asset-choice"><input type="checkbox" data-ref-view value="${e(view.id)}" ${j===0?'checked':''}>${e(view.label)}</label>`).join('')}
          node.querySelector('select').onchange=drawViews;drawViews();
          node.querySelector('[data-use-ref]').onclick=()=>safe(node,async()=>{const asset=choices.find(a=>a.id===node.querySelector('select').value);await request(latest,'bind',{shot_id:shot.id,asset_id:asset.id,version:asset.adopted_version,view_ids:[...node.querySelectorAll('[data-ref-view]:checked')].map(x=>x.value)});node.close();await done()});
        }catch(error){toast(error.message)}
      };
    });
  }
  return {mount,mountShotReferences};
})();
