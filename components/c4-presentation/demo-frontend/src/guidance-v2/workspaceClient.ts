import {API_BASE} from '../api/client';
export class WorkspaceError extends Error {constructor(message:string,public readonly status:number){super(message);}}
export async function workspaceRequest<T>(path:string,body?:unknown,token?:string,method?:string):Promise<T>{
 const response=await fetch(`${API_BASE}${path}`,{method:method??(body===undefined?'GET':'POST'),headers:{'Content-Type':'application/json',...(token?{'X-C4-Token':token}:{})},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
 const value=await response.json();if(!response.ok)throw new WorkspaceError(typeof value.detail==='string'?value.detail:'The supplied settings could not be accepted.',response.status);return value;
}
