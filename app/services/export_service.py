import io
import csv
import pandas as pd
from datetime import datetime

# Lazy-import reportlab so a missing PDF dependency never crashes the entire backend
_reportlab_available = False
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    _reportlab_available = True
except ImportError:
    print("[WARN] reportlab not installed - PDF export will be unavailable.")

def generate_forecast_csv(forecast):
    """Generate CSV from forecast data."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Headers
    writer.writerow(["Date", "Predicted Value", "Confidence Lower", "Confidence Upper"])
    
    forecast_data = forecast.forecast_data
    conf_lower = forecast.confidence_lower or []
    conf_upper = forecast.confidence_upper or []
    
    # Map confidence intervals by date for easy lookup
    lower_map = {item["date"]: item["value"] for item in conf_lower}
    upper_map = {item["date"]: item["value"] for item in conf_upper}
    
    for item in forecast_data:
        date = item["date"]
        val = item["value"]
        writer.writerow([
            date,
            val,
            lower_map.get(date, ""),
            upper_map.get(date, "")
        ])
    
    return output.getvalue()

def generate_forecast_pdf(forecast, metrics, insights, chart_base64=None):
    """Generate professional PDF report."""
    if not _reportlab_available:
        raise RuntimeError(
            "PDF export requires 'reportlab'. Install it with: pip install reportlab"
        )
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    normal_style = styles["Normal"]
    
    # Custom styles
    kpi_title_style = ParagraphStyle(
        'KPITitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=5
    )
    kpi_value_style = ParagraphStyle(
        'KPIValue',
        parent=styles['Normal'],
        fontSize=14,
        fontWeight='BOLD',
        textColor=colors.black,
        spaceAfter=15
    )
    
    elements = []
    
    # Title
    elements.append(Paragraph(f"SmartSales AI - Forecast Report", title_style))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", normal_style))
    elements.append(Spacer(1, 0.2 * inch))
    
    # KPI Section
    elements.append(Paragraph("Key Performance Indicators", heading_style))
    
    kpi_data = [
        [
            Paragraph(f"Projected Revenue<br/><b>${forecast.projected_revenue:,.2f}</b>", normal_style),
            Paragraph(f"Growth Rate<br/><b>{forecast.growth_rate}%</b>", normal_style)
        ],
        [
            Paragraph(f"Model Accuracy<br/><b>{forecast.accuracy}%</b>", normal_style),
            Paragraph(f"Top Driver<br/><b>{forecast.top_driver}</b>", normal_style)
        ]
    ]
    
    kpi_table = Table(kpi_data, colWidths=[2.5 * inch, 2.5 * inch])
    kpi_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 0.3 * inch))
    
    # Forecast Details
    elements.append(Paragraph("Model Details", heading_style))
    model_info = [
        ["Model Type", forecast.model_type.upper()],
        ["Aggregation", forecast.aggregation.capitalize()],
        ["Horizon", f"{forecast.horizon_months} Months"],
    ]
    
    # Add metrics if available
    if metrics:
        m = metrics[0] if isinstance(metrics, list) else metrics
        model_info.extend([
            ["MAE", f"{m.mae:.4f}"],
            ["RMSE", f"{m.rmse:.4f}"],
            ["MAPE", f"{m.mape:.2f}%"],
            ["R² Score", f"{m.r2_score:.4f}"]
        ])
        
    model_table = Table(model_info, colWidths=[2 * inch, 3 * inch])
    model_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('BACKGROUND', (0, 0), (0, -1), colors.whitesmoke),
    ]))
    elements.append(model_table)
    elements.append(Spacer(1, 0.3 * inch))
    
    # AI Insights Section
    if insights:
        elements.append(Paragraph("AI Business Insights", heading_style))
        for insight in insights:
            elements.append(Paragraph(f"<b>{insight['title']}</b>", normal_style))
            elements.append(Paragraph(insight['content'], normal_style))
            elements.append(Spacer(1, 0.1 * inch))
            
    # Chart Image
    if chart_base64:
        try:
            import base64
            from reportlab.lib.utils import ImageReader
            
            # Remove header if present (e.g. "data:image/png;base64,")
            if "," in chart_base64:
                chart_base64 = chart_base64.split(",")[1]
                
            img_data = base64.b64decode(chart_base64)
            img_io = io.BytesIO(img_data)
            img = ImageReader(img_io)
            
            elements.append(PageBreak())
            elements.append(Paragraph("Forecast Visualisation", heading_style))
            elements.append(Image(img_io, width=6*inch, height=3.5*inch))
        except Exception as e:
            print(f"Error adding chart to PDF: {e}")
            
    doc.build(elements)
    buffer.seek(0)
    return buffer
