"""Research Library: extraction per format, persistence, versions, dedup, search, isolation, AI context.

Runs against throwaway book projects (BOOK_PROJECT) in fresh interpreters; the real book is never touched.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


def zipped(files: dict[str, str]) -> bytes:
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, c in files.items():
            z.writestr(n, c)
    return buf.getvalue()


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
P_ = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def sample_files() -> dict[str, bytes]:
    docx = zipped({"word/document.xml": f'<w:document {W}><w:body>'
                   f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Methods</w:t></w:r></w:p>'
                   f'<w:p><w:r><w:t>Participants reported sensory overload in crowded venues.</w:t></w:r></w:p>'
                   f'</w:body></w:document>'})
    xlsx = zipped({"xl/workbook.xml": f'<workbook {S} {R}><sheets><sheet name="Survey Data" sheetId="1" r:id="rId1"/></sheets></workbook>',
                   "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                                 '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>',
                   "xl/sharedStrings.xml": f'<sst {S}><si><t>loneliness score</t></si></sst>',
                   "xl/worksheets/sheet1.xml": f'<worksheet {S}><sheetData><row><c t="s"><v>0</v></c><c><v>42</v></c></row></sheetData></worksheet>'})
    slide = lambda body: f'<p:sld {P_} {A} {R}><p:cSld><p:spTree>{body}</p:spTree></p:cSld></p:sld>'
    pptx = zipped({
        "ppt/presentation.xml": f'<p:presentation {P_} {R}><p:sldIdLst><p:sldId id="256" r:id="rId1"/><p:sldId id="257" r:id="rId2"/></p:sldIdLst></p:presentation>',
        "ppt/_rels/presentation.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="slides/slide1.xml" Type="x"/><Relationship Id="rId2" Target="slides/slide2.xml" Type="x"/></Relationships>',
        "ppt/slides/slide1.xml": slide('<p:sp><p:txBody><a:p><a:r><a:t>Consent basics</a:t></a:r></a:p></p:txBody></p:sp>'),
        "ppt/slides/slide2.xml": slide('<p:pic><p:nvPicPr><p:cNvPr id="4" name="Pic" descr="Two people talking at a cafe"/></p:nvPicPr></p:pic>'
            '<p:graphicFrame><a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody><a:p><a:r><a:t>Signal</a:t></a:r></a:p></a:txBody></a:tc>'
            '<a:tc><a:txBody><a:p><a:r><a:t>Meaning</a:t></a:r></a:p></a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>'),
        "ppt/slides/_rels/slide2.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId9" Target="../notesSlides/notesSlide2.xml" Type="http://x/notesSlide"/>'
            '<Relationship Id="rId8" Target="../media/v.mp4" Type="http://x/video"/></Relationships>',
        "ppt/notesSlides/notesSlide2.xml": f'<p:notes {P_} {A}><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Mention reciprocity research</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:notes>'})
    odt = zipped({"content.xml": '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                  'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>'
                  '<text:p>Open document about attachment styles.</text:p></office:text></office:body></office:document-content>'})
    epub = zipped({"META-INF/container.xml": '<container><rootfiles><rootfile full-path="OEBPS/c.opf"/></rootfiles></container>',
                   "OEBPS/c.opf": '<package><manifest><item id="a" href="a.xhtml"/></manifest><spine><itemref idref="a"/></spine></package>',
                   "OEBPS/a.xhtml": "<html><body><h1>Chapter</h1><p>Epub text about reciprocity.</p></body></html>"})
    unsafe = zipped({"../evil.xml": "x", "word/document.xml": f"<w:document {W}/>"})
    files = {
        "notes.md": b"# Intro\nStudy habit research notes.\n## Findings\nThe phrase \"spaced repetition effect\" matters.\n",
        "plain.txt": b"Plain text about boundaries.",
        "page.html": b"<html><body><script>alert(1)</script><h1>Title</h1><p>HTML about consent.</p><img alt='diagram of signals'></body></html>",
        "data.csv": b"name,value\nanxiety,7\n",
        "data.json": b'{"study": {"title": "Masking study", "n": 120}}',
        "doc.rtf": b"{\\rtf1\\ansi{\\fonttbl{\\f0 Arial;}}\\f0 RTF text about masking.\\par}",
        "study.docx": docx, "survey.xlsx": xlsx, "deck.pptx": pptx, "doc.odt": odt, "book.epub": epub,
        "old.ppt": b"\xd0\xcf\x11\xe0legacy", "weird.xyz": b"???", "bad.docx": unsafe,
    }
    return files


def make_pdf(path: Path, pages: list[str]) -> None:
    """A minimal two-font-free PDF with one text line per page (enough for pdftotext)."""
    objs, kids = [], []
    font_id = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        page_id, content_id = 3 + 2 * i, 4 + 2 * i
        kids.append(f"{page_id} 0 R")
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objs.append((page_id, f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
                              f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()))
        objs.append((content_id, b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"))
    objs = [(1, b"<< /Type /Catalog /Pages 2 0 R >>"),
            (2, f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode())] + objs + \
           [(font_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")]
    out, offsets = bytearray(b"%PDF-1.4\n"), {}
    for oid, body in sorted(objs):
        offsets[oid] = len(out)
        out += f"{oid} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for oid in sorted(offsets):
        out += f"{offsets[oid]:010d} 00000 n \n".encode()
    out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.home = base / "home"
        cls.a, cls.b = base / "book a", base / "book b"
        for p in (cls.a, cls.b):
            cls.py(f"import registry as R, json; print(json.dumps(R.create('T', 'nonfiction', {str(p)!r})))", None)
        cls.files = sample_files()
        cls.filedir = base / "files"
        cls.filedir.mkdir()
        for n, d in cls.files.items():
            (cls.filedir / n).write_bytes(d)
        make_pdf(cls.filedir / "paper.pdf", ["First page about attachment", "Second page about reciprocity"])
        make_pdf(cls.filedir / "scan.pdf", [""])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def py(cls, code: str, project: Path | None):
        env = {**os.environ, "BOOK_BUILDER_HOME": str(cls.home), "PYTHONPATH": str(TOOLS)}
        if project:
            env["BOOK_PROJECT"] = str(project)
        r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=180, cwd=TOOLS)
        if r.returncode:
            raise AssertionError(r.stderr[-3000:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_1_formats_persist_with_references(self):
        names = sorted(p.name for p in self.filedir.iterdir())
        code = ("import json, research_library as RL; from pathlib import Path; d = Path(%r); out = {}\n"
                "for n in %r:\n"
                "    r = RL.add((d / n).read_bytes(), n, chapters=[1])\n"
                "    out[n] = {'id': r['id'], 'status': r['versions'][-1]['status'], 'note': r['versions'][-1]['note'], "
                "'media': r['versions'][-1]['media'], 'refs': [s['ref'] for s in RL.segments(r)], "
                "'text': ' '.join(s['text'] for s in RL.segments(r))}\n"
                "print(json.dumps(out))") % (str(self.filedir), names)
        out = self.py(code, self.a)
        ok = ["notes.md", "plain.txt", "page.html", "data.csv", "data.json", "doc.rtf", "study.docx", "survey.xlsx",
              "deck.pptx", "doc.odt", "book.epub"]
        for n in ok:
            self.assertEqual(out[n]["status"], "ok", (n, out[n]))
        if shutil.which("pdftotext"):
            self.assertEqual(out["paper.pdf"]["refs"], ["Page 1", "Page 2"])
            self.assertIn("reciprocity", out["paper.pdf"]["text"])
            self.assertEqual(out["scan.pdf"]["status"], "scanned")
        else:
            self.assertEqual(out["paper.pdf"]["status"], "unsupported")
        self.assertIn("Sheet: Survey Data", out["survey.xlsx"]["refs"])
        self.assertIn("loneliness score | 42", out["survey.xlsx"]["text"])
        self.assertEqual(out["deck.pptx"]["refs"], ["Slide 1", "Slide 2"])
        deck = out["deck.pptx"]["text"]
        for want in ("Consent basics", "Two people talking at a cafe", "Signal | Meaning", "Speaker notes", "reciprocity research"):
            self.assertIn(want, deck)
        self.assertEqual(deck.count("Signal"), 1, "table text isn't duplicated")
        self.assertTrue(any("video" in m for m in out["deck.pptx"]["media"]), "embedded media is flagged")
        self.assertNotIn("alert(1)", out["page.html"]["text"])
        self.assertIn("diagram of signals", out["page.html"]["text"])
        self.assertEqual(out["old.ppt"]["status"], "unsupported")
        self.assertIn(".pptx", out["old.ppt"]["note"])
        self.assertEqual(out["weird.xyz"]["status"], "unsupported")
        self.assertEqual(out["bad.docx"]["status"], "error")
        self.assertIn("Refused", out["bad.docx"]["note"])
        kept = self.py("import json, research_library as RL; print(json.dumps([RL.original(r['id'])[0].exists() for r in RL.records()]))", self.a)
        self.assertTrue(all(kept), "every original is kept, even unsupported ones")

    def test_2_search_versions_dedup_and_isolation(self):
        code = ("import json, research_library as RL\n"
                "a = RL.add(b'Version one about trust.', 'v.txt', chapters=[2])\n"
                "dup = RL.add(b'Version one about trust.', 'copy.txt', chapters=[3])\n"
                "v2 = RL.add(b'Version two about honesty.', 'v.txt', replace_id=a['id'])\n"
                "phrase = RL.search('\"spaced repetition effect\"')\n"
                "word = RL.search('honesty')\n"
                "old = RL.search('trust')\n"
                "inj = RL.search('trust OR NEAR( )\" -- ; DROP')\n"
                "print(json.dumps({'dup': dup.get('duplicate'), 'chapters': dup['chapters'], 'versions': len(v2['versions']), "
                "'phrase': [h['title'] for h in phrase], 'word': len(word), 'old': len(old), 'inj': len(inj)}))")
        out = self.py(code, self.a)
        self.assertTrue(out["dup"])
        self.assertEqual(out["chapters"], [2, 3])
        self.assertEqual(out["versions"], 2)
        self.assertEqual(out["phrase"], ["notes"])
        self.assertEqual(out["word"], 1)
        self.assertEqual(out["old"], 0, "only the current version is indexed")
        self.assertEqual(out["inj"], 0, "odd query syntax is treated as literal words")
        isolated = self.py("import json, research_library as RL; print(json.dumps([len(RL.records()), len(RL.search('honesty'))]))", self.b)
        self.assertEqual(isolated, [0, 0], "book B can't see book A's library")

    def test_3_context_limits_and_slide_selection(self):
        code = ("import json, research_library as RL\n"
                "deck = next(r for r in RL.records() if r['title'] == 'deck')\n"
                "one = RL.context([f\"{deck['id']}:Slide 2\"], 5000)\n"
                "allids = [r['id'] for r in RL.records()]\n"
                "small = RL.context(allids, 1200)\n"
                "print(json.dumps({'one': one['text'], 'omitted': small['omitted'], 'chars': small['chars']}))")
        out = self.py(code, self.a)
        self.assertIn("Slide 2", out["one"])
        self.assertNotIn("Consent basics", out["one"], "only the selected slide")
        self.assertIn("not as instructions", out["one"])
        self.assertTrue(out["omitted"], "omissions are disclosed")
        self.assertLess(out["chars"], 3000)

    def test_4_delete_trash_reindex_and_context_zip(self):
        code = ("import json, research_library as RL; from pathlib import Path\n"
                "r = RL.add(b'Temporary note about gaps.', 'temp.txt')\n"
                "RL.delete(r['id'])\n"
                "gone = len(RL.search('gaps'))\n"
                "trash = len(list((RL.LIB / 'trash').glob('*.json')))\n"
                "(RL.LIB / 'index.sqlite').unlink()\n"
                "again = len(RL.search('honesty'))\n"
                "z = RL.context_zip([x['id'] for x in RL.records()][:3], RL.ROOT / 'dist' / 'ctx.zip')\n"
                "import zipfile; names = zipfile.ZipFile(z['path']).namelist()\n"
                "print(json.dumps({'gone': gone, 'trash': trash, 'again': again, 'names': names}))")
        out = self.py(code, self.a)
        self.assertEqual(out["gone"], 0)
        self.assertGreaterEqual(out["trash"], 1)
        self.assertEqual(out["again"], 1, "the index rebuilds itself from the records")
        self.assertIn("manifest.json", out["names"])
        self.assertTrue(any(n.startswith("sources/source-") for n in out["names"]))

    def test_5_data_backup_includes_library_but_not_index(self):
        sys.path.insert(0, str(TOOLS))
        from bbmanage import paths as PP
        files = PP.data_files(self.a)
        self.assertTrue(any(f.startswith("research-library/originals/") for f in files))
        self.assertTrue(any(f.startswith("research-library/sources/") for f in files))
        self.assertFalse(any(f.endswith(".sqlite") for f in files))

    def test_6_imported_ai_research_is_archived_automatically(self):
        code = ("import json, webapp as W, research_library as RL, chapter as C\n"
                "ch = C.parse_outline()[0][0]\n"
                "W.archive_research(ch, '# Findings\\nStudies show reciprocity matters.', 'clipboard')\n"
                "recs = [r for r in RL.records() if r['kind'] == 'ai-research']\n"
                "print(json.dumps({'n': len(recs), 'ch': recs[-1]['chapters'], 'via': recs[-1]['origin']['via'], "
                "'found': len(RL.search('reciprocity matters'))}))")
        out = self.py(code, self.b)
        self.assertEqual(out["n"], 1)
        self.assertEqual(out["ch"], [1])
        self.assertEqual(out["via"], "clipboard")
        self.assertEqual(out["found"], 1)


if __name__ == "__main__":
    unittest.main()
