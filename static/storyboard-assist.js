/* Independent, opt-in editor. Call mount() from the host; no automatic persistence. */
(function (root) {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let serial = 0;
  function mount(container, shot, options = {}) {
    const prefix = `assist-${++serial}-`, original = clone(shot.creative_details || {});
    let draft = clone(original), dirty = false;
    const section = document.createElement('details');
    section.className = 'storyboard-assist';
    section.innerHTML = '<summary>辅助编辑 · 动作、道具与参考图</summary><p class="assist-note muted">选填。预检只比较显式字段和少量文字规则，不代表画面质量通过。修改后仍须使用镜头的保存按钮；不会自动生成或改写提示词。</p><div data-assist-fields></div><div class="shot-actions"><button type="button" data-assist-check>检查当前分镜草稿</button></div><p class="muted" data-assist-dirty role="status"></p><div class="assist-report" data-assist-report tabindex="-1" role="region" aria-label="分镜预检结果"></div>';
    container.append(section);
    const fields = section.querySelector('[data-assist-fields]');
    const ids = new Map(), hints = [];
    function clearHints() {
      hints.splice(0).forEach(({node,target}) => {
        const rest=(target.getAttribute('aria-describedby') || '').split(' ').filter(x => x && x !== node.id);
        if(rest.length)target.setAttribute('aria-describedby',rest.join(' '));else target.removeAttribute('aria-describedby');
        node.remove();
      });
    }
    function id(path) { if (!ids.has(path)) ids.set(path, prefix + ids.size); return ids.get(path); }
    function input(path, label, value, type = 'text') {
      const ident = id(path);
      const control = type === 'textarea'
        ? `<textarea id="${ident}" data-path="${escape(path)}">${escape(value)}</textarea>`
        : type === 'visible'
          ? `<select id="${ident}" data-path="${escape(path)}">${[['unknown','未注明'],['visible','画内可见'],['offscreen','画外／被遮挡']].map(([v,l]) => `<option value="${v}" ${value === v || (!value && v === 'unknown') ? 'selected' : ''}>${l}</option>`).join('')}</select>`
          : `<input id="${ident}" data-path="${escape(path)}" type="${type}" ${type === 'number' ? 'min="0" step="1"' : ''} value="${escape(value)}">`;
      return `<label for="${ident}">${escape(label)}</label>${control}`;
    }
    function markDirty() {
      dirty = true;
      section.querySelector('[data-assist-dirty]').textContent = '辅助字段有未保存修改；提示词和审批尚未改变。';
      section.querySelector('[data-assist-report]').replaceChildren();
      clearHints();
      options.onDirty?.();
    }
    function draw() {
      const chain = draft.action_chain || {}, props = draft.prop_states || [], refs = shot.reference_images || [];
      fields.innerHTML = `<fieldset><legend>动作链</legend><p class="muted">静物可保持同一起止状态，触发和动作步骤可留空。相机运动放在原视频提示中。</p>${input('action_chain.start','起始状态',chain.start)}${input('action_chain.trigger','触发事件（可空）',chain.trigger)}${input('action_chain.steps','动作步骤（每行一步，可空）',(chain.steps || []).join('\n'),'textarea')}${input('action_chain.end','结束状态',chain.end)}${input('action_chain.incoming_transition','入镜前过渡／时间跳跃（可空）',chain.incoming_transition)}</fieldset>
        <fieldset><legend>道具状态</legend><p class="muted">用相同资产 ID 关联跨镜道具；未知留空。持有人写角色 ID／左手或右手。画外不等于道具不存在。</p>${props.map((p,i) => `<fieldset data-prop-row="${i}"><legend>道具 ${i+1}</legend>${input(`prop_states.${i}.asset_id`,'资产 ID（例如 P01-v1）',p.asset_id)}<div class="assist-grid">${['start','end'].map(phase => `<div><strong>${phase === 'start' ? '起始' : '结束'}</strong>${input(`prop_states.${i}.${phase}.location`,'位置',p[phase]?.location)}${input(`prop_states.${i}.${phase}.holder`,'持有人／持有手',p[phase]?.holder)}${input(`prop_states.${i}.${phase}.count`,'数量（空白表示未知）',p[phase]?.count,'number')}${input(`prop_states.${i}.${phase}.visible`,'可见性',p[phase]?.visible,'visible')}</div>`).join('')}</div>${input(`prop_states.${i}.transition`,'镜内过渡（拾取／放下／交接，可空）',p.transition)}${input(`prop_states.${i}.incoming_transition`,'入镜前过渡（画外动作／跳时，可空）',p.incoming_transition)}<button type="button" data-prop-remove="${i}">移除道具 ${i+1} 状态行</button></fieldset>`).join('')}<button type="button" data-prop-add>添加道具状态</button></fieldset>
        <fieldset><legend>参考图用途</legend><p class="muted">按当前参考图顺序绑定；链接变化后须重新确认用途。资产版本与来源任务可留空，但不会自动冒充已批准母版。</p>${refs.length ? refs.map((url,i) => {
          const b = (draft.reference_bindings || []).find(b => b.reference_index === i+1 && b.url === url) || {};
          return `<fieldset><legend>参考图 ${i+1}</legend><p class="muted">当前链接已绑定到此序号；链接不在此重复展示。</p>${input(`reference_bindings.${i}.purpose`,'用途（人物／场景／道具／构图）',b.purpose)}${input(`reference_bindings.${i}.preserve`,'必须保持的特征（每行一项）',(b.preserve || []).join('\n'),'textarea')}${input(`reference_bindings.${i}.asset_version`,'资产 ID／明确版本',b.asset_version)}${input(`reference_bindings.${i}.source_task_id`,'来源任务 ID 或内容哈希',b.source_task_id)}</fieldset>`;
        }).join('') : '<p class="muted">当前没有参考图，无需填写参考图描述。保存参考图列表后可添加用途。</p>'}</fieldset>`;
    }
    function set(path, value) {
      const parts = path.split('.');
      if (parts[0] === 'reference_bindings') {
        const i = Number(parts[1]), url = shot.reference_images[i];
        draft.reference_bindings ||= [];
        let binding = draft.reference_bindings.find(b => b.reference_index === i+1 && b.url === url);
        if (!binding) { binding = {reference_index:i+1,url}; draft.reference_bindings.push(binding); }
        binding[parts[2]] = value;
      } else {
        let obj = draft;
        parts.slice(0,-1).forEach((part,i) => { obj[part] ||= /^\d+$/.test(parts[i+1]) ? [] : {}; obj = obj[part]; });
        obj[parts.at(-1)] = value;
      }
    }
    fields.addEventListener('input', event => {
      const el = event.target, path = el.dataset.path;
      if (!path) return;
      let value = el.value;
      if (path.endsWith('.steps') || path.endsWith('.preserve')) value = value.split('\n').map(s => s.trim()).filter(Boolean);
      if (el.type === 'number') value = value === '' ? null : Number(value);
      set(path,value); markDirty();
    });
    fields.addEventListener('change', event => {
      if (event.target.tagName === 'SELECT') { set(event.target.dataset.path,event.target.value);markDirty(); }
    });
    fields.addEventListener('click', event => {
      const button = event.target.closest('button');
      if (!button) return;
      if (button.hasAttribute('data-prop-add')) {
        (draft.prop_states ||= []).push({asset_id:'',start:{},end:{}});markDirty();draw();
        fields.querySelector(`[data-prop-row="${draft.prop_states.length-1}"] input`).focus();
      }
      if (button.hasAttribute('data-prop-remove')) {
        const index = Number(button.dataset.propRemove);
        draft.prop_states.splice(index,1);markDirty();draw();fields.querySelector('[data-prop-add]').focus();
      }
    });
    function read(baseShot = shot) {
      if (!dirty) return clone(baseShot);
      return {...clone(baseShot),creative_details:{...(baseShot.creative_details || {}),...clone(draft)}};
    }
    section.querySelector('[data-assist-check]').addEventListener('click', () => {
      const context = options.readContext ? options.readContext() : [shot];
      const shots = context.map(s => s.id === shot.id ? read(s) : s);
      const results = root.StoryboardChecks.check(shots), report = section.querySelector('[data-assist-report]');
      clearHints();
      report.innerHTML = `<strong>规则预检：${results.length} 项待核对</strong><p class="muted">${results.length ? '以下是结构或文字线索，尚未判断哪份正确。' : '本次规则未发现问题；不等于画面、语义或审批通过。'}</p><ol>${results.map((issue,i) => {
        const path = issue.field.replace(/\[(\d+)\]/g,'.$1');
        const target = (issue.shot_id === shot.id ? fields.querySelector(`[data-path="${path}"]`) : null)
          || options.locateIssue?.(issue, path);
        if (target) {
          const hint = document.createElement('p');hint.className='muted';hint.dataset.assistHint='';hint.id=prefix+'hint-'+i;
          hint.textContent=issue.evidence+' '+issue.suggestion;target.after(hint);
          hints.push({node:hint,target});
          target.setAttribute('aria-describedby',((target.getAttribute('aria-describedby') || '')+' '+hint.id).trim());
        }
        return `<li><strong>${escape(issue.shot_name)}</strong> · ${escape(issue.field)}<p>${escape(issue.evidence)}</p><p>建议：${escape(issue.suggestion)}</p>${target ? `<a href="#${target.id}">定位此字段</a>` : ''}</li>`;
      }).join('')}</ol>`;
      report.querySelectorAll('a').forEach(a => a.addEventListener('click', e => {
        e.preventDefault();const target=document.getElementById(a.hash.slice(1));
        let parent=target?.parentElement;while(parent){if(parent.tagName==='DETAILS')parent.open=true;parent=parent.parentElement}
        target?.focus();
      }));
      report.focus();
    });
    draw();
    return {element:section,read,isDirty:() => dirty,destroy:() => {clearHints();section.remove()}};
  }
  root.StoryboardAssist = {mount};
})(globalThis);
