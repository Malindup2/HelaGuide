import { useState } from 'react';

const KEY = 'c4-research-view';

function initial(): boolean {
  try { return new URLSearchParams(location.search).get('research') === '1' || sessionStorage.getItem(KEY) === '1'; } catch { return false; }
}

/** Research view is off by default and never shown to ordinary citizens. */
export function useResearchView(): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(initial);
  return [on, (value: boolean) => { setOn(value); try { sessionStorage.setItem(KEY, value ? '1' : '0'); } catch { /* storage unavailable */ } }];
}
