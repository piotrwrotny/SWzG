from swzg_instagram.cli.display import print_results_summary, print_preview
from swzg_instagram.models.results import ActionResult, ActionStatus


class TestDisplay:
    def test_print_preview(self, capsys) -> None:
        print_preview(["alice", "bob"], "Test")
        captured = capsys.readouterr()
        assert "alice" in captured.out
        assert "bob" in captured.out
        assert "Liczba kont: 2" in captured.out

    def test_print_results_summary_empty(self, capsys) -> None:
        print_results_summary([])
        captured = capsys.readouterr()
        assert "Brak wyników" in captured.out

    def test_print_results_summary_counts(self, capsys) -> None:
        results = [
            ActionResult(username="alice", status=ActionStatus.SUCCESS),
            ActionResult(username="bob", status=ActionStatus.FAILED, message="error"),
            ActionResult(username="charlie", status=ActionStatus.SUCCESS),
        ]
        print_results_summary(results)
        captured = capsys.readouterr()
        assert "Sukces:    2" in captured.out
        assert "Błąd:      1" in captured.out
        assert "bob" in captured.out
