from sam_worker.session import route_session_kind


def test_room_prefix_routes_moderator_and_intake() -> None:
    assert route_session_kind(surface="portal", room_name="mod-abc") == "moderator"
    assert route_session_kind(surface="portal", room_name="demo-xyz") == "intake"
    assert route_session_kind(surface="portal", room_name="intake-1") == "intake"
    assert route_session_kind(surface="phone", room_name="samuel-dial-abc") == "intake"