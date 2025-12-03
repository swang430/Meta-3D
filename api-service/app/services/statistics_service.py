"""
Statistical Analysis Service for Report Comparisons

Provides algorithms for:
- Multi-report comparison
- Statistical metrics calculation
- Trend analysis
- Data aggregation for visualization
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from statistics import mean, stdev, median
from collections import defaultdict
import numpy as np

# Note: TestExecution model to be implemented in future phase
# from app.models.test_execution import TestExecution
from app.models.report import TestReport


class StatisticsService:
    """Service for statistical analysis and report comparisons"""

    def __init__(self):
        """Initialize statistics service"""
        pass

    # ==================== Basic Statistics ====================

    def calculate_basic_stats(self, values: List[float]) -> Dict[str, float]:
        """
        Calculate basic statistical metrics

        Args:
            values: List of numerical values

        Returns:
            Dictionary containing mean, median, std, min, max, range
        """
        if not values:
            return {
                "mean": 0.0,
                "median": 0.0,
                "std": 0.0,
                "min": 0.0,
                "max": 0.0,
                "range": 0.0,
                "count": 0
            }

        return {
            "mean": float(mean(values)),
            "median": float(median(values)),
            "std": float(stdev(values)) if len(values) > 1 else 0.0,
            "min": float(min(values)),
            "max": float(max(values)),
            "range": float(max(values) - min(values)),
            "count": int(len(values))
        }

    def calculate_confidence_interval(
        self,
        values: List[float],
        confidence: float = 0.95
    ) -> Tuple[float, float]:
        """
        Calculate confidence interval

        Args:
            values: List of numerical values
            confidence: Confidence level (default 95%)

        Returns:
            Tuple of (lower_bound, upper_bound)
        """
        if len(values) < 2:
            m = mean(values) if values else 0.0
            return (float(m), float(m))

        m = mean(values)
        s = stdev(values)
        n = len(values)

        # Using t-distribution for small samples
        from scipy import stats
        t_value = stats.t.ppf((1 + confidence) / 2, n - 1)
        margin = t_value * (s / np.sqrt(n))

        return (float(m - margin), float(m + margin))

    def calculate_percentiles(
        self,
        values: List[float],
        percentiles: List[int] = [25, 50, 75, 90, 95, 99]
    ) -> Dict[str, float]:
        """
        Calculate percentiles

        Args:
            values: List of numerical values
            percentiles: List of percentile values to calculate

        Returns:
            Dictionary mapping percentile to value (keys are strings)
        """
        if not values:
            return {str(p): 0.0 for p in percentiles}

        return {
            str(p): float(np.percentile(values, p)) for p in percentiles
        }

    # ==================== Report Comparison ====================

    def compare_reports(
        self,
        report_ids: List[str],
        metrics: Optional[List[str]] = None,
        group_by: Optional[str] = None,
        confidence_level: float = 0.95
    ) -> Dict[str, Any]:
        """
        Compare multiple reports

        Args:
            report_ids: List of report IDs to compare
            metrics: Specific metrics to compare (optional)
            group_by: Grouping strategy (optional)
            confidence_level: Confidence level for statistical tests

        Returns:
            Comprehensive comparison analysis
        """
        # TODO: Replace with actual database query when test execution model exists
        # For now, generate mock data for each report

        if not report_ids:
            return {"error": "No report IDs provided"}

        # Generate mock metrics for each report
        all_metrics = defaultdict(lambda: {"by_report": {}, "overall": {}, "values": []})

        metric_names = metrics or ["throughput_mbps", "latency_ms", "packet_loss_percent", "rsrp_dbm", "sinr_db"]

        for report_id in report_ids:
            for metric_name in metric_names:
                # Generate realistic mock data with some variation
                base_value = {
                    "throughput_mbps": 500,
                    "latency_ms": 50,
                    "packet_loss_percent": 1.5,
                    "rsrp_dbm": -80,
                    "sinr_db": 15
                }.get(metric_name, 100)

                # Add random variation (use absolute value for scale to avoid negative std)
                values = [base_value + np.random.normal(0, abs(base_value) * 0.15) for _ in range(20)]

                stats = self.calculate_basic_stats(values)
                stats["percentiles"] = self.calculate_percentiles(values)
                ci = self.calculate_confidence_interval(values, confidence_level)
                stats["confidence_interval"] = {"lower": ci[0], "upper": ci[1]}

                all_metrics[metric_name]["by_report"][report_id] = stats
                all_metrics[metric_name]["values"].extend(values)

        # Calculate overall statistics for each metric
        for metric_name, metric_data in all_metrics.items():
            overall_stats = self.calculate_basic_stats(metric_data["values"])
            overall_stats["coefficient_of_variation"] = (
                (overall_stats["std"] / overall_stats["mean"] * 100)
                if overall_stats["mean"] != 0 else 0.0
            )
            metric_data["overall"] = overall_stats

        return {
            "metrics": dict(all_metrics),
            "summary": {
                "total_reports": len(report_ids),
                "metrics_analyzed": len(metric_names),
                "confidence_level": confidence_level
            }
        }


    # ==================== Time Series Analysis ====================

    def analyze_time_series(
        self,
        test_plan_id: str,
        metric_name: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        window_size: int = 5,
        anomaly_threshold: float = 3.0
    ) -> Dict[str, Any]:
        """
        Analyze time series data for a specific metric

        Args:
            test_plan_id: Test plan ID
            metric_name: Name of the metric to analyze
            start_date: Start date for analysis
            end_date: End date for analysis
            window_size: Rolling window size for trend analysis
            anomaly_threshold: Z-score threshold for anomaly detection

        Returns:
            Time series analysis including trend, seasonality, anomalies
        """
        # TODO: Replace with actual database query when test execution model exists
        # For now, generate mock time series data

        # Generate mock timestamps
        now = datetime.utcnow()
        num_points = 30
        timestamps = [now - __import__('datetime').timedelta(days=i) for i in range(num_points-1, -1, -1)]

        # Generate mock values with trend and some anomalies
        base_value = {
            "throughput_mbps": 500,
            "latency_ms": 50,
            "packet_loss_percent": 1.5,
            "rsrp_dbm": -80,
            "sinr_db": 15
        }.get(metric_name, 100)

        # Add trend and noise (use absolute value for scale to avoid negative std)
        values = []
        for i in range(num_points):
            trend_component = base_value + (i * base_value * 0.01)  # Slight upward trend
            noise = np.random.normal(0, abs(base_value) * 0.1)
            # Add occasional anomalies
            if i in [10, 20]:
                noise += abs(base_value) * 0.5  # Anomaly
            values.append(trend_component + noise)

        # Generate mock execution IDs
        import uuid
        execution_ids = [str(uuid.uuid4()) for _ in range(num_points)]

        # Calculate rolling statistics
        actual_window = min(window_size, len(values))
        rolling_mean = self._calculate_rolling_mean(values, actual_window)
        rolling_std = self._calculate_rolling_std(values, actual_window)

        # Detect anomalies
        anomalies = self._detect_anomalies(values, rolling_mean, rolling_std, anomaly_threshold)

        # Calculate trend
        trend_data = self._calculate_linear_trend(timestamps, values)

        # Determine trend strength and direction
        r_squared = trend_data["r_squared"]
        strength = "strong" if r_squared > 0.7 else "moderate" if r_squared > 0.4 else "weak"
        direction = trend_data["trend_direction"]

        # Build data points with anomaly flags
        data_points = []
        anomaly_indices = {a["index"] for a in anomalies}
        for i, (ts, val, exec_id) in enumerate(zip(timestamps, values, execution_ids)):
            z_score = None
            if i in anomaly_indices:
                z_score = next((a["z_score"] for a in anomalies if a["index"] == i), None)

            data_points.append({
                "timestamp": ts,
                "value": val,
                "execution_id": exec_id,
                "is_anomaly": i in anomaly_indices,
                "z_score": z_score
            })

        return {
            "data_points": data_points,
            "trend": {
                "direction": direction,
                "slope": trend_data["slope"],
                "r_squared": r_squared,
                "strength": strength
            },
            "anomalies": anomalies,
            "statistics": self.calculate_basic_stats(values),
            "rolling_mean": rolling_mean,
            "rolling_std": rolling_std
        }

    def _calculate_rolling_mean(
        self,
        values: List[float],
        window: int
    ) -> List[float]:
        """Calculate rolling mean"""
        if len(values) < window:
            return [mean(values)] * len(values)

        return [
            mean(values[max(0, i-window+1):i+1])
            for i in range(len(values))
        ]

    def _calculate_rolling_std(
        self,
        values: List[float],
        window: int
    ) -> List[float]:
        """Calculate rolling standard deviation"""
        if len(values) < window:
            return [stdev(values) if len(values) > 1 else 0.0] * len(values)

        return [
            stdev(values[max(0, i-window+1):i+1]) if i >= window-1 else 0.0
            for i in range(len(values))
        ]

    def _detect_anomalies(
        self,
        values: List[float],
        rolling_mean: List[float],
        rolling_std: List[float],
        threshold: float = 3.0
    ) -> List[Dict[str, Any]]:
        """
        Detect anomalies using statistical methods

        Uses z-score method: points beyond threshold standard deviations
        from the rolling mean are considered anomalies
        """
        anomalies = []

        for i, (value, mean_val, std_val) in enumerate(zip(values, rolling_mean, rolling_std)):
            if std_val > 0:
                z_score = abs((value - mean_val) / std_val)
                if z_score > threshold:
                    anomalies.append({
                        "index": i,
                        "value": value,
                        "expected": mean_val,
                        "z_score": z_score,
                        "severity": "high" if z_score > 5 else "medium"
                    })

        return anomalies

    def _calculate_linear_trend(
        self,
        timestamps: List[datetime],
        values: List[float]
    ) -> Dict[str, Any]:
        """Calculate linear trend using least squares"""
        if len(timestamps) < 2:
            return {"slope": 0, "intercept": 0, "r_squared": 0}

        # Convert timestamps to numeric values (seconds since first timestamp)
        t0 = timestamps[0].timestamp()
        x = np.array([(t.timestamp() - t0) for t in timestamps])
        y = np.array(values)

        # Calculate linear regression
        n = len(x)
        x_mean = np.mean(x)
        y_mean = np.mean(y)

        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = np.sum((x - x_mean) ** 2)

        if denominator == 0:
            return {"slope": 0, "intercept": y_mean, "r_squared": 0}

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        # Calculate R-squared
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y_mean) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        return {
            "slope": float(slope),
            "intercept": float(intercept),
            "r_squared": float(r_squared),
            "trend_direction": "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable"
        }

    # ==================== Performance Benchmarking ====================

    def benchmark_performance(
        self,
        report_id: str,
        reference_report_ids: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Benchmark a report's performance against reference reports

        Args:
            report_id: Report to benchmark
            reference_report_ids: List of reference report IDs (baseline)
            metrics: Specific metrics to benchmark (optional)

        Returns:
            Benchmarking analysis with percentile rankings
        """
        # TODO: Replace with actual database query when test execution model exists
        # For now, generate mock benchmarking data

        # Determine number of reference reports
        num_references = len(reference_report_ids) if reference_report_ids else 50

        # Generate mock metrics for target report and references
        metric_names = metrics or ["throughput_mbps", "latency_ms", "packet_loss_percent", "rsrp_dbm", "sinr_db"]

        benchmark_metrics = []
        percentiles = []

        for metric_name in metric_names:
            # Base values for different metrics
            base_value = {
                "throughput_mbps": 500,
                "latency_ms": 50,
                "packet_loss_percent": 1.5,
                "rsrp_dbm": -80,
                "sinr_db": 15
            }.get(metric_name, 100)

            # Generate target value (slightly above average, use absolute value for scale)
            target_value = base_value + np.random.normal(0, abs(base_value) * 0.1)

            # Generate reference values (use absolute value for scale to avoid negative std)
            reference_values = [
                base_value + np.random.normal(0, abs(base_value) * 0.15)
                for _ in range(num_references)
            ]

            # Calculate percentile rank
            below = sum(1 for v in reference_values if v < target_value)
            percentile_rank = (below / len(reference_values)) * 100

            # Calculate reference statistics
            ref_mean = mean(reference_values)
            ref_std = stdev(reference_values) if len(reference_values) > 1 else 0.0

            # Calculate z-score
            z_score = (target_value - ref_mean) / ref_std if ref_std > 0 else 0.0

            # Determine performance rating
            if percentile_rank >= 90:
                rating = "excellent"
            elif percentile_rank >= 70:
                rating = "good"
            elif percentile_rank >= 40:
                rating = "average"
            elif percentile_rank >= 20:
                rating = "below_average"
            else:
                rating = "poor"

            benchmark_metrics.append({
                "metric_name": metric_name,
                "value": target_value,
                "percentile_rank": percentile_rank,
                "performance_rating": rating,
                "reference_mean": ref_mean,
                "reference_std": ref_std,
                "z_score": z_score
            })

            percentiles.append(percentile_rank)

        # Calculate overall performance
        overall_percentile = mean(percentiles)
        if overall_percentile >= 90:
            overall_rating = "excellent"
        elif overall_percentile >= 70:
            overall_rating = "good"
        elif overall_percentile >= 40:
            overall_rating = "average"
        elif overall_percentile >= 20:
            overall_rating = "below_average"
        else:
            overall_rating = "poor"

        summary = f"Report performs at {overall_percentile:.1f}th percentile across {len(metric_names)} metrics, rated as '{overall_rating}' compared to {num_references} reference reports."

        return {
            "reference_count": num_references,
            "metrics": benchmark_metrics,
            "overall_percentile": overall_percentile,
            "overall_rating": overall_rating,
            "summary": summary
        }
