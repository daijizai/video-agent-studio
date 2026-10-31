'use strict';
const list=document.querySelector('#global-providers'),select=document.querySelector('#global-provider'),form=document.querySelector('#credential-form'),error=document.querySelector('#settings-error'),result=document.querySelector('#credential-result');
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function loadProviders(){
 const response=await fetch('/api/workspace/providers'),entries=await response.json();if(!response.ok)throw Error(entries.error||'读取供应商状态失败');
 const current=select.value;
 list.innerHTML=entries.map(entry=>`<article class="provider-card"><div><h3>${esc(entry.label.replace(/\s*·\s*(默认|主用|可选|对照)$/,''))}</h3><p>${entry.credential_present?'已配置密钥':'尚未配置密钥'}${entry.id==='wan'&&!entry.endpoint_configured?' · 缺少工作空间 ID':''}</p></div><span class="provider-state ${entry.credential_present&&entry.endpoint_configured?'configured':''}">${entry.credential_present&&entry.endpoint_configured?'已配置':'待配置'}</span></article>`).join('');
 select.innerHTML=entries.map(entry=>`<option value="${esc(entry.id)}">${esc(entry.label.replace(/\s*·\s*(默认|主用|可选|对照)$/,''))}</option>`).join('');if(entries.some(entry=>entry.id===current))select.value=current;
}
form.onsubmit=async event=>{event.preventDefault();const input=document.querySelector('#global-key'),button=form.querySelector('button'),value=input.value;input.value='';button.disabled=true;error.textContent='';result.textContent='正在保存…';try{const response=await fetch('/api/workspace/credentials',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:select.value,value})});const data=await response.json();if(!response.ok)throw Error(data.error||'保存失败');await loadProviders();result.textContent='密钥已保存，尚未验证连接。'}catch(e){result.textContent='';error.textContent=e.message}finally{input.value='';button.disabled=false}};
loadProviders().catch(e=>{list.textContent='';error.textContent=e.message});
