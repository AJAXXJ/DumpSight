from server.models.client.case_info import CaseInfo


def add_case(
    case_id,
    signal_name=None,
    crash_type=None,
    crash_function=None,
    main_path=None,
    dpdk_subsystems=None,
    missing_libs=None,
    root_cause=None,
    repair_steps=None,
    description=None,
    log_feature=None,
    reference_feature=None,
    anomaly_flags=None,
):
    case = CaseInfo.create(
        case_id=case_id,
        signal_name=signal_name,
        crash_type=crash_type,
        crash_function=crash_function,
        main_path=main_path,
        dpdk_subsystems=dpdk_subsystems,
        missing_libs=missing_libs,
        root_cause=root_cause,
        repair_steps=repair_steps,
        description=description,
        log_feature=log_feature,
        reference_feature=reference_feature,
        anomaly_flags=anomaly_flags,
    )

    return case["id"]


def update_case(case_id, updates):
    """
    updates example:
    {
        "crash_type": "null_pointer_deref",
        "dpdk_lib_missing": True
    }
    """
    return CaseInfo.update(filters={"case_id": case_id}, updates=updates)


def get_case(case_id):
    case = CaseInfo.get(case_id=case_id)
    return case if case else None

def get_all_case():
    return CaseInfo.all()

def get_case_batch(case_ids):
    if not case_ids:
        return []

    return CaseInfo.in_filter("case_id", case_ids)


def page_case(page_num, page_size):
    return CaseInfo.page(page_num, page_size)


def filter_case(crash_type=None, signal_name=None):
    filters = {}

    if crash_type:
        filters["crash_type"] = crash_type

    if signal_name:
        filters["signal_name"] = signal_name

    return CaseInfo.filter(filters=filters)
