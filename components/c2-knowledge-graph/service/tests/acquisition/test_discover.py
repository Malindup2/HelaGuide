"""Link discovery and scoring, against a fake fetcher: no network."""

import asyncio

import pytest

from app.core.acquisition.discover import Link, discover, extract_links, score_text, wanted
from app.core.acquisition.fetch import FetchResult

START = "https://www.immigration.gov.lk/pages_e.php?id=3"

NAV = """
<ul>
  <li><a href="pages_e.php?id=7">General Information</a></li>
  <li><a href="/pages_e.php?id=9">Overseas   Applications</a></li>
  <li><a href="pages_e.php?id=9#top">Overseas Applications again</a></li>
  <li><a href="pages_s.php?id=7">සිංහල</a></li>
  <li><a href="pages_t.php?id=7">தமிழ்</a></li>
  <li><a href="imageGal_e.php">Photo Gallery</a></li>
  <li><a href="pages_e.php?id=46">Vacancies</a></li>
  <li><a href="/content/files/applications/passport_application.pdf">Application form</a></li>
  <li><a href="https://www.eta.gov.lk/">ETA</a></li>
  <li><a href="https://www.facebook.com/dept">Facebook</a></li>
  <li><a href="mailto:info@immigration.gov.lk">Mail</a></li>
  <li><a href="images/logo.png">logo</a></li>
</ul>
"""


def run(coro):
    return asyncio.run(coro)


class FakeSite:
    def __init__(self, pages: dict[str, tuple[str, str]]):
        self.pages = pages  # url -> (html, text)
        self.calls: list[str] = []

    async def fetch(self, url):
        self.calls.append(url)
        if url not in self.pages:
            return FetchResult(url, False, error="404")
        html, text = self.pages[url]
        return FetchResult(url, True, status=200, html=html, text=text)


# --------------------------------------------------------------------- extraction
def test_links_are_absolute_deduplicated_and_fragment_free():
    links = extract_links(NAV, START)
    urls = [link.url for link in links]
    assert "https://www.immigration.gov.lk/pages_e.php?id=7" in urls
    assert urls.count("https://www.immigration.gov.lk/pages_e.php?id=9") == 1
    assert not any(u.startswith("mailto:") for u in urls)
    assert next(link for link in links if link.url.endswith("id=9")).text == "Overseas Applications"


# ------------------------------------------------------------------------ filtering
@pytest.mark.parametrize("url,keep", [
    ("https://www.immigration.gov.lk/pages_e.php?id=7", True),
    ("https://immigration.gov.lk/pages_e.php?id=7", True),            # same site, no www
    ("https://www.immigration.gov.lk/content/files/applications/passport_application.pdf", True),
    ("https://www.immigration.gov.lk/pages_s.php?id=7", False),       # Sinhala copy
    ("https://www.immigration.gov.lk/pages_t.php?id=7", False),       # Tamil copy
    ("https://www.immigration.gov.lk/imageGal_e.php", False),
    ("https://www.immigration.gov.lk/pages_e.php?id=46&x=vacancies", False),
    ("https://www.immigration.gov.lk/images/logo.png", False),
    ("https://www.eta.gov.lk/", False),                                # a different site
    ("https://www.immigration.gov.lk/pages_e.php?id=3", False),        # the page itself
])
def test_which_links_are_worth_following(url, keep):
    assert wanted(Link(url), START) is keep


# --------------------------------------------------------------------------- scoring
def test_menu_text_does_not_count_as_a_signal():
    menu = ("* [Yellow fever vaccination certificate](https://x.gov.lk/p?id=22)\n"
            "  * [Visa Fees](https://x.gov.lk/p?id=45)\n"
            "![](https://x.gov.lk/logo.png)\n")
    assert score_text(menu).score == 0
    body = menu + "\n1. Original Birth Certificate of the applicant with a photocopy.\n"
    assert score_text(body).has_docs


def test_signals_are_read_from_text():
    s = score_text("Normal Basis - LKR. 10,000.00. Original Birth Certificate with a photocopy.")
    assert s.has_fee and s.has_docs and not s.has_prereq
    assert s.score == 2 and s.flags == "FD-"
    assert score_text("Our vision and mission").score == 0


# ------------------------------------------------------------------------ discovery
def site():
    return FakeSite({
        START: (NAV, ""),
        "https://www.immigration.gov.lk/pages_e.php?id=7": ("<p>info</p>", "Passports are issued by the department."),
        "https://www.immigration.gov.lk/pages_e.php?id=9": ("<p>x</p>", "Fee LKR. 3,500.00. Documents: birth certificate."),
        "https://www.immigration.gov.lk/content/files/applications/passport_application.pdf": ("", "Application form"),
    })


def test_discovery_lists_and_scores_candidates():
    fake = site()
    found = run(discover(START, fake))
    by_url = {c.url.rsplit("/", 1)[-1]: c for c in found}
    assert set(by_url) == {"pages_e.php?id=7", "pages_e.php?id=9", "passport_application.pdf"}
    assert by_url["pages_e.php?id=9"].signals.flags == "FD-"
    assert by_url["pages_e.php?id=7"].signals.score == 0
    assert by_url["passport_application.pdf"].source_type == "pdf"
    assert all(c.discovered_from == START for c in found)


