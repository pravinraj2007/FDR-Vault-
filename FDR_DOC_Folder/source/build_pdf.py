
"""
FDR Vault Documentation PDF Builder
------------------------------------
1. Render HTML to PDF using headless Chrome.
2. Extract actual page numbers for all TOC headings.
3. Update the HTML table of contents.
4. Render the final PDF again.
5. Add PDF metadata and validate the output.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path
from pypdf import PdfReader, PdfWriter


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

HERE = Path(__file__).resolve().parent

SRC = HERE / "FDR_Vault_Project_Documentation.html"
OUT = HERE.parent / "FDR_Vault_Project_Documentation.pdf"
TMP = HERE / "_fdr_vault_build.html"

CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
]

EXPECTED_SECTIONS = 24


# --------------------------------------------------
# CHROME DETECTION
# --------------------------------------------------

def find_chrome():
    for candidate in CHROME_CANDIDATES:
        if candidate.exists():
            return candidate

    chrome = shutil.which("chrome") or shutil.which("chrome.exe")

    if chrome:
        return Path(chrome)

    raise FileNotFoundError(
        "Google Chrome not found. Install Chrome or update CHROME_CANDIDATES."
    )


CHROME = find_chrome()


# --------------------------------------------------
# PDF RENDERING
# --------------------------------------------------

def render(html_path: Path, pdf_path: Path):
    if pdf_path.exists():
        pdf_path.unlink()

    command = [
        str(CHROME),
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--generate-pdf-document-outline",
        "--virtual-time-budget=10000",
        f"--print-to-pdf={pdf_path.resolve()}",
        html_path.resolve().as_uri(),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=180,
    )

    if result.returncode != 0 or not pdf_path.exists():
        raise RuntimeError(
            "Chrome PDF rendering failed:\n"
            + result.stderr[-3000:]
        )

    if pdf_path.stat().st_size == 0:
        raise RuntimeError("Generated PDF is empty.")

    # Validate that the generated file is readable.
    PdfReader(str(pdf_path))


# --------------------------------------------------
# TEXT NORMALIZATION
# --------------------------------------------------

def norm(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


# --------------------------------------------------
# EXTRACT SECTION HEADINGS
# --------------------------------------------------

def extract_headings(html: str):
    pattern = (
        r'<h2 class="sec[^"]*" id="(s\w+)">'
        r'<span class="n">(\w+)</span>([^<]+)</h2>'
    )

    headings = re.findall(pattern, html)

    if len(headings) != EXPECTED_SECTIONS:
        raise ValueError(
            f"Expected {EXPECTED_SECTIONS} sections, "
            f"but found {len(headings)}."
        )

    section_ids = [item[0] for item in headings]

    if len(section_ids) != len(set(section_ids)):
        raise ValueError("Duplicate section IDs found.")

    return headings


# --------------------------------------------------
# FIND REAL PAGE NUMBERS
# --------------------------------------------------

def find_page_numbers(pdf_path: Path, headings):
    reader = PdfReader(str(pdf_path))

    pages = [
        norm(page.extract_text() or "")
        for page in reader.pages
    ]

    found = {}

    for sid, number, title in headings:
        clean_title = title.replace("&amp;", "&")
        key = norm(number + clean_title)

        matches = [
            index + 1
            for index, page_text in enumerate(pages)
            if index >= 2 and key in page_text
        ]

        if not matches:
            raise ValueError(
                f"Heading not found in PDF: {number} {title}"
            )

        found[sid] = matches[0]

    return found


# --------------------------------------------------
# UPDATE TABLE OF CONTENTS
# --------------------------------------------------

def fill_toc(html: str, page_numbers: dict):
    pattern = r'<span class="pg" data-sec="(s\w+)">\d+</span>'

    def replace_page(match):
        section_id = match.group(1)

        if section_id not in page_numbers:
            raise ValueError(
                f"Missing page number for {section_id}"
            )

        return (
            f'<span class="pg" data-sec="{section_id}">'
            f'{page_numbers[section_id]}'
            f'</span>'
        )

    updated, count = re.subn(pattern, replace_page, html)

    if count != EXPECTED_SECTIONS:
        raise ValueError(
            f"Expected {EXPECTED_SECTIONS} TOC entries, "
            f"but updated {count}."
        )

    return updated


# --------------------------------------------------
# ADD PDF METADATA
# --------------------------------------------------

def add_metadata(pdf_path: Path):
    writer = PdfWriter(clone_from=str(pdf_path))

    writer.add_metadata({
        "/Title": "FDR Vault - Complete Project Documentation",
        "/Author": "Team Prime Developers",
        "/Subject": (
            "AICTE Intelligent Regulatory Validation Platform "
            "(AI-IRVP) - Smart India Hackathon 2026"
        ),
        "/Keywords": (
            "FDR Vault, AICTE, Security Deposit, FDR, "
            "Joint Lien, SIH 2026"
        ),
    })

    temp_pdf = pdf_path.with_name("_metadata_final.pdf")

    with open(temp_pdf, "wb") as file:
        writer.write(file)

    temp_pdf.replace(pdf_path)


# --------------------------------------------------
# MAIN BUILD PROCESS
# --------------------------------------------------

def main():

    if not SRC.exists():
        raise FileNotFoundError(
            f"Source HTML not found: {SRC}"
        )

    original_html = SRC.read_text(encoding="utf-8")

    headings = extract_headings(original_html)

    try:
        print("[1/5] Rendering initial PDF...")

        TMP.write_text(original_html, encoding="utf-8")
        render(TMP, OUT)

        print("[2/5] Extracting actual TOC page numbers...")

        page_numbers = find_page_numbers(OUT, headings)

        print("[3/5] Updating table of contents...")

        updated_html = fill_toc(original_html, page_numbers)

        TMP.write_text(updated_html, encoding="utf-8")

        print("[4/5] Rendering final PDF...")

        render(TMP, OUT)

        # Verify the updated TOC against the final PDF.
        final_pages = find_page_numbers(OUT, headings)

        if final_pages != page_numbers:
            raise RuntimeError(
                "TOC page numbers changed after final rendering."
            )

        print("[5/5] Adding PDF metadata...")

        add_metadata(OUT)

        # Update the source only after successful PDF generation.
        SRC.write_text(updated_html, encoding="utf-8")

        reader = PdfReader(str(OUT))

        print("\nBUILD SUCCESSFUL")
        print("------------------------------")
        print("Pages:", len(reader.pages))
        print("PDF Size:", round(OUT.stat().st_size / 1024), "KB")
        print("Outline entries:", len(reader.outline))
        print("Title:", reader.metadata.title)
        print("Author:", reader.metadata.author)
        print("\nTOC PAGE NUMBERS:")

        for sid, number, title in headings:
            print(
                f"{number} {title.strip()} "
                f"-> Page {page_numbers[sid]}"
            )

        print("\nPDF:", OUT)

    finally:
        if TMP.exists():
            TMP.unlink()


if __name__ == "__main__":
    main()
