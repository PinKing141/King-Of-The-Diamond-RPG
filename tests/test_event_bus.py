from core.event_bus import EventBus


def test_event_bus_invokes_subscriber():
    bus = EventBus()
    received = []

    def handler(payload):
        received.append(payload)

    bus.subscribe("TEST_EVENT", handler)
    bus.publish("TEST_EVENT", {"value": 1})

    assert received == [{"value": 1}]


def test_event_bus_preserves_payload_data():
    bus = EventBus()
    payload = {"pitcher": "Furuya"}
    captured = []

    bus.subscribe("DATA", lambda data: captured.append(data))
    bus.publish("DATA", payload)

    assert captured[0]["pitcher"] == "Furuya"