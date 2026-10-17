import json

import pytest
from tools import agy_judge_replay as replay
from tools.agy_pilot import ModelCall

MAPS = {
    "a": {"A": "m1", "B": "m2", "C": "m3"},
    "b": {"A": "m2", "B": "m3", "C": "m1"},
    "c": {"A": "m3", "B": "m1", "C": "m2"},
}


def _experiment(tmp_path):
    (tmp_path / "eval-maps.json").write_text(json.dumps(MAPS))
    outs = {
        "a": {"A": 8, "B": 5, "C": 2},
        "b": {"A": 5, "B": 2, "C": 8},
        "c": {"A": 2, "B": 8, "C": 5},
    }
    for judge, scores in outs.items():
        (tmp_path / f"eval-prompt-{judge}.txt").write_text(f"prompt for {judge}")
        (tmp_path / f"eval-out-{judge}.txt").write_text(
            "noise\n" + json.dumps({"scores": scores}) + "\n"
        )
    return replay.load_experiment(tmp_path)


def test_parse_scores_takes_the_last_scores_object_and_ignores_others():
    text = 'x {"foo": 1} y {"scores": {"A": 1}} z {"scores": {"A": 4, "B": "6"}}'
    assert replay.parse_scores(text) == {"A": 4.0, "B": 6.0}
    assert replay.parse_scores("no json") is None


def test_letters_map_to_members_per_judge(tmp_path):
    experiment = _experiment(tmp_path)
    assert experiment["real"]["a"] == {"m1": 8.0, "m2": 5.0, "m3": 2.0}
    assert experiment["real"]["b"] == {"m2": 5.0, "m3": 2.0, "m1": 8.0}


def test_a_candidate_matching_consensus_has_zero_error_and_perfect_rank(tmp_path):
    experiment = _experiment(tmp_path)

    def backend(prompt):
        return ModelCall(
            text=json.dumps({"scores": {"A": 8, "B": 5, "C": 2}}), tokens_in=10, tokens_out=5
        )

    row = replay.replay_experiment(experiment, backend, prompt_judge="a")
    assert row["usable"] and row["candidate_mae"] == 0 and row["candidate_rank_corr"] == 1
    assert row["real_judges_mae_mean"] == 0 and row["real_judges"] == 3


def test_an_inverted_candidate_has_large_error_and_negative_rank(tmp_path):
    experiment = _experiment(tmp_path)

    def backend(prompt):
        return ModelCall(text=json.dumps({"scores": {"A": 2, "B": 5, "C": 8}}))

    row = replay.replay_experiment(experiment, backend, prompt_judge="a")
    assert row["candidate_mae"] > 3 and row["candidate_rank_corr"] == -1


def test_empty_or_unparseable_candidate_is_unusable_not_a_score(tmp_path):
    experiment = _experiment(tmp_path)
    empty = replay.replay_experiment(experiment, lambda p: ModelCall(text="", error="empty"), "a")
    junk = replay.replay_experiment(experiment, lambda p: ModelCall(text="nope"), "a")
    assert empty["usable"] is False and junk["usable"] is False
    assert replay.summarise([empty, junk])["candidate_mae_mean"] is None


def test_fewer_than_three_real_judges_is_not_replayable(tmp_path):
    experiment = _experiment(tmp_path)
    experiment["real"].pop("c")
    row = replay.replay_experiment(experiment, lambda p: ModelCall(text="{}"), "a")
    assert row["usable"] is False


@pytest.mark.parametrize(
    "scores",
    [
        {"A": 8},
        {"X": 8},
        {"A": 8, "B": 5, "C": 2, "X": 8},
        {"A": float("nan"), "B": 5, "C": 2},
        {"A": 8, "B": float("inf"), "C": 2},
    ],
    ids=["partial", "unknown", "extra", "nan", "infinite"],
)
def test_incomplete_unknown_or_nonfinite_scores_do_not_count_as_usable(tmp_path, scores):
    experiment = _experiment(tmp_path)
    row = replay.replay_experiment(
        experiment,
        lambda prompt: ModelCall(text=json.dumps({"scores": scores}), tokens_in=10),
        "a",
    )
    assert row["usable"] is False
    assert row["tokens_in"] == 10
    summary = replay.summarise([row])
    assert summary["usable"] == 0
    assert summary["candidate_mae_mean"] is None
