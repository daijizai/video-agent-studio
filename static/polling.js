// Query-only, serial, project-checked polling. This module never calls a submit endpoint.
(function(){
 const attempts=new Map(),failures=new Map();let busy=false,timer;
 function eligible(tasks){return tasks.filter(t=>t.provider_task_id&&(['queued','running'].includes(t.status)||(t.status==='unknown'&&t.provider_task_id)||(t.status==='completed'&&t.download_error))&&(attempts.get(t.id)||0)<90)}
 async function tick(){
  if(busy){schedule(8000);return}busy=true;let delay=document.hidden?30000:8000;
  try{
   if(typeof state==='undefined'||!state)return;
   const pid=state.project_id,latest=await api('state');if(latest.project_id!==pid||state.project_id!==pid)return;state=latest;const currentHealth=await api('health');if(state.project_id!==pid)return;health=currentHealth;updateImageProgress();const list=[...eligible(state.image_tasks||[]).map(t=>({...t,pollKind:'image'})),...eligible(state.tasks||[]).filter(t=>['wan3','wan3-prime','wan','seedance'].includes(t.provider)).map(t=>({...t,pollKind:'video'}))];window.framePollPausedIds=(state.image_tasks||[]).filter(t=>t.provider_task_id&&['queued','running','unknown'].includes(t.status)&&(attempts.get(t.id)||0)>=90).map(t=>t.id);renderLiveStatus();
   for(const task of list){
    if(state.project_id!==pid)break;
    attempts.set(task.id,(attempts.get(task.id)||0)+1);
    try{
     const fresh=await api('state');if(fresh.project_id!==pid||state.project_id!==pid)break;state=fresh;
     const updated=await api(task.pollKind==='video'?'provider/poll':'image/poll',{task_id:task.id});if(updated.project_id!==pid||state.project_id!==pid)break;
     state=updated;const result=(task.pollKind==='video'?updated.tasks:updated.image_tasks).find(t=>t.id===task.id);
     if(result.poll_error){failures.set(task.id,(failures.get(task.id)||0)+1);delay=Math.max(delay,Math.min(60000,8000*2**failures.get(task.id)))}else failures.delete(task.id);
     updateImageProgress();
    }catch(error){failures.set(task.id,(failures.get(task.id)||0)+1);delay=Math.max(delay,Math.min(60000,8000*2**failures.get(task.id)));const bar=document.querySelector('#live-production');if(bar)bar.textContent='查询暂时失败：'+error.message+'；将退避重查，不重新生成。'}
   }
  }finally{busy=false;schedule(delay)}
 }
 function schedule(ms){clearTimeout(timer);timer=setTimeout(tick,ms)}
 document.addEventListener('visibilitychange',()=>{if(!busy)schedule(document.hidden?30000:1000)});
 window.addEventListener('load',()=>schedule(1000));
})();
