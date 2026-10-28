const test = require('node:test');
const assert = require('node:assert/strict');
const {check} = require('../static/storyboard-checks.js');
const prop = (start,end,extra={}) => ({asset_id:'key',start,end,...extra});
const shot = (id, props=[], chain={}) => ({id,name:id,creative_details:{prop_states:props,action_chain:chain}});
test('legacy, static and missing references remain valid; check never mutates approvals', () => {
  const shots=[{id:'legacy',approved:true,approval_snapshot:{content_hash:'old'}},shot('still',[],{start:'全程静止',end:'全程静止'})];
  const original=JSON.stringify(shots);assert.deepEqual(check(shots),[]);assert.equal(JSON.stringify(shots),original);
});
test('offscreen is not disappearance; unknown is not zero', () => {
  assert.deepEqual(check([shot('a',[prop({count:1,visible:'visible'},{count:1,visible:'offscreen'})]),shot('b',[prop({count:null},{})])]),[]);
});
test('detect an unrecorded pickup/hand switch and localize the property', () => {
  const results=check([shot('a',[prop({count:1,holder:'right'},{count:2,holder:'left'})])]);
  assert.equal(results.length,2);assert.equal(results[0].field,'prop_states[0].end.count');
  assert.equal(results[0].severity,'review');assert.ok(results[1].evidence.includes('holder=right'));
});
test('documented within-shot transition does not excuse a contradictory cut', () => {
  const results=check([shot('a',[prop({},{count:1,holder:'right'})]),shot('b',[prop({count:2,holder:'left'},{},{transition:'放下'})])]);
  assert.equal(results.length,2);assert.equal(results[0].related_shot_id,'a');
  const documented=shot('b',[prop({count:2,holder:'left'},{},{incoming_transition:'跳时后交接'})]);
  assert.deepEqual(check([shot('a',[prop({},{count:1,holder:'right'})]),documented]),[]);
});
test('only compare same asset ID and skip ambiguous duplicates', () => {
  const a=shot('a',[prop({},{count:1}),prop({},{count:3})]);
  const b=shot('b',[{asset_id:'other',start:{count:2}}]);
  assert.equal(check([a,b]).length,1);assert.equal(check([a,b])[0].code,'prop-duplicate');
});
test('reference purpose follows both exact index and URL, not stale ordinal alone', () => {
  const s={id:'a',reference_images:['new'],creative_details:{reference_bindings:[{reference_index:1,url:'old',purpose:'身份'}]}};
  assert.equal(check([s])[0].code,'reference-purpose');
  s.creative_details.reference_bindings[0].url='new';assert.deepEqual(check([s]),[]);
});
test('image temporal overload yields a hint, static visual relations do not', () => {
  assert.equal(check([{id:'a',image_prompt:'先转头再拾起，随后开门'}])[0].code,'image-temporal');
  assert.deepEqual(check([{id:'a',image_prompt:'右侧关闭的门，右手握钥匙，钟楼停在23:53，画面静态。'}]),[]);
});
test('exact state contradictions and free text hints do not claim semantic truth', () => {
  assert.equal(check([shot('a',[],{end:'坐姿'}),shot('b',[],{start:'站姿'})])[0].code,'action-cut');
  assert.deepEqual(check([shot('a',[],{end:'小猫坐姿'}),shot('b',[],{start:'姚宁站姿'})]),[]);
  assert.equal(check([{id:'a',prompt:'钥匙全程静止',creative_details:{action:'姚宁转身'}}])[0].code,'text-review');
});
test('invalid counts are reported rather than silently normalized', () => {
  assert.equal(check([shot('a',[prop({count:-1},{count:1.5})])]).filter(x=>x.code==='prop-count').length,2);
});
test('public questions ask story facts without exposing internal fields or housekeeping', () => {
  const {questions}=require('../static/storyboard-review.js');
  const shots=[shot('a',[prop({},{count:1})]),shot('b',[prop({count:2},{})])];
  shots[1].reference_images=['reference'];
  const issues=check(shots),result=questions(issues,shots,'b');
  assert.equal(result.length,1);assert.ok(result[0].includes('拾取、放下、交接'));
  assert.ok(!/count|prop_states|reference|key/.test(result[0]));
  assert.deepEqual(questions([{shot_id:'b',code:'reference-purpose'}],shots,'b'),[]);
});
