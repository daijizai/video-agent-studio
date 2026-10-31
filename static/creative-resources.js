'use strict';
const categories={size:'景别',composition:'构图',movement:'运镜'};
const escapeText=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let resources=[],kind='all',query='';
const list=document.querySelector('#creative-list'),dialog=document.querySelector('#creative-detail');
function draw(){
 const filtered=resources.filter(x=>(kind==='all'||x.kind===kind)&&(!query||[x.name,x.description,x.use].some(v=>v.toLocaleLowerCase().includes(query))));
 document.querySelector('#resource-count').textContent=filtered.length+' 项';
 document.querySelectorAll('[data-kind]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.kind===kind)));
 list.innerHTML=filtered.length?filtered.map(x=>`<article class="creative-card"><span class="creative-tag">${escapeText(categories[x.kind])}</span><h3>${escapeText(x.name)}</h3><p>${escapeText(x.description)}</p><button type="button" data-item="${escapeText(x.id)}" aria-label="查看${escapeText(x.name)}详情">查看详情</button></article>`).join(''):'<p class="creative-empty">没有找到匹配的镜头语言。</p>';
 list.querySelectorAll('[data-item]').forEach(b=>b.onclick=()=>{const item=resources.find(x=>x.id===b.dataset.item);document.querySelector('#detail-title').textContent=item.name;document.querySelector('#detail-description').textContent=item.description;document.querySelector('#detail-use').textContent=item.use;document.querySelector('#detail-instruction').textContent=item.instruction;const example=creativeExamples[item.id],section=document.querySelector('#detail-example');section.hidden=!example;document.querySelector('#example-graphic').innerHTML=example?.graphic||'';document.querySelector('#example-note').textContent=example?.note||'';document.querySelector('#example-prompt').textContent=example?.prompt||'';const toggle=document.querySelector('#example-motion-toggle');toggle.hidden=!example?.motion;document.querySelector('#example-type').textContent=example?.motion?'动态示意':'示意图';const playing=!!example?.motion&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches;section.dataset.playing=String(playing);toggle.textContent=playing?'暂停动画':'播放动画';dialog.showModal()});
}
document.querySelectorAll('[data-kind]').forEach(b=>b.onclick=()=>{kind=b.dataset.kind;draw()});
document.querySelector('#creative-search').oninput=e=>{query=e.target.value.trim().toLocaleLowerCase();draw()};
document.querySelector('#example-motion-toggle').onclick=()=>{const section=document.querySelector('#detail-example'),playing=section.dataset.playing!=='true';section.dataset.playing=String(playing);document.querySelector('#example-motion-toggle').textContent=playing?'暂停动画':'播放动画'};
document.querySelector('#close-detail').onclick=()=>dialog.close();document.querySelector('#close-detail-bottom').onclick=()=>dialog.close();
(async()=>{try{const r=await fetch('/api/workspace/creative-resources');const data=await r.json();if(!r.ok)throw Error(data.error||'读取失败');resources=data.items;draw()}catch(e){document.querySelector('#resource-count').textContent='读取失败';document.querySelector('#creative-error').textContent=e.message}})();
