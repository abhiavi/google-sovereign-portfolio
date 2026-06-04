# generate_architecture.py - Architecture diagram generator for Track 5
import os
import logging
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diagram_generator")

def draw_diagram(output_path: str = "architecture_diagram.png"):
    logger.info("Initializing canvas for architecture diagram...")
    # Set canvas dimensions (width, height)
    width, height = 1200, 750
    # Create canvas with a clean dark mode slate background
    img = Image.new("RGBA", (width, height), (30, 41, 59, 255)) # slate-800
    draw = ImageDraw.Draw(img)
    
    # Try to load a font, otherwise fall back to default
    try:
        # Load a standard system font
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if not os.path.exists(font_path):
            font_path = "arial.ttf"
        font_title = ImageFont.truetype(font_path, 22)
        font_text = ImageFont.truetype(font_path, 14)
        font_header = ImageFont.truetype(font_path, 28)
    except Exception:
        font_title = font_text = font_header = ImageFont.load_default()
        logger.warning("Using default system font.")

    # Draw diagram header
    draw.text((40, 30), "Track 5: Real-Time Agentic Routing & Data Mesh Architecture", fill=(255, 255, 255, 255), font=font_header)
    draw.text((40, 65), "Leveraging BigQuery Continuous Queries, Pub/Sub, and Active Knowledge Catalog", fill=(148, 163, 184, 255), font=font_text)
    
    # Draw a line separator
    draw.line([(40, 95), (1160, 95)], fill=(71, 85, 105, 255), width=2)
    
    # Draw Architecture Layers
    # We will draw boxes for each step in the data pipeline
    # Coordinates format: [x0, y0, x1, y1]
    
    # 1. Generation Box
    draw.rounded_rectangle([60, 160, 320, 240], radius=8, fill=(14, 116, 144, 255), outline=(34, 211, 238, 255), width=2) # cyan
    draw.text((80, 175), "1. Telco Event Stream", fill=(255, 255, 255, 255), font=font_title)
    draw.text((80, 205), "CDR logs, Signal strengths", fill=(207, 250, 254, 255), font=font_text)
    
    # 2. Ingress (Write API) Box
    draw.rounded_rectangle([60, 300, 320, 380], radius=8, fill=(13, 148, 136, 255), outline=(45, 212, 191, 255), width=2) # teal
    draw.text((80, 315), "2. BQ Storage Write API", fill=(255, 255, 255, 255), font=font_title)
    draw.text((80, 345), "Sub-second streaming buffer", fill=(204, 251, 241, 255), font=font_text)

    # 3. BQ Raw Storage Box
    draw.rounded_rectangle([440, 300, 720, 380], radius=8, fill=(30, 58, 138, 255), outline=(96, 165, 250, 255), width=2) # blue
    draw.text((460, 315), "3. BigQuery Raw Table", fill=(255, 255, 255, 255), font=font_title)
    draw.text((460, 345), "tower_telemetry partition", fill=(219, 234, 254, 255), font=font_text)

    # 4. BQ Continuous Query Box
    draw.rounded_rectangle([440, 440, 720, 540], radius=8, fill=(88, 28, 135, 255), outline=(192, 132, 252, 255), width=2) # purple
    draw.text((460, 455), "4. Continuous Query", fill=(255, 255, 255, 255), font=font_title)
    draw.text((460, 485), "Stateful streaming SQL", fill=(243, 232, 255, 255), font=font_text)
    draw.text((460, 505), "latency: < 300ms", fill=(216, 180, 254, 255), font=font_text)

    # 5. Pub/Sub Broker Box
    draw.rounded_rectangle([840, 440, 1120, 520], radius=8, fill=(180, 83, 9, 255), outline=(251, 191, 36, 255), width=2) # amber/orange
    draw.text((860, 455), "5. GC Pub/Sub Topic", fill=(255, 255, 255, 255), font=font_title)
    draw.text((860, 485), "network-anomalies queue", fill=(254, 243, 199, 255), font=font_text)

    # 6. Autonomous Agents Box
    draw.rounded_rectangle([840, 580, 1120, 680], radius=8, fill=(20, 83, 45, 255), outline=(74, 222, 128, 255), width=2) # green
    draw.text((860, 595), "6. Autonomous AI Agent", fill=(255, 255, 255, 255), font=font_title)
    draw.text((860, 625), "Troubleshoots & dispatches", fill=(220, 252, 231, 255), font=font_text)
    draw.text((860, 645), "self-healing tower API calls", fill=(187, 247, 208, 255), font=font_text)

    # 7. Active Knowledge Catalog (cross-cutting)
    draw.rounded_rectangle([440, 140, 720, 220], radius=8, fill=(124, 45, 18, 255), outline=(251, 146, 60, 255), width=2) # reddish/orange
    draw.text((460, 155), "Knowledge Catalog", fill=(255, 255, 255, 255), font=font_title)
    draw.text((460, 185), "Active metadata and schemas", fill=(255, 237, 213, 255), font=font_text)

    # Draw Connecting Arrows / Lines
    # Step 1 -> Step 2
    draw.line([(190, 240), (190, 300)], fill=(34, 211, 238, 255), width=3)
    draw.polygon([(185, 295), (190, 300), (195, 295)], fill=(34, 211, 238, 255))
    
    # Step 2 -> Step 3
    draw.line([(320, 340), (440, 340)], fill=(45, 212, 191, 255), width=3)
    draw.polygon([(435, 335), (440, 340), (435, 345)], fill=(45, 212, 191, 255))

    # Step 3 -> Step 4
    draw.line([(580, 380), (580, 440)], fill=(96, 165, 250, 255), width=3)
    draw.polygon([(575, 435), (580, 440), (585, 435)], fill=(96, 165, 250, 255))

    # Step 4 -> Step 5
    draw.line([(720, 480), (840, 480)], fill=(192, 132, 252, 255), width=3)
    draw.polygon([(835, 475), (840, 480), (835, 485)], fill=(192, 132, 252, 255))

    # Step 5 -> Step 6
    draw.line([(980, 520), (980, 580)], fill=(251, 191, 36, 255), width=3)
    draw.polygon([(975, 575), (980, 580), (985, 575)], fill=(251, 191, 36, 255))

    # Knowledge Catalog connections (dotted lines representation)
    # KC -> Step 3
    draw.line([(580, 220), (580, 300)], fill=(251, 146, 60, 150), width=2)
    # KC -> Step 6
    draw.line([(720, 180), (980, 180), (980, 580)], fill=(251, 146, 60, 150), width=2)
    
    # Save image
    img.save(output_path)
    logger.info(f"Architecture diagram successfully saved to {output_path}")

if __name__ == "__main__":
    draw_diagram()
