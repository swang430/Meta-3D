import {readFile,writeFile} from 'node:fs/promises';
import {parseArgs} from 'node:util';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {mkdir} from 'node:fs/promises';
const {values:args}=parseArgs({options:{'lauraycs-repo':{type:'string'},timeline:{type:'string'},output:{type:'string'},'tool-root':{type:'string'},'wasm-dir':{type:'string'}}});
for(const k of ['lauraycs-repo','timeline','output','tool-root','wasm-dir'])if(!args[k])throw new Error('Missing --'+k);
await mkdir(args.output,{recursive:true});
const {transform}=await import(pathToFileURL(join(resolve(args['tool-root']),'node_modules/esbuild/lib/main.js')));
const {instantiate}=await import(pathToFileURL(join(resolve(args['wasm-dir']),'asc.js')));
const source=await readFile(join(args['lauraycs-repo'],'web/src/utils/asc-timing.ts'),'utf8');
const {code}=await transform(source,{loader:'ts',format:'esm'});
const {automaticAscRate}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const m=await instantiate(await WebAssembly.compile(await readFile(join(args['wasm-dir'],'asc.wasm'))));
const out={}; const fc=2.4e9,rate=automaticAscRate(fc,5,null);
function run(rows,times,dopplers,r=rate,resample=true,simple=false){
 const offsets=[0];for(const row of rows)offsets.push(offsets.at(-1)+row.length);
 const info=m.initializeAsc(new Float64Array(rows.flat()),new Int32Array(offsets),new Float64Array(times),fc,r,false,false,resample,new Float64Array(dopplers),fc,simple);
 return {n:info[0],header:m.ascHeader(), rows:m.ascChunk(0,info[0]).trim().split('\n').map(s=>s.split('\t').map(Number))};
}
function single(fd,simple=false){
 const T=1, tau0=100, tau1=tau0-fd/fc*1e9;
 const result=run([[tau0,1,0],[tau1,Math.cos(2*Math.PI*fd*T),Math.sin(2*Math.PI*fd*T)]],[0,T],[fd,fd],rate,true,simple);
 return {count:result.n,maxComplexError:Math.max(...result.rows.map((a,i)=>Math.hypot(a[1]-Math.cos(2*Math.PI*fd*i/rate),a[2]-Math.sin(2*Math.PI*fd*i/rate))))};
}
out.R1={rate,nyquist:rate/2,stationary:single(0),positive:single(40.04388),negative:single(-40.04388),simple:single(40.04388,true)};
// Endpoint correction scenario: measured Doppler 40 Hz, unresolved phase residual pi across 10ms.
const dt=.01,residual=.9*Math.PI,phase=2*Math.PI*40*dt+residual;
const corrected=run([[100,1,0],[100,Math.cos(phase),Math.sin(phase)]],[0,dt],[40,40],rate);
const dense=run([[100,1,0],[100,Math.cos(phase),Math.sin(phase)]],[0,dt],[40,40],100000);
let maxStep=0;for(let i=1;i<dense.rows.length;i++){let a=dense.rows[i-1],b=dense.rows[i];maxStep=Math.max(maxStep,Math.abs(Math.atan2(b[2]*a[1]-b[1]*a[2],b[1]*a[1]+b[2]*a[2]))*100000/(2*Math.PI));}
out.R1.endpointResidual={duration:dt,residualRad:residual,analyticPeakHz:40+residual/(2*Math.PI)*1.5/dt,denseMeasuredPeakHz:maxStep,autoNyquistHz:rate/2,autoCount:corrected.n,scope:'synthetic short interval; not supplied 38-frame sample'};
const timelineText=await readFile(args.timeline,'utf8');
let times;
if(args.timeline.endsWith('.json')){
 const adapted=JSON.parse(timelineText);
 if(adapted.schema_version!=='s5-raw-paths/1')throw new Error('不支持的时间文件版本');
 times=adapted.directions[0].frames.map(f=>f.time_s);
}else{
 const csv=timelineText.trim().split(/\r?\n/).map(s=>s.split(','));
 const index=csv[0].indexOf('time_s');
 if(index<0)throw new Error('时间文件缺少time_s列');
 times=csv.slice(1).map(r=>Number(r[index]));
}
if(times.length<2 || times[0]!==0 || times.some((t,i)=>!Number.isFinite(t)||(i>0 && t<=times[i-1])))
 throw new Error('参考探针仅接受从0秒起严格递增的有限时刻');
