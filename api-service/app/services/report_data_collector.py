"""
Report Data Collector

Collects and aggregates test data from the database for report generation.
Handles data extraction, statistics calculation, and time series building.
"""

from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict
import statistics
import logging

from app.models.test_plan import TestPlan, TestExecution, TestStep
from app.models.report import TestReport

logger = logging.getLogger(__name__)


@dataclass
class MetricStats:
    """Statistical summary for a single metric"""
    metric_name: str
    mean: float
    median: float
    std: float
    min_value: float
    max_value: float
    count: int
    percentile_25: float = 0.0
    percentile_75: float = 0.0
    percentile_95: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "mean": self.mean,
            "median": self.median,
            "std": self.std,
            "min": self.min_value,
            "max": self.max_value,
            "range": self.max_value - self.min_value,
            "count": self.count,
            "percentiles": {
                "25": self.percentile_25,
                "50": self.median,
                "75": self.percentile_75,
                "95": self.percentile_95,
            }
        }


@dataclass
class TestPlanInfo:
    """Test plan information for report"""
    id: str
    name: str
    description: Optional[str]
    status: str
    dut_info: Dict[str, Any]
    test_environment: Dict[str, Any]
    created_by: str
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "dut_info": self.dut_info,
            "test_environment": self.test_environment,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class ExecutionSummary:
    """Summary of test executions"""
    total_executions: int
    passed: int
    failed: int
    pending: int
    total_duration_sec: float
    pass_rate: float
    first_execution: Optional[datetime] = None
    last_execution: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_executions": self.total_executions,
            "passed": self.passed,
            "failed": self.failed,
            "pending": self.pending,
            "total_duration_sec": self.total_duration_sec,
            "pass_rate": self.pass_rate,
            "first_execution": self.first_execution.isoformat() if self.first_execution else None,
            "last_execution": self.last_execution.isoformat() if self.last_execution else None,
        }


@dataclass
class TimeSeriesPoint:
    """Single point in time series data"""
    timestamp: datetime
    execution_id: str
    values: Dict[str, float]
    is_anomaly: bool = False
    z_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "execution_id": self.execution_id,
            "values": self.values,
            "is_anomaly": self.is_anomaly,
            "z_score": self.z_score,
        }


@dataclass
class ReportData:
    """Complete data structure for report generation"""
    # Basic info
    title: str
    report_type: str
    generated_by: str
    generated_at: datetime

    # Test plan info
    test_plan: Optional[TestPlanInfo] = None

    # Execution summary
    execution_summary: Optional[ExecutionSummary] = None

    # Raw measurements grouped by metric
    measurements: Dict[str, List[float]] = field(default_factory=dict)

    # Statistics for each metric
    statistics: Dict[str, MetricStats] = field(default_factory=dict)

    # Time series data
    time_series: List[TimeSeriesPoint] = field(default_factory=list)

    # Step results
    step_results: List[Dict[str, Any]] = field(default_factory=list)

    # Table data for PDF generation
    table_data: List[Dict[str, Any]] = field(default_factory=list)

    # Chart data (processed for visualization)
    chart_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "report_type": self.report_type,
            "generated_by": self.generated_by,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "test_plan": self.test_plan.to_dict() if self.test_plan else None,
            "execution_summary": self.execution_summary.to_dict() if self.execution_summary else None,
            "measurements": self.measurements,
            "statistics": {k: v.to_dict() for k, v in self.statistics.items()},
            "time_series": [p.to_dict() for p in self.time_series],
            "step_results": self.step_results,
            "table_data": self.table_data,
            "chart_data": self.chart_data,
        }


