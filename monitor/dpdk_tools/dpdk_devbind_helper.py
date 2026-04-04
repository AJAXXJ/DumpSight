import dpdk_devbind as db


def _load_devices():
    """
    Loads device information into the database. This is a necessary step before querying device statuses or performing any operations on the devices.
    """
    db.clear_data()
    db.check_modules()
    for dev_type in [
        db.network_devices, db.baseband_devices, db.crypto_devices,
        db.dma_devices, db.eventdev_devices, db.mempool_devices,
        db.compress_devices, db.regex_devices, db.ml_devices, db.misc_devices
    ]:
        db.get_device_details(dev_type)


def get_device_status():
    """
    Gets the current status of all devices, categorized by type and binding status (DPDK-bound, kernel-bound, or no driver).
    """
    _load_devices()

    type_map = {
        "network":  (db.network_devices,  True),
        "baseband": (db.baseband_devices, False),
        "crypto":   (db.crypto_devices,   False),
        "dma":      (db.dma_devices,      False),
        "eventdev": (db.eventdev_devices, False),
        "mempool":  (db.mempool_devices,  False),
        "compress": (db.compress_devices, False),
        "regex":    (db.regex_devices,    False),
        "ml":       (db.ml_devices,       False),
        "misc":     (db.misc_devices,     False),
    }

    result = {}
    for category, (dev_type, has_iface) in type_map.items():
        dpdk_bound, kernel_bound, no_drv = [], [], []

        for slot, dev in db.devices.items():
            if not db.device_type_match(dev, dev_type):
                continue

            entry = {
                "slot":   dev.get("Slot", slot),
                "device": dev.get("Device_str", ""),
                "driver": dev.get("Driver_str", ""),
                "unused": dev.get("Module_str", ""),
                "iface":  dev.get("Interface", "") if has_iface else "",
                "active": dev.get("Active", ""),
            }

            if not db.has_driver(slot):
                no_drv.append(entry)
            elif dev["Driver_str"] in db.dpdk_drivers:
                dpdk_bound.append(entry)
            else:
                kernel_bound.append(entry)

        result[category] = {
            "dpdk_bound":   sorted(dpdk_bound,   key=lambda x: x["slot"]),
            "kernel_bound": sorted(kernel_bound, key=lambda x: x["slot"]),
            "no_driver":    sorted(no_drv,       key=lambda x: x["slot"]),
        }

    return result


def get_network_devices():
    """
    Only returns the network devices, categorized by their binding status. This is a convenience function for users who are primarily interested in network interfaces.
    """
    return get_device_status()["network"]


def get_dpdk_bound_devices():
    """
    Returns all devices that are bound to the DPDK driver (across all types).
    """
    result = []
    for category, data in get_device_status().items():
        for dev in data["dpdk_bound"]:
            result.append({**dev, "category": category})
    return result