"""Shared tab labels and local macOS/Linux network history in Kitty.

The native timer reads kernel byte counters without spawning programs.
Physical interfaces are counted once, excluding tunnels and bridges.
Linux network namespaces without hardware use their default interface.
"""

from collections import deque
import ctypes as c
import json
from math import ceil, log10
import os
from pathlib import Path
import re
import shlex
import sys
from time import monotonic
from urllib.parse import unquote, urlsplit


class InterfaceData64(c.Structure):
    # Public Darwin ABI: net/if_var.h, struct if_data64, packed to 4 bytes.
    _pack_ = 4
    _fields_ = [("metadata", c.c_ubyte * 8), ("mtu", c.c_uint32), ("metric", c.c_uint32),
                ("baudrate", c.c_uint64), ("packets", c.c_uint64 * 5),
                ("ibytes", c.c_uint64), ("obytes", c.c_uint64),
                ("multicast_drops", c.c_uint64 * 4), ("timing", c.c_uint32 * 2),
                ("lastchange", c.c_uint32 * 2)]


class InterfaceMibData(c.Structure):
    # Public Darwin ABI: net/if_mib.h, struct ifmibdata.
    _fields_ = [("name", c.c_char * 16), ("flags_queue", c.c_uint32 * 9),
                ("data", InterfaceData64)]


def parse_counters(output):
    counters = {}
    size = c.sizeof(InterfaceMibData)
    if len(output) % size:
        raise ValueError("incomplete interface snapshot")
    for pos in range(0, len(output), size):
        interface = InterfaceMibData.from_buffer_copy(output, pos)
        name = interface.name.decode("ascii", "replace")
        if re.fullmatch(r"en\d+", name):
            counters[name] = (interface.data.ibytes, interface.data.obytes)
    return counters


_sysctl = None


def read_mac_counters():
    global _sysctl
    if _sysctl is None:
        if c.sizeof(InterfaceMibData) != 180 or InterfaceMibData.data.offset != 52:
            raise ValueError("unsupported Darwin interface ABI")
        _sysctl = c.CDLL(None, use_errno=True).sysctl
        _sysctl.argtypes = [c.POINTER(c.c_int), c.c_uint, c.c_void_p, c.POINTER(c.c_size_t), c.c_void_p, c.c_size_t]
        _sysctl.restype = c.c_int
    # CTL_NET / PF_LINK / NETLINK_GENERIC / IFMIB_IFALLDATA / IFDATA_GENERAL.
    # The routing API's if_msghdr2 can contain truncated byte counters on macOS.
    mib = (c.c_int * 6)(4, 18, 0, 3, 0, 1)
    for _ in range(3):
        size = c.c_size_t()
        if _sysctl(mib, 6, None, c.byref(size), None, 0):
            raise OSError(c.get_errno(), "network counters unavailable")
        if size.value > 8 * 1024 * 1024:
            raise ValueError("interface snapshot too large")
        buffer = c.create_string_buffer(size.value)
        if not _sysctl(mib, 6, buffer, c.byref(size), None, 0):
            return parse_counters(buffer.raw[:size.value])
        if c.get_errno() != 12:  # ENOMEM: an interface changed between the two reads.
            raise OSError(c.get_errno(), "network counters unavailable")
    raise OSError("interfaces kept changing")


def linux_default_interface(proc_net, interfaces):
    routes = []
    try:
        for line in (proc_net / "route").read_text().splitlines()[1:]:
            fields = line.split()
            if len(fields) >= 11 and fields[0] in interfaces:
                try:
                    if fields[1] == fields[7] == "00000000" and int(fields[3], 16) & 1:
                        routes.append((int(fields[6]), fields[0]))
                except ValueError:
                    continue
    except OSError:
        pass
    if not routes:
        try:
            for line in (proc_net / "ipv6_route").read_text().splitlines():
                fields = line.split()
                if len(fields) == 10 and fields[-1] in interfaces:
                    try:
                        if fields[0] == "0" * 32 and fields[1] == "00" and int(fields[8], 16) & 1:
                            routes.append((int(fields[5], 16), fields[-1]))
                    except ValueError:
                        continue
        except OSError:
            pass
    return min(routes)[1] if routes else None


