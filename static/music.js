'use strict';
const button=document.querySelector('#music-start'),statusText=document.querySelector('#music-status'),errorText=document.querySelector('#music-error'),frame=document.querySelector('#music-frame'),openLink=document.querySelector('#music-open');
function show(data){
 statusText.textContent=data.ready?'音乐服务已连接 · 下载保存在本机':data.installed?'音乐服务已安装，点击启动后可搜索、试听和下载。':'音乐服务尚未安装，请查看 docs/MUSIC.md。';
 button.hidden=data.ready;openLink.hidden=!data.ready;frame.hidden=!data.ready;
 if(data.ready&&!frame.getAttribute('src'))frame.src=data.url;
}
async function request(start=false){
 errorText.textContent='';button.disabled=true;statusText.textContent=start?'正在启动音乐服务…':'正在检查本地音乐服务…';
 try{const response=await fetch('/api/music/'+(start?'start':'status'),start?{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}:{});const data=await response.json();if(!response.ok)throw Error(data.error||'音乐服务暂不可用');show(data)}catch(error){errorText.textContent=error.message;statusText.textContent='连接未完成，请重试。';button.hidden=false}finally{button.disabled=false}
}
button.onclick=()=>request(true);request();
