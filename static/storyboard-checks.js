/* Deterministic text/structure hints only. No network, writes, or quality verdict. */
(function (root) {
  'use strict';
  const text = value => typeof value === 'string' ? value.trim() : '';
  const known = value => value !== undefined && value !== null && value !== '' && value !== 'unknown';
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  function check(shots) {
    const issues = [];
    function add(shot, field, code, evidence, suggestion, relatedShotId) {
      issues.push({shot_id: shot.id, shot_name: shot.name || shot.id, field, code,
        evidence, suggestion, related_shot_id: relatedShotId || null, severity: 'review'});
    }
    (shots || []).forEach((shot, index) => {
      const details = shot.creative_details || {}, props = details.prop_states || [];
      const refs = shot.reference_images || [], bindings = details.reference_bindings || [];
      refs.forEach((url, i) => {
        const binding = bindings.find(b => b.reference_index === i + 1 && b.url === url);
        if (!binding || !text(binding.purpose)) add(shot, `reference_bindings[${i}].purpose`, 'reference-purpose',
          `参考图 ${i + 1} 未绑定用途，或链接已变化。`, '写明用于人物、场景、道具还是构图；核对序号与实际参考图。');
      });
      if (/(?:^|\n)\s*(?:\[|【)?\d{1,2}:\d{2}(?:\s*[-–—]|\s*[\]】])|随后|然后|先.{0,30}再|第[一二三四五六\d]+个?镜头/.test(shot.image_prompt || '')) {
        add(shot, 'image_prompt', 'image-temporal', '图片描述含时间码、动作先后或多镜头词。',
          '核对是否应只保留一个静态瞬间，将动作顺序留在视频提示；不会自动删除原文。');
      }
      const ids = props.map(p => text(p.asset_id));
      props.forEach((prop, pi) => {
        const field = `prop_states[${pi}]`, asset = text(prop.asset_id);
        if (!asset) {
          add(shot, field + '.asset_id', 'prop-id', '道具状态行没有资产 ID。', '关联同一道具的稳定 ID，避免把不同道具互相比较。');
          return;
        }
        if (ids.indexOf(asset) !== pi) {
          add(shot, field + '.asset_id', 'prop-duplicate', `道具 ${asset} 在本镜重复记录。`, '合并或改成不同资产 ID；重复项不作跨镜推断。');
          return;
        }
        const start = prop.start || {}, end = prop.end || {};
        ['start','end'].forEach(phase => {
          const value = (prop[phase] || {}).count;
          if (known(value) && (!Number.isInteger(value) || value < 0)) add(shot, `${field}.${phase}.count`, 'prop-count',
            `${asset}：${phase} 数量不是非负整数。`, '数量使用非负整数；未知留空，不将画外自动填写为零。');
        });
        ['count', 'location', 'holder'].forEach(key => {
          if (known(start[key]) && known(end[key]) && !same(start[key], end[key]) && !text(prop.transition)) {
            add(shot, `${field}.end.${key}`, 'prop-transition', `${asset}：起始 ${key}=${start[key]}；结束 ${key}=${end[key]}，未记录过渡。`,
              '补充拾取、放下或交接过程；也可修正状态，预检不判断哪项正确。');
          }
        });
        const prev = index > 0 ? shots[index - 1] : null;
        const previousProps = prev?.creative_details?.prop_states || [];
        const matches = previousProps.filter(p => text(p.asset_id) === asset);
        if (matches.length === 1 && !text(prop.incoming_transition)) {
          ['count', 'location', 'holder'].forEach(key => {
            const before = (matches[0].end || {})[key], after = start[key];
            if (known(before) && known(after) && !same(before, after)) add(shot, `${field}.start.${key}`, 'prop-cut',
              `${prev.name || prev.id} → ${shot.name || shot.id}，${asset}：上镜结束 ${key}=${before}；本镜开始 ${key}=${after}。`,
              '核对跨镜状态；若有画外动作或时间跳跃，明确填写入镜前过渡。', prev.id);
          });
        }
        // Visibility is deliberately NOT compared to existence/count/location.
      });
      const chain = details.action_chain || {}, prev = index > 0 ? shots[index - 1] : null;
      const priorEnd = text(prev?.creative_details?.action_chain?.end), nextStart = text(chain.start);
      if (priorEnd && nextStart && !text(chain.incoming_transition)) {
        // Only a whole-state literal pair is deterministic. Free prose is not treated as semantic truth.
        const pairs = [['坐姿', '站姿'], ['门关闭', '门打开'], ['静止', '行走']];
        if (pairs.some(pair => pair.includes(priorEnd) && pair.includes(nextStart) && priorEnd !== nextStart)) {
          add(shot, 'action_chain.start', 'action-cut', `上镜结束「${priorEnd}」；本镜开始「${nextStart}」。`,
            '核对是否漏写过渡；这些只是显式状态词比较，不能替代人工理解人物和故事。', prev.id);
        }
      }
      // Contradictions in free text are hints only; never choose a source of truth.
      const steps = Array.isArray(chain.steps) ? chain.steps.filter(text) : [];
      if (/全程静止/.test(text(chain.start)) && /全程静止/.test(text(chain.end)) && /拾起|放下|站起|转身/.test(shot.prompt || '')) {
        add(shot, 'action_chain.end', 'text-review', '结构字段起止写「全程静止」，视频自由文本含拾起、放下、站起或转身。',
          '核对描述是否指同一主体；结构字段与自由文本都可能需要修订，不自动判断哪份正确。');
      }
      if (chain.start === chain.end && /全程静止|保持静止/.test(text(chain.start)) && steps.length) {
        add(shot, 'action_chain.steps', 'text-review', `起止均为「${chain.start}」，但填写了动作步骤。`, '核对动作是否仅为环境或相机变化；不自动判定冲突。');
      }
      if (text(details.action) && text(shot.prompt) && /全程静止/.test(shot.prompt) && /拾起|放下|站起|转身/.test(details.action)) {
        add(shot, 'prompt / creative_details.action', 'text-review', '视频提示含「全程静止」，创作动作含拾起、放下、站起或转身。',
          '核对两段描述是否指同一主体，选择是否修订；关键词不足以确定语义矛盾。');
      }
    });
    return issues;
  }
  const api = {check};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.StoryboardChecks = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
