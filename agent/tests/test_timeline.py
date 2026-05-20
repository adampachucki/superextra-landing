from superextra_agent.timeline import EVENT_TTL_DAYS


def test_activity_events_are_retained_for_past_sessions():
    assert EVENT_TTL_DAYS == 30
