local newInput(type, valueSelector, otterdogName, inputName = otterdogName) = {
  [otterdogName]: {
    type: type,
    valueSelector: valueSelector,
    selector: 'input[type="%s"][name="%s"]' % [type, inputName],
    save: 'form:has(%s) button[type="submit"]' % self.selector,
  }
};

local newCheckbox(otterdogName, inputName = otterdogName) =
  newInput('checkbox', 'checked', otterdogName, inputName);

local newTextInput(otterdogName, inputName = otterdogName) =
  newInput('text', 'value', otterdogName, inputName);

local newRadioInput(otterdogName, inputName = otterdogName) =
  newInput('radio', 'value', otterdogName, inputName);

{
  'settings/member_privileges':
    newCheckbox('members_can_change_repo_visibility') +
    newCheckbox('members_can_delete_repositories') +
    newCheckbox('members_can_delete_issues') +
    newCheckbox('readers_can_create_discussions') +
    newCheckbox('members_can_create_teams'),

  'settings/security':
    newCheckbox('two_factor_requirement'),

  'settings/repository-defaults':
    newTextInput('default_branch_name'),

  'settings/packages':
    newCheckbox('packages_containers_public', 'packages[containers][public]') +
    newCheckbox('packages_containers_internal', 'packages[containers][internal]'),

  'settings/projects':
    newCheckbox('members_can_change_project_visibility', 'organization[members_can_change_project_visibility]'),

  'settings/actions':
    newRadioInput('default_workflow_permissions', 'actions_default_workflow_permissions'),
}