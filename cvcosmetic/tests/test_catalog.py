from app.catalog import _score_match, find_by_text, rebuild_catalog


def test_score_match_prefers_similar_title():
    query = "аква крем для лица чистая линия идеальная кожа 50 мл"
    good = "аква крем для лица чистая линия идеальная кожа мгновенная матовость 50 мл"
    bad = "шампунь для волос другой бренд 400 мл"

    assert _score_match(query, good) > _score_match(query, bad)


def test_catalog_lookup_finds_known_product():
    rows = rebuild_catalog()
    assert rows > 0

    query = "ЧИСТАЯ ЛИНИЯ аква-крем для лица 50 мл"
    match = find_by_text(query)

    assert match is not None
    assert "ЧИСТАЯ ЛИНИЯ" in match.title
    assert match.composition


def test_catalog_lookup_handles_noisy_ocr_text():
    rows = rebuild_catalog()
    assert rows > 0

    noisy_ocr = (
        "ЧМСТАЯ НОВАЯ ФОРНУЛА ЛИНИЯ ИДЕАЛЬНАЯ КОЖА МГНОВЕННАЯ МАТОВОСТЬ "
        "АКВА-КРЕМ Для лИЦа 12 чаСОВ без жирНОГО блеска ЦИНК ПАНТЕНОЛ"
    )
    match = find_by_text(noisy_ocr)

    assert match is not None
    assert "ЧИСТАЯ ЛИНИЯ" in match.title
    assert match.score >= 0.38
    assert match.matched_tokens > 0


def test_catalog_lookup_brand_lock_carbon_theory():
    rows = rebuild_catalog()
    assert rows > 0

    noisy_ocr = (
        "Carbon Theory LABS Anti-Breakout Facial Moisturiser Vitamin "
        "Iea Tree 0il Cranbery Exlract Vogan Cruelly Free NET WT 3.5floZ10DML"
    )
    match = find_by_text(noisy_ocr)

    assert match is not None
    assert match.brand == "CARBON THEORY"
    assert "ANTI-BREAKOUT" in match.title


def test_catalog_lookup_axisy_spaced_brand_and_common_words():
    rows = rebuild_catalog()
    assert rows > 0

    noisy_ocr = (
        "Dark Spot Correcting Glow Cream A X I S -Y 5OmL"
    )
    match = find_by_text(noisy_ocr)

    assert match is not None
    assert "AXIS-Y" in match.title
    assert "Крем для лица" in match.title