def read_linux_counters(proc_net=Path("/proc/net"), sys_net=Path("/sys/class/net")):
    counters = {}
    for line in (proc_net / "dev").read_text().splitlines():
        if ":" not in line:
            continue
        name, values = line.rsplit(":", 1)
        name, fields = name.strip(), values.split()
        if name == "lo" or len(fields) != 16:
            continue
        try:
            rx, tx = int(fields[0]), int(fields[8])
        except ValueError:
            continue
        if rx >= 0 and tx >= 0:
            counters[name] = (rx, tx)
    physical = {name: value for name, value in counters.items() if (sys_net / name / "device").exists()}
    if physical:
        return physical
    # Containers expose veth devices without a hardware parent. Choose one
    # default interface rather than summing bridge and tunnel traffic twice.
    interface = linux_default_interface(proc_net, counters)
    return {interface: counters[interface]} if interface else {}


def read_counters():
    if sys.platform == "darwin":
        return read_mac_counters()
    if sys.platform.startswith("linux"):
        return read_linux_counters()
    return {}


class NetworkHistory:
    def __init__(self):
        self.samples = deque(maxlen=90)
        self.previous = None
        self.previous_time = None
        self.rx = self.tx = 0.0
        self.status = "starting"

    def update(self, counters, now):
        if not counters:
            self.previous = self.previous_time = None
            self.samples.append((now, None, None))
            self.status = "unavailable"
            return
        elapsed = now - self.previous_time if self.previous_time is not None else 0
        common = counters.keys() & self.previous.keys() if self.previous else set()
        # Resume, reconnect, new interfaces and resets must not create spikes.
        reset = any(counters[n][i] < self.previous[n][i] for n in common for i in (0, 1))
        if common and 0 < elapsed <= 5 and not reset:
            self.rx, self.tx = [
                sum(counters[n][i] - self.previous[n][i] for n in common) * 8 / elapsed
                for i in (0, 1)
            ]
            self.samples.append((now, self.rx, self.tx))
            self.status = "ready"
        else:
            self.samples.append((now, None, None))
            if elapsed > 5:
                self.samples.clear()
            self.status = "starting"
        self.previous, self.previous_time = counters, now


def chart_data(samples, now, count):
    bins = [[None, None] for _ in range(count)]
    for stamp, rx, tx in samples:
        if not now - 60 < stamp <= now or rx is None:
            continue
        pos = min(count - 1, int((stamp - (now - 60)) * count / 60))
        for channel, value in enumerate((rx, tx)):
            bins[pos][channel] = max(bins[pos][channel] or 0, value)
    peak = max((v or 0 for pair in bins for v in pair), default=0)
    # A shared 1/2/5 scale keeps RX and TX comparable, with a quiet 100 kb/s floor.
    peak = max(peak, 100_000)
    decade = 10 ** int(log10(peak))
    scale = next(m * decade for m in (1, 2, 5, 10) if m * decade >= peak)
    glyphs = "▁▂▃▄▅▆▇█"
    graphs = tuple(
        "".join("·" if pair[c] is None else glyphs[min(7, ceil(pair[c] / scale * 7))] for pair in bins)
        for c in (0, 1)
    )
    return graphs, scale


def compact_rate(value):
    for multiplier, suffix in ((1e9, "G"), (1e6, "M"), (1e3, "k")):
        if value >= multiplier:
            number = value / multiplier
            return (f"{number:.1f}" if number < 99.95 else f"{number:.0f}") + suffix
    return f"{value:.0f}"


class NetworkMonitor:
    def __init__(self):
        from kitty.fast_data_types import add_timer
        self.history = NetworkHistory()
        self.closed = False
        self.sample()
        self.timer = add_timer(self.refresh, 1.0, True)

    def sample(self):
        try:
            counters = read_counters()
        except (OSError, ValueError):
            counters = {}
        self.history.update(counters, monotonic())

    def snapshot(self):
        h = self.history
        return list(h.samples), h.rx, h.tx, h.status

    def refresh(self, timer_id):
        from kitty.fast_data_types import get_boss, get_options
        if get_options().tab_bar_style != "custom":
            self.close()
            return
        boss = get_boss()
        if boss and not self.closed:
            self.sample()
            for manager in boss.all_tab_managers:
                manager.update_tab_bar_data()
                manager.mark_tab_bar_dirty()

    def close(self):
        if self.closed:
            return
        from kitty.fast_data_types import remove_timer
        self.closed = True
        remove_timer(self.timer)


_monitor = None
_remote_locations = {}


def plain_title(title):
    title = re.sub(r"\x1b\[[0-9;:]*m", "", title)
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", "", title).strip()


def command_name(command):
    try:
        words = shlex.split(plain_title(command))
    except ValueError:
        words = command.split()
    # Show the executable, never arguments that may contain credentials.
    while words and (re.match(r"^[A-Za-z_][A-Za-z_0-9]*=", words[0]) or words[0] in ("command", "exec")):
        words.pop(0)
    return words[0].rsplit("/", 1)[-1] if words else ""


