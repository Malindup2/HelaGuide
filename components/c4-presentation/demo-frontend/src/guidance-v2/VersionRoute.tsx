import {useSyncExternalStore} from 'react';
import InspectorRoute from '../inspector/InspectorRoute';
import V2App from './V2App';
function subscribe(listener:()=>void){window.addEventListener('hashchange',listener);return()=>window.removeEventListener('hashchange',listener);}
export default function VersionRoute(){
 const hash=useSyncExternalStore(subscribe,()=>window.location.hash,()=> '');
 return hash.startsWith('#c4-v2')?<V2App key={hash} inspector={hash==='#c4-v2-inspector'}/>:<InspectorRoute/>;
}
