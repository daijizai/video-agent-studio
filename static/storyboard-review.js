/* Public story/review surface. Machine contracts remain in state and diagnostics. */
const StoryReview = (() => {
  const intent = shot => shot.story_intent ?? shot.creative_details?.beat ?? '';
  let scriptDraft=null, scriptMode='edit';
  function scriptHTML(s) {
    const draft=scriptDraft?.projectId===s.project_id?scriptDraft:s;
    return `<section class="script-workspace" aria-label="剧本编辑"><div class="script-toolbar"><div class="script-view-switch" role="group" aria-label="剧本显示模式"><button id="script-edit" aria-pressed="${scriptMode==='edit'}">编辑</button><button id="script-read" aria-pressed="${scriptMode==='read'}">阅读</button></div><div class="script-save"><span id="script-save-state" role="status">${draft===s?'已保存到本机':'有未保存的修改'}</span><button class="primary" id="save-script">保存剧本</button></div></div><div class="script-metadata"><label for="title">作品名称</label><input id="title" value="${esc(draft.title)}"><label for="episode">本集标题</label><input id="episode" value="${esc(draft.episode)}"></div><div class="script-document"><label class="sr-only" for="script">剧本正文</label><textarea id="script" spellcheck="false" ${scriptMode==='read'?'hidden':''}>${esc(draft.script)}</textarea><article id="script-reading" aria-label="剧本阅读" ${scriptMode==='edit'?'hidden':''}>${esc(draft.script||'还没有剧本正文，切换到编辑模式开始创作。')}</article></div><div class="script-footer"><span id="script-count">${String(draft.script||'').length} 字符</span><span>Ctrl / ⌘ + S 保存 · 修改内容后需重新核对相关审批</span></div></section>`;
  }
  function bindScript(){
    const title=document.querySelector('#title'),episode=document.querySelector('#episode'),text=document.querySelector('#script'),status=document.querySelector('#script-save-state'),save=document.querySelector('#save-script');
    const snapshot=()=>({projectId:state.project_id,title:title.value,episode:episode.value,script:text.value});
    const changed=()=>{const draft=snapshot();scriptDraft=draft.title===state.title&&draft.episode===state.episode&&draft.script===state.script?null:draft;status.textContent=scriptDraft?'有未保存的修改':'已保存到本机';document.querySelector('#script-count').textContent=text.value.length+' 字符';document.querySelector('#script-reading').textContent=text.value};
    [title,episode,text].forEach(input=>input.addEventListener('input',changed));
    const mode=value=>{scriptMode=value;text.hidden=value==='read';document.querySelector('#script-reading').hidden=value==='edit';document.querySelector('#script-edit').setAttribute('aria-pressed',value==='edit');document.querySelector('#script-read').setAttribute('aria-pressed',value==='read');};
    document.querySelector('#script-edit').onclick=()=>mode('edit');document.querySelector('#script-read').onclick=()=>mode('read');
    save.onclick=async()=>{if(save.disabled)return;const draft=snapshot();save.disabled=true;status.textContent='保存中…';try{const result=await api('save',{title:draft.title,episode:draft.episode,script:draft.script});if(state.project_id!==draft.projectId)return;state=result;const current=snapshot();if(current.title===draft.title&&current.episode===draft.episode&&current.script===draft.script){scriptDraft=null;status.textContent='已保存到本机'}else{scriptDraft=current;status.textContent='有未保存的修改'}toast('剧本已保存到本机')}catch(error){status.textContent='保存失败，修改仍保留';toast(error.message)}finally{save.disabled=false}};
  }
  if(typeof window!=='undefined')window.addEventListener('beforeunload',event=>{if(scriptDraft){event.preventDefault();event.returnValue=''}});
  if(typeof document!=='undefined')document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'&&document.body.dataset.page==='script'){event.preventDefault();document.querySelector('#save-script')?.click()}});
  if(typeof document!=='undefined')document.addEventListener('click',event=>{const link=event.target.closest('a[href]');if(document.body.dataset.page==='script'&&scriptDraft&&link&&link.getAttribute('href')!=='#script'){if(!window.confirm('剧本有未保存的修改。离开后本次草稿暂存，关闭或刷新页面会丢失。仍要离开吗？')){event.preventDefault();event.stopImmediatePropagation()}}},true);
  function internalHTML(s) {
    return `<section class="panel"><h2>内部制作规则</h2><p>保留原始内容供 Agent 和开发者维护；保存会按内容变化重新计算审批有效性。</p><label class="field" for="continuity">连续性手册（内部）</label><textarea id="continuity" rows="8">${esc(s.continuity)}</textarea><label class="field" for="brief">项目提案与 IP 规则（内部）</label><textarea id="brief" rows="8">${esc(s.project_brief || '')}</textarea><button id="save-internal" type="button">保存内部规则</button></section>`;
  }
  function draft(shot,i) {
    const result={...shot,name:document.querySelector('#sn'+i).value,duration:Number(document.querySelector('#sd'+i).value),review:document.querySelector('#feedback'+i).value};
    const value=document.querySelector('#intent'+i).value;
    if(value!==intent(shot))result.story_intent=value;
    return result;
  }
  function questions(issues, shots, shotId) {
    const seen=new Set();
    return issues.filter(issue=>issue.shot_id===shotId).flatMap(issue=>{
      let message;
      if(['prop-cut','prop-transition'].includes(issue.code)) {
        const prev=shots.find(s=>s.id===issue.related_shot_id);
        message=`${prev?'与「'+prev.name+'」衔接时':'这一镜中'}，道具的数量、位置或持有方式发生了变化。这里是否有拾取、放下、交接或时间跳跃？`;
      } else if(issue.code==='action-cut') {
        message='上一镜结束时与这一镜开始时的状态不同。中间是否发生了动作，或有意跳过了一段时间？';
      } else if(issue.code==='text-review') {
        message='这一镜的动作描述可能有出入：主体应该保持静止，还是发生动作？请按故事意图留下反馈。';
      }
      if(!message || seen.has(message))return [];
      seen.add(message);return [message];
    });
  }
  function bind(page) {
    if(page==='script')bindScript();
    const internal=document.querySelector('#save-internal');
    if(internal)internal.onclick=()=>act(()=>persist({continuity:document.querySelector('#continuity').value,project_brief:document.querySelector('#brief').value}));
    if(page!=='shots')return;
    document.querySelectorAll('[data-feedback-save]').forEach(button=>button.onclick=()=>act(async()=>{
      const i=Number(button.dataset.feedbackSave),shots=structuredClone(state.shots);
      shots[i].review=document.querySelector('#feedback'+i).value;
      await persist({shots},'反馈已保存；尚未改写画面或发起生成');
    }));
    document.querySelectorAll('[data-story-check]').forEach(button=>button.onclick=()=>{
      const i=Number(button.dataset.storyCheck),shots=state.shots.map((s,j)=>draft(s,j));
      const list=questions(StoryboardChecks.check(shots),shots,shots[i].id);
      const box=document.querySelector(`[data-story-questions="${i}"]`);
      box.innerHTML=list.length ? `<p>有 ${list.length} 处故事关系需要确认：</p><ul>${list.map(message=>`<li>${esc(message)}</li>`).join('')}</ul><p>可在上方留下你的判断，制作时再处理。</p>` : '<p>暂时没有需要你确认的故事问题。仍请以画面审阅为准。</p>';
      box.focus();
    });
  }
  return {scriptHTML,internalHTML,draft,questions,bind};
})();
if(typeof module!=='undefined' && module.exports)module.exports=StoryReview;