class ReportDataCollector:
    """
    Collects and aggregates test data from the database for report generation.

    This class handles:
    - Fetching test plan and execution data
    - Extracting measurements from execution records
    - Calculating statistics (mean, std, percentiles)
    - Building time series data for trend analysis
    - Detecting anomalies using z-score
    """

    def __init__(self, anomaly_threshold: float = 3.0):
        self.anomaly_threshold = anomaly_threshold

    def collect(self, db: Session, report: TestReport) -> ReportData:
        """
        Collect all data needed for report generation.

        Args:
            db: Database session
            report: Report model with configuration

        Returns:
            ReportData: Complete data structure for report generation
        """
        logger.info(f"Collecting data for report: {report.id}")

        # Initialize report data
        report_data = ReportData(
            title=report.title,
            report_type=report.report_type,
            generated_by=report.generated_by,
            generated_at=datetime.utcnow(),
        )

        # 1. Get test plan info
        if report.test_plan_id:
            test_plan = self._get_test_plan(db, report.test_plan_id)
            if test_plan:
                report_data.test_plan = TestPlanInfo(
                    id=str(test_plan.id),
                    name=test_plan.name,
                    description=test_plan.description,
                    status=test_plan.status,
                    dut_info=test_plan.dut_info or {},
                    test_environment=test_plan.test_environment or {},
                    created_by=test_plan.created_by,
                    created_at=test_plan.created_at,
                )

        # 2. Get test executions
        executions = self._get_executions(db, report)
        if executions:
            # 3. Build execution summary
            report_data.execution_summary = self._build_execution_summary(executions)

            # 4. Extract measurements
            report_data.measurements = self._extract_measurements(executions)

            # 5. Calculate statistics
            report_data.statistics = self._calculate_statistics(report_data.measurements)

            # 6. Build time series
            report_data.time_series = self._build_time_series(executions)

            # 7. Detect anomalies
            self._detect_anomalies(report_data)

            # 8. Build step results
            if report.test_plan_id:
                report_data.step_results = self._get_step_results(db, report.test_plan_id)

            # 9. Build table data for PDF
            report_data.table_data = self._build_table_data(report_data)

            # 10. Build chart data
            report_data.chart_data = self._build_chart_data(report_data)

        logger.info(f"Data collection complete for report: {report.id}")
        return report_data

    def _get_test_plan(self, db: Session, test_plan_id: UUID) -> Optional[TestPlan]:
        """Fetch test plan from database"""
        return db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()

    def _get_executions(self, db: Session, report: TestReport) -> List[TestExecution]:
        """Fetch test executions based on report configuration"""
        from uuid import UUID as PyUUID
        query = db.query(TestExecution)

        if report.test_execution_ids:
            # Use specific execution IDs if provided
            # Convert string IDs to UUID if needed
            execution_ids = [
                PyUUID(eid) if isinstance(eid, str) else eid
                for eid in report.test_execution_ids
            ]
            query = query.filter(TestExecution.id.in_(execution_ids))
        elif report.test_plan_id:
            # Otherwise, get all executions for the test plan
            query = query.filter(TestExecution.test_plan_id == report.test_plan_id)
        else:
            return []

        return query.order_by(TestExecution.executed_at.asc()).all()

    def _build_execution_summary(self, executions: List[TestExecution]) -> ExecutionSummary:
        """Build summary from execution records"""
        total = len(executions)
        passed = sum(1 for e in executions if e.validation_pass is True)
        failed = sum(1 for e in executions if e.validation_pass is False)
        pending = sum(1 for e in executions if e.validation_pass is None)
        total_duration = sum(e.duration_sec or 0 for e in executions)

        execution_times = [e.executed_at for e in executions if e.executed_at]
        first_execution = min(execution_times) if execution_times else None
        last_execution = max(execution_times) if execution_times else None

        return ExecutionSummary(
            total_executions=total,
            passed=passed,
            failed=failed,
            pending=pending,
            total_duration_sec=total_duration,
            pass_rate=round(passed / total * 100, 2) if total > 0 else 0,
            first_execution=first_execution,
            last_execution=last_execution,
        )

    def _extract_measurements(self, executions: List[TestExecution]) -> Dict[str, List[float]]:
        """Extract all measurements from executions, grouped by metric name"""
        measurements = defaultdict(list)

        for execution in executions:
            if execution.measurements:
                for metric, value in execution.measurements.items():
                    if isinstance(value, (int, float)):
                        measurements[metric].append(float(value))
                    elif isinstance(value, list):
                        # Handle array values (e.g., time series within single execution)
                        for v in value:
                            if isinstance(v, (int, float)):
                                measurements[metric].append(float(v))

            # Also extract from test_results if available
            if execution.test_results:
                for key, value in execution.test_results.items():
                    if isinstance(value, (int, float)):
                        measurements[f"result_{key}"].append(float(value))

        return dict(measurements)

    def _calculate_statistics(self, measurements: Dict[str, List[float]]) -> Dict[str, MetricStats]:
        """Calculate statistics for each metric"""
        stats = {}

        for metric, values in measurements.items():
            if not values:
                continue

            try:
                # Sort values for percentile calculation
                sorted_values = sorted(values)
                n = len(sorted_values)

                # Helper function to safely get percentile index
                def get_percentile_index(n: int, percentile: float) -> int:
                    """Calculate percentile index with proper boundary handling"""
                    if n == 0:
                        return 0
                    idx = int(n * percentile)
                    return min(idx, n - 1)  # Ensure index doesn't exceed array bounds

                stats[metric] = MetricStats(
                    metric_name=metric,
                    mean=statistics.mean(values),
                    median=statistics.median(values),
                    std=statistics.stdev(values) if n > 1 else 0,
                    min_value=min(values),
                    max_value=max(values),
                    count=n,
                    percentile_25=sorted_values[get_percentile_index(n, 0.25)] if n > 0 else 0,
                    percentile_75=sorted_values[get_percentile_index(n, 0.75)] if n > 0 else 0,
                    percentile_95=sorted_values[get_percentile_index(n, 0.95)] if n > 0 else 0,
                )
            except Exception as e:
                logger.warning(f"Error calculating statistics for {metric}: {e}")

        return stats

    def _build_time_series(self, executions: List[TestExecution]) -> List[TimeSeriesPoint]:
        """Build time series data from executions"""
        time_series = []

        for execution in executions:
            if not execution.executed_at:
                continue

            # Extract all numeric values from measurements
            values = {}
            if execution.measurements:
                for metric, value in execution.measurements.items():
                    if isinstance(value, (int, float)):
                        values[metric] = float(value)

            if values:
                time_series.append(TimeSeriesPoint(
                    timestamp=execution.executed_at,
                    execution_id=str(execution.id),
                    values=values,
                ))

        return time_series

    def _detect_anomalies(self, report_data: ReportData) -> None:
        """Detect anomalies in time series using z-score"""
        if not report_data.time_series or not report_data.statistics:
            return

        for point in report_data.time_series:
            max_z_score = 0
            is_anomaly = False

            for metric, value in point.values.items():
                if metric in report_data.statistics:
                    stats = report_data.statistics[metric]
                    if stats.std > 0:
                        z_score = abs((value - stats.mean) / stats.std)
                        if z_score > max_z_score:
                            max_z_score = z_score
                        if z_score > self.anomaly_threshold:
                            is_anomaly = True

            point.z_score = max_z_score
            point.is_anomaly = is_anomaly

    def _get_step_results(self, db: Session, test_plan_id: UUID) -> List[Dict[str, Any]]:
        """Get step results for the test plan"""
        steps = db.query(TestStep).filter(
            TestStep.test_plan_id == test_plan_id
        ).order_by(TestStep.order.asc()).all()

        results = []
        for step in steps:
            results.append({
                "order": step.order,
                "name": step.name,
                "status": step.status,
                "result": step.result,
                "duration_minutes": step.actual_duration_minutes,
                "error_message": step.error_message,
                # Enhanced: Include detailed parameters and validation criteria
                "parameters": step.parameters or {},
                "validation_criteria": step.validation_criteria or {},
                "started_at": step.started_at.isoformat() if step.started_at else None,
                "completed_at": step.completed_at.isoformat() if step.completed_at else None,
            })

        return results

    def _build_table_data(self, report_data: ReportData) -> List[Dict[str, Any]]:
        """Build table data for PDF generation"""
        table_data = []

        for metric, stats in report_data.statistics.items():
            # Determine pass/fail based on some criteria (can be customized)
            pass_fail = "N/A"

            table_data.append({
                "Metric": metric,
                "Mean": f"{stats.mean:.2f}",
                "Median": f"{stats.median:.2f}",
                "Std Dev": f"{stats.std:.2f}",
                "Min": f"{stats.min_value:.2f}",
                "Max": f"{stats.max_value:.2f}",
                "Count": str(stats.count),
                "Pass/Fail": pass_fail,
            })

        return table_data

    def _build_chart_data(self, report_data: ReportData) -> Dict[str, Any]:
        """Build chart data for visualization"""
        chart_data = {}

        # Time series chart data
        if report_data.time_series:
            timestamps = [p.timestamp.isoformat() for p in report_data.time_series]

            for metric in report_data.statistics.keys():
                values = []
                anomalies = []

                for i, point in enumerate(report_data.time_series):
                    if metric in point.values:
                        values.append(point.values[metric])
                        if point.is_anomaly:
                            anomalies.append(i)
                    else:
                        values.append(None)

                if values:
                    chart_data[f"time_series_{metric}"] = {
                        "timestamps": timestamps,
                        "values": values,
                        "anomaly_indices": anomalies,
                    }

        # Statistics comparison chart data
        if report_data.statistics:
            metrics = list(report_data.statistics.keys())
            means = [report_data.statistics[m].mean for m in metrics]
            stds = [report_data.statistics[m].std for m in metrics]

            chart_data["statistics_comparison"] = {
                "metrics": metrics,
                "means": means,
                "stds": stds,
            }

        return chart_data