const rows=times.map(t=>[100,1,0]);
const yes=run(rows,times,times.map(()=>0));const no=run(rows,times,times.map(()=>0),rate,false);
out.R2={duration:times.at(-1),resampledCount:yes.n,resampledLastTime:(yes.n-1)/rate,truncatedTail:times.at(-1)-(yes.n-1)/rate,noResampleCount:no.n,noResampleLastTime:(no.n-1)/rate,noResampleNoverRate:no.n/rate};
// Known path A moves 100->106 ns; B moves 110->104 ns. Both maintain respective amplitudes 1 and 2.
const fdA=-fc*6e-9,fdB=fc*6e-9;
const a1=[106,Math.cos(2*Math.PI*fdA),Math.sin(2*Math.PI*fdA)],b1=[104,2*Math.cos(2*Math.PI*fdB),2*Math.sin(2*Math.PI*fdB)];
const cross=run([[100,1,0,110,2,0],[...a1,...b1]],[0,1],[fdA,fdB,fdA,fdB],4);
out.R3={crossing:{actualMid:cross.rows[2].slice(0,6),expectedMidDelays:[103,107],expectedAmplitudes:[1,2]},powerExchange:run([[100,2,0,110,1,0],[100,1,0,110,2,0]],[0,1],[0,0,0,0],4).rows[2].slice(0,6),replacement:run([[100,1,0],[110,2,0]],[0,1],[0,0],4).rows[2].slice(0,6)};
// 1 ns/s delay growth at 2.4 GHz => -2.4 Hz. Endpoint coefficients exactly match that path.
const fd=-2.4, end=[101,Math.cos(2*Math.PI*fd),Math.sin(2*Math.PI*fd)];
for(const simple of [false,true])for(const missing of [true,false]){
 const r=run([[100,1,0],end],[0,1],missing?[NaN,NaN]:[0,0],100,true,simple);
 out['R4_'+(simple?'simple':'matched')+'_'+(missing?'missing':'zero')]={maxComplexError:Math.max(...r.rows.map((a,i)=>Math.hypot(a[1]-Math.cos(2*Math.PI*fd*i/100),a[2]-Math.sin(2*Math.PI*fd*i/100)))),quarter:r.rows[25].slice(0,3)};
}

// Independent two-ray reference: complex coefficients sum, no cross-algorithm oracle.
const fd2=[17,-23],amps=[1,.6],phis=[.2,-.7],T2=1;
const rowAt=t=>fd2.flatMap((f,j)=>[100+j*100-f/fc*1e9*t,amps[j]*Math.cos(phis[j]+2*Math.PI*f*t),amps[j]*Math.sin(phis[j]+2*Math.PI*f*t)]);
const two=run([rowAt(0),rowAt(T2)],[0,T2],[...fd2,...fd2],rate);
let twoErr=0;
for(let i=0;i<two.n;i++){const t=i/rate,a=two.rows[i],ref=rowAt(t);twoErr=Math.max(twoErr,Math.hypot(a[1]+a[4]-ref[1]-ref[4],a[2]+a[5]-ref[2]-ref[5]));}
out.S5a_two_ray={maxComplexSumError:twoErr,count:two.n,lastTime:(two.n-1)/rate};
// Known straight track RX=(5t,20,0), TX=(0,0,0), constant 5m/s.
// Geometry reference H(t)=exp(-j*2pi*fc*(L(t)-L(0))/c), fD=-fc/c*dL/dt.
const C=299792458, L=t=>Math.hypot(5*t,20),F=t=>-fc/C*25*t/L(t),P=t=>-2*Math.PI*fc/C*(L(t)-L(0));
const geoTimes=times.map(t=>t),geoRows=geoTimes.map(t=>[L(t)/C*1e9,Math.cos(P(t)),Math.sin(P(t))]);
for(const simple of [false,true]){
 const rr=run(geoRows,geoTimes,geoTimes.map(F),rate,true,simple);let maxComplex=0,maxDelay=0,maxPhase=0,maxFreq=0,sum=0;
 for(let i=0;i<rr.n;i++){let t=i/rate,a=rr.rows[i],err=Math.hypot(a[1]-Math.cos(P(t)),a[2]-Math.sin(P(t)));maxComplex=Math.max(maxComplex,err);sum+=err*err;maxDelay=Math.max(maxDelay,Math.abs(a[0]-L(t)/C*1e9));maxPhase=Math.max(maxPhase,Math.abs(Math.atan2(a[2]*Math.cos(P(t))-a[1]*Math.sin(P(t)),a[1]*Math.cos(P(t))+a[2]*Math.sin(P(t)))));
 if(i){let b=rr.rows[i-1],obs=Math.atan2(a[2]*b[1]-a[1]*b[2],a[1]*b[1]+a[2]*b[2])*rate/(2*Math.PI);maxFreq=Math.max(maxFreq,Math.abs(obs-F((i-.5)/rate)));}}
 out['S5a_known_track_'+(simple?'simple':'matched')]={sourceFrames:geoTimes.length,outputFrames:rr.n,maxComplexError:maxComplex,rmsComplexError:Math.sqrt(sum/rr.n),maxWrappedPhaseErrorRad:maxPhase,maxDelayErrorNs:maxDelay,maxFrequencyErrorHz:maxFreq,lastTime:(rr.n-1)/rate,scope:'synthetic geometry on supplied derived timeline; not actual MPDB ray reconstruction'};
}


const currentCross=run([[100,1,0,110,2,0],[...a1,...b1]],[0,1],[fdA,fdB,fdA,fdB],4,true,true);
out.R3.currentSimpleCrossing={actualMid:currentCross.rows[2].slice(0,6),expectedMidDelays:[103,107],expectedAmplitudes:[1,2]};
const sc=run([[100,1,0],[100,Math.cos(phase),Math.sin(phase)]],[0,dt],[40,40],100000,true,true);
const u=sc.rows[0],v=sc.rows[1];
out.R1.simpleResidual={analyticAdjustedHz:40+residual/(2*Math.PI*dt),measuredHz:Math.atan2(v[2]*u[1]-v[1]*u[2],v[1]*u[1]+v[2]*u[2])*100000/(2*Math.PI),autoNyquistHz:rate/2,scope:'10 ms synthetic inconsistent residual; not supplied sample'};

await writeFile(join(args.output,'lr-results.json'),JSON.stringify(out,null,2));console.log(JSON.stringify(out,null,2));
