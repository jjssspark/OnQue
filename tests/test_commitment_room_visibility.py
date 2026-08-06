"""비공개 채팅방에서 뽑은 약속이 그 방 멤버가 아닌 그룹원에게 새지 않는지 검증한다.

채팅방은 그룹 전원에게 공개되지 않는다(main.py:588 _require_room_access는
ChatRoomMember를 요구한다). 하지만 스윕은 그룹의 모든 방을 훑고
Commitment.evidence에 대화 원문을 그대로 저장한 뒤 GET /api/v1/commitments가
그룹 멤버 전원에게 내려준다 — 방 멤버십으로 다시 걸러야 한다.

가시성은 Commitment.room_id로 직접 판정한다(source_id로 chat_messages를
역참조하던 예전 방식은 사라졌다 — SQLite에서 메시지 id가 재사용될 수 있어
엉뚱한 방 멤버에게 새는 latent bug가 있었다). 방이 삭제되면
main.py._delete_room_cascade가 room_id를 NULL로 만들고, 그 순간부터는
검사할 멤버십이 없으므로 그룹 전원에게 공개된다 — 조용히 사라지는 것보다
낫다고 판단한 트레이드오프다.
"""

from models import ChatMessage, ChatRoom, ChatRoomMember, Commitment, GroupMembership


def _setup_two_group_members(client):
    """관리자(owner)와 같은 그룹의 일반 멤버(outsider)를 만든다.

    outsider는 그룹에는 속하지만 어떤 채팅방에도 초대되지 않은 상태다.
    """
    owner_signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "owner@onque.dev", "password": "password123", "name": "방장"},
    ).json()["data"]
    owner_headers = {"Authorization": f"Bearer {owner_signup['token']}"}
    owner_id = owner_signup["user"]["id"]

    group = client.post(
        "/api/v1/groups", json={"name": "A팀"}, headers=owner_headers
    ).json()["data"]

    outsider_signup = client.post(
        "/api/v1/auth/signup",
        json={"email": "outsider@onque.dev", "password": "password123", "name": "외부인"},
    ).json()["data"]
    outsider_headers = {"Authorization": f"Bearer {outsider_signup['token']}"}
    outsider_id = outsider_signup["user"]["id"]

    return {
        "group_id": group["id"],
        "owner_id": owner_id,
        "owner_headers": owner_headers,
        "outsider_id": outsider_id,
        "outsider_headers": outsider_headers,
    }


def _make_private_room(db_session, group_id, owner_id, name="비공개 방"):
    """owner만 초대된 방을 만든다. outsider는 그룹원이지만 이 방엔 없다."""
    room = ChatRoom(group_id=group_id, name=name, created_by=owner_id)
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)
    db_session.add(ChatRoomMember(room_id=room.id, user_id=owner_id))
    db_session.commit()
    return room


def _add_to_group(db_session, user_id, group_id):
    db_session.add(GroupMembership(user_id=user_id, group_id=group_id))
    db_session.commit()


def _seed_message(db_session, room_id, content="수요일까지 시안 드릴게요"):
    message = ChatMessage(room_id=room_id, sender="방장", content=content)
    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)
    return message


def _seed_chat_commitment(db_session, group_id, source_id, **kwargs):
    defaults = {
        "group_id": group_id,
        "content": "시안 3종 전달",
        "source_type": "chat",
        "source_id": source_id,
        "evidence": "수요일까지 시안 드릴게요",
    }
    defaults.update(kwargs)
    c = Commitment(**defaults)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def test_list_hides_chat_commitment_from_non_room_member(client, db_session):
    ctx = _setup_two_group_members(client)
    _add_to_group(db_session, ctx["outsider_id"], ctx["group_id"])
    room = _make_private_room(db_session, ctx["group_id"], ctx["owner_id"])
    message = _seed_message(db_session, room.id)
    _seed_chat_commitment(db_session, ctx["group_id"], message.id, room_id=room.id)

    outsider_res = client.get(
        "/api/v1/commitments",
        params={"group_id": ctx["group_id"]},
        headers=ctx["outsider_headers"],
    )
    assert outsider_res.json()["data"] == []
    assert outsider_res.json()["meta"]["total"] == 0

    owner_res = client.get(
        "/api/v1/commitments",
        params={"group_id": ctx["group_id"]},
        headers=ctx["owner_headers"],
    )
    assert len(owner_res.json()["data"]) == 1
    assert owner_res.json()["meta"]["total"] == 1


