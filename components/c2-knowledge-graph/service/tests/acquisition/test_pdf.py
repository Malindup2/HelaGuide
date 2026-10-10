"""PDF acquisition with no network: URL routing, text extraction, archiving, monitoring."""

import asyncio

from app.core.acquisition.fetch import FetchResult
from app.core.acquisition.fingerprint import ChangeKind
from app.core.acquisition.monitor import JsonlRunLog, run_pass
from app.core.acquisition.pdf import PdfAwareFetcher, PdfFetcher, is_pdf_url, pdf_to_text
from app.core.acquisition.seeds import Seed
from app.core.acquisition.store import SnapshotStore


def make_pdf(line: str) -> bytes:
    """A one-page PDF with a text layer, built by hand so the test needs no PDF library."""
    stream = f"BT /F1 12 Tf 72 720 Td ({line}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return out


def run(coro):
    return asyncio.run(coro)


def downloader(status=200, content_type="application/pdf", data=b""):
    async def get(url):
        return status, content_type, data

    return get


# ------------------------------------------------------------------------ routing
def test_pdf_urls_are_recognised_by_path_not_query():
    assert is_pdf_url("https://www.immigration.gov.lk/content/files/applications/passport_application.pdf")
    assert is_pdf_url("https://a.gov.lk/Form.PDF")
    assert not is_pdf_url("https://a.gov.lk/pages_e.php?id=8")
    assert not is_pdf_url("https://a.gov.lk/page.html?file=x.pdf")


def test_router_sends_pdfs_and_pages_to_the_right_fetcher():
    seen = []

    class Tag:
        def __init__(self, name):
            self.name = name

        async def fetch(self, url):
            seen.append((self.name, url))
            return FetchResult(url, True)

    router = PdfAwareFetcher(Tag("page"), Tag("pdf"))
    run(router.fetch("https://a.gov.lk/form.pdf"))
    run(router.fetch("https://a.gov.lk/pages_e.php?id=8"))
    assert seen == [("pdf", "https://a.gov.lk/form.pdf"), ("page", "https://a.gov.lk/pages_e.php?id=8")]


# ------------------------------------------------------------------------- reading
def test_text_layer_is_read_into_markdown():
    text = pdf_to_text(make_pdf("Normal Basis - LKR. 10,000.00"))
    assert text.startswith("## Page 1")
    assert "Normal Basis - LKR. 10,000.00" in text


def test_fetcher_returns_text_bytes_and_source_type():
    data = make_pdf("Urgent Basis - LKR. 20,000.00")
    result = run(PdfFetcher(downloader(data=data)).fetch("https://a.gov.lk/form.pdf"))
    assert result.ok and result.source_type == "pdf"
    assert result.content == data and result.html == ""
    assert "LKR. 20,000.00" in result.text


def test_non_pdf_body_is_a_failure_not_a_crash():
    result = run(PdfFetcher(downloader(content_type="text/html", data=b"<html></html>"))
                 .fetch("https://a.gov.lk/form.pdf"))
    assert not result.ok and "not a pdf" in result.error


def test_download_error_is_reported_per_page():
    async def boom(url):
        raise TimeoutError("slow")

    result = run(PdfFetcher(boom).fetch("https://a.gov.lk/form.pdf"))
    assert not result.ok and "TimeoutError" in result.error


# ----------------------------------------------------------------------- monitoring
def test_pdf_goes_through_a_pass_and_is_archived_as_pdf(tmp_path):
    url = "https://a.gov.lk/form.pdf"
    seed = Seed(url=url, service="svc:passport", agency="Immigration")
    store, log = SnapshotStore(tmp_path), JsonlRunLog(tmp_path)
    fetcher = PdfFetcher(downloader(data=make_pdf("Normal Basis - LKR. 10,000.00")))

    first = run(run_pass([seed], fetcher, store, log))
    assert first.pages[0].kind is ChangeKind.NEW
    assert first.pages[0].source_type == "pdf"
    day = next((tmp_path / "archive").iterdir())
    assert sorted(p.suffix for p in day.iterdir()) == [".md", ".pdf"]

    second = run(run_pass([seed], fetcher, store, log))
    assert second.pages[0].kind is ChangeKind.UNCHANGED


def test_changed_pdf_text_is_content_changed(tmp_path):
    url = "https://a.gov.lk/form.pdf"
    seed = Seed(url=url, service="svc:passport", agency="Immigration")
    store, log = SnapshotStore(tmp_path), JsonlRunLog(tmp_path)

    run(run_pass([seed], PdfFetcher(downloader(data=make_pdf("Normal Basis - LKR. 10,000.00"))), store, log))
    after = run(run_pass([seed], PdfFetcher(downloader(data=make_pdf("Normal Basis - LKR. 11,000.00"))),
                         store, log))
    assert after.pages[0].kind is ChangeKind.CONTENT_CHANGED
