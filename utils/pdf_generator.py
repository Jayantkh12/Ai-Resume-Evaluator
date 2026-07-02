import textwrap


def create_text_pdf(title, text):
    lines = build_lines(title, text)
    pages = chunk(lines, 46)
    objects = []

    def add_object(body):
        objects.append(body)
        return len(objects)

    catalog_id = add_object("<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add_object("")
    font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids = []

    for page_lines in pages:
        content = build_page_content(page_lines)
        content_id = add_object(f"<< /Length {len(content.encode('latin-1', errors='replace'))} >>\nstream\n{content}\nendstream")
        page_id = add_object(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        )
        page_ids.append(page_id)

    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {len(page_ids)} >>"
    return assemble_pdf(objects)


def build_lines(title, text):
    lines = [title, ""]
    for raw_line in text.splitlines():
        if not raw_line.strip():
            lines.append("")
            continue
        prefix = "- " if raw_line.strip().startswith("- ") else ""
        content = raw_line.strip()[2:] if prefix else raw_line.strip()
        wrapped = textwrap.wrap(content, width=88) or [""]
        for index, wrapped_line in enumerate(wrapped):
            lines.append((prefix if index == 0 else "  ") + wrapped_line)
    return lines


def build_page_content(lines):
    commands = ["BT", "/F1 11 Tf", "50 752 Td", "14 TL"]
    for line in lines:
        commands.append(f"({escape_pdf_text(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands)


def assemble_pdf(objects):
    output = ["%PDF-1.4\n"]
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(sum(len(part.encode("latin-1", errors="replace")) for part in output))
        output.append(f"{index} 0 obj\n{body}\nendobj\n")

    xref_offset = sum(len(part.encode("latin-1", errors="replace")) for part in output)
    output.append(f"xref\n0 {len(objects) + 1}\n")
    output.append("0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.append(f"{offset:010d} 00000 n \n")
    output.append(
        "trailer\n"
        f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        "startxref\n"
        f"{xref_offset}\n"
        "%%EOF"
    )
    return "".join(output).encode("latin-1", errors="replace")


def escape_pdf_text(value):
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def chunk(items, size):
    return [items[index : index + size] for index in range(0, len(items), size)] or [[]]
