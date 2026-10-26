import {test} from 'node:test';
import assert from 'node:assert/strict';
import {nominalFieldsForNode, parseOptionalNominalNumber, setNodeNominal, setEdgeNominal, nominalMetadata} from '../src/features/TopologyEditor/nominalProperties.ts';

test('清空是null且零不丢，编辑不改原节点或扩展字段',()=>{
  assert.equal(parseOptionalNominalNumber(''),null);
  assert.equal(parseOptionalNominalNumber(0),0);
  assert.equal(parseOptionalNominalNumber(-3),-3);
  for(const value of ['not-a-number','-', '12',NaN,Infinity]) assert.throws(()=>parseOptionalNominalNumber(value));
  const before={id:'pa',type:'amplifier',label:'PA',position:{x:10,y:20},params:{gain_db:20,unknown:{keep:1}}};
  const metadata={unit:'dB' as const,source_note:null,frequency_range_mhz:null};
  const after=setNodeNominal(before,'gain_db',0,metadata);
  assert.equal(after.params.gain_db,0);
  assert.equal(before.params.gain_db,20);
  assert.deepEqual(after.params.unknown,{keep:1});
  assert.deepEqual(after.position,{x:10,y:20});
  assert.notEqual(after.params.nominal_metadata.gain_db,metadata);
  const updated=setNodeNominal(after,'gain_db',null,{...metadata,source_note:'铭牌，非实测'});
  assert.equal(updated.params.gain_db,null);
  assert.equal(after.params.nominal_metadata.gain_db.source_note,null);
});

test('字段表只允许本片器件声明，非负字段与单位准确',()=>{
  assert.deepEqual(nominalFieldsForNode('amplifier'),[{key:'gain_db',label:'PA标称增益',unit:'dB',nonnegative:false}]);
  for(const type of ['probe','antenna','reference_antenna']) assert.equal(nominalFieldsForNode(type)[0].unit,'dBi');
  assert.equal(nominalFieldsForNode('pad')[0].nonnegative,true);
  assert.equal(nominalFieldsForNode('combiner')[0].key,'loss_db');
  for(const type of ['cable','receive_cable','channel_emulator']) assert.deepEqual(nominalFieldsForNode(type),[]);
});

test('边标称更新保留稀疏键、校准零与其他元数据，不泄漏引用',()=>{
  const before={id:'e',source:'a',target:'b',calibrated_loss_db:0,nominal_metadata:{cable_loss_db:{unit:'dB',source_note:null,frequency_range_mhz:null}}};
  const metadata={unit:'dB' as const,source_note:'旧声明',frequency_range_mhz:[2500,2700] as [number,number]};
  const after=setEdgeNominal(before,'pa_gain_db',0,metadata);
  assert.equal(after.pa_gain_db,0);
  assert.equal(after.calibrated_loss_db,0);
  assert.equal(Object.hasOwn(after,'cable_loss_db'),false);
  assert.equal(Object.hasOwn(before,'pa_gain_db'),false);
  assert.deepEqual(after.nominal_metadata.cable_loss_db,before.nominal_metadata.cable_loss_db);
  metadata.frequency_range_mhz[0]=1;
  assert.deepEqual(after.nominal_metadata.pa_gain_db.frequency_range_mhz,[2500,2700]);
});

test('来源空白为null；频率必须成对且有限为正，允许单频',()=>{
  assert.deepEqual(nominalMetadata('dB','  ','',''),{unit:'dB',source_note:null,frequency_range_mhz:null});
  assert.deepEqual(nominalMetadata('dBi',' 铭牌 ',2595,2595),{unit:'dBi',source_note:'铭牌',frequency_range_mhz:[2595,2595]});
  for(const [a,b] of [[2500,''],['',2700],[0,2700],[2800,2700],[NaN,2700],['2500',2700]] as [number|string,number|string][])
    assert.throws(()=>nominalMetadata('dB','来源',a,b));
});
