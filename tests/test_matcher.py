from jobradar.core.matcher import matched_keywords, matches
from jobradar.models import Job, MatchRule


def job(title: str) -> Job:
    return Job(
        id="workday:acme:R-1",
        source="workday",
        company="Acme",
        title=title,
        url="https://x/y",
    )


# --- word-boundary awareness (the whole point) ---


def test_single_letter_keyword_needs_boundaries() -> None:
    rule = MatchRule(keywords=("C",))
    assert matches(job("Embedded C Developer"), rule)
    assert not matches(job("C++ Developer"), rule)
    assert not matches(job("Calculus Tutor"), rule)


def test_plus_hash_dot_are_part_of_the_token() -> None:
    assert matches(job("C++ Developer"), MatchRule(keywords=("C++",)))
    assert matches(job("C# Engineer"), MatchRule(keywords=("C#",)))
    assert matches(job("Senior .NET Developer"), MatchRule(keywords=(".NET",)))


def test_keyword_does_not_match_a_longer_word() -> None:
    rule = MatchRule(keywords=("Go",))
    assert matches(job("Go Developer"), rule)
    assert not matches(job("Good Engineer"), rule)
    assert not matches(job("Django Developer"), rule)  # 'go' sits inside


def test_java_does_not_match_javascript() -> None:
    rule = MatchRule(keywords=("Java",))
    assert matches(job("Java Backend Engineer"), rule)
    assert not matches(job("JavaScript Developer"), rule)


def test_adjacent_punctuation_still_matches() -> None:
    rule = MatchRule(keywords=("Go",))
    assert matches(job("Go, Rust & Python Developer"), rule)
    assert matches(job("Developer (Go)"), rule)


# --- case-insensitivity ---


def test_matching_is_case_insensitive() -> None:
    assert matches(job("Senior PYTHON Engineer"), MatchRule(keywords=("python",)))
    assert matches(job("python developer"), MatchRule(keywords=("Python",)))


# --- multi-word keywords ---


def test_multi_word_keyword_allows_flexible_whitespace() -> None:
    rule = MatchRule(keywords=("Machine Learning",))
    assert matches(job("Machine Learning Scientist"), rule)
    assert matches(job("Staff Machine  Learning Engineer"), rule)  # doubled space


# --- matched_keywords: which ones, in order, original casing ---


def test_matched_keywords_returns_hits_in_rule_order() -> None:
    rule = MatchRule(keywords=("Rust", "Go", "C++"))
    assert matched_keywords(job("Go and Rust Systems Engineer"), rule) == ["Rust", "Go"]


def test_matched_keywords_preserves_keyword_casing() -> None:
    rule = MatchRule(keywords=(".NET",))
    assert matched_keywords(job("senior .net developer"), rule) == [".NET"]


def test_matched_keywords_empty_when_nothing_hits() -> None:
    assert matched_keywords(job("Product Manager"), MatchRule(keywords=("Go",))) == []


# --- empty rule = match everything ---


def test_empty_rule_matches_every_job() -> None:
    empty = MatchRule()
    assert matches(job("Anything At All"), empty)
    assert matches(job("Product Manager"), empty)


def test_empty_rule_reports_no_matched_keywords() -> None:
    # It matches (no filter), but there are no keywords to name.
    assert matched_keywords(job("Anything"), MatchRule()) == []
