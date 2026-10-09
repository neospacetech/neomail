from neomail.ids import is_ulid, new_ulid, object_ref


def test_ulids_are_crockford_base32_and_time_ordered() -> None:
    first = new_ulid(timestamp_ms=1_700_000_000_000, randomness=bytes(10))
    later = new_ulid(timestamp_ms=1_700_000_000_001, randomness=bytes(10))
    assert first == "01HF7YAT000000000000000000"
    assert is_ulid(first)
    assert first < later
    assert is_ulid(new_ulid())
    assert not is_ulid("01HF7YAT00000000000000000I")


def test_object_refs() -> None:
    assert (
        object_ref("acme", "01ARZ3NDEKTSV4RRFFQ69G5FAV")
        == "neo://acme/o/01ARZ3NDEKTSV4RRFFQ69G5FAV"
    )
