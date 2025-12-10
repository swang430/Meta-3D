"""Chart Generation Service for Reports

This module generates various types of charts for test reports using matplotlib.
Supports line charts, bar charts, scatter plots, and heatmaps.
"""
import io
import logging
from typing import Dict, List, Any, Optional
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Service for generating charts for reports"""

    def __init__(self):
        # Set default style
        plt.style.use('default')
        self.default_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']

    def generate_line_chart(
        self,
        data: Dict[str, Any],
        config: Dict[str, Any],
        save_path: Optional[str] = None
    ) -> bytes:
        """
        Generate a line chart

        Args:
            data: Dictionary containing x_data and y_data lists
            config: Chart configuration (title, labels, colors, etc.)
            save_path: Optional file path to save the chart

        Returns:
            Bytes of PNG image
        """
        fig, ax = plt.subplots(figsize=(10, 6))

        # Extract data
        x_data = data.get('x_data', [])
        y_data = data.get('y_data', [])

        # Handle multiple series
        if isinstance(y_data[0], list):
            for i, series in enumerate(y_data):
                label = config.get('series_labels', [])[i] if i < len(config.get('series_labels', [])) else f'Series {i+1}'
                color = config.get('colors', self.default_colors)[i % len(self.default_colors)]
                ax.plot(x_data, series, label=label, color=color, linewidth=2)
        else:
            color = config.get('color', self.default_colors[0])
            ax.plot(x_data, y_data, color=color, linewidth=2)

        # Set labels and title
        ax.set_xlabel(config.get('x_axis', {}).get('label', 'X Axis'), fontsize=12)
        ax.set_ylabel(config.get('y_axis', {}).get('label', 'Y Axis'), fontsize=12)
        ax.set_title(config.get('title', 'Line Chart'), fontsize=14, fontweight='bold')

        # Add grid
        ax.grid(True, alpha=0.3)

        # Add legend if multiple series
        if isinstance(y_data[0], list) or config.get('show_legend', False):
            ax.legend(loc='best')

        # Tight layout
        plt.tight_layout()

        # Save to bytes
        return self._save_figure(fig, save_path)

    def generate_bar_chart(
        self,
        data: Dict[str, Any],
        config: Dict[str, Any],
        save_path: Optional[str] = None
    ) -> bytes:
        """
        Generate a bar chart

        Args:
            data: Dictionary containing categories and values
            config: Chart configuration
            save_path: Optional file path to save the chart

        Returns:
            Bytes of PNG image
        """
        fig, ax = plt.subplots(figsize=(10, 6))

        categories = data.get('categories', [])
        values = data.get('values', [])

        # Handle grouped bar chart
        if isinstance(values[0], list):
            x = np.arange(len(categories))
            width = 0.8 / len(values)

            for i, series in enumerate(values):
                offset = (i - len(values)/2 + 0.5) * width
                label = config.get('series_labels', [])[i] if i < len(config.get('series_labels', [])) else f'Series {i+1}'
                color = config.get('colors', self.default_colors)[i % len(self.default_colors)]
                ax.bar(x + offset, series, width, label=label, color=color)

            ax.set_xticks(x)
            ax.set_xticklabels(categories, rotation=45, ha='right')
            ax.legend()
        else:
            color = config.get('color', self.default_colors[0])
            ax.bar(categories, values, color=color)
            plt.xticks(rotation=45, ha='right')

        # Set labels and title
        ax.set_xlabel(config.get('x_axis', {}).get('label', 'Category'), fontsize=12)
        ax.set_ylabel(config.get('y_axis', {}).get('label', 'Value'), fontsize=12)
        ax.set_title(config.get('title', 'Bar Chart'), fontsize=14, fontweight='bold')

        # Add grid
        ax.grid(True, alpha=0.3, axis='y')

        # Tight layout
        plt.tight_layout()

        return self._save_figure(fig, save_path)

    def generate_scatter_plot(
        self,
        data: Dict[str, Any],
        config: Dict[str, Any],
        save_path: Optional[str] = None
    ) -> bytes:
        """
        Generate a scatter plot

        Args:
            data: Dictionary containing x_data and y_data
            config: Chart configuration
            save_path: Optional file path to save the chart

        Returns:
            Bytes of PNG image
        """
        fig, ax = plt.subplots(figsize=(10, 6))

        x_data = data.get('x_data', [])
        y_data = data.get('y_data', [])

        color = config.get('color', self.default_colors[0])
        size = config.get('marker_size', 50)

        ax.scatter(x_data, y_data, c=color, s=size, alpha=0.6, edgecolors='black', linewidth=0.5)

        # Add trend line if requested
        if config.get('show_trendline', False):
            z = np.polyfit(x_data, y_data, 1)
            p = np.poly1d(z)
            ax.plot(x_data, p(x_data), "r--", alpha=0.8, label='Trend Line')
            ax.legend()

        # Set labels and title
        ax.set_xlabel(config.get('x_axis', {}).get('label', 'X Axis'), fontsize=12)
        ax.set_ylabel(config.get('y_axis', {}).get('label', 'Y Axis'), fontsize=12)
        ax.set_title(config.get('title', 'Scatter Plot'), fontsize=14, fontweight='bold')

        # Add grid
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        return self._save_figure(fig, save_path)

    def generate_heatmap(
        self,
        data: Dict[str, Any],
        config: Dict[str, Any],
        save_path: Optional[str] = None
    ) -> bytes:
        """
        Generate a heatmap

        Args:
            data: Dictionary containing 2D matrix data
            config: Chart configuration
            save_path: Optional file path to save the chart

        Returns:
            Bytes of PNG image
        """
        fig, ax = plt.subplots(figsize=(10, 8))

        matrix = np.array(data.get('matrix', []))
        x_labels = data.get('x_labels', [])
        y_labels = data.get('y_labels', [])

        # Create heatmap
        im = ax.imshow(matrix, cmap=config.get('colormap', 'viridis'), aspect='auto')

        # Add colorbar
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label(config.get('colorbar_label', 'Value'), rotation=270, labelpad=20)

        # Set ticks and labels
        if x_labels:
            ax.set_xticks(np.arange(len(x_labels)))
            ax.set_xticklabels(x_labels, rotation=45, ha='right')

        if y_labels:
            ax.set_yticks(np.arange(len(y_labels)))
            ax.set_yticklabels(y_labels)

        # Add values in cells if requested
        if config.get('show_values', False):
            for i in range(len(y_labels)):
                for j in range(len(x_labels)):
                    text = ax.text(j, i, f'{matrix[i, j]:.2f}',
                                 ha="center", va="center", color="white", fontsize=10)

        # Set title
        ax.set_title(config.get('title', 'Heatmap'), fontsize=14, fontweight='bold')

        plt.tight_layout()

        return self._save_figure(fig, save_path)

    def generate_throughput_vs_time(
        self,
        time_data: List[float],
        throughput_data: List[float],
        config: Optional[Dict[str, Any]] = None
    ) -> bytes:
        """
        Generate throughput vs time chart (common for MIMO OTA tests)

        Args:
            time_data: List of time points (seconds)
            throughput_data: List of throughput values (Mbps)
            config: Optional chart configuration

        Returns:
            Bytes of PNG image
        """
        config = config or {}
        data = {'x_data': time_data, 'y_data': throughput_data}

        default_config = {
            'title': 'Throughput vs Time',
            'x_axis': {'label': 'Time (s)'},
            'y_axis': {'label': 'Throughput (Mbps)'},
            'color': '#1f77b4',
            'show_legend': False
        }
        default_config.update(config)

        return self.generate_line_chart(data, default_config)

    def generate_power_vs_frequency(
        self,
        frequency_data: List[float],
        power_data: List[float],
        config: Optional[Dict[str, Any]] = None
    ) -> bytes:
        """
        Generate power vs frequency chart (common for TRP/TIS tests)

        Args:
            frequency_data: List of frequencies (MHz)
            power_data: List of power values (dBm)
            config: Optional chart configuration

        Returns:
            Bytes of PNG image
        """
        config = config or {}
        data = {'categories': [f'{f:.0f}' for f in frequency_data], 'values': power_data}

        default_config = {
            'title': 'TRP/TIS Results',
            'x_axis': {'label': 'Frequency (MHz)'},
            'y_axis': {'label': 'Power (dBm)'},
            'color': '#ff7f0e'
        }
        default_config.update(config)

        return self.generate_bar_chart(data, default_config)

    def generate_time_series_with_anomalies(
        self,
        data: Dict[str, Any],
        config: Dict[str, Any],
        save_path: Optional[str] = None
    ) -> bytes:
        """
        Generate a time series chart with anomaly detection markers.

        Args:
            data: Dictionary containing:
                - timestamps: List of datetime strings
                - values: List of values
                - anomaly_indices: List of indices where anomalies occur
            config: Chart configuration

        Returns:
            Bytes of PNG image
        """
        fig, ax = plt.subplots(figsize=(12, 6))

        timestamps = data.get('timestamps', [])
        values = data.get('values', [])
        anomaly_indices = data.get('anomaly_indices', [])

        # Convert timestamps to datetime if they're strings
        if timestamps and isinstance(timestamps[0], str):
            try:
                timestamps = [datetime.fromisoformat(t.replace('Z', '+00:00')) for t in timestamps]
            except:
                timestamps = list(range(len(values)))

        # Plot main line
        color = config.get('color', self.default_colors[0])
        ax.plot(timestamps, values, color=color, linewidth=2, label=config.get('metric_name', 'Value'))

        # Mark anomalies
        if anomaly_indices:
            anomaly_x = [timestamps[i] for i in anomaly_indices if i < len(timestamps)]
            anomaly_y = [values[i] for i in anomaly_indices if i < len(values)]
            ax.scatter(anomaly_x, anomaly_y, color='red', s=100, marker='x',
                      label='Anomalies', zorder=5, linewidths=2)

        # Add rolling mean if provided
        rolling_mean = data.get('rolling_mean', [])
        if rolling_mean and len(rolling_mean) == len(timestamps):
            ax.plot(timestamps, rolling_mean, color='green', linewidth=1.5,
                   linestyle='--', alpha=0.7, label='Rolling Mean')

        # Set labels and title
        ax.set_xlabel(config.get('x_axis', {}).get('label', 'Time'), fontsize=12)
        ax.set_ylabel(config.get('y_axis', {}).get('label', 'Value'), fontsize=12)
        ax.set_title(config.get('title', 'Time Series with Anomaly Detection'),
                    fontsize=14, fontweight='bold')

        # Rotate x-axis labels for better readability
        plt.xticks(rotation=45, ha='right')

        # Add grid and legend
        ax.grid(True, alpha=0.3)
        ax.legend(loc='best')

        plt.tight_layout()

        return self._save_figure(fig, save_path)

    def generate_statistics_box_plot(
        self,
        data: Dict[str, Any],
        config: Dict[str, Any],
        save_path: Optional[str] = None
    ) -> bytes:
        """
        Generate a box plot for statistics comparison.

        Args:
            data: Dictionary containing:
                - metrics: List of metric names
                - values: Dict of metric_name -> list of values
            config: Chart configuration

        Returns:
            Bytes of PNG image
        """
        fig, ax = plt.subplots(figsize=(12, 6))

        metrics = data.get('metrics', [])
        values_dict = data.get('values', {})

        # Prepare data for box plot
        box_data = []
        labels = []
        for metric in metrics:
            if metric in values_dict and values_dict[metric]:
                box_data.append(values_dict[metric])
                labels.append(metric)

        if not box_data:
            ax.text(0.5, 0.5, 'No data available', ha='center', va='center',
                   transform=ax.transAxes, fontsize=14)
        else:
            bp = ax.boxplot(box_data, labels=labels, patch_artist=True)

            # Color the boxes
            colors = config.get('colors', self.default_colors)
            for i, (box, color) in enumerate(zip(bp['boxes'], colors * (len(bp['boxes']) // len(colors) + 1))):
                box.set_facecolor(color)
                box.set_alpha(0.7)

            # Show means
            if config.get('show_mean', True):
                means = [np.mean(d) for d in box_data]
                ax.scatter(range(1, len(means) + 1), means, color='red',
                          marker='D', s=50, zorder=5, label='Mean')

        # Set labels and title
        ax.set_xlabel(config.get('x_axis', {}).get('label', 'Metric'), fontsize=12)
        ax.set_ylabel(config.get('y_axis', {}).get('label', 'Value'), fontsize=12)
        ax.set_title(config.get('title', 'Statistics Comparison'),
                    fontsize=14, fontweight='bold')

        # Rotate x-axis labels
        plt.xticks(rotation=45, ha='right')

        # Add grid
        ax.grid(True, alpha=0.3, axis='y')
        ax.legend(loc='best')

        plt.tight_layout()

        return self._save_figure(fig, save_path)

    def generate_performance_radar(
        self,
        data: Dict[str, Any],
        config: Dict[str, Any],
        save_path: Optional[str] = None
    ) -> bytes:
        """
        Generate a radar chart for performance benchmarking.

        Args:
            data: Dictionary containing:
                - metrics: List of metric names
                - values: List of values (normalized to 0-100 or percentile)
            config: Chart configuration

        Returns:
            Bytes of PNG image
        """
        metrics = data.get('metrics', [])
        values = data.get('values', [])

        if not metrics or not values:
            fig, ax = plt.subplots(figsize=(8, 8))
            ax.text(0.5, 0.5, 'No data available', ha='center', va='center',
                   transform=ax.transAxes, fontsize=14)
            return self._save_figure(fig, save_path)

        # Number of metrics
        num_metrics = len(metrics)

        # Calculate angles for each metric
        angles = np.linspace(0, 2 * np.pi, num_metrics, endpoint=False).tolist()
        angles += angles[:1]  # Complete the loop

        values = values + values[:1]  # Complete the loop

        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

        # Plot data
        color = config.get('color', self.default_colors[0])
        ax.plot(angles, values, 'o-', linewidth=2, color=color)
        ax.fill(angles, values, alpha=0.25, color=color)

        # Set metric labels
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(metrics, fontsize=10)

        # Set title
        ax.set_title(config.get('title', 'Performance Radar'),
                    fontsize=14, fontweight='bold', pad=20)

        # Set y-axis limits
        ax.set_ylim(0, 100)

        plt.tight_layout()

        return self._save_figure(fig, save_path)

    def generate_comparison_bar(
        self,
        data: Dict[str, Any],
        config: Dict[str, Any],
        save_path: Optional[str] = None
    ) -> bytes:
        """
        Generate a grouped bar chart for comparing metrics across reports.

        Args:
            data: Dictionary containing:
                - metrics: List of metric names
                - means: List of mean values
                - stds: List of standard deviation values (optional)
            config: Chart configuration

        Returns:
            Bytes of PNG image
        """
        fig, ax = plt.subplots(figsize=(12, 6))

        metrics = data.get('metrics', [])
        means = data.get('means', [])
        stds = data.get('stds', [])

        x = np.arange(len(metrics))
        width = 0.6

        # Create bars
        color = config.get('color', self.default_colors[0])
        bars = ax.bar(x, means, width, color=color, alpha=0.8)

        # Add error bars if stds provided
        if stds and len(stds) == len(means):
            ax.errorbar(x, means, yerr=stds, fmt='none', color='black',
                       capsize=5, capthick=1.5)

        # Add value labels on bars
        if config.get('show_values', True):
            for bar, mean in zip(bars, means):
                height = bar.get_height()
                ax.annotate(f'{mean:.2f}',
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           xytext=(0, 3),
                           textcoords="offset points",
                           ha='center', va='bottom', fontsize=9)

        # Set labels and title
        ax.set_xlabel(config.get('x_axis', {}).get('label', 'Metric'), fontsize=12)
        ax.set_ylabel(config.get('y_axis', {}).get('label', 'Value'), fontsize=12)
        ax.set_title(config.get('title', 'Metrics Comparison'),
                    fontsize=14, fontweight='bold')

        ax.set_xticks(x)
        ax.set_xticklabels(metrics, rotation=45, ha='right')

        # Add grid
        ax.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()

        return self._save_figure(fig, save_path)

    def _save_figure(self, fig, save_path: Optional[str] = None) -> bytes:
        """
        Save figure to bytes or file

        Args:
            fig: Matplotlib figure
            save_path: Optional file path to save

        Returns:
            Bytes of PNG image
        """
        try:
            if save_path:
                fig.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"Chart saved to {save_path}")

            # Save to bytes
            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=300, bbox_inches='tight')
            buf.seek(0)
            image_bytes = buf.read()

            # Clean up
            plt.close(fig)
            buf.close()

            return image_bytes

        except Exception as e:
            logger.error(f"Error saving figure: {e}")
            plt.close(fig)
            raise