def compact_title(title):
    # Parse only the shell's host: path convention; keep other labels intact.
    title = plain_title(title)
    host, separator, detail = title.partition(": ")
    if separator and re.fullmatch(r"(?:[^\s@:/]+@)?[^\s@:/]+", host):
        if not host.startswith("root@"):
            host = host.rsplit("@", 1)[-1]
        if detail.startswith(("/", "~", "…/")):
            detail = compact_title(detail)
        else:
            detail = detail.split()[0] if detail.split() else ""
        return f"{host}:{detail}" if detail else host
    if title in ("~", "~/", "/"):
        return title.rstrip("/") or "/"
    if title.startswith(("/", "~/", "…/")):
        return title.rstrip("/").rsplit("/", 1)[-1]
    return title or "shell"


def shell_state(window):
    if window.child_is_remote:
        return None
    value = window.user_vars.get("terminal_dotfiles_state", "")
    if not value:
        return None
    try:
        state = json.loads(value)
        if not isinstance(state, dict) or state.get("v") != 1:
            return None
        owner = state.get("pid")
        if type(owner) is not int or owner < 1 or state.get("phase") not in ("prompt", "running"):
            return None
        if not all(isinstance(state.get(field), str) for field in ("cwd", "context", "command")):
            return None
        # Kubie shells and their supervisor need not share a foreground group.
        # Trust the publishing shell in this PTY session, not another process's
        # environment. getsid also rejects metadata from an exited shell.
        root_pid = window.child.pid
        if os.getsid(owner) != os.getsid(root_pid):
            return None
    except (OSError, ValueError, TypeError, OverflowError):
        return None
    return state


def kubie_label(window):
    state = shell_state(window)
    return plain_title(state["context"]) if state else ""


def local_program(window):
    argv = window.child.foreground_cmdline
    executable = Path(argv[0]).name.lstrip("-") if argv else ""
    return "" if executable in ("bash", "zsh", "fish", "sh", "dash", "login", "kitten", "kitty", "kubie", "starship") else executable


def remote_title(window, title):
    key = window.id
    host, directory = _remote_locations.get(key, ("", ""))
    prefix, separator, detail = title.partition(": ")
    if separator and re.fullmatch(r"(?:[^\s@:/]+@)?[^\s@:/]+", prefix):
        new_host = prefix if prefix.startswith("root@") else prefix.rsplit("@", 1)[-1]
        if new_host != host:
            directory = ""
        host = new_host
    else:
        detail = title
    location, running, command = detail.partition(" · ")
    if location.startswith(("/", "~", "…/")):
        directory = compact_title(location)
        command = command_name(command) if running else ""
    else:
        command = command_name(detail)
    # OSC 7 is also available when a TUI replaces the shell's window title.
    try:
        reported = urlsplit(window.screen.last_reported_cwd or "")
    except ValueError:
        reported = urlsplit("")
    if not directory and reported.scheme == "file" and reported.hostname and host and reported.hostname.split(".")[0] == host.rsplit("@", 1)[-1].split(".")[0]:
        directory = compact_title(unquote(reported.path))
    if len(_remote_locations) > 256:
        _remote_locations.pop(next(iter(_remote_locations)))
    _remote_locations[key] = host, directory
    identity = f"{host}:{directory}" if host and directory else host or directory
    if not identity:
        return compact_title(title)
    return f"{identity} {command}" if command else identity


def sgr_rgb(text, channel):
    color = None
    for parameters in re.findall(r"\x1b\[([0-9;:]*)m", text):
        values = [int(value) for value in parameters.replace(":", ";").split(";") if value]
        for i in range(len(values) - 4):
            if values[i:i + 2] == [channel, 2] and all(0 <= value <= 255 for value in values[i + 2:i + 5]):
                color = tuple(values[i + 2:i + 5])
    return color


def contrast(first, second):
    def luminance(rgb):
        values = [value / 255 for value in rgb]
        values = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in values]
        return sum(value * weight for value, weight in zip(values, (0.2126, 0.7152, 0.0722)))
    low, high = sorted((luminance(first), luminance(second)))
    return (high + 0.05) / (low + 0.05)


