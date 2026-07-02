from pathlib import Path

from jobradar.core.dedup import SeenStore
from jobradar.models import Job


def make_job(id: str) -> Job:
    return Job(
        id=id,
        source="workday",
        company="Acme",
        title="Engineer",
        url="https://x/y",
    )


def test_new_store_is_empty(tmp_path: Path) -> None:
    with SeenStore(tmp_path / "seen.db") as store:
        assert store.known_ids() == set()


def test_filter_new_returns_all_on_first_sight(tmp_path: Path) -> None:
    with SeenStore(tmp_path / "seen.db") as store:
        jobs = [make_job("a"), make_job("b")]
        assert store.filter_new(jobs) == jobs


def test_filter_new_excludes_already_seen(tmp_path: Path) -> None:
    with SeenStore(tmp_path / "seen.db") as store:
        store.filter_new([make_job("a"), make_job("b")])
        result = store.filter_new([make_job("a"), make_job("c")])
        assert [j.id for j in result] == ["c"]


def test_filter_new_dedups_within_a_batch(tmp_path: Path) -> None:
    with SeenStore(tmp_path / "seen.db") as store:
        result = store.filter_new([make_job("a"), make_job("a"), make_job("b")])
        assert [j.id for j in result] == ["a", "b"]


def test_filter_new_preserves_order(tmp_path: Path) -> None:
    with SeenStore(tmp_path / "seen.db") as store:
        result = store.filter_new([make_job("c"), make_job("a"), make_job("b")])
        assert [j.id for j in result] == ["c", "a", "b"]


def test_recorded_ids_become_known(tmp_path: Path) -> None:
    with SeenStore(tmp_path / "seen.db") as store:
        store.filter_new([make_job("a"), make_job("b")])
        assert store.known_ids() == {"a", "b"}


def test_persists_across_reopen(tmp_path: Path) -> None:
    db = tmp_path / "seen.db"
    with SeenStore(db) as store:
        store.filter_new([make_job("a")])
    with SeenStore(db) as store:
        assert store.known_ids() == {"a"}
        result = store.filter_new([make_job("a"), make_job("b")])
        assert [j.id for j in result] == ["b"]


def test_filter_new_on_empty_iterable(tmp_path: Path) -> None:
    with SeenStore(tmp_path / "seen.db") as store:
        assert store.filter_new([]) == []
