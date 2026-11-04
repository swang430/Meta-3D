"""GUI请求使用真实TS封装；HTTP仅在外部边界替换。"""
from pathlib import Path
import subprocess


def test_source_workbench_requests_and_identity():
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('typescript');
const calls=[];let next=null,fail=false;
const client={get:async(...args)=>{calls.push(args);if(fail)throw Error('offline');return {data:next}},
post:async(...args)=>{calls.push(args);if(fail)throw Error('offline');return {data:next}}};
const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/api/labProfileService.ts','utf8'),
{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,require:name=>{assert.equal(name,'./client');return {default:client}}});
(async()=>{
 next={lab_profile_id:'lab',operating_mode:'mimo_ota',frequency_mhz:3499.995};
 await exports.fetchRouteCalibrationAvailability('lab','mimo_ota',3499.995);
 assert.equal(calls.at(-1)[1].params.frequency_mhz,3499.995);
 assert.equal(calls.at(-1)[1].params.operating_mode,'mimo_ota');
 for(const changed of [{lab_profile_id:'other'},{operating_mode:'other'},{frequency_mhz:3500}]){
  const saved=next;next={...next,...changed};await assert.rejects(()=>exports.fetchRouteCalibrationAvailability('lab','mimo_ota',3499.995));next=saved;
 }
 next=null;assert.equal(await exports.fetchRouteRevocation('lab','application','run'),null);
 next={lab_profile_id:'lab',acquisition_run_id:'run',application_id:'earlier-application'};
 await exports.fetchRouteRevocation('lab','application','run');
 await exports.revokeRouteApplication('lab','application','run',{confirmed:true,reason:'读数错误'});
 assert.equal(calls.at(-1)[0],'/lab-profiles/lab/route-calibration-applications/application/revocation');
 assert.equal(calls.at(-1)[1].confirmed,true);assert.equal(calls.at(-1)[1].reason,'读数错误');
 for(const changed of [{lab_profile_id:'other'},{acquisition_run_id:'other'}]){
  const saved=next;next={...next,...changed};await assert.rejects(()=>exports.fetchRouteRevocation('lab','application','run'));next=saved;
 }
 fail=true;await assert.rejects(()=>exports.revokeRouteApplication('lab','application','run',{confirmed:true,reason:'读数错误'}));
})().catch(error=>{console.error(error);process.exitCode=1});
'''
    result = subprocess.run(['node', '-e', script], cwd=Path(__file__).parents[2]/'gui', text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
