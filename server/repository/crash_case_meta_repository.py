from server.models.client.crash_case_meta import CrashCaseMeta


def add_crash_case_meta(
    case_id,
    signal_name=None,
    crash_type=None,
    crash_function=None,
    dpdk_lib_missing=None,
    dpdk_subsystems=None,
    missing_libs=None,
    root_cause=None,
    repair_steps=None,
):
    case = CrashCaseMeta.create(
        case_id=case_id,
        signal_name=signal_name,
        crash_type=crash_type,
        crash_function=crash_function,
        dpdk_lib_missing=dpdk_lib_missing,
        dpdk_subsystems=dpdk_subsystems,
        missing_libs=missing_libs,
        root_cause=root_cause,
        repair_steps=repair_steps,
    )

    return case.id


def update_crash_case_meta(case_id, updates: dict):
    """
    updates example:
    {
        "crash_type": "null_pointer_deref",
        "dpdk_lib_missing": True
    }
    """
    return CrashCaseMeta.update(filters={"case_id": case_id}, updates=updates)


def get_crash_case_meta(case_id):
    case = CrashCaseMeta.get(case_id=case_id)
    return case if case else None


def page_crash_case_meta(page_num, page_size):
    return CrashCaseMeta.page(page_num, page_size)


def filter_crash_case_meta(crash_type=None, signal_name=None) -> list[CrashCaseMeta]:
    filters = {}

    if crash_type:
        filters["crash_type"] = crash_type

    if signal_name:
        filters["signal_name"] = signal_name

    return CrashCaseMeta.filter(filters=filters)
