/** Run with Node's TypeScript stripping enabled. Exports the agreed UI scope, not acceptance. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {phases,journeys,screenStates,detailTabs} from '../frontend/src/productExperience.ts';
import {reviewCriteria,HANDOFF_LIMIT,UI_RECORD_LIMIT} from '../frontend/src/uiHandoff.ts';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const catalog=JSON.parse(fs.readFileSync(path.join(root,'backend/nexus/interface_catalog.json'),'utf8'));
const modules=catalog.modules.map(m=>({id:m.id,title:m.title,area:m.area,phase:phases.find(p=>p.modules.includes(m.id)).id,functions:m.features.map(f=>({id:f.id,title:f.title,fields:f.fields,steps:f.steps,roles:f.roles,planned_path:f.planned_path,working_view:f.working_view||null,runtime_note:f.implementation_note||null,deep_link:'?ui_feature='+f.id+'#product',ui_reviewed:false}))}));
const scope={release:'0.16.0',schema:8,scope:'Navigable UI baseline for the agreed 18-area/216-function inventory; backend acceptance separate',phases,journeys,screenStates,detailTabs,reviewCriteria,resume:{format:"nexus-ui-review",schema:1,maxBytes:HANDOFF_LIMIT,maxRecords:UI_RECORD_LIMIT,maxEventsPerRecord:50},modules,production_ready:false,manual_device_acceptance:false};
fs.writeFileSync(path.join(root,'docs/UI_BASELINE_0_16_0.json'),JSON.stringify(scope,null,2)+'\n');
const rows=[['Area','Workspace','Function ID','Function screen','Implementation phase','Direct UI link','Configuration controls','Detail views','Screen states','Manual UI acceptance','Existing runtime workspace']];
for(const m of modules)for(const f of m.functions)rows.push([m.area,m.title,f.id,f.title,m.phase,f.deep_link,f.fields.map(x=>x.label).join('; '),detailTabs.join('; '),screenStates.join('; '),'Not accepted by default',f.working_view||'Planned service path']);
const csv=rows.map(row=>row.map(value=>'"'+String(value).replaceAll('"','""')+'"').join(',')).join('\r\n')+'\r\n';
fs.writeFileSync(path.join(root,'docs/UI_SCREEN_COVERAGE_0_16_0.csv'),csv);
console.log('Exported '+modules.length+' areas / '+modules.flatMap(m=>m.functions).length+' function screens. Acceptance remains open.');
