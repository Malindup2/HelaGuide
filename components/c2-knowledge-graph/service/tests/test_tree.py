from app.core.acquisition import tree


def rows(*pairs):
    return [{"url": u, "label": u[-3:], "signals": "FD-", "source_type": "html", "chars": 10,
             "discovered_from": p} for u, p in pairs]


def test_pages_are_kept_under_the_page_they_were_found_on(tmp_path):
    tree.merge(tmp_path, "https://a.lk/", rows(("https://a.lk/x", "https://a.lk/"),
                                                ("https://a.lk/y", "https://a.lk/x")))
    kids = tree.children_of(tree.load(tmp_path)["nodes"])
    assert kids[None] == ["https://a.lk/"]
    assert kids["https://a.lk/"] == ["https://a.lk/x"]
    assert kids["https://a.lk/x"] == ["https://a.lk/y"]


def test_a_later_run_does_not_move_a_page_to_a_different_parent(tmp_path):
    tree.merge(tmp_path, "https://a.lk/", rows(("https://a.lk/x", "https://a.lk/")))
    tree.merge(tmp_path, "https://a.lk/z", rows(("https://a.lk/x", "https://a.lk/z")))
    assert tree.load(tmp_path)["nodes"]["https://a.lk/x"]["parent"] == "https://a.lk/"


def test_a_missing_or_broken_file_is_an_empty_tree(tmp_path):
    assert tree.load(tmp_path) == {"nodes": {}}
    (tmp_path / "tree.json").write_text("{not json", encoding="utf-8")
    assert tree.load(tmp_path) == {"nodes": {}}