def accent_kubernetes(title, data, encoded_state):
    formatter = data.get("fmt")
    if not formatter or "☸" not in title:
        return title
    try:
        raw_context = json.loads(encoded_state)["context"]
        color = sgr_rgb(raw_context.split("☸", 1)[0], 38)
    except (ValueError, TypeError, KeyError):
        return title
    if color:
        background = sgr_rgb(formatter.bg.tab, 48)
        if background and contrast(color, background) < 3:
            # Retain the hue while making the icon readable on an active tab.
            target = 0 if sum(background) > 384 else 255
            for amount in (0.2, 0.4, 0.6, 0.8, 1.0):
                adjusted = tuple(round(value * (1 - amount) + target * amount) for value in color)
                if contrast(adjusted, background) >= 3:
                    color = adjusted
                    break
        icon = f"\x1b[38;2;{color[0]};{color[1]};{color[2]}m☸{formatter.fg.tab}"
        return title.replace("☸", icon, 1)
    return title


def draw_title(data):
    from kitty.fast_data_types import get_boss
    tab = get_boss().tab_for_id(data["tab_id"])
    # An explicitly assigned name always wins, including names with ': '.
    if tab and tab.name:
        return plain_title(tab.name)
    window = tab.active_window if tab else None
    title = plain_title(data["title"])
    if window is None:
        return compact_title(title)
    key = (title, window.at_prompt, getattr(window.child, "pid_for_cwd", None),
           window.user_vars.get("terminal_dotfiles_state", ""))
    now = monotonic()
    cached = getattr(window, "_dotfiles_title_cache", None)
    # Kitty calls this for every tab during both layout and painting. Avoid
    # repeating process/cwd lookups within one frame; expire state promptly.
    if cached and cached[0] == key and now - cached[1] < 0.1:
        return accent_kubernetes(cached[2], data, key[-1])
    result = window_title(window, title)
    window._dotfiles_title_cache = key, now, result
    return accent_kubernetes(result, data, key[-1])


def window_title(window, title):
    if window.child_is_remote:
        return remote_title(window, title)
    _remote_locations.pop(window.id, None)
    state = shell_state(window)
    cwd = state["cwd"] if state else window.get_cwd_of_child() or ""
    directory = "~" if cwd == str(Path.home()) else compact_title(cwd) if cwd else ""
    if state:
        context = plain_title(state["context"])
        command = command_name(state["command"]) if state["phase"] == "running" else ""
        # Bash PS0 can have an older history entry when HISTIGNORE/ignorespace
        # excludes a command. Prefer a real foreground application once started.
        if state["phase"] == "running" and not window.at_prompt:
            command = local_program(window) or command
        # Bash 3.2 has no PS0 hook. Keep a real foreground application visible,
        # while a waiting Kubie supervisor is never mistaken for that app.
        if not command and not window.at_prompt:
            command = local_program(window)
        return " ".join(part for part in (context, directory, command) if part)
    command = ""
    # OSC 2 can arrive just before OSC 133 marks command execution. A non-path
    # title already names that command, even while at_prompt still says True.
    if not window.at_prompt or not title.startswith(("/", "~", "…/")):
        executable = local_program(window)
        if executable:
            command = executable
        elif not title.startswith(("/", "~", "…/")):
            command = command_name(title)
            if command in ("kubie", "starship"):
                command = ""
    identity = directory
    if not identity:
        return compact_title(title)
    return f"{identity} {command}" if command else identity


