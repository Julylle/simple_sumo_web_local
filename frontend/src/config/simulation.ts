import type { Params } from '../api/client';

export const defaultParameters:Params={flow_m3_d:50000,influent_cod_mg_l:450,influent_nh4_mg_l:40,do_mg_l:2,srt_d:15,duration_h:24};
type Field={key:keyof Params;label:string;unit:string;min:number;max:number;step:number;hint:string};
export const parameterGroups:{title:string;subtitle:string;fields:Field[]}[]=[
 {title:'Influent',subtitle:'Boundary conditions entering the model',fields:[
  {key:'flow_m3_d',label:'Flow',unit:'m³/d',min:100,max:1000000,step:100,hint:'Influent flow rate'},
  {key:'influent_cod_mg_l',label:'Influent COD',unit:'mg/L',min:10,max:3000,step:1,hint:'Initial biodegradable COD'},
  {key:'influent_nh4_mg_l',label:'Influent NH₄-N',unit:'mg/L',min:.1,max:300,step:.1,hint:'Initial ammonium nitrogen'}]},
 {title:'Operating conditions',subtitle:'Parameters controlling process kinetics',fields:[
  {key:'do_mg_l',label:'DO setpoint',unit:'mg/L',min:.2,max:8,step:.1,hint:'Dissolved oxygen concentration'},
  {key:'srt_d',label:'SRT',unit:'d',min:1,max:80,step:1,hint:'Solids retention time'}]},
 {title:'Simulation settings',subtitle:'Numerical run configuration',fields:[
  {key:'duration_h',label:'Simulation duration',unit:'h',min:1,max:240,step:1,hint:'ODE integration horizon'}]}
];
