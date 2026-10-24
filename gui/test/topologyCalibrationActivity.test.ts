import test from 'node:test'
import assert from 'node:assert/strict'
import { calibrationActivityBlocked } from '../src/features/TopologyEditor/calibrationActivity.ts'

test('只有成功读到无运行任务才能放行编辑；离线、失败、未读取不能作停发证据',()=>{
  const good={isSuccess:true,isFetching:false,isPaused:false,isError:false}
  assert.equal(calibrationActivityBlocked(false,false,good),false)
  for(const query of [{...good,isError:true},{...good,isPaused:true},{...good,isSuccess:false},{...good,isFetching:true}])
    assert.equal(calibrationActivityBlocked(false,false,query),true)
  assert.equal(calibrationActivityBlocked(true,false,good),true)
  assert.equal(calibrationActivityBlocked(false,true,good),true)
})
