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
