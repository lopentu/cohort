# /// script
# requires-python = ">=3.11"
# dependencies = ["python-pptx", "markdown"]
# ///
"""Build editable slides and the walkthrough from the checked-in presentation source."""
from __future__ import annotations

import argparse
import base64
import html
import json
import shutil
from pathlib import Path

import markdown
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1280, 720


def svg_item(item):
    x, y, w, h = (item.get(k, 0) for k in ("x", "y", "w", "h"))
    if item["kind"] == "image":
        data = base64.b64encode((HERE / item["path"]).read_bytes()).decode()
        return f'<image x="{x}" y="{y}" width="{w}" height="{h}" href="data:image/png;base64,{data}"/>'
    colour = item.get("color", "24384A")
    if item["kind"] == "line":
        return f'<line x1="{x}" y1="{y}" x2="{x+w}" y2="{y+h}" stroke="#{colour}" stroke-width="2" marker-end="url(#arrow)"/>'
    if item["kind"] == "shape":
        shape = item.get("shape", "rect")
        fill = item.get("fill", "FFFFFF")
        common = f'fill="#{fill}" stroke="#{colour}" stroke-width="1.5"'
        if shape == "ellipse":
            return f'<ellipse cx="{x+w/2}" cy="{y+h/2}" rx="{w/2}" ry="{h/2}" {common}/>'
        if shape == "diamond":
            return f'<polygon points="{x+w/2},{y} {x+w},{y+h/2} {x+w/2},{y+h} {x},{y+h/2}" {common}/>'
        if shape == "star":
            import math
            points = []
            for i in range(10):
                radius = 0.5 if i % 2 == 0 else 0.22
                angle = math.pi * i / 5 - math.pi / 2
                points.append(f"{x+w/2+w*radius*math.cos(angle)},{y+h/2+h*radius*math.sin(angle)}")
            return f'<polygon points="{" ".join(points)}" {common}/>'
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" {common}/>'
    return ""


