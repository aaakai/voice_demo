from __future__ import annotations

from scenarios.scenario_1_normal import scenario as scenario_1_normal
from scenarios.scenario_2_pause_take_floor import scenario as scenario_2_pause_take_floor
from scenarios.scenario_3_user_barge_in import scenario as scenario_3_user_barge_in
from scenarios.scenario_4_early_clarify import scenario as scenario_4_early_clarify
from scenarios.scenario_5_corrective_interrupt import scenario as scenario_5_corrective_interrupt

SCENARIOS = {
    "1": scenario_1_normal,
    "normal": scenario_1_normal,
    "2": scenario_2_pause_take_floor,
    "pause": scenario_2_pause_take_floor,
    "3": scenario_3_user_barge_in,
    "barge": scenario_3_user_barge_in,
    "4": scenario_4_early_clarify,
    "clarify": scenario_4_early_clarify,
    "5": scenario_5_corrective_interrupt,
    "corrective": scenario_5_corrective_interrupt,
}
