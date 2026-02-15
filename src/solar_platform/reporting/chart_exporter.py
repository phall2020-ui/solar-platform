"""Export Plotly charts to PNG for PDF embedding using kaleido.

Provides a helper to convert a Plotly ``Figure`` to a PNG file and a
cleanup utility that removes temporary chart images after the PDF has
been built.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import TYPE_CHECKING

from solar_platform.services.logging import get_logger

if TYPE_CHECKING:
    import plotly.graph_objects as go

logger = get_logger("reporting.chart_exporter")

# Default directory for temporary chart images
_DEFAULT_TMP_DIR = Path("reports/tmp")


def chart_to_png(
    fig: go.Figure,
    filepath: str | Path,
    width: int = 1200,
    height: int = 600,
    scale: int = 2,
) -> str:
    """Export a Plotly figure to a PNG image.

    Parameters
    ----------
    fig:
        Plotly ``Figure`` instance.
    filepath:
        Destination file path (must end in ``.png``).
    width:
        Image width in pixels (before *scale*).
    height:
        Image height in pixels (before *scale*).
    scale:
        Resolution multiplier (2 = retina-quality).

    Returns
    -------
    str
        Absolute path of the written PNG file.

    Requires
    --------
    ``kaleido`` (already in *requirements.txt*).
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    try:
        fig.write_image(
            str(filepath),
            width=width,
            height=height,
            scale=scale,
            format="png",
        )
        logger.debug("chart_exported", filepath=str(filepath))
    except Exception as exc:
        logger.error("chart_export_failed", filepath=str(filepath), error=str(exc))
        raise

    return str(filepath.resolve())


def cleanup_temp_images(directory: str | Path | None = None) -> int:
    """Remove temporary PNG chart images.

    Parameters
    ----------
    directory:
        Directory to clean. Defaults to ``reports/tmp``.

    Returns
    -------
    int
        Number of files deleted.
    """
    target_dir = Path(directory) if directory else _DEFAULT_TMP_DIR
    if not target_dir.exists():
        return 0

    removed = 0
    for png_file in target_dir.glob("*.png"):
        try:
            png_file.unlink()
            removed += 1
        except OSError as exc:
            logger.warning("cleanup_failed", file=str(png_file), error=str(exc))

    if removed:
        logger.info("temp_images_cleaned", count=removed, directory=str(target_dir))

    return removed
