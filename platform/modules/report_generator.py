"""
PDF Report Generator for Monthly Reporting.
Uses ReportLab to generate professional, branded PDF reports.
"""
import io
from datetime import datetime
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from unified_config import config


class PDFReportGenerator:
    """Generates professional PDF reports."""
    
    def __init__(self, title="Monthly Executive Report", subtitle="", landscape_mode=False):
        self.buffer = io.BytesIO()
        self.pagesize = landscape(A4) if landscape_mode else A4
        self.doc = SimpleDocTemplate(
            self.buffer,
            pagesize=self.pagesize,
            rightMargin=15*mm,
            leftMargin=15*mm,
            topMargin=15*mm,
            bottomMargin=15*mm
        )
        self.elements = []
        self.styles = getSampleStyleSheet()
        self._setup_styles()
        
        # Add Title Page
        self.add_title_page(title, subtitle)
        
    def _setup_styles(self):
        """Define custom styles based on brand colors."""
        brand_primary = config.BRAND_COLORS['primary']
        
        # Custom Title
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Title'],
            fontSize=24,
            leading=30,
            textColor=colors.HexColor(brand_primary),
            alignment=TA_CENTER,
            spaceAfter=20
        ))
        
        # Custom Heading
        self.styles.add(ParagraphStyle(
            name='ReportHeading',
            parent=self.styles['Heading2'],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor(brand_primary),
            spaceBefore=15,
            spaceAfter=10,
            borderPadding=5,
            borderWidth=0,
            frame='bottom',
            borderColor=colors.HexColor(config.BRAND_COLORS['secondary'])
        ))
        
        # Custom Normal
        self.styles.add(ParagraphStyle(
            name='ReportNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            leading=14,
            alignment=TA_LEFT
        ))

    def add_title_page(self, title, subtitle):
        """Add a professional title page."""
        self.elements.append(Spacer(1, 2*inch))
        self.elements.append(Paragraph(title, self.styles['ReportTitle']))
        if subtitle:
            self.elements.append(Paragraph(subtitle, self.styles['Heading3']))
        
        self.elements.append(Spacer(1, 1*inch))
        
        # Add Date
        date_str = datetime.now().strftime("%d %B %Y")
        self.elements.append(Paragraph(f"Generated on: {date_str}", self.styles['Normal']))
        
        self.elements.append(PageBreak())

    def add_section_header(self, text):
        """Add a section header."""
        self.elements.append(Paragraph(text, self.styles['ReportHeading']))

    def add_text(self, text):
        """Add normal text."""
        self.elements.append(Paragraph(text, self.styles['ReportNormal']))
        self.elements.append(Spacer(1, 0.1*inch))

    def add_table(self, df: pd.DataFrame, title=None, col_widths=None):
        """Add a pandas dataframe as a table."""
        if title:
            self.elements.append(Paragraph(title, self.styles['Heading4']))
            
        data = [df.columns.tolist()] + df.values.tolist()
        
        # Format data: Round floats
        formatted_data = []
        for row in data:
            new_row = []
            for item in row:
                if isinstance(item, float):
                    new_row.append(f"{item:.2f}")
                else:
                    new_row.append(str(item))
            formatted_data.append(new_row)
            
        t = Table(formatted_data, colWidths=col_widths)
        
        # Style
        brand_primary = config.BRAND_COLORS['primary']
        _brand_light = config.BRAND_COLORS['background'] # Using lighter tone if possible, else light grey
        
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(brand_primary)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.Color(0.9, 0.9, 0.9)),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
        ])
        t.setStyle(style)
        
        self.elements.append(t)
        self.elements.append(Spacer(1, 0.2*inch))

    def add_plot(self, fig, width=6*inch, height=4*inch):
        """Add a matplotlib or plotly figure."""
        # Convert Plotly to Image bytes if possible (requires kaleido), else skip
        # For simplicity, assume Matplotlib or handle conversion outside.
        # If passed a BytesIO or path, use it.
        
        img_buffer = None
        
        if isinstance(fig, (str, io.BytesIO)):
            img_buffer = fig
        elif hasattr(fig, 'write_image'): # Plotly
            # Try converting to image bytes
            try:
                img_bytes = fig.to_image(format="png", width=1200, height=800, scale=2)
                img_buffer = io.BytesIO(img_bytes)
            except Exception:
                # Fallback: Can't render plotly easily without kaleido
                return
        elif hasattr(fig, 'savefig'): # Matplotlib
            img_buffer = io.BytesIO()
            fig.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
            img_buffer.seek(0)
            
        if img_buffer:
            img = Image(img_buffer, width=width, height=height)
            self.elements.append(img)
            self.elements.append(Spacer(1, 0.2*inch))

    def add_image_from_bytes(self, image_bytes: bytes, width=6*inch, height=4*inch, caption=None):
        """Add an image from PNG bytes."""
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Image as RLImage

        if image_bytes:
            img_buffer = io.BytesIO(image_bytes)
            img = RLImage(img_buffer, width=width, height=height)
            self.elements.append(img)

            if caption:
                caption_style = ParagraphStyle(
                    'Caption',
                    parent=self.styles['Normal'],
                    fontSize=9,
                    alignment=TA_CENTER,
                    textColor=colors.grey
                )
                self.elements.append(Paragraph(caption, caption_style))

            self.elements.append(Spacer(1, 0.2*inch))

    def add_kpi_section(self, kpis: dict):
        """Add a section of KPI metrics."""
        # kpis format: {'label1': 'value1', 'label2': 'value2', ...}

        if not kpis:
            return

        # Convert dict to table data
        data = []
        kpi_items = list(kpis.items())

        # Create rows of up to 4 KPIs each
        for i in range(0, len(kpi_items), 4):
            row_items = kpi_items[i:i+4]
            labels = [item[0] for item in row_items]
            values = [str(item[1]) for item in row_items]

            data.append(labels)
            data.append(values)

        if not data:
            return

        # Calculate column width based on number of columns
        num_cols = min(len(kpi_items), 4)
        col_width = (self.pagesize[0] - 2*15*mm) / num_cols

        t = Table(data, colWidths=[col_width] * num_cols)

        style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTSIZE', (0, 1), (-1, 1), 14),
            ('BACKGROUND', (0, 0), (-1, -1), colors.Color(0.95, 0.95, 0.95)),
            ('GRID', (0, 0), (-1, -1), 1, colors.Color(0.8, 0.8, 0.8)),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ])
        t.setStyle(style)

        self.elements.append(t)
        self.elements.append(Spacer(1, 0.2*inch))

    def add_report_item(self, item):
        """
        Add a ReportItem to the PDF.
        Universal entry point that routes based on item type.
        """

        # Add section header with source page
        header_text = f"{item.title}"
        if item.source_page:
            header_text += f" <i>(Source: {item.source_page})</i>"

        self.add_section_header(header_text)

        # Add description if present
        if item.description:
            self.add_text(item.description)

        # Add content based on type
        if item.item_type == 'chart':
            img_bytes = item.image_bytes
            if not img_bytes and item.image_path:
                try:
                    img_bytes = Path(item.image_path).read_bytes()
                except Exception:
                    img_bytes = None

            if img_bytes:
                self.add_image_from_bytes(
                    img_bytes,
                    width=item.width_inches*inch,
                    height=item.height_inches*inch
                )

        elif item.item_type == 'table':
            df = item.dataframe
            if df is None and item.data_path:
                try:
                    df = pd.read_csv(item.data_path)
                except Exception:
                    df = None

            if df is not None:
                self.add_table(df, title=None)  # Title already added

        elif item.item_type == 'kpi' and item.kpi_data:
            self.add_kpi_section(item.kpi_data)

        elif item.item_type == 'text' and item.text_content:
            self.add_text(item.text_content)

        # Add spacer between items
        self.elements.append(Spacer(1, 0.3*inch))

    def generate(self) -> bytes:
        """Build PDF and return bytes."""
        self.doc.build(self.elements)
        self.buffer.seek(0)
        return self.buffer.getvalue()