def test_patch_forbidden_for_non_room_member(client, db_session):
    ctx = _setup_two_group_members(client)
    _add_to_group(db_session, ctx["outsider_id"], ctx["group_id"])
    room = _make_private_room(db_session, ctx["group_id"], ctx["owner_id"])
    message = _seed_message(db_session, room.id)
    commitment = _seed_chat_commitment(db_session, ctx["group_id"], message.id, room_id=room.id)

    res = client.patch(
        f"/api/v1/commitments/{commitment.id}",
        json={"status": "confirmed"},
        headers=ctx["outsider_headers"],
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "COMMITMENT_ACCESS_FORBIDDEN"

    db_session.expire_all()
    assert db_session.get(Commitment, commitment.id).status == "proposed"

    # 방 멤버인 owner는 정상적으로 상태를 바꿀 수 있다.
    ok = client.patch(
        f"/api/v1/commitments/{commitment.id}",
        json={"status": "confirmed"},
        headers=ctx["owner_headers"],
    )
    assert ok.status_code == 200


def test_bulk_status_rejects_whole_batch_for_non_room_member(client, db_session):
    ctx = _setup_two_group_members(client)
    _add_to_group(db_session, ctx["outsider_id"], ctx["group_id"])
    room = _make_private_room(db_session, ctx["group_id"], ctx["owner_id"])
    message = _seed_message(db_session, room.id)
    hidden = _seed_chat_commitment(db_session, ctx["group_id"], message.id, room_id=room.id)
    visible = Commitment(
        group_id=ctx["group_id"],
        content="통화로 받은 약속",
        source_type="call",
        evidence="전화로 말씀드린 내용",
    )
    db_session.add(visible)
    db_session.commit()
    db_session.refresh(visible)

    res = client.post(
        "/api/v1/commitments/bulk-status",
        json={"ids": [hidden.id, visible.id], "status": "confirmed"},
        headers=ctx["outsider_headers"],
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "COMMITMENT_ACCESS_FORBIDDEN"

    db_session.expire_all()
    # all-or-nothing: outsider가 볼 수 있었던 visible도 함께 거부되어야 한다.
    assert db_session.get(Commitment, visible.id).status == "proposed"
    assert db_session.get(Commitment, hidden.id).status == "proposed"

    # 방 멤버인 owner는 같은 요청을 정상적으로 수행할 수 있다.
    ok = client.post(
        "/api/v1/commitments/bulk-status",
        json={"ids": [hidden.id, visible.id], "status": "confirmed"},
        headers=ctx["owner_headers"],
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["updated"] == 2


def test_chat_commitment_with_null_room_id_is_visible_to_group(client, db_session):
    """room_id가 NULL이면 "방이 사라졌다"는 뜻이라 그룹 전원에게 공개된다.

    예전 방식(source_id 역참조)에서는 참조가 끊기면 fail-closed로 숨겼지만,
    이제는 room_id를 채팅 커밋 시점에 직접 저장하므로 NULL은 오직 방 삭제로만
    발생한다 — 그래서 그룹 공개로 승격시키는 게 맞는 정책이다(TS 기록된
    "방 삭제 → 약속 영구 은닉" 버그를 막는 선택).
    """
    ctx = _setup_two_group_members(client)
    _add_to_group(db_session, ctx["outsider_id"], ctx["group_id"])
    room = _make_private_room(db_session, ctx["group_id"], ctx["owner_id"])
    message = _seed_message(db_session, room.id)
    orphan = _seed_chat_commitment(
        db_session, ctx["group_id"], message.id, room_id=None
    )

    list_res = client.get(
        "/api/v1/commitments",
        params={"group_id": ctx["group_id"]},
        headers=ctx["outsider_headers"],
    )
    assert len(list_res.json()["data"]) == 1

    patch_res = client.patch(
        f"/api/v1/commitments/{orphan.id}",
        json={"status": "confirmed"},
        headers=ctx["outsider_headers"],
    )
    assert patch_res.status_code == 200


def test_deleting_room_makes_commitment_visible_to_non_member(client, db_session):
    """방을 명시적으로 지우면 그 방에서 나온 약속이 조용히 사라지는 대신
    그룹 전원에게 보이게 된다 (main.py._delete_room_cascade가 room_id를
    NULL로 만든다)."""
    ctx = _setup_two_group_members(client)
    _add_to_group(db_session, ctx["outsider_id"], ctx["group_id"])
    room = _make_private_room(db_session, ctx["group_id"], ctx["owner_id"])
    message = _seed_message(db_session, room.id)
    commitment = _seed_chat_commitment(
        db_session, ctx["group_id"], message.id, room_id=room.id
    )

    # 방이 살아있는 동안은 원래의 Critical대로 비멤버에게 숨는다.
    before = client.get(
        "/api/v1/commitments",
        params={"group_id": ctx["group_id"]},
        headers=ctx["outsider_headers"],
    )
    assert before.json()["data"] == []

    delete_res = client.delete(
        f"/chat/rooms/{room.id}", headers=ctx["owner_headers"]
    )
    assert delete_res.status_code == 200

    after = client.get(
        "/api/v1/commitments",
        params={"group_id": ctx["group_id"]},
        headers=ctx["outsider_headers"],
    )
    ids = {c["id"] for c in after.json()["data"]}
    assert commitment.id in ids

    db_session.expire_all()
    assert db_session.get(Commitment, commitment.id).room_id is None


def test_last_member_leaving_auto_deletes_room_and_reveals_commitment(
    client, db_session
):
    """마지막 멤버가 방을 나가 자동 삭제되는 경로도 명시적 삭제와 같은
    결과를 내야 한다 — main.py:788-797의 자동 삭제도 같은 _delete_room_cascade를
    타므로 room_id가 NULL이 된다."""
    ctx = _setup_two_group_members(client)
    _add_to_group(db_session, ctx["outsider_id"], ctx["group_id"])
    room = _make_private_room(db_session, ctx["group_id"], ctx["owner_id"])
    message = _seed_message(db_session, room.id)
    commitment = _seed_chat_commitment(
        db_session, ctx["group_id"], message.id, room_id=room.id
    )

    leave_res = client.delete(
        f"/chat/rooms/{room.id}/members/{ctx['owner_id']}",
        headers=ctx["owner_headers"],
    )
    assert leave_res.status_code == 200

    after = client.get(
        "/api/v1/commitments",
        params={"group_id": ctx["group_id"]},
        headers=ctx["outsider_headers"],
    )
    ids = {c["id"] for c in after.json()["data"]}
    assert commitment.id in ids

    db_session.expire_all()
    assert db_session.get(Commitment, commitment.id).room_id is None


def test_call_and_document_sourced_commitments_are_unaffected_by_room_filter(
    client, db_session
):
    """call/document 출처는 방 개념이 없으므로 room-membership 필터의 영향을 받지 않는다."""
    ctx = _setup_two_group_members(client)
    _add_to_group(db_session, ctx["outsider_id"], ctx["group_id"])
    # outsider는 어떤 채팅방에도 속하지 않지만, call/document 약속은 봐야 한다.
    call_commitment = Commitment(
        group_id=ctx["group_id"],
        content="통화 약속",
        source_type="call",
        evidence="전화 내용",
    )
    doc_commitment = Commitment(
        group_id=ctx["group_id"],
        content="문서 약속",
        source_type="document",
        evidence="문서 내용",
    )
    db_session.add_all([call_commitment, doc_commitment])
    db_session.commit()
    db_session.refresh(call_commitment)
    db_session.refresh(doc_commitment)

    res = client.get(
        "/api/v1/commitments",
        params={"group_id": ctx["group_id"]},
        headers=ctx["outsider_headers"],
    )
    contents = {c["content"] for c in res.json()["data"]}
    assert contents == {"통화 약속", "문서 약속"}

    patch_res = client.patch(
        f"/api/v1/commitments/{call_commitment.id}",
        json={"status": "confirmed"},
        headers=ctx["outsider_headers"],
    )
    assert patch_res.status_code == 200
