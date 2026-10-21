import {useSyncExternalStore} from 'react';
import App from '../App';
import V2App from './V2App';
import Embed from '../citizen/Embed';
function subscribe(listener:()=>void){window.addEventListener('hashchange',listener);return()=>window.removeEventListener('hashchange',listener);}
/** One citizen application. Historical V2 links return to the integrated workspace. */
export default function VersionRoute(){
 const hash=useSyncExternalStore(subscribe,()=>window.location.hash,()=> '');
 if(hash.startsWith('#embed/'))return <Embed key={hash} procedureId={decodeURIComponent(hash.slice(7))}/>;
 return hash==='#c4-v2-inspector'||hash.startsWith('#pipeline-inspector')?<V2App key={hash}/>:<App/>;
}
