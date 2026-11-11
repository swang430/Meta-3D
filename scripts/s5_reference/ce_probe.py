import sys,json, pathlib, socket
sys.dont_write_bytecode=True
import argparse
parser=argparse.ArgumentParser(description='Offline analytic probes; no hardware or production entry point')
parser.add_argument('--ce-repo',required=True)
parser.add_argument('--timeline',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
output=pathlib.Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(pathlib.Path(args.ce_repo).resolve()))
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('network forbidden'))
import numpy as np
from types import SimpleNamespace as C
from mimo_ota_simulator.exporters import PropsimASCIIExporter
from mimo_ota_simulator.data_models import PropsimExportConfig
from mimo_ota_simulator.spatiotemporal_tracking import _match_greedy
from mimo_ota_simulator.doppler_native_mapping import _doppler_from_angles
out={}
def calc(fd,rate=1000,duration=.1017):
 e=PropsimASCIIExporter(PropsimExportConfig(filename=str(output/'ce.asc'),mode='B',duration_s=duration,sample_rate_hz=rate))
 taps=[dict(cluster_index=0,delay=1e-7,coeff=np.ones((1,1),complex))]
 rays=[dict(cluster_index=0,W_base=np.ones((1,1),complex),phi_init=0.,doppler_hz=fd)]
 h,_=e._compute_dynamic_tensor(dict(pathloss_db=0),taps,rays)
 z=h[:,0,0,0]; t=np.arange(len(z))/rate
 return e,z,t,taps,rays
for fd in [0,40,-40,600]:
 e,z,t,taps,rays=calc(fd)
 out[str(fd)]={'samples':len(z),'max_analytic_error':float(np.max(abs(z-np.exp(2j*np.pi*fd*t)))),'observed_frequency_hz':float(np.angle(z[1]*z[0].conjugate())*1000/(2*np.pi)),'last_time_s':float(t[-1])}
e,z,t,taps,rays=calc(40,rate=1000.04)
files=e.export(dict(pathloss_db=0,center_frequency_hz=2.4e9,channel_impulse_response=taps,ray_components=rays))
header=pathlib.Path(files[0]).read_text().splitlines()[:12]
out['R2_header']={'requested_rate':1000.04,'header':header,'configured_duration':.1017,'count':len(z),'last_sample_time':float(t[-1])}
# Known identities A and B cross between snapshots: delay A 100->106ns, B 110->104ns; same AoA.
p=[C(cluster_id=10,delay_s=100e-9,aoa_deg=0),C(cluster_id=11,delay_s=110e-9,aoa_deg=0)]
c=[C(cluster_id=0,delay_s=106e-9,aoa_deg=0),C(cluster_id=1,delay_s=104e-9,aoa_deg=0)]
out['R3_crossing']={'expected':{0:10,1:11},'actual':_match_greedy(p,c,1e-8,20)}
out['R3_power_exchange']=_match_greedy(p,[C(cluster_id=0,delay_s=110e-9,aoa_deg=0),C(cluster_id=1,delay_s=100e-9,aoa_deg=0)],1e-8,20)
out['R3_replacement_same_geometry']={'expected':'old dies, new born; indistinguishable geometry','actual':_match_greedy(p[:1],[C(cluster_id=0,delay_s=100e-9,aoa_deg=0)],1e-8,20)}
out['geometry_sign']={'actual':_doppler_from_angles([0,90,180],[90,90,90],[5,0,0],2.4e9).tolist(),'analytic_using_exact_c':[5*2.4e9/299792458,0,-5*2.4e9/299792458]}

from mimo_ota_simulator.geometric_native_fit import MPC,F64CapabilityProfile
from mimo_ota_simulator.spatiotemporal_tracking import native_fit_trajectory
import csv
# Two physical rays with independently specified phases, amplitudes, frequencies.
e=PropsimASCIIExporter(PropsimExportConfig(filename=str(output/'two.asc'),mode='B',duration_s=1,sample_rate_hz=1000))
taps=[dict(cluster_index=j,delay=(100+j*100)*1e-9,coeff=np.ones((1,1),complex)) for j in range(2)]
rays=[dict(cluster_index=j,W_base=np.full((1,1),a,complex),phi_init=p,doppler_hz=f) for j,(a,p,f) in enumerate([(1,.2,17),(.6,-.7,-23)])]
h,_=e._compute_dynamic_tensor(dict(pathloss_db=0),taps,rays);t=np.arange(h.shape[0])/1000
ref=np.exp(1j*(.2+2*np.pi*17*t))+.6*np.exp(1j*(-.7-2*np.pi*23*t))
out['S5a_two_ray']={'maxComplexSumError':float(np.max(abs(h[:,0,0,:].sum(axis=1)-ref))),'samples':len(t),'lastTime':float(t[-1])}
# Curved range on straight constant-speed track; call the real multi-snapshot native fitting entry.
with open(args.timeline) as stream:
 if pathlib.Path(args.timeline).suffix == '.json':
  adapted=json.load(stream)
  if adapted['schema_version'] != 's5-raw-paths/1': raise ValueError('不支持的时间文件版本')
  times=np.array([float(r['time_s']) for r in adapted['directions'][0]['frames']])
 else:
  times=np.array([float(r['time_s']) for r in csv.DictReader(stream)])
if len(times)<2 or times[0]!=0 or not np.isfinite(times).all() or not np.all(np.diff(times)>0):
 raise ValueError('参考探针仅接受从0秒起严格递增的有限时刻')
lengths=np.hypot(5*times,20); aoa=np.degrees(np.arctan2(-np.full_like(times,20),-5*times))
mpcs=[[MPC(delay_s=float(d/299792458),power_linear=1,aoa_deg=float(a),aod_deg=float(a+180))] for d,a in zip(lengths,aoa)]
prof=native_fit_trajectory(mpcs,[5,0,0],2.4e9,F64CapabilityProfile(tap_budget=24,rho_thresh=.06),skeleton_rate_hz=1,delta_d_geo_m=5,route_len_m=5*times[-1])
actual=np.array([sn.clusters[0].doppler_repr.f_d_centroid_hz for sn in prof.snapshots]);reference=-2.4e9/299792458*25*times/lengths
out['S5a_known_track']={'snapshots':len(prof.snapshots),'maxDopplerErrorHz_exactC':float(np.max(abs(actual-reference))),'maxDopplerErrorHz_modelC':float(np.max(abs(actual-reference*299792458/3e8))),'maxDelayErrorS':float(max(abs(sn.clusters[0].delay_s-d/299792458) for sn,d in zip(prof.snapshots,lengths))),'frequencyFirstLast':actual[[0,-1]].tolist(),'representedLastTimeS':(len(times)-1)/prof.trajectory_meta.skeleton_rate_hz,'referenceLastTimeS':float(times[-1]),'limitation':'native_fit_trajectory accepts uniform skeleton_rate_hz, no per-snapshot timestamps; native profile contains spectra not reconstructed complex trajectory. Exporter fixed rays cannot express changing delays/directions.'}

(output/'ce-results.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