def svg(slide):
    items = []
    for item in slide["items"]:
        if item["kind"] != "text":
            items.append(svg_item(item))
            continue
        x, y, w, h = (item[k] for k in ("x", "y", "w", "h"))
        # foreignObject preserves the same wrapping as the browser proof.
        style = text_style(item)
        items.append(f'<foreignObject x="{x}" y="{y}" width="{w}" height="{h}"><div xmlns="http://www.w3.org/1999/xhtml" style="{style}">{html.escape(item["text"])}</div></foreignObject>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720" role="img" aria-label="{html.escape(slide["title"])}"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10Z" fill="#526778"/></marker></defs><rect width="1280" height="720" fill="white"/>{"".join(items)}</svg>'


def text_style(item):
    return f'font-family:Lato,Microsoft JhengHei,Droid Sans Fallback,sans-serif;font-size:{item["size"]*96/72}px;font-weight:{700 if item.get("bold") else 400};color:#{item.get("color", "24384A")};line-height:1.18;white-space:pre-wrap;overflow-wrap:break-word;'


def add_native(slide, item):
    x, y, w, h = (Inches(item.get(k, 0) / 96) for k in ("x", "y", "w", "h"))
    colour = RGBColor.from_string(item.get("color", "24384A"))
    if item["kind"] == "image":
        slide.shapes.add_picture(str(HERE / item["path"]), x, y, width=w, height=h)
    elif item["kind"] == "line":
        line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x, y, x+w, y+h)
        line.line.color.rgb = colour
        line.line.width = Pt(1.5)
        end = OxmlElement("a:tailEnd")
        end.set("type", "triangle")
        line.line._get_or_add_ln().append(end)
    elif item["kind"] == "shape":
        kind = {"rect": MSO_SHAPE.RECTANGLE, "ellipse": MSO_SHAPE.OVAL, "diamond": MSO_SHAPE.DIAMOND, "star": MSO_SHAPE.STAR_5_POINT}[item.get("shape", "rect")]
        shape = slide.shapes.add_shape(kind, x, y, w, h)
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(item.get("fill", "FFFFFF"))
        shape.line.color.rgb = colour
        shape.line.width = Pt(1)
    else:
        box = slide.shapes.add_textbox(x, y, w, h)
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        for i, text in enumerate(item["text"].split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = text
            p.font.name = "Lato"
            p.font.size = Pt(item["size"])
            p.font.bold = item.get("bold", False)
            p.font.color.rgb = colour
            p.space_before = p.space_after = Pt(0)
            p.line_spacing = 1.18
            for run in p.runs:
                ea = OxmlElement("a:ea")
                ea.set("typeface", "Microsoft JhengHei")
                run._r.get_or_add_rPr().append(ea)


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    slides = json.loads((HERE / "slides.json").read_text())
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(WIDTH / 96), Inches(HEIGHT / 96)
    sections = []
    for i, data in enumerate(slides, 1):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        for item in data["items"]:
            add_native(slide, item)
        slide.notes_slide.notes_text_frame.text = data["notes"]
        content = []
        for item in data["items"]:
            if item["kind"] == "text":
                style = f'left:{item["x"]}px;top:{item["y"]}px;width:{item["w"]}px;height:{item["h"]}px;{text_style(item)}'
                content.append(f'<div class="text" style="{style}">{html.escape(item["text"])}</div>')
        shapes = "".join(svg_item(item) for item in data["items"] if item["kind"] != "text")
        sections.append(f'<section class="slide" id="slide-{i}" aria-label="{html.escape(data["title"])}"><svg viewBox="0 0 1280 720"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10Z" fill="#526778"/></marker></defs>{shapes}</svg>{"".join(content)}</section>')
        if data.get("diagram"):
            folder = output / "diagrams"
            folder.mkdir(exist_ok=True)
            (folder / f'{data["diagram"]}.svg').write_text(svg(data))
    prs.save(output / "cohort-pnc-2026.pptx")
    style = 'body{margin:0;background:#dce2e6}.slide{position:relative;width:1280px;height:720px;margin:20px auto;background:white;overflow:hidden}.slide>svg{position:absolute;inset:0;width:100%;height:100%}.text{position:absolute;box-sizing:border-box}@media print{@page{size:13.333333in 7.5in;margin:0}body{background:white}.slide{margin:0;break-after:page}.slide:last-child{break-after:auto}}'
    (output / "slides-preview.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Cohort · PNC 2026</title><style>'+style+'</style>'+"".join(sections)+'</html>')
    (output / "speaker-notes.md").write_text('# Cohort · speaker notes\n\n'+"\n\n".join(f'## {i}. {s["title"]}\n\n{s["notes"]}' for i, s in enumerate(slides, 1)))
    guide = (HERE / "walkthrough.md").read_text()
    (output / "how-cohort-works.md").write_text(guide)
    body = markdown.markdown(guide, extensions=["tables", "toc"])
    css = 'body{max-width:980px;margin:48px auto;padding:0 26px;color:#24384a;font:18px/1.65 Lato,sans-serif;background:white}h1,h2,h3{line-height:1.2}h2{margin-top:2.3em}img{width:100%;height:auto;border:1px solid #d2dae0}table{border-collapse:collapse;width:100%;font-size:16px}td,th{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #d2dae0}a{color:#126b85}blockquote{border-left:3px solid #126b85;margin-left:0;padding-left:20px}@media print{@page{size:A4;margin:18mm}body{margin:0;padding:0;font-size:11pt}h2,h3{break-after:avoid}tr,blockquote,img{break-inside:avoid}}'
    (output / "how-cohort-works.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cohort: presenter walkthrough</title><style>'+css+'</style>'+body+'</html>')
    for name in ("measurements.json", "method-examples.json", "researcher-review.md", "presenter-cue-card.md", "conjecture-review.md", "slides.json"):
        shutil.copy2(HERE / name, output / name)
    (output / "README.md").write_text('# Current PNC materials\n\nUse `cohort-pnc-2026.pptx` for editable slides, `cohort-pnc-2026.pdf` for a fixed-layout fallback, and `how-cohort-works.html` for the walkthrough. Detailed notes are embedded in PowerPoint and in `speaker-notes.md`.\n\nAll slides form one main sequence following the abstract. Interface diagrams use editable text and shapes, not captured source passages. Source files and slide exports are versioned on the presentation branch.\n\n`researcher-review.md` assesses usefulness and the separate Q3 branches. `measurements.json` records the aggregate vocabulary results used in the slides.\n\nThe HTML/PDF proof is checked locally. PowerPoint must still be opened in the presenting application to check font substitution.\n')
    print(json.dumps({"slides": len(slides), "main": sum(not s.get("appendix", False) for s in slides), "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)
