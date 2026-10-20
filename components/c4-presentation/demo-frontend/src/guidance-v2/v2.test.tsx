import {describe,expect,it,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import fixture from './fixture.json';
import GuidanceMessage from './GuidanceMessage';
import ProcessMap from './ProcessMap';
import {previousActions,relationshipLines} from './semantics';
import type {Configuration,Journey} from './types';
const source=fixture as unknown as Journey;
function render(configuration:Configuration){
 const j=structuredClone(source);j.views[j.current_view].configuration=configuration;
 return renderToStaticMarkup(<GuidanceMessage journey={j} event={vi.fn()} adjust={vi.fn()} rate={vi.fn()}/>);
}
const base:Configuration={navigation:'overview',explanation:'concise',disclosure:'collapsed',relationships:'none',recap:'off',summary:'off'};
describe('V2 six-dimensional renderer contract',()=>{
 it('renders every nominal combination without losing conditions or current essential instruction',()=>{
  let count=0;
  for(const navigation of ['overview','guided'] as const)
  for(const explanation of ['concise','expanded'] as const)
  for(const disclosure of ['collapsed','expanded'] as const)
  for(const relationships of ['none','inline','map'] as const)
  for(const recap of ['off','on'] as const)
  for(const summary of ['off','on'] as const){
   const html=render({navigation,explanation,disclosure,relationships,recap,summary});count++;
   expect(html).toContain('Fictional practice procedure');
   expect(html).toContain('Register at the fictional Registration Desk');
   expect(html).toContain('You already have the fictional supporting copy');
   expect(html).toContain('You do not have the fictional supporting copy');
   expect(html.includes('aria-label="Integrated supplied process"')).toBe(relationships==='map');
  }
  expect(count).toBe(96);
 });
 it('separates all four depth/disclosure combinations',()=>{
  for(const explanation of ['concise','expanded'] as const)
  for(const disclosure of ['collapsed','expanded'] as const){
   const html=render({...base,explanation,disclosure});
   const prose=[...html.matchAll(/class="v2-prose">([\s\S]*?)<\/div>/g)].map(m=>m[1]).join(' ');
   expect(prose.includes('Registration is the common prerequisite')).toBe(explanation==='expanded');
   expect(html.includes('<details open=""><summary>Optional explanation')).toBe(disclosure==='expanded');
  }
 });
 it('uses actual current-journey displays and excludes a focused alternative',()=>{
  const j=structuredClone(source);const actions=j.document.actions;
  expect(previousActions(j,actions[4].id)).toEqual([]);
  j.seen=actions.map(a=>a.id);
  const own=actions.find(a=>a.id==='action:prepare_copy')!, office=actions.find(a=>a.id==='action:obtain_copy')!;
  j.focused_routes={[own.branch!]:office.option!};
  expect(previousActions(j,actions[4].id).map(a=>a.id)).not.toContain(own.id);
  expect(previousActions(j,actions[4].id)).toHaveLength(3);
 });
 it('represents conditional joins, parallel areas and agency owners without an AND between XOR alternatives',()=>{
  const lines=relationshipLines(source.document).join(' ');
  expect(lines).toContain('applicable one alternative');
  expect(lines).toContain('parallel work areas');
  const html=renderToStaticMarkup(<ProcessMap doc={source.document} onAction={vi.fn()}/>);
  expect(html).toContain('Fictional Records Desk');
  expect(html).toContain('Complete text equivalent');
 });
 it('keeps researcher feature names and IDs out of ordinary guidance',()=>{
  const html=render(base);
  expect(html).not.toContain('familiarity.1*');
  expect(html).not.toContain('posterior_revision');
  expect(html).not.toContain('Fact reference:');
 });
});
