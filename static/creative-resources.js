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
 list.querySelectorAll('[data-item]').forEach(b=>b.onclick=()=>{const item=resources.find(x=>x.id===b.dataset.item);document.querySelector('#detail-title').textContent=item.name;document.querySelector('#detail-description').textContent=item.description;document.querySelector('#detail-use').textContent=item.use;document.querySelector('#detail-instruction').textContent=item.instruction;dialog.showModal()});
}
document.querySelectorAll('[data-kind]').forEach(b=>b.onclick=()=>{kind=b.dataset.kind;draw()});
document.querySelector('#creative-search').oninput=e=>{query=e.target.value.trim().toLocaleLowerCase();draw()};
document.querySelector('#close-detail').onclick=()=>dialog.close();document.querySelector('#close-detail-bottom').onclick=()=>dialog.close();
(async()=>{try{const r=await fetch('/api/workspace/creative-resources');const data=await r.json();if(!r.ok)throw Error(data.error||'读取失败');resources=data.items;draw()}catch(e){document.querySelector('#resource-count').textContent='读取失败';document.querySelector('#creative-error').textContent=e.message}})();
