import json

import pytest

from trend_analysis.automation_multifailure import aggregate_numbers

payload = json.dumps({"demo": 1})


@pytest.mark.cosmetic
def test_cosmetic_aggregate_numbers_failure():
    result = aggregate_numbers([1, 2, 3])
    assert result == "1 | 2 | 3", "Intentional cosmetic failure to exercise automation"
