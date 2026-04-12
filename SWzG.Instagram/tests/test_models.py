from swzg_instagram.models.account import AccountInfo, UNAVAILABLE


class TestAccountInfo:
    def test_profile_url_or_default(self) -> None:
        a = AccountInfo(username="testuser")
        assert a.profile_url_or_default() == "https://www.instagram.com/testuser/"

    def test_profile_url_existing(self) -> None:
        a = AccountInfo(username="testuser", profile_url="https://custom.url/")
        assert a.profile_url_or_default() == "https://custom.url/"

    def test_display_value_none(self) -> None:
        a = AccountInfo(username="testuser")
        assert a.display_value(None) == UNAVAILABLE

    def test_display_value_bool_true(self) -> None:
        a = AccountInfo(username="testuser")
        assert a.display_value(True) == "tak"

    def test_display_value_bool_false(self) -> None:
        a = AccountInfo(username="testuser")
        assert a.display_value(False) == "nie"

    def test_display_value_string(self) -> None:
        a = AccountInfo(username="testuser")
        assert a.display_value("hello") == "hello"

    def test_display_value_int(self) -> None:
        a = AccountInfo(username="testuser")
        assert a.display_value(42) == "42"

    def test_to_export_dict_complete(self) -> None:
        a = AccountInfo(
            username="alice",
            full_name="Alice",
            bio="hi",
            has_chat_history=True,
            chat_count=10,
            last_chat_date="2025-01-01",
            source_list="following",
        )
        d = a.to_export_dict()
        assert d["username"] == "alice"
        assert d["full_name"] == "Alice"
        assert d["has_chat_history"] == "tak"
        assert d["chat_count"] == "10"
        assert d["profile_url"] == "https://www.instagram.com/alice/"

    def test_to_export_dict_missing_values(self) -> None:
        a = AccountInfo(username="bob")
        d = a.to_export_dict()
        assert d["full_name"] == UNAVAILABLE
        assert d["bio"] == UNAVAILABLE
        assert d["has_chat_history"] == UNAVAILABLE