def test_each_url_is_fetched_once_and_screening_can_be_skipped():
    fake = site()
    run(discover(START, fake))
    assert len(fake.calls) == len(set(fake.calls))

    fake2 = site()
    found = run(discover(START, fake2, screen=False))
    assert fake2.calls == [START]  # links only, no candidate was fetched
    assert len(found) == 3 and not any(c.ok for c in found)


def test_limit_and_known_urls_are_respected():
    found = run(discover(START, site(), limit=1))
    assert len(found) == 1

    known = {"https://www.immigration.gov.lk/pages_e.php?id=9"}
    found = run(discover(START, site(), known=known))
    assert all(c.url not in known for c in found)


def test_unreachable_start_page_is_an_error():
    with pytest.raises(RuntimeError, match="start page"):
        run(discover("https://nowhere.gov.lk/", FakeSite({})))


def test_depth_two_follows_one_more_level():
    child = "https://www.immigration.gov.lk/pages_e.php?id=7"
    pages = {
        START: ('<a href="pages_e.php?id=7">A</a>', ""),
        child: ('<a href="pages_e.php?id=70">B</a>', "General passport information"),
        "https://www.immigration.gov.lk/pages_e.php?id=70": ("", "Fee LKR 1,000"),
    }
    one = run(discover(START, FakeSite(dict(pages)), depth=1))
    two = run(discover(START, FakeSite(dict(pages)), depth=2))
    assert len(one) == 1 and len(two) == 2
    assert two[1].discovered_from == child


# ================================ lessons from the first real runs on DRP and RGD
def test_language_folders_and_the_sites_own_gallery_spelling_are_skipped():
    home = "https://www.drp.gov.lk/en/home.php"
    for url in ("https://www.drp.gov.lk/si/home.php", "https://www.drp.gov.lk/ta/home.php",
                "https://www.rgd.gov.lk/web/index.php/si/", "https://www.drp.gov.lk/en/gallary5.php",
                "https://www.drp.gov.lk/en/testgallary.php"):
        assert wanted(Link(url), home) is False, url
    assert wanted(Link("https://www.drp.gov.lk/en/normal.php"), home) is True


def test_backslashes_and_spaces_in_a_path_become_a_fetchable_url():
    links = extract_links(r'<a href="assets\formats\Purawesi Eng.pdf">Charter</a>',
                          "https://www.drp.gov.lk/en/home.php")
    assert links[0].url == "https://www.drp.gov.lk/en/assets/formats/Purawesi%20Eng.pdf"


def test_a_page_whose_text_repeats_an_earlier_candidate_is_marked_a_duplicate():
    start = "https://www.rgd.gov.lk/web/index.php?lang=en"
    html = '<a href="/web/">a</a><a href="/web/index.php/en/">b</a><a href="/web/index.php/en/about">c</a>'
    same = "Registrar General's Department. Birth certificate fee Rs. 100."
    site = FakeSite({
        start: (html, ""),
        "https://www.rgd.gov.lk/web/": ("<p>x</p>", same),
        "https://www.rgd.gov.lk/web/index.php/en/": ("<p>x</p>", same),
        "https://www.rgd.gov.lk/web/index.php/en/about": ("<p>x</p>", "About us"),
    })
    found = run(discover(start, site))
    dup = next(c for c in found if c.duplicate_of)
    assert dup.url == "https://www.rgd.gov.lk/web/index.php/en/"
    assert dup.duplicate_of == "https://www.rgd.gov.lk/web/"
    assert all(c.duplicate_of == "" for c in found if c.url.endswith("/about"))


def test_a_page_that_is_already_a_seed_still_has_its_links_read():
    seed = "https://www.immigration.gov.lk/pages_e.php?id=7"
    form = "https://www.immigration.gov.lk/assets/fees.pdf"
    pages = {
        START: ('<a href="pages_e.php?id=7">Passport</a>', ""),
        seed: (f'<a href="{form}">Fees</a>', "Passport information"),
        form: ("", "Fee LKR 1,000"),
    }
    found = run(discover(START, FakeSite(dict(pages)), depth=2, known={seed}))
    assert [c.url for c in found] == [form]          # the seed itself is not a new candidate
    assert found[0].discovered_from == seed          # but its links were followed


def test_same_site_http_links_are_followed_over_https():
    from app.core.acquisition.discover import _upgrade_scheme

    page = "https://www.immigration.gov.lk/index_e.php"
    got = _upgrade_scheme([Link("http://www.immigration.gov.lk/pages_e.php?id=38", "Appointment"),
                           Link("https://www.immigration.gov.lk/pages_e.php?id=38", "Appointment"),
                           Link("http://other.gov.lk/x", "elsewhere")], page)
    assert [l.url for l in got] == ["https://www.immigration.gov.lk/pages_e.php?id=38",
                                    "http://other.gov.lk/x"]


@pytest.mark.parametrize("url,keep", [
    ("https://www.rgd.gov.lk/web/index.php/en/faqs", True),
    ("https://www.rgd.gov.lk/web/index.php/en/department-report/web/web/web/index.php?lang=en", False),
])
def test_a_repeating_path_is_a_crawler_trap(url, keep):
    assert wanted(Link(url, ""), "https://www.rgd.gov.lk/web/index.php/en/") is keep
