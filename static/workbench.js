/* Local display preferences only; never changes project or execution state. */
(() => {
  document.addEventListener('click',event=>{
    document.querySelectorAll('.production-status[open]').forEach(details=>{if(!details.contains(event.target))details.open=false});
  });
  document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.production-status[open]').forEach(details=>details.open=false)});
})();

/* Keep shot cards stable while editing their original, already-bound controls. */
(() => {
  const view=document.querySelector('#view');
  let activeDialog=null;
  function mount(){
    if(document.body.dataset.page!=='shots')return;
    view.querySelectorAll('.shot-body > .shot-details, .shot-body > .asset-ref-summary, .shot-body > .comfy-repair').forEach(details=>{
      if(details.dataset.modalReady)return;
      details.dataset.modalReady='true';details.hidden=true;
      const summary=details.querySelector(':scope > summary');
      const button=document.createElement('button');button.type='button';button.className='shot-detail-launch';button.dataset.shotPanel=details.classList.contains('shot-details')?'feedback':details.classList.contains('comfy-repair')?'repair':'references';button.textContent=details.classList.contains('comfy-repair')?'修复画面':summary.textContent;button.setAttribute('aria-haspopup','dialog');
      const reopen=details.open;
      details.before(button);
      button.onclick=()=>{
        if(activeDialog)return;
        const title=details.closest('.shot').querySelector('h3').textContent+' · '+summary.textContent;
        const node=document.createElement('dialog');node.className='shot-detail-dialog';node.setAttribute('aria-label',title);
        const header=document.createElement('header'),heading=document.createElement('h2'),close=document.createElement('button');
        heading.textContent=title;close.type='button';close.textContent='关闭';close.setAttribute('aria-label','关闭'+title);header.append(heading,close);node.append(header);
        document.body.append(node);node._owner=button;activeDialog=node;
        details.hidden=false;summary.hidden=true;node.append(details);details.open=true;
        close.onclick=()=>node.close();
        node.addEventListener('close',()=>{
          details.open=false;details.hidden=true;summary.hidden=false;
          if(button.isConnected){button.after(details);button.focus()}
          node.remove();activeDialog=null;
        },{once:true});
        node.showModal();
      };
      if(reopen)queueMicrotask(()=>{if(button.isConnected)button.click()});
    });
  }
  new MutationObserver(()=>{
    // Saving/reloading replaces the card. Close its stale dialog with the old form.
    if(activeDialog){const owner=activeDialog._owner;if(owner&&!owner.isConnected)activeDialog.close()}
    mount();
  }).observe(view,{childList:true,subtree:true});
})();
