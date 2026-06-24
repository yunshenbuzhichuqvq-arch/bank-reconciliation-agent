from faker import Faker

from scripts.mock_narratives import AMBIGUOUS, COLLOQUIAL, FORMAL, sample_narrative


def test_narrative_tiers_have_enough_entries() -> None:
    assert len(FORMAL) >= 10
    assert len(COLLOQUIAL) >= 10
    assert len(AMBIGUOUS) >= 10


def test_sample_narrative_returns_value_from_requested_tier() -> None:
    faker = Faker("zh_CN")
    faker.seed_instance(20260624)

    assert sample_narrative("formal", faker) in FORMAL
    assert sample_narrative("colloquial", faker) in COLLOQUIAL
    assert sample_narrative("ambiguous", faker) in AMBIGUOUS


def test_sample_narrative_is_deterministic_for_same_seed() -> None:
    first = Faker("zh_CN")
    second = Faker("zh_CN")
    first.seed_instance(20260624)
    second.seed_instance(20260624)

    assert sample_narrative("formal", first) == sample_narrative("formal", second)
    assert sample_narrative("colloquial", first) == sample_narrative("colloquial", second)
    assert sample_narrative("ambiguous", first) == sample_narrative("ambiguous", second)
