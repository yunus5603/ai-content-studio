from app.core.permissions import Action, Role, can, can_assign


def test_role_hierarchy():
    assert can(Role.viewer, Action.view)
    assert not can(Role.viewer, Action.generate)
    assert can(Role.member, Action.generate)
    assert not can(Role.member, Action.manage_members)
    assert can(Role.admin, Action.manage_members)
    assert not can(Role.admin, Action.manage_billing)
    assert can(Role.owner, Action.manage_billing)


def test_nobody_assigns_owner_and_owner_is_untouchable():
    assert not can_assign(Role.owner, Role.member, Role.owner)
    assert not can_assign(Role.admin, Role.owner, Role.member)
    assert can_assign(Role.admin, Role.member, Role.admin)
    assert not can_assign(Role.member, Role.viewer, Role.member)
