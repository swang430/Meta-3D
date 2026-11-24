import type {
  fetchConductedCalibration, prepareConducted, registerConductedCalibration,
} from '../src/api/roadTestService'
import type { ConductedSelection } from '../src/types/roadTest'

// 这些约束只在编译时检查，不会登记校准或启动设备。
type Equal<A, B> = (<T>() => T extends A ? 1 : 2) extends (<T>() => T extends B ? 1 : 2) ? true : false
type Assert<T extends true> = T
type Detail = Awaited<ReturnType<typeof fetchConductedCalibration>>
type Preparation = Awaited<ReturnType<typeof prepareConducted>>
type Binding = NonNullable<Preparation['binding']>
type Check = NonNullable<NonNullable<Binding['real_preflight']>['calibration']>

export type CalibrationContract = [
  Assert<Equal<Parameters<typeof registerConductedCalibration>[0], { report_file: string }>>,
  Assert<Equal<Detail['readings_b64'], string>>,
  Assert<Equal<Detail['revoked_at'], string | null>>,
  Assert<Equal<ConductedSelection['calibration_id'], string | null | undefined>>,
  Assert<Equal<Binding['execution_mode'], 'real' | 'simulated' | null>>,
  Assert<Equal<Check['applicable'], boolean>>,
  Assert<Equal<Check['ports'][number]['dut_input_margin_db'], number>>,
]
