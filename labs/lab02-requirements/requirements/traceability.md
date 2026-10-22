# 需求可追踪矩阵

Qxx采用线上23题编号，对应369份修订后问卷的统计结果；题号映射见research/questionnaire.md。“项目设计约束”表示项目范围、角色职责和工作流决策，学校相关制度尚待核实；“领域约束”表示业务完整性和安全要求，课程资料提供质量与文档规范要求。

下述实现和测试映射对应feat/core-platform开发分支，业务验证日期为2026-10-13，问卷统计日期为2026-10-21。

2026-10-13 补充实现映射：Design ID 对应 `docs/design/architecture.md` 的设计单元；`test_*` 对应 `project/tests/test_business.py` 和 `project/tests/test_extensions.py` 中实际执行的自动化用例。已有 62 个用例完成整套执行，新增密码存储用例单独执行通过，共 63 个业务用例在独立 SQLite 数据库和受控时间下通过。`browser-smoke` 对应 `project/tests/browser-smoke.cjs`，23 项界面检查已通过。表中映射表示覆盖对应场景，不表示所有需求条件或生产环境均已验收；真实用户易用性、性能负载与完整浏览器兼容性仍保留 TBD，备份恢复时间目标和日志保留策略也需后续验证。

| 需求 ID | 来源 | Design ID | Test Case ID |
|---|---|---|---|
| FR-001 | 领域约束 | D-IDENTITY | test_login_rejects_bad_credentials_without_opening_session；test_logout_revokes_authenticated_access |
| FR-002 | 项目设计约束, 领域约束 | D-IDENTITY | test_cross_club_create_edit_and_task_management_are_rejected |
| FR-003 | Q15, 项目设计约束 | D-CLUB | test_session_and_public_clubs_do_not_expose_credentials_or_private_roster |
| FR-004 | Q15 | D-CLUB | test_pending_application_is_unique_and_acceptance_creates_membership；test_application_owner_can_cancel_then_reapply |
| FR-005 | Q15, 项目设计约束 | D-CLUB | test_pending_application_is_unique_and_acceptance_creates_membership；test_rejection_requires_reason_and_does_not_add_member |
| FR-006 | 项目设计约束 | D-ACTIVITY | test_draft_is_hidden_until_approval_and_publication；test_activity_validates_required_fields_time_zone_order_and_capacity |
| FR-007 | 项目设计约束 | D-ACTIVITY | test_draft_is_hidden_until_approval_and_publication |
| FR-008 | 项目设计约束 | D-ACTIVITY | test_draft_is_hidden_until_approval_and_publication；test_rejected_activity_can_be_corrected_but_cannot_be_published |
| FR-009 | 项目设计约束 | D-ACTIVITY | test_draft_is_hidden_until_approval_and_publication |
| FR-010 | Q03, Q04, Q05 | D-ACTIVITY | test_public_filters_combine_and_do_not_reveal_drafts；test_date_filter_uses_requested_local_day_at_utc_midnight_boundary |
| FR-011 | Q06, 项目设计约束 | D-ACTIVITY | test_draft_is_hidden_until_approval_and_publication |
| FR-012 | Q06, 项目设计约束 | D-REGISTRATION | test_duplicate_registration_fails_without_duplicate_notification；test_cancellation_and_registration_are_denied_exactly_at_deadline |
| FR-013 | Q07, 项目设计约束 | D-REGISTRATION | test_cancellation_is_personal_and_freed_capacity_can_be_reused；test_cancellation_and_registration_are_denied_exactly_at_deadline |
| FR-014 | Q09, 领域约束 | D-REGISTRATION | test_concurrent_requests_do_not_exceed_capacity |
| FR-015 | Q09, 项目设计约束 | D-REGISTRATION | test_waitlist_cancellation_is_skipped_and_first_effective_waiter_is_promoted_once；test_concurrent_cancellation_and_registration_preserve_waitlist_priority |
| FR-016 | Q12, 项目设计约束 | D-REGISTRATION | test_checkin_requires_in_progress_confirmed_registration_and_club_authority |
| FR-017 | Q13, 项目设计约束 | D-REGISTRATION | test_checkin_requires_in_progress_confirmed_registration_and_club_authority；test_stopping_member_removes_organization_authority_but_keeps_history |
| FR-018 | Q16, Q18, 项目设计约束 | D-COLLABORATION | test_tasks_assigned_only_to_active_members_and_updates_respect_ownership |
| FR-019 | Q18, 项目设计约束 | D-COLLABORATION | test_tasks_assigned_only_to_active_members_and_updates_respect_ownership；test_stopping_member_invalidates_existing_task_authority |
| FR-020 | Q10, 项目设计约束 | D-COLLABORATION | test_duplicate_registration_fails_without_duplicate_notification；test_tasks_assigned_only_to_active_members_and_updates_respect_ownership；test_notifications_are_private_and_mark_read_is_idempotent |
| FR-021 | Q10, Q18, 项目设计约束 | D-COLLABORATION | test_personal_todos_hide_other_clubs_and_completed_tasks_disappear；test_leader_and_staff_todos_include_only_their_actionable_pending_items |
| FR-022 | Q05, 项目设计约束 | D-ACTIVITY | test_date_filter_uses_requested_local_day_at_utc_midnight_boundary；browser-smoke: UI local-day activity calendar（23 项界面检查通过） |
| FR-023 | Q18, 项目设计约束 | D-COLLABORATION | browser-smoke: UI task progress（23 项界面检查通过） |
| FR-024 | Q19, 项目设计约束 | D-RESOURCE | test_venue_request_separates_owning_leader_from_staff_and_other_clubs；test_simultaneous_overlapping_approvals_accept_only_one_reservation；test_adjacent_intervals_and_different_venues_can_both_be_approved |
| FR-025 | Q13, 项目设计约束 | D-FEEDBACK | test_feedback_requires_finished_activity_and_personal_checkin_and_is_unique；test_feedback_validates_integer_rating_and_comment_length |
| FR-026 | 项目设计约束 | D-FEEDBACK | test_finished_statistics_match_effective_registrations_checkins_and_feedback |
| FR-027 | Q19, 项目设计约束 | D-RESOURCE | test_materials_are_private_and_managed_only_by_owning_leader；test_materials_validate_names_quantities_status_and_disabled_club |
| FR-028 | Q05 | D-FEEDBACK | test_recommendations_prioritize_exact_preferences_then_time_and_hide_drafts；test_recommendations_without_preferences_use_public_activity_time_and_id |
| FR-029 | 项目设计约束 | D-FEEDBACK | test_reports_are_personal_until_staff_resolves_and_duplicates_are_rejected；test_reports_reject_hidden_activities_and_roll_back_failed_notifications |
| FR-030 | 项目设计约束 | D-FEEDBACK | test_csv_export_preserves_statistics_and_neutralizes_spreadsheet_formulas；test_finished_statistics_match_effective_registrations_checkins_and_feedback |
| FR-031 | 项目设计约束 | D-OPERATIONS | test_audit_and_runtime_logs_require_staff_and_do_not_leak_authentication_material |
| FR-032 | Q15, 项目设计约束, 领域约束 | D-CLUB | test_stopping_member_removes_organization_authority_but_keeps_history；test_current_leader_cannot_be_stopped_by_membership_endpoint |
| FR-033 | 项目范围澄清（2026-09-29） | D-CLUB | test_applicant_does_not_get_formal_club_or_leadership_before_staff_approval；test_pending_club_registration_is_unique_and_rejection_requires_reason |
| FR-034 | 项目范围澄清（2026-09-29） | D-CLUB | test_leadership_change_requires_staff_and_active_member_then_changes_authority；test_disabled_club_blocks_business_writes_but_personal_cancellation_remains |
| NFR-001 | Q05, Q06, 项目设计约束 | D-ACTIVITY / D-REGISTRATION | TBD（待真实用户任务验证） |
| NFR-002 | Q06, 领域约束 | D-ACTIVITY / D-REGISTRATION | TBD（负载、环境与性能阈值尚未冻结） |
| NFR-003 | Q09, 领域约束 | D-REGISTRATION | test_notification_failure_rolls_back_registration_and_capacity；test_failed_transfer_notification_rolls_back_cancellation_and_promotion |
| NFR-004 | 领域约束 | D-IDENTITY | test_password_storage_uses_independently_salted_hashes_and_checks_credentials；test_audit_and_runtime_logs_require_staff_and_do_not_leak_authentication_material |
| NFR-005 | 项目设计约束, 领域约束 | D-IDENTITY | test_anonymous_users_cannot_read_internal_lists；test_cross_club_create_edit_and_task_management_are_rejected |
| NFR-006 | 项目设计约束, 领域约束 | D-IDENTITY / D-ACTIVITY | test_activity_validates_required_fields_time_zone_order_and_capacity；test_expired_session_is_rejected_at_expiry；test_missing_and_foreign_csrf_tokens_are_rejected_including_login |
| NFR-007 | 项目设计约束 | D-OPERATIONS | test_audit_and_runtime_logs_require_staff_and_do_not_leak_authentication_material；test_leadership_change_requires_staff_and_active_member_then_changes_authority |
| NFR-008 | 领域约束 | D-IDENTITY / D-CLUB / D-ACTIVITY / D-REGISTRATION / D-COLLABORATION / D-OPERATIONS / D-RESOURCE / D-FEEDBACK | TBD（待设计与用例映射评审） |
| NFR-009 | 领域约束 | D-ACTIVITY / D-REGISTRATION | test_deadline_start_and_end_lifecycle_use_exact_instants_and_leave_drafts_unchanged；test_cancellation_and_registration_are_denied_exactly_at_deadline |
| NFR-010 | Q05, 领域约束 | D-ACTIVITY / D-REGISTRATION | TBD（待兼容性清单及浏览器逐项验证） |
| NFR-011 | Q06, 项目设计约束, 领域约束 | D-REGISTRATION / D-CLUB | test_simultaneous_same_student_requests_create_one_effective_record；test_waitlist_cancellation_is_skipped_and_first_effective_waiter_is_promoted_once；test_pending_application_is_unique_and_acceptance_creates_membership |
| NFR-012 | Q21, 项目设计约束 | D-IDENTITY | test_session_and_public_clubs_do_not_expose_credentials_or_private_roster；test_other_club_leader_cannot_inspect_or_change_members；test_notifications_are_private_and_mark_read_is_idempotent |
| NFR-013 | 教师 SRS 模板, 领域约束 | D-OPERATIONS | test_backup_restore_preserves_committed_business_records；test_backup_and_restore_refuse_to_overwrite_existing_targets；test_restore_rejects_corrupt_or_unrelated_databases_without_creating_target（恢复时间目标待验证） |
| NFR-014 | 教师 SRS 模板, 项目设计约束, 领域约束 | D-OPERATIONS | test_runtime_log_records_four_failure_categories_without_sensitive_details；test_audit_and_runtime_logs_require_staff_and_do_not_leak_authentication_material（日志保留策略待验证） |
| BR-001 | Q06, 领域约束 | D-REGISTRATION | test_draft_is_hidden_until_approval_and_publication；test_cancellation_and_registration_are_denied_exactly_at_deadline |
| BR-002 | Q06, Q09, 领域约束 | D-REGISTRATION | test_simultaneous_same_student_requests_create_one_effective_record；test_concurrent_requests_do_not_exceed_capacity |
| BR-003 | Q09 | D-REGISTRATION | test_concurrent_requests_do_not_exceed_capacity；test_waitlist_cancellation_is_skipped_and_first_effective_waiter_is_promoted_once |
| BR-004 | Q07, Q09, 项目设计约束 | D-REGISTRATION | test_waitlist_cancellation_is_skipped_and_first_effective_waiter_is_promoted_once；test_failed_transfer_notification_rolls_back_cancellation_and_promotion |
| BR-005 | Q09, 领域约束 | D-REGISTRATION | test_waitlist_cancellation_is_skipped_and_first_effective_waiter_is_promoted_once；test_cancellation_and_registration_are_denied_exactly_at_deadline |
| BR-006 | 项目设计约束, 领域约束 | D-ACTIVITY | test_deadline_start_and_end_lifecycle_use_exact_instants_and_leave_drafts_unchanged；test_rejected_activity_can_be_corrected_but_cannot_be_published |
| BR-007 | 项目设计约束, 领域约束 | D-ACTIVITY / D-REGISTRATION | test_draft_is_hidden_until_approval_and_publication；test_cancelled_activity_notifies_participants_and_never_progresses |
| BR-008 | Q16, Q18, 项目设计约束 | D-COLLABORATION | test_tasks_assigned_only_to_active_members_and_updates_respect_ownership |
| BR-009 | 项目设计约束, 领域约束 | D-IDENTITY | test_cross_club_create_edit_and_task_management_are_rejected；test_other_club_leader_cannot_inspect_or_change_members |
| BR-010 | Q12, 项目设计约束 | D-REGISTRATION | test_checkin_requires_in_progress_confirmed_registration_and_club_authority |
| BR-011 | 项目设计约束 | D-ACTIVITY | test_rejected_activity_can_be_corrected_but_cannot_be_published |
| BR-012 | Q19, 项目设计约束 | D-RESOURCE | test_simultaneous_overlapping_approvals_accept_only_one_reservation；test_adjacent_intervals_and_different_venues_can_both_be_approved |