def fit_title(title, width, restore_fg=""):
    from kitty.fast_data_types import wcswidth
    from kitty.tab_bar import truncate_line
    if wcswidth(re.sub(r"\x1b\[[0-9;:]*m", "", title)) <= width:
        return title
    identity, separator, command = title.rpartition(" ")
    if separator and width >= 12:
        command_width = min(wcswidth(command), width // 2)
        if wcswidth(command) > command_width:
            command = truncate_line(command, command_width)
        identity_width = width - command_width - 1
        if wcswidth(re.sub(r"\x1b\[[0-9;:]*m", "", identity)) > identity_width:
            identity = truncate_line(identity, identity_width)
        return identity + restore_fg + " " + command
    return truncate_line(title, width)


def get_monitor():
    global _monitor
    if _monitor is None or _monitor.closed:
        from kitty.fast_data_types import get_boss
        boss = get_boss()
        previous = getattr(boss, "_dotfiles_network_monitor", None)
        if previous is not None:
            previous.close()
        _monitor = NetworkMonitor()
        boss._dotfiles_network_monitor = _monitor
    return _monitor


def format_panel(snapshot, available, now, platform):
    samples, rx, tx, status = snapshot
    label = " Mac " if platform == "darwin" else " Linux "
    # Both modes keep rates and units. Tabs own their width budget first.
    full_width = len(label) + 2 * (1 + 8 + 9 + 1)
    rates_width = len(label) + 2 * (1 + 8 + 1)
    if available < rates_width:
        return [], 0
    full = available >= full_width
    count = 8 if full else 0
    graphs = chart_data(samples, now, count)[0] if count else ("", "")
    segments = [(0xa2adbd, label)]
    if status == "unavailable":
        # An unavailable measurement is different from a measured zero.
        segments += [(0xbf616a, "network unavailable ")]
    else:
        for color, arrow, graph, rate in ((0xa3be8c, "↓", graphs[0], rx), (0x88c0d0, "↑", graphs[1], tx)):
            value = f"{' ' if full else ''}{compact_rate(rate) if status == 'ready' else '--':>5}b/s"
            segments.append((color, f"{arrow}{graph}{value} "))
    # Reserve the same width through warming, zero traffic and errors.
    width = full_width if full else rates_width
    length = sum(len(text) for _, text in segments)
    if length < width:
        segments.append((0xa2adbd, " " * (width - length)))
    return segments, width


def panel_segments(available):
    return format_panel(get_monitor().snapshot(), available, monotonic(), sys.platform)


def allocate_widths(desired, available, priorities=()):
    widths = [0] * len(desired)
    # Focus must not change hit targets or move the neighboring tabs.
    available = max(0, available)
    minimum = min(8, available // max(1, len(desired)))
    for i, want in enumerate(desired):
        widths[i] = min(want, minimum)
    remaining = available - sum(widths)
    for i in priorities:
        extra = min(remaining, max(0, desired[i] - widths[i]))
        widths[i] += extra
        remaining -= extra
    while remaining > 0:
        changed = False
        for i, want in enumerate(desired):
            if widths[i] < want and remaining:
                widths[i] += 1
                remaining -= 1
                changed = True
        if not changed:
            break
    return widths


def draw_tab(draw_data, screen, tab, before, max_tab_length, index, is_last, extra_data):
    from kitty.fast_data_types import get_boss, wcswidth
    from kitty.tab_bar import apply_title_template, draw_attributed_string, draw_tab_with_fade
    from kitty.utils import color_as_int
    if sys.platform not in ("darwin", "linux") or draw_data.tab_bar_edge not in ("top", "bottom"):
        return draw_tab_with_fade(draw_data, screen, tab, before, max_tab_length, index, is_last, extra_data)

    manager = get_boss().os_window_map.get(draw_data.os_window_id)
    data = manager.tab_bar.last_laid_out_tabs if manager else (tab,)
    titles = [apply_title_template(draw_data, item, i + 1).split("\n", 1)[0].rstrip() for i, item in enumerate(data)]
    # SGR prefixes and transient attention icons must not shift tab boundaries.
    stable_titles = [apply_title_template(draw_data, item._replace(is_active=False, needs_attention=False,
                     has_activity_since_last_focus=False), i + 1).split("\n", 1)[0].rstrip()
                     for i, item in enumerate(data)]
    desired = [min(draw_data.max_tab_title_length or 28, wcswidth(re.sub(r"\x1b\[[0-9;:]*m", "", title)) + 1)
               for title in stable_titles]
    segments, panel_width = panel_segments(max(0, screen.columns - sum(desired) - 1))
    priorities = [i for i, item in enumerate(data) if item.title.startswith("root@")]
    widths = allocate_widths(desired, screen.columns - panel_width - 1, priorities)
    width = widths[index - 1]
    if extra_data.for_layout:
        screen.cursor.x = width
        return width

    start = sum(widths[:index - 1])
    screen.cursor.x = start
    screen.cursor.bg = (color_as_int(draw_data.tab_bg(tab)) << 8) | 2
    screen.draw(" " * max(0, width - 1))
    screen.cursor.x = start
    if width > 1:
        title = titles[index - 1]
        if wcswidth(re.sub(r"\x1b\[[0-9;:]*m", "", title)) > width - 1:
            fg = color_as_int(draw_data.tab_fg(tab))
            restore_fg = f"\x1b[38;2;{fg >> 16};{(fg >> 8) & 255};{fg & 255}m"
            title = fit_title(title, width - 1, restore_fg)
        draw_attributed_string(title, screen)
    screen.cursor.x = start + width
    end = max(start, screen.cursor.x - 1)
    screen.cursor.bg = (color_as_int(draw_data.default_bg) << 8) | 2
    screen.cursor.bold = screen.cursor.italic = False
    if width:
        screen.cursor.x -= 1
        screen.draw(" ")
    if is_last:
        screen.cursor.x = screen.columns - panel_width
        for color, text in segments:
            screen.cursor.fg = (color << 8) | 2
            screen.draw(text)
    return end
