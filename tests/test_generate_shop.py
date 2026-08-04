from generate_shop import render, build_workshop


def test_render_contains_parts_and_gen(root):
    html = render(root)
    # Title (may be literal or unicode-escaped)
    assert "\u96f6\u4ef6\u6742\u8d23\u94fa" in html or "零件杂货铺" in html
    # Part names come from JSON payload (always literal)
    assert "requests\u5e93\u8c03\u7528\u6a21\u677f" in html or "requests库调用模板" in html
    # Generation name from JSON
    assert "周报汇总助手" in html
    # Nav tab labels
    assert "\u8d27\u67b6\u89c6\u56fe" in html or "货架视图" in html
    assert "\u751f\u6210\u8bb0\u5f55" in html or "生成记录" in html
    # Data injection method (new: application/json script tag)
    assert 'id="__data"' in html or "window.__SHOP_DATA__" in html


def test_render_stats(root):
    data = build_workshop(root)
    assert data["stats"]["parts"] == 23  # initial parts only (no fill_test_data in test fixtures)
    assert data["stats"]["generations"] == 1


def test_render_structure_markers(root):
    html = render(root)
    assert 'id="shelf"' in html
    assert 'id="gens"' in html
    assert "showDetail" in html


def test_shop_js_syntax_valid(root):
    """Guard: the embedded IIFE must be syntactically valid JavaScript.

    A blank/broken page ships whenever the generated <script> fails to parse
    at all — e.g. a missing closing quote, a single-quote colliding with an
    inline onclick handler, or an undeclared variable under 'use strict'.
    node --check catches these at parse time. Without this guard such
    regressions pass pytest yet render nothing in the browser (the whole IIFE
    silently dies, so try/catch never even runs).
    """
    import re, shutil, subprocess, tempfile, os
    html = render(root)
    m = re.search(r"<script>([\s\S]*?)</script>", html)
    assert m, "no IIFE <script> block found in generated HTML"
    js = m.group(1)
    node = shutil.which("node")
    if node is None:
        import pytest
        pytest.skip("node not installed; cannot syntax-check embedded JS")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
        path = f.name
    try:
        r = subprocess.run([node, "--check", path], capture_output=True, text=True)
        assert r.returncode == 0, f"Embedded JS has a syntax error:\n{r.stderr}"
    finally:
        os.unlink(path)
