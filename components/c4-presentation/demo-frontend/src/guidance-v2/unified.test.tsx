import {describe,it,expect} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import VersionRoute from './VersionRoute';

describe('Integrated citizen and research routing',()=>{
 it('mounts the original professional identity workspace as the citizen entry',()=>{
  const html=renderToStaticMarkup(<VersionRoute/>);
  expect(html).toContain('Continue as guest');expect(html).toContain('Create demo profile');
  expect(html).not.toContain('C4 V2 research workspace');
 });
});
