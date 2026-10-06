import math

from pipeline import plotstyle


def test_synthetic_titles_are_labelled() -> None:
    assert plotstyle.label("Bias", synthetic=False) == "Bias"
    assert plotstyle.label("Bias", synthetic=True).startswith("SYNTHETIC")


def test_stream_colours_are_distinct_and_fixed() -> None:
    assert plotstyle.CLASSICAL != plotstyle.QUANTUM


def test_format_p_never_shows_zero() -> None:
    assert plotstyle.format_p(0.0183) == "= 0.018"
    assert plotstyle.format_p(0.0) == "< 1e-300"
    assert plotstyle.format_p(math.nan) == "= n/a"


def test_banner_and_table() -> None:
    assert plotstyle.SYNTHETIC_LABEL in plotstyle.banner_html()
    assert plotstyle.markdown_table(["a", "b"], [(1, 2)]) == "| a | b |\n|---|---|\n| 1 | 2 |"
