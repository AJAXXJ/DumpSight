#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright(c) 2010-2014 Intel Corporation
# Copyright(c) 2017 Cavium, Inc. All rights reserved.

base_path = "/sys/devices/system/cpu"

def _read_cpu_topology():
    """
    Reads the CPU topology information from the system files and constructs a structured representation of sockets, cores, and their mappings.
    """
    sockets = []
    cores = []
    core_map = {}

    fd = open("{}/kernel_max".format(base_path))
    max_cpus = int(fd.read())
    fd.close()

    for cpu in range(max_cpus + 1):
        try:
            fd = open("{}/cpu{}/topology/core_id".format(base_path, cpu))
        except IOError:
            continue
        core = int(fd.read())
        fd.close()
        fd = open("{}/cpu{}/topology/physical_package_id".format(base_path, cpu))
        socket = int(fd.read())
        fd.close()

        if core not in cores:
            cores.append(core)
        if socket not in sockets:
            sockets.append(socket)

        key = (socket, core)
        if key not in core_map:
            core_map[key] = []
        core_map[key].append(cpu)

    return sockets, cores, core_map


def get_cpu_layout():
    """
    Returns a structured representation of the CPU topology, including sockets, cores, and their mappings.
    """
    sockets, cores, core_map = _read_cpu_topology()
    return {
        "sockets": sockets,
        "cores": cores,
        "core_map": {str(k): v for k, v in core_map.items()},
    }


def get_cpu_layout_simple():
    """
    Returns a simplified list of CPU topology information, suitable for display or simple processing.
    """
    _, _, core_map = _read_cpu_topology()
    result = []
    for (socket, core), cpus in core_map.items():
        result.append({
            "socket": socket,
            "core": core,
            "cpus": cpus,
        })
    return sorted(result, key=lambda x: (x["socket"], x["core"]))


def _print_layout(sockets, cores, core_map):
    """
    Raw data printout for debugging purposes. Not intended for external use.
    """
    print(format("=" * (47 + len(base_path))))
    print("Core and Socket Information (as reported by '{}')".format(base_path))
    print("{}\n".format("=" * (47 + len(base_path))))
    print("cores = ", cores)
    print("sockets = ", sockets)
    print("")

    max_processor_len = len(str(len(cores) * len(sockets) * 2 - 1))
    max_thread_count = len(list(core_map.values())[0])
    max_core_map_len = (max_processor_len * max_thread_count) \
                       + len(", ") * (max_thread_count - 1) \
                       + len('[]') + len('Socket ')
    max_core_id_len = len(str(max(cores)))

    output = " ".ljust(max_core_id_len + len('Core '))
    for s in sockets:
        output += " Socket %s" % str(s).ljust(max_core_map_len - len('Socket '))
    print(output)

    output = " ".ljust(max_core_id_len + len('Core '))
    for s in sockets:
        output += " --------".ljust(max_core_map_len)
        output += " "
    print(output)

    for c in cores:
        output = "Core %s" % str(c).ljust(max_core_id_len)
        for s in sockets:
            if (s, c) in core_map:
                output += " " + str(core_map[(s, c)]).ljust(max_core_map_len)
            else:
                output += " " * (max_core_map_len + 1)
        print(output)


if __name__ == "__main__":
    sockets, cores, core_map = _read_cpu_topology()
    _print_layout(sockets, cores, core_map)